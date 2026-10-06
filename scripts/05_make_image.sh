#!/bin/bash
# Step 5: SD card image = FAT boot partition + ext4 root partition
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
WORK=/root/s9v2
ROOTFS=$WORK/rootfs
B="$HERE/out/boot"
IMG=ardzy_debian13.img
IMG_MB=2560
BOOT_MB=256
BOOT_START_MB=4

# U-Boot script: works with the new U-Boot AND with the fallback (old) BOOT.bin
# Safe updates: "ardzy update" sets ardzy_try=1. The first start of a new kernel marks itself
# (ardzy_tried=1); Linux clears both when it is up ("ardzy boot-ok"). If the board restarts
# before that (panic: panic=5 restarts it, watchdog, power), the previous kernel is used.
cat > $WORK/boot.cmd <<'EOF'
echo "Ardzy: loading Linux from SD"
setenv kimg zImage
setenv kdtb system.dtb
if test "${ardzy_try}" = "1"; then
  if test "${ardzy_tried}" = "1"; then
    echo "Ardzy: the new kernel did not start last time: using the previous one"
    setenv kimg zImage.old
    setenv kdtb system.dtb.old
    setenv ardzy_try 0
    setenv ardzy_tried 0
    setenv ardzy_rollback 1
    saveenv
  else
    echo "Ardzy: first start of a new kernel (it goes back by itself if this fails)"
    setenv ardzy_tried 1
    saveenv
  fi
fi
setenv bootargs "console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait panic=5 earlycon uio_pdrv_genirq.of_id=generic-uio"
load mmc 0:1 0x2000000 ${kimg}
load mmc 0:1 0x2A00000 ${kdtb}
bootz 0x2000000 - 0x2A00000
echo "Ardzy: Linux did not start from ${kimg}"
if test "${ardzy_tried}" = "1"; then
  echo "Ardzy: restarting to go back to the previous kernel"
  reset
fi
EOF
mkimage -A arm -O linux -T script -C none -n "Ardzy boot" -d $WORK/boot.cmd "$B/boot.scr" >/dev/null

# U-Boot settings file, read by BOTH the new U-Boot and the fallback one (same 128 KB format).
# Upstream U-Boot has no boot command of its own; this one runs boot.scr.
# No MAC address here: every board gets its own at the first start and keeps it (ardzy-config saves it
# into uboot.env). To give an image a fixed one (for example your old card's), build with ARDZY_MAC=xx:xx:..
cat > $WORK/uboot.env.txt <<'EOF'
bootcmd=if load mmc 0:1 0x3000000 boot.scr; then source 0x3000000; fi
bootdelay=2
baudrate=115200
fdt_high=0xefff000
initrd_high=0xefff000
EOF
if [ -n "${ARDZY_MAC:-}" ]; then echo "ethaddr=$ARDZY_MAC" >> $WORK/uboot.env.txt; fi
mkenvimage -s 0x20000 -o "$B/uboot.env" $WORK/uboot.env.txt

cat > $WORK/FALLBACK.txt <<'EOF'
If the board does not start with this card (no ardzy.local after 3 minutes):

  1. Put the SD card in the PC (this BOOT partition opens in Windows).
  2. Rename  BOOT.bin           ->  BOOT_new.bin
  3. Rename  BOOT_fallback.bin  ->  BOOT.bin
  4. Put the card back in the board and power on.

BOOT_fallback.bin = the proven boot loader from the old card (Xilinx FSBL +
U-Boot 2025.01 + the old FM "TEST" FPGA design). It starts the same new Linux.
BOOT.bin = the new open-source U-Boot 2026.07 SPL (FPGA empty at power-on).
EOF

# example projects (only what the board needs: bitstream + programs)
rm -rf $ROOTFS/opt/ardzy/projects/* && mkdir -p $ROOTFS/opt/ardzy/projects
# Only the built-in examples go on the card (your own projects in projects/ stay on the PC);
# ARDZY_EXAMPLES="all" takes every project, or give your own list.
EXAMPLES="${ARDZY_EXAMPLES:-ardzy_io blink board_hello fpga_ramtest fpga_selftest leds_python}"
for p in "$HERE"/projects/*/; do
  [ -d "$p" ] || continue
  n=$(basename "$p")
  case "$n" in libraries|_*|.*|plot_test) continue ;; esac     # not projects (Arduino libraries, build folders)
  [ "$EXAMPLES" = all ] || case " $EXAMPLES " in *" $n "*) ;; *) continue ;; esac
  mkdir -p $ROOTFS/opt/ardzy/projects/$n
  find "$p" -maxdepth 1 -type f \( -name '*.bit' -o -name '*.py' -o -name '*.c' -o -name '*.h' -o -name '*.ino' -o -name '*.cpp' \
       -o -name 'Makefile' -o -name 'run.sh' -o -name 'devices.dtsi' -o -name 'overlay.dts' \) \
       -exec cp {} $ROOTFS/opt/ardzy/projects/$n/ \;
  find $ROOTFS/opt/ardzy/projects/$n -type f ! -name '*.bit' -exec sed -i 's/\r$//' {} +
  echo "example project: $n ($(ls $ROOTFS/opt/ardzy/projects/$n | tr '\n' ' '))"
done
# refresh the S9 tools too (so tool fixes don't need a full rootfs rebuild)
bash "$HERE/scripts/install_board_files.sh" $ROOTFS

# release stamp: which Ardzy image is this (shown by the app and "cat /etc/ardzy-release")
KREL=$(ls /root/s9v2/out/modules/lib/modules/)
cat > $ROOTFS/etc/ardzy-release <<EOF
ARDZY_VERSION=${ARDZY_VERSION:-0.2}
BUILD_DATE=$(date +%Y-%m-%d)
UBOOT=2026.07
KERNEL=$KREL
DEBIAN=$(cat $ROOTFS/etc/debian_version)
EOF

cd $WORK
rm -f boot.vfat root.ext4 $IMG
mkfs.vfat -F 32 -n S9BOOT -C boot.vfat $((BOOT_MB * 1024)) >/dev/null
for f in BOOT.bin u-boot.img zImage system.dtb boot.scr uboot.env; do mcopy -i boot.vfat "$B/$f" ::/$f; done
# The fallback boot loader comes from the board's original card (Bitmain), so it is not part of the
# public repository or images: it is added only when you have it in fallback/ (ARDZY_FALLBACK=0: never,
# use that for images you share).
if [ "${ARDZY_FALLBACK:-1}" = 1 ] && [ -f "$HERE/fallback/BOOT_fallback.bin" ]; then
  mcopy -i boot.vfat "$HERE/fallback/BOOT_fallback.bin" ::/BOOT_fallback.bin
  mcopy -i boot.vfat FALLBACK.txt ::/FALLBACK.txt
fi
# the board's settings (the Ardzy app writes this file when it flashes a card)
cat > $WORK/ardzy.txt <<'EOF'
# Ardzy board settings. The Ardzy app writes this file; you can also edit it on a PC
# (the SD card's boot partition). Applied at the next boot, or at once from the app.
#   hostname  board name: <hostname>.local          network  auto | static | linklocal
#   password  new root password (erased once used)   address/gateway/dns  for network = static
#   timezone  for example Europe/Athens or UTC       ssh      on | off
#   at_boot   pin-control | none | <project name>
hostname  = ardzy
password  =
network   = auto
address   =
gateway   =
dns       =
timezone  = Europe/Athens
ssh       = on
at_boot   = pin-control
EOF
mcopy -i boot.vfat $WORK/ardzy.txt ::/ardzy.txt
mdir -i boot.vfat ::/

ROOT_MB=$((IMG_MB - BOOT_START_MB - BOOT_MB))
mkfs.ext4 -q -L rootfs -d $ROOTFS root.ext4 ${ROOT_MB}M
truncate -s ${IMG_MB}M $IMG
sfdisk -q $IMG <<EOF
label: dos
start=$((BOOT_START_MB * 2048)), size=$((BOOT_MB * 2048)), type=c, bootable
start=$(((BOOT_START_MB + BOOT_MB) * 2048)), type=83
EOF
dd if=boot.vfat of=$IMG bs=1M seek=$BOOT_START_MB conv=notrunc status=none
dd if=root.ext4 of=$IMG bs=1M seek=$((BOOT_START_MB + BOOT_MB)) conv=notrunc status=none
e2fsck -fn root.ext4 | tail -1
cp $IMG "$HERE/out/$IMG"
ls -l "$HERE/out/$IMG"
echo IMAGE_OK
