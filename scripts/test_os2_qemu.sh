#!/bin/bash
# Emulator test of Ardzy OS 0.2 (WSL, root): boot, settings, compressed swap, then the safe update:
#   1. normal start of the image (U-Boot 2026.07 -> boot.scr -> kernel -> Debian), services
#   2. a good update bundle through the board's web API: trial start, then confirmed at "boot OK"
#   3. an update with a broken kernel: U-Boot must go back to the previous kernel by itself
# Log: /root/s9v2/qemu/boot.log
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
Q=/root/s9v2/qemu
BUNDLE=$(ls -t "$HERE"/out/release/Ardzy-*-update.tar.gz | head -1)
mkdir -p $Q && cd $Q
pkill -f qemu-system-arm 2>/dev/null; sleep 1
command -v sshpass >/dev/null || apt-get install -y -qq sshpass >/dev/null
cp "$HERE/out/ardzy_debian13.img" sd.img
truncate -s 4G sd.img
: > boot.log
API=http://127.0.0.1:8080
SSH="sshpass -p root ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@127.0.0.1"
PASS=0; FAIL=0; RETRIES=0
check() { if eval "$2" >/dev/null 2>&1; then echo "ok   $1"; PASS=$((PASS+1)); else echo "FAIL $1"; FAIL=$((FAIL+1)); fi; }

start_qemu() {
  setsid timeout 3000 qemu-system-arm -M xilinx-zynq-a9 -m 512M -display none -monitor none -serial null -serial stdio \
    -drive file=sd.img,if=sd,format=raw,index=0 \
    -netdev user,id=n0,hostfwd=tcp::2222-:22,hostfwd=tcp::8080-:80 -net nic,netdev=n0 \
    -kernel /root/s9v2/out/uboot_qemu/u-boot.elf \
    -device loader,addr=0xF8000008,data=0xDF0D,data-len=4 -device loader,addr=0xF800025C,data=0x5,data-len=4 \
    < /dev/null >> boot.log 2>&1 &
}
wait_api() {   # until the board's web API answers (a restart first takes it away)
  for i in $(seq 1 120); do
    curl -s -m 3 $API/api/info > /tmp/info.json 2>/dev/null && [ -s /tmp/info.json ] && return 0
    sleep 5
  done
  return 1
}
put_bundle() {   # $1 bundle, $2 answer file. One retry: an empty answer = the connection broke (shown)
  for try in 1 2; do
    curl -sS -m 900 -T "$1" -X PUT $API/api/system/update > "$2" 2> /tmp/curl.err
    [ -s "$2" ] && return 0
    echo "  (try $try: no answer: $(cat /tmp/curl.err); again in 15 s)"; RETRIES=$((RETRIES+1)); sleep 15; wait_api
  done
  return 1
}
restart_board() {   # restart, wait until the board is really gone (the emulator shuts down slowly), then back
  $SSH 'systemd-run --on-active=1 systemctl reboot'
  for i in $(seq 1 90); do curl -s -m 2 $API/api/info >/dev/null 2>&1 || break; sleep 2; done
  wait_api
}
wait_for() {   # $1 seconds, $2 condition: poll until it holds
  for i in $(seq 1 $(($1 / 5))); do eval "$2" >/dev/null 2>&1 && return 0; sleep 5; done
  return 1
}
envget() { $SSH "python3 -c 'import ardzy_env; e=ardzy_env.read()[0]; print(e.get(\"$1\",\"\"))'" 2>/dev/null; }

echo "===== 1. first start"
start_qemu
wait_api && echo "board answers after $SECONDS s" || { echo "board did not come up"; tail -40 boot.log; exit 1; }
sleep 20
python3 -c "import json; d=json.load(open('/tmp/info.json')); print('version', d['image'].get('ARDZY_VERSION'), 'kernel', d['kernel'], 'host', d['hostname'])"
check "Ardzy 0.2 image"                 "grep -q '\"ARDZY_VERSION\": \"0.2\"' /tmp/info.json"
check "U-Boot reads uboot.env (FAT)"    "grep -q 'Loading Environment from FAT... OK' boot.log"
check "settings file applied"           "$SSH 'ardzy config' | grep -q '\"hostname\": \"ardzy\"'"
check "compressed swap (zram) on"       "$SSH 'swapon --show' | grep -q zram"
check "no failed services"              "[ -z \"\$($SSH 'systemctl --failed --no-legend --plain')\" ]"
$SSH 'systemctl --failed --no-legend --plain; cat /var/lib/ardzy/at_boot; ardzy status | head -4; free -m | tail -1'
check "boot script has the trial logic" "grep -q 'ardzy_try' /dev/null || $SSH 'strings /boot/boot.scr' | grep -q ardzy_tried"
check "change a setting live (timezone)" "$SSH 'ardzy config timezone=UTC && date +%Z' | grep -q UTC"

echo "===== 2. good update: tried, then kept"
put_bundle "$BUNDLE" /tmp/upd.json
python3 -c "import json; d=json.load(open('/tmp/upd.json')); print(d['out'][-400:]); print('ok', d['ok'], 'reboot', d.get('reboot'))"
check "release update installed"       "grep -q '\"ok\": true' /tmp/upd.json"
# the web service restarts after an update: wait until it reports a new start (like the app)
OLD_START=$(python3 -c "import json; print(json.load(open('/tmp/upd.json')).get('started', ''))")
check "update asks for a web restart"   "grep -q '\"restart_web\": true' /tmp/upd.json"
for i in $(seq 1 60); do
  NEW_START=$(curl -s -m 3 $API/api/info | python3 -c "import json,sys; print(json.load(sys.stdin).get('started',''))" 2>/dev/null)
  [ -n "$NEW_START" ] && [ "$NEW_START" != "$OLD_START" ] && break
  sleep 2
done
check "web service restarted (new start id)" "[ -n \"$NEW_START\" ] && [ \"$NEW_START\" != \"$OLD_START\" ]"
# the release bundle has the same kernel as the image (nothing to try); a "new" kernel for the
# trial: the same zImage with 4 KB appended (the zImage header gives its real length)
rm -rf /tmp/good && mkdir -p /tmp/good/boot
cp "$HERE/out/boot/zImage" /tmp/good/boot/ && head -c 4096 /dev/zero >> /tmp/good/boot/zImage
cp "$HERE/out/boot/system.dtb" /tmp/good/boot/
echo '{"version": "kernel-test", "reboot": true, "restart_web": false}' > /tmp/good/manifest.json
( cd /tmp/good && tar czf /tmp/good.tar.gz . )
put_bundle /tmp/good.tar.gz /tmp/upd2.json
python3 -c "import json; d=json.load(open('/tmp/upd2.json')); print(d['out'][-300:])"
NEWK=$(sha256sum /tmp/good/boot/zImage | cut -d' ' -f1)
check "next start is a trial"           "[ \"\$(envget ardzy_try)\" = 1 ]"
restart_board && echo "back after the restart" || { echo "no answer after the update"; tail -30 boot.log; }
check "U-Boot started the new kernel as a trial" "grep -q 'first start of a new kernel' boot.log"
echo "waiting for boot OK (90 s after start) ..."
wait_for 300 "[ \"\$(envget ardzy_try)\" = 0 ]"
check "trial confirmed (ardzy_try=0)"   "[ \"\$(envget ardzy_try)\" = 0 ]"
check "the new kernel is kept"          "[ \"\$($SSH 'sha256sum /boot/zImage' | cut -d' ' -f1)\" = '$NEWK' ]"
$SSH 'cat /var/lib/ardzy/update_status'

echo "===== 3. broken kernel: back to the previous one by itself"
rm -rf /tmp/bad && mkdir -p /tmp/bad/boot && head -c 3000000 /dev/urandom > /tmp/bad/boot/zImage
cp "$HERE/out/boot/system.dtb" /tmp/bad/boot/
echo '{"version": "bad-test", "reboot": true, "restart_web": false}' > /tmp/bad/manifest.json
( cd /tmp/bad && tar czf /tmp/bad.tar.gz . )
put_bundle /tmp/bad.tar.gz /tmp/upd3.json
python3 -c "import json; d=json.load(open('/tmp/upd3.json')); print(d['out'][-300:])"
GOOD=$($SSH 'sha256sum /boot/zImage.old' | cut -d' ' -f1)
restart_board && echo "back after the bad update" || { echo "no answer after the bad update"; tail -40 boot.log; }
wait_for 120 "$SSH 'cat /var/lib/ardzy/update_status' | grep -q 'put back'"
check "U-Boot saw the failed start"     "grep -q 'did not start last time' boot.log"
check "old kernel put back for good"    "[ \"\$($SSH 'sha256sum /boot/zImage' | cut -d' ' -f1)\" = '$GOOD' ]"
check "status tells what happened"      "$SSH 'cat /var/lib/ardzy/update_status' | grep -q 'put back'"
$SSH 'cat /var/lib/ardzy/update_status'
pkill -f qemu-system-arm
check "every update answered at the first try" "[ $RETRIES = 0 ]"
echo "===== $PASS passed, $FAIL failed"
