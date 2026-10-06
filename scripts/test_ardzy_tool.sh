#!/bin/bash
# Dry-run test of the board's "ardzy" tool inside the ARM rootfs (chroot + qemu), with a fake
# FPGA manager / configfs so the logic can be checked on the PC. Run in WSL as root.
set -uo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
R=/root/s9v2/rootfs
T=/root/s9v2/tooltest
rm -rf $T && mkdir -p $T/proj/demo $T/fpga $T/ovl
cp "$HERE/projects/blink/main.py" $T/proj/demo/
BIT=$(ls "$HERE"/projects/*/*.bit 2>/dev/null | head -1)
[ -n "$BIT" ] && cp "$BIT" $T/proj/demo/ || echo "(no .bit built yet: testing without bitstream)"
echo operating > $T/fpga/state; echo "Xilinx Zynq FPGA Manager" > $T/fpga/name

# patch paths to the fake ones, run inside the ARM rootfs
sed -e "s#^PROJ = .*#PROJ = '/tmp/t/proj'#" -e "s#^STATE = .*#STATE = '/tmp/t/state'#" \
    -e "s#^FW_DIR = .*#FW_DIR = '/tmp/t/fwroot/ardzy'#" -e "s#^OVL = .*#OVL = '/tmp/t/ovl/ardzy'#" \
    -e "s#^FPGA = .*#FPGA = '/tmp/t/fpga'#" -e "s#'/lib/firmware/' + fw#'/tmp/t/fwroot/' + fw#" \
    "$HERE/board/usr/local/bin/ardzy" | sed 's/\r$//' > $T/s9tool
# fake systemctl: just report
mkdir -p $T/bin
printf '#!/bin/sh\necho "  [systemctl $*]"\nexit 3\n' > $T/bin/systemctl; chmod +x $T/bin/systemctl $T/s9tool
mkdir -p $R/tmp/t && cp -a $T/. $R/tmp/t/
cp /usr/bin/qemu-arm-static $R/usr/bin/
run() { echo "\$ ardzy $*"; chroot $R env PATH=/tmp/t/bin:/usr/bin:/bin python3 /tmp/t/s9tool "$@"; echo "  (exit $?)"; }
run list
run bitinfo /tmp/t/proj/demo/blink.bit
run load demo --default
echo "--- firmware written:"; ls -l $R/tmp/t/fwroot/ardzy/; echo "--- overlay dir:"; ls -l $R/tmp/t/ovl/ardzy
echo "--- generated overlay:"; cat $R/tmp/t/proj/demo/.ardzy_overlay.dts 2>/dev/null
run status
run new hello
run list
run default none
run boot; run status
rm -rf $R/tmp/t; rm -f $R/usr/bin/qemu-arm-static
