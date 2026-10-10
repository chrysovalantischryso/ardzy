#!/bin/bash
# Step 3b: the Linux device tree of another board (BOARD=ebaz4205). The kernel itself (step 3) is the same
# for every Zynq-7000 board; only this file differs. Out: out/boot_<board>/system.dtb (+ zImage copied).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BOARD="${BOARD:?BOARD=<board> please (for the S9 the tree is made by 03_build_kernel.sh)}"
SRC=/root/s9v2/src/linux-xlnx
KD="$HERE/boards/$BOARD/kernel"
DEST="$HERE/out/boot_$BOARD"
DTS=$(basename "$(ls "$KD"/*.dts | head -1)" .dts)
mkdir -p "$DEST"
sed 's/\r$//' "$KD/$DTS.dts" > $SRC/arch/arm/boot/dts/xilinx/$DTS.dts
# with __symbols__ (-@) so the FPGA overlays can refer to &fpga_full etc.
dtc -@ -I dts -O dtb -o "$DEST/system.dtb" \
  <(cpp -nostdinc -undef -x assembler-with-cpp -D__DTS__ \
        -I $SRC/include -I $SRC/arch/arm/boot/dts -I $SRC/arch/arm/boot/dts/xilinx \
        $SRC/arch/arm/boot/dts/xilinx/$DTS.dts) 2> >(grep -v Warning >&2 || true)
cp "$HERE/out/boot/zImage" "$DEST/zImage"
fdtget "$DEST/system.dtb" / model
fdtget "$DEST/system.dtb" /memory@0 reg
ls -l "$DEST"
echo DTB_OK
