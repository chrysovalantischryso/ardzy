#!/bin/bash
# Step 6: release package of the SD card image
#   out/release/Ardzy-<ver>-sdcard.img.xz   compressed image (balenaEtcher / Rufus flash it directly)
#   out/release/SHA256SUMS.txt               checksums (compressed + uncompressed image)
#   out/release/HOW_TO_FLASH.txt             instructions
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VER=${ARDZY_VERSION:-0.2}
SRC=/root/s9v2/ardzy_debian13.img           # written by 05_make_image.sh
REL="$HERE/out/release"
NAME=Ardzy-$VER-sdcard.img
W=/root/s9v2/release
mkdir -p "$REL" $W
[ -f $SRC ] || { echo "run 05_make_image.sh first"; exit 1; }

cp $SRC $W/$NAME
# sanity: partition table + both file systems are readable
sfdisk -l $W/$NAME | tail -2
echo "compressing (xz, all cores) ..."
rm -f $W/$NAME.xz
xz -T0 -6 -k $W/$NAME
( cd $W && sha256sum $NAME $NAME.xz ) > "$REL/SHA256SUMS.txt"
xz -t $W/$NAME.xz && echo "xz archive test OK"
cp $W/$NAME.xz "$REL/"
cat > "$REL/HOW_TO_FLASH.txt" <<EOF
Ardzy $VER BETA - SD card image for the Antminer S9 control board (Zynq XC7Z010)
==========================================================================

File: $NAME.xz   (compressed; unpacked it is $(( $(stat -c %s $W/$NAME) / 1024 / 1024 )) MB, any SD card >= 4 GB works)

1. Easiest: the Ardzy app, button "SD card": choose this file and your card, set the board's
   name, password and network, Write. It checks the card after writing.
2. Or balenaEtcher (https://etcher.balena.io): Flash from file -> $NAME.xz (no need to unzip),
   Select target -> your microSD card (check the size!), Flash. Then edit ardzy.txt on the
   card's boot partition if you want another name, password or network.
   If Windows asks "format the disk?" afterwards: click Cancel.
3. Board: boot jumpers on SD card (JP2 = 1, JP4 = 1), Ethernet cable, 12 V power.
4. Wait about 2 minutes (first start: SSH keys + the partition grows to the whole card).
5. Start Ardzy on the PC (Ardzy.exe from the Windows release zip): it finds the board by itself.
   Or: browser http://ardzy.local   /   PuTTY ardzy.local, login root / root  (then: passwd)

Inside: U-Boot 2026.07 (SPL), Linux $(ls /root/s9v2/out/modules/lib/modules/), Debian $(cat /root/s9v2/rootfs/etc/debian_version),
Ardzy tools, web page, Arduino core and libraries, the pin-control FPGA design (loaded at power-on),
example projects. Settings: ardzy.txt on the boot partition.

Did not start? On the card's BOOT partition (opens in Windows) rename
BOOT.bin -> BOOT_new.bin and BOOT_fallback.bin -> BOOT.bin, then try again.
Full guide: Desktop\\FPGA\\Documents\\02_Ardzy.html

Check the download (PowerShell):  Get-FileHash $NAME.xz   (compare with SHA256SUMS.txt)
EOF
sed -i 's/$/\r/' "$REL/HOW_TO_FLASH.txt" "$REL/SHA256SUMS.txt"     # Windows line endings for Notepad
ls -l "$REL"
cat "$REL/SHA256SUMS.txt"
echo RELEASE_OK
