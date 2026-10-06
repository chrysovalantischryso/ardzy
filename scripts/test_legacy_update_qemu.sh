#!/bin/bash
# Emulator test: update a board that runs Ardzy 0.1 to 0.2 the way the Ardzy app does it
# (0.1 has no update service: the app sends the installer as a one-off project).
#   test_legacy_update_qemu.sh start   copy the 0.1 image, start it, wait for the web API (port 8080)
#   (then on Windows: python pc_app\tests\legacy_update_test.py   runs the app's update code)
#   test_legacy_update_qemu.sh after   restart the emulated board, check it runs 0.2 and kept the kernel
set -u
Q=/root/s9v2/qemu
API=http://127.0.0.1:8080
SSH="sshpass -p root ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@127.0.0.1"
cd $Q
wait_api() {
  for i in $(seq 1 120); do
    curl -s -m 3 $API/api/info > /tmp/info.json 2>/dev/null && [ -s /tmp/info.json ] && return 0
    sleep 5
  done
  return 1
}
envget() { $SSH "python3 -c 'import ardzy_env; e=ardzy_env.read()[0]; print(e.get(\"$1\",\"\"))'" 2>/dev/null; }
case "${1:-}" in
start)
  pkill -f qemu-system-arm 2>/dev/null; sleep 1
  cp /root/s9v2/release/Ardzy-1.0-sdcard.img sd.img && truncate -s 4G sd.img
  : > boot.log
  setsid timeout 3000 qemu-system-arm -M xilinx-zynq-a9 -m 512M -display none -monitor none -serial null -serial stdio \
    -drive file=sd.img,if=sd,format=raw,index=0 \
    -netdev user,id=n0,hostfwd=tcp::2222-:22,hostfwd=tcp::8080-:80 -net nic,netdev=n0 \
    -kernel /root/s9v2/out/uboot_qemu/u-boot.elf < /dev/null >> boot.log 2>&1 &
  wait_api && echo "0.1 board answers after $SECONDS s" || { echo "board did not come up"; tail -30 boot.log; exit 1; }
  sleep 20
  python3 -c "import json; d=json.load(open('/tmp/info.json')); print('version', d['image'].get('ARDZY_VERSION'), 'kernel', d['kernel'])"
  curl -s -o /dev/null -w 'update service on 0.1: HTTP %{http_code}\n' $API/api/update/status
  ;;
after)
  P=0; F=0
  check() { if eval "$2" >/dev/null 2>&1; then echo "ok   $1"; P=$((P+1)); else echo "FAIL $1"; F=$((F+1)); fi; }
  check "next start is a trial"            "[ \"\$(envget ardzy_try)\" = 1 ]"
  check "0.1 kernel kept as zImage.old"    "$SSH 'test -f /boot/zImage.old'"
  $SSH 'systemd-run --on-active=1 systemctl reboot'
  for i in $(seq 1 90); do curl -s -m 2 $API/api/info >/dev/null 2>&1 || break; sleep 2; done   # really gone
  wait_api && echo "back after the restart" || { echo "no answer after the update"; tail -40 boot.log; exit 1; }
  check "U-Boot started the new kernel as a trial" "grep -q 'first start of a new kernel' boot.log"
  check "runs Ardzy 0.2"                   "grep -q '\"ARDZY_VERSION\": \"0.2\"' /tmp/info.json"
  check "runs the 0.2 kernel"              "grep -q '\"kernel\": \"6.18.0-xilinx-s9\"' /tmp/info.json"
  echo "waiting for boot OK ..."
  for i in $(seq 1 60); do [ "$(envget ardzy_try)" = 0 ] && break; sleep 5; done
  check "trial confirmed (ardzy_try=0)"    "[ \"\$(envget ardzy_try)\" = 0 ]"
  check "settings service runs"            "$SSH 'ardzy config' | grep -q hostname"
  check "compressed swap (zram) on"        "$SSH 'swapon --show' | grep -q zram"
  check "no failed services"               "[ -z \"\$($SSH 'systemctl --failed --no-legend --plain')\" ]"
  check "update service answers"           "curl -s -m 5 $API/api/update/status | grep -q '\"ok\": true'"
  check "Arduino sketch builds"            "$SSH 'ls /usr/lib/ardzy/arduino/build.py'"
  $SSH 'systemctl --failed --no-legend --plain; cat /var/lib/ardzy/update_status; ls /opt/ardzy/projects'
  pkill -f qemu-system-arm
  echo "===== $P passed, $F failed"
  ;;
*) echo "usage: $0 start|after"; exit 2 ;;
esac
