#!/bin/bash
# Step 2: U-Boot SPL (replaces the Xilinx FSBL) + U-Boot, mainline v2026.07,
# board config bitmain_antminer_s9 with the 512 MB register tables in ../uboot/ps7_init_gpl.c
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC=/root/s9v2/src/u-boot
OUT=/root/s9v2/out/uboot
export CROSS_COMPILE=/opt/toolchains/arm/bin/arm-none-linux-gnueabihf- ARCH=arm

cp "$HERE/uboot/ps7_init_gpl.c" $SRC/board/bitmain/antminer_s9/bitmain-antminer-s9/ps7_init_gpl.c
cd $SRC
make -s O=$OUT bitmain_antminer_s9_defconfig
# The upstream defconfig has NO boot command (the old card supplied one in uboot.env).
# Built-in default: run boot.scr from the FAT partition (uboot.env on the card does the same).
$SRC/scripts/config --file $OUT/.config -d BOOTSTD_BOOTCOMMAND -e USE_BOOTCOMMAND \
  --set-str BOOTCOMMAND "if load mmc 0:1 0x3000000 boot.scr; then source 0x3000000; fi"
make -s O=$OUT olddefconfig
grep -q '^CONFIG_BOOTCOMMAND="if load mmc' $OUT/.config || { echo "BOOTCOMMAND not set"; exit 1; }
make -s O=$OUT -j"$(nproc)"

mkdir -p "$HERE/out/boot"
cp $OUT/spl/boot.bin "$HERE/out/boot/BOOT.bin"
cp $OUT/u-boot.img "$HERE/out/boot/u-boot.img"
ls -l "$HERE/out/boot"
echo UBOOT_OK
