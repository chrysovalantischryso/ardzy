#!/bin/bash
# Test-only U-Boot for QEMU: identical to the board build, except that QEMU 4.2 does not report
# the SD boot mode (its SLCR ignores the boot-mode write), and U-Boot then keeps no settings.
# This build always uses the SD mode settings: uboot.env on the FAT partition, exactly like the
# real board in SD mode, so the safe-update logic (ardzy_try / ardzy_tried / saveenv) is tested.
# board.c is patched only for this build and restored afterwards.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC=/root/s9v2/src/u-boot
OUT=/root/s9v2/out/uboot_qemu
BC=$SRC/board/xilinx/zynq/board.c
export CROSS_COMPILE=/opt/toolchains/arm/bin/arm-none-linux-gnueabihf- ARCH=arm
cp "$HERE/uboot/ps7_init_gpl.c" $SRC/board/bitmain/antminer_s9/bitmain-antminer-s9/ps7_init_gpl.c
cp -p $BC /tmp/zynq_board.c.orig
trap 'cp -p /tmp/zynq_board.c.orig $BC' EXIT
python3 - "$BC" <<'PY'
import sys
p = sys.argv[1]
s = open(p).read()
a = s.index('enum env_location env_get_location')
b = s.index('\n}\n', a)
f = s[a:b]
old = '\t\treturn ENVL_UNKNOWN;\n'
assert old in f
f = f.replace(old, old + '\tbootmode = ZYNQ_BM_SD;\t/* QEMU test build only */\n', 1)
open(p, 'w').write(s[:a] + f + s[b:])
PY
cd $SRC
make -s O=$OUT bitmain_antminer_s9_defconfig
$SRC/scripts/config --file $OUT/.config -d ENV_IS_NOWHERE -d BOOTSTD_BOOTCOMMAND -e USE_BOOTCOMMAND \
  --set-str BOOTCOMMAND "if load mmc 0:1 0x3000000 boot.scr; then source 0x3000000; fi"
make -s O=$OUT olddefconfig
make -s O=$OUT -j"$(nproc)" u-boot.elf
grep -E '^CONFIG_ENV_IS_IN_FAT=y' $OUT/.config
ls -l $OUT/u-boot.elf
echo QEMU_UBOOT_OK
