#!/bin/bash
# Emulator test of the finished image (WSL, root):
#   mode "uboot":  QEMU runs our U-Boot 2026.07, which must find boot.scr on the SD image
#                  and start our kernel + Debian 13   (tests U-Boot, boot.scr, kernel, dtb, rootfs)
#   mode "kernel": QEMU starts our kernel directly   (tests kernel, dtb, rootfs)
# The SPL (DDR init) can't be emulated: it is only testable on the real board.
# Log: /root/s9v2/qemu/boot.log, SSH to the emulated board: ssh -p 2222 root@127.0.0.1
set -eu
MODE=${1:-uboot}
HERE="$(cd "$(dirname "$0")/.." && pwd)"
Q=/root/s9v2/qemu
mkdir -p $Q && cd $Q
rm -f boot.log
cp "$HERE/out/ardzy_debian13.img" sd.img
truncate -s 4G sd.img            # QEMU wants a power-of-2 SD size
COMMON="-M xilinx-zynq-a9 -m 512M -display none -monitor none -serial null -serial stdio \
  -drive file=sd.img,if=sd,format=raw,index=0 \
  -netdev user,id=n0,hostfwd=tcp::2222-:22,hostfwd=tcp::8080-:80 -net nic,netdev=n0"
if [ "$MODE" = uboot ]; then
  # make the emulated SLCR report boot mode = SD (0x5), like the jumper on the real board
  timeout 900 qemu-system-arm $COMMON -kernel /root/s9v2/out/uboot_qemu/u-boot.elf \
    -device loader,addr=0xF8000008,data=0xDF0D,data-len=4 -device loader,addr=0xF800025C,data=0x5,data-len=4 < /dev/null > boot.log 2>&1 || true
else
  timeout 900 qemu-system-arm $COMMON -kernel "$HERE/out/boot/zImage" -dtb "$HERE/out/boot/system.dtb" \
    -append "console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon" < /dev/null > boot.log 2>&1 || true
fi
echo "qemu stopped"
