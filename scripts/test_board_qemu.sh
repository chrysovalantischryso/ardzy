#!/bin/bash
# Emulator test of the image of another board (WSL, root):  BOARD=ebaz4205 bash scripts/test_board_qemu.sh
# QEMU's Zynq runs our boot script (boot.scr: base FPGA design, then Linux) from the SD image with this
# board's device tree and memory; then the Ardzy tools must know the board. Not testable here: the SPL
# (DDR set-up) and the FPGA itself (QEMU has no FPGA; the Ethernet works in QEMU without it).
# Log: /root/s9v2/qemu/board.log
set -u
BOARD="${BOARD:-ebaz4205}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
Q=/root/s9v2/qemu
RAM=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['ram_mb'])" "$HERE/boards/$BOARD/board.json")
mkdir -p $Q && cd $Q
pkill -f qemu-system-arm 2>/dev/null; sleep 1
command -v sshpass >/dev/null || apt-get install -y -qq sshpass >/dev/null
if [ "$BOARD" = s9 ]; then cp "$HERE/out/ardzy_debian13.img" sd.img; else cp "$HERE/out/ardzy_debian13_$BOARD.img" sd.img; fi
truncate -s 4G sd.img
: > board.log
API=http://127.0.0.1:8080
SSH="sshpass -p root ssh -p 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR root@127.0.0.1"
PASS=0; FAIL=0
check() { if eval "$2" >/dev/null 2>&1; then echo "ok   $1"; PASS=$((PASS+1)); else echo "FAIL $1"; FAIL=$((FAIL+1)); fi; }

setsid timeout 2400 qemu-system-arm -M xilinx-zynq-a9 -m ${RAM}M -display none -monitor none -serial null -serial stdio \
  -drive file=sd.img,if=sd,format=raw,index=0 \
  -netdev user,id=n0,hostfwd=tcp::2222-:22,hostfwd=tcp::8080-:80 -net nic,netdev=n0 \
  -kernel /root/s9v2/out/uboot_qemu/u-boot.elf \
  -device loader,addr=0xF8000008,data=0xDF0D,data-len=4 -device loader,addr=0xF800025C,data=0x5,data-len=4 \
  < /dev/null >> board.log 2>&1 &

for i in $(seq 1 150); do curl -s -m 3 $API/api/info > /tmp/info.json 2>/dev/null && [ -s /tmp/info.json ] && break; sleep 5; done
[ -s /tmp/info.json ] || { echo "the board did not come up"; tail -40 board.log; pkill -f qemu-system-arm; exit 1; }
echo "board answers after $SECONDS s"
sleep 25
[ "$BOARD" = s9 ] || check "boot script loads the base FPGA design" "grep -q 'loading the base FPGA design' board.log"
check "Linux started" "grep -q 'Linux version' board.log"
MODEL=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['name'])" "$HERE/boards/$BOARD/board.json")
check "device tree: the $MODEL" "grep -qi \"Machine model: .*$MODEL\" board.log"
check "the web service says board = $BOARD" "python3 -c \"import json,sys; sys.exit(json.load(open('/tmp/info.json')).get('board') != '$BOARD')\""
check "memory = $RAM MB" "[ \$($SSH \"awk '/MemTotal/ {print int(\\\$2/1024)}' /proc/meminfo\") -le $RAM ]"
check "board-io.txt written" "$SSH 'grep -q led_green /run/ardzy/board-io.txt'"
check "ardzy_board knows the board" "[ \"\$($SSH 'python3 -c \"import ardzy_board; print(ardzy_board.board_id())\"')\" = $BOARD ]"
check "pin-control design of this board" "$SSH 'test -f \$(python3 -c \"import ardzy_board; print(ardzy_board.pin_control_bit())\")'"
[ "$BOARD" = s9 ] || check "the I/O pin list of this board" "$SSH 'python3 -c \"import sys; sys.path.insert(0, \\\"/opt/ardzy/web\\\"); import hwapi; m = hwapi.io_map(); assert m[0][\\\"name\\\"].startswith(\\\"DATA\\\")\"'"
check "ardzy.py: the S9 names work (led green, button ip)" "$SSH 'python3 -c \"import ardzy; ardzy.led(\\\"green\\\"); ardzy.button(\\\"ip\\\"); ardzy.button(\\\"reset\\\")\"'"
[ "$BOARD" = s9 ] || check "ardzy.py: this board's names work (button s3, led red)" "$SSH 'python3 -c \"import ardzy; ardzy.button(\\\"s3\\\"); ardzy.led(\\\"red\\\", False)\"'"
check "welcome text names the board" "$SSH 'grep -qi \"$MODEL\" /etc/motd'"
check "release file has the board" "$SSH 'grep -q BOARD=$BOARD /etc/ardzy-release'"
check "the NAND is read-only" "$SSH 'grep -q . /sys/class/mtd/mtd0/name && test \$(( \$(cat /sys/class/mtd/mtd0/flags) & 0x400 )) -eq 0' || $SSH 'test ! -e /sys/class/mtd/mtd0'"
check "no failed services" "[ -z \"\$($SSH 'systemctl --failed --no-legend')\" ]"
$SSH 'systemctl --failed --no-legend; cat /run/ardzy/board-io.txt; journalctl -b -u ardzy-board -o cat | tail -3' 2>/dev/null

# the libraries of the languages: the board's LEDs and buttons from board-io.txt
T="$HERE/pc_app/templates"
SCP="sshpass -p root scp -P 2222 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
$SSH 'rm -rf /tmp/zt && mkdir -p /tmp/zt'
$SCP "$T/cpp_program/ardzy.hpp" "$T/shell_script/ardzy.sh" "$T/perl_script/Ardzy.pm" root@127.0.0.1:/tmp/zt/
$SSH 'cd /tmp/zt && sed -i "s/\r$//" ardzy.sh Ardzy.pm && printf "#include \"ardzy.hpp\"\n#include <cstdio>\nint main() { ardzy::led(\"green\", true); std::printf(\"cpp %%d %%d\\\\n\", ardzy::button(\"ip\"), ardzy::button(\"reset\")); }\n" > t.cpp'
check "C++ library (ardzy.hpp) compiles and reads the buttons" "$SSH 'cd /tmp/zt && g++ -std=gnu++17 -O1 -o t t.cpp && ./t | grep -q \"^cpp [01] [01]\$\"'"
check "Shell library (ardzy.sh): led and button" "$SSH 'cd /tmp/zt && bash -c \"source ./ardzy.sh; led green on; button ip; [ \\\$? -le 1 ]\"'"
check "Perl library (Ardzy.pm): led and button" "$SSH 'cd /tmp/zt && perl -I. -e \"use Ardzy; led(\\\"green\\\", 1); my \\\$b = button(\\\"reset\\\"); print \\\"ok\\\\n\\\"\" | grep -q ok'"

# an Arduino sketch: compiled on the board with this board's pins (S9 names compile on every board)
$SSH 'rm -rf /opt/ardzy/projects/zt_sketch && mkdir -p /opt/ardzy/projects/zt_sketch && printf "void setup() { pinMode(LED_BUILTIN, OUTPUT); pinMode(J1_5, OUTPUT); Serial.begin(115200); }\nvoid loop() { digitalWrite(LED_BUILTIN, HIGH); digitalWrite(J1_5, digitalRead(BUTTON_IP)); delay(500); }\n" > /opt/ardzy/projects/zt_sketch/zt_sketch.ino'
[ "$BOARD" = s9 ] || $SSH "printf 'void ebazPins() { pinMode(DATA3_20, OUTPUT); digitalWrite(DATA3_20, digitalRead(BUTTON_S3)); digitalWrite(LED_RED, HIGH); }\n' > /opt/ardzy/projects/zt_sketch/extra.ino"
echo "(compiling a sketch in the emulator: some minutes)"
check "Arduino sketch compiles for this board" "$SSH 'timeout 1500 ardzy build zt_sketch 2>&1 | tail -3 | grep -q \"compiled OK\"'"
$SSH 'rm -rf /opt/ardzy/projects/zt_sketch /tmp/zt'
pkill -f qemu-system-arm
echo "RESULT: $PASS ok, $FAIL failed"
