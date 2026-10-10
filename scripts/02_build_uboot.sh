#!/bin/bash
# Step 2: U-Boot SPL (replaces the Xilinx FSBL) + U-Boot, mainline v2026.07.
#   BOARD=s9 (default): board config bitmain_antminer_s9 with the 512 MB register tables in ../uboot/ps7_init_gpl.c
#   BOARD=ebaz4205:     the same board code (it is Xilinx's generic Zynq board) with the EBAZ4205's device tree
#                       and register tables from ../boards/ebaz4205/uboot (256 MB DDR3, FCLK3 = PHY clock)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
BOARD="${BOARD:-s9}"
SRC=/root/s9v2/src/u-boot
export CROSS_COMPILE=/opt/toolchains/arm/bin/arm-none-linux-gnueabihf- ARCH=arm

if [ "$BOARD" = s9 ]; then
  OUT=/root/s9v2/out/uboot
  DEST="$HERE/out/boot"
  DTS=bitmain-antminer-s9
  cp "$HERE/uboot/ps7_init_gpl.c" $SRC/board/bitmain/antminer_s9/bitmain-antminer-s9/ps7_init_gpl.c
else
  BD="$HERE/boards/$BOARD/uboot"
  [ -d "$BD" ] || { echo "no U-Boot files for board $BOARD ($BD)"; exit 1; }
  OUT=/root/s9v2/out/uboot_$BOARD
  DEST="$HERE/out/boot_$BOARD"
  DTS=$(basename "$(ls "$BD"/*.dts | head -1)" .dts)
  sed 's/\r$//' "$BD/$DTS.dts" > $SRC/arch/arm/dts/$DTS.dts
  grep -q "$DTS.dtb" $SRC/arch/arm/dts/Makefile || \
    sed -i "s|^\(\s*\)bitmain-antminer-s9.dtb \\\\|&\n\1$DTS.dtb \\\\|" $SRC/arch/arm/dts/Makefile
  grep -q "$DTS.dtb" $SRC/arch/arm/dts/Makefile || { echo "could not add $DTS.dtb to the dts Makefile"; exit 1; }
  mkdir -p $SRC/board/bitmain/antminer_s9/$DTS
  cp "$BD/ps7_init_gpl.c" $SRC/board/bitmain/antminer_s9/$DTS/ps7_init_gpl.c
fi

cd $SRC
make -s O=$OUT bitmain_antminer_s9_defconfig
# The upstream defconfig has NO boot command (the old card supplied one in uboot.env).
# Built-in default: run boot.scr from the FAT partition (uboot.env on the card does the same).
$SRC/scripts/config --file $OUT/.config -d BOOTSTD_BOOTCOMMAND -e USE_BOOTCOMMAND \
  --set-str BOOTCOMMAND "if load mmc 0:1 0x3000000 boot.scr; then source 0x3000000; fi"
if [ "$BOARD" != s9 ]; then
  # this board's device tree; U-Boot's settings only on the SD card (never in the NAND: it keeps the original firmware)
  $SRC/scripts/config --file $OUT/.config --set-str DEFAULT_DEVICE_TREE "$DTS" --set-str SYS_PROMPT "ardzy-$BOARD> " \
    -d ENV_IS_IN_NAND
fi
make -s O=$OUT olddefconfig
grep -q '^CONFIG_BOOTCOMMAND="if load mmc' $OUT/.config || { echo "BOOTCOMMAND not set"; exit 1; }
grep -q "^CONFIG_DEFAULT_DEVICE_TREE=\"$DTS\"" $OUT/.config || { echo "device tree $DTS not set"; exit 1; }
if [ "$BOARD" != s9 ] && grep -q '^CONFIG_ENV_IS_IN_NAND=y' $OUT/.config; then echo "U-Boot settings would go to the NAND: stop"; exit 1; fi
make -s O=$OUT -j"$(nproc)"

mkdir -p "$DEST"
cp $OUT/spl/boot.bin "$DEST/BOOT.bin"
cp $OUT/u-boot.img "$DEST/u-boot.img"
ls -l "$DEST"
echo UBOOT_OK
