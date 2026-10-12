#!/bin/bash
# A release of the Ardzy files only: the boot loader, kernel and Debian of an earlier (tested) image stay
# exactly the same, the Ardzy tools, web service, libraries and Arduino core are the ones of now.
#   ARDZY_VERSION=0.3 BASE=out/release/Ardzy-0.2-sdcard.img.xz bash scripts/07b_files_release.sh
# makes  out/release/Ardzy-<ver>-update.tar.gz   for boards that run Ardzy (files only: no kernel, no restart)
#        out/release/Ardzy-<ver>-sdcard.img.xz   the earlier image with these files (for new cards)
# (S9 images: the EBAZ4205 image is made with 05_make_image.sh)
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
VER=${ARDZY_VERSION:?set ARDZY_VERSION, for example 0.3}
BASE=${BASE:-$HERE/out/release/Ardzy-0.2-sdcard.img.xz}
REL="$HERE/out/release"
W=/root/s9v2/files_release
cleanup() { mountpoint -q $W/mnt && umount $W/mnt; [ -n "${LOOP:-}" ] && losetup -d $LOOP 2>/dev/null; true; }
trap cleanup EXIT
rm -rf $W && mkdir -p $W/stage $W/mnt "$REL"
TODAY=$(date +%Y-%m-%d)

echo "== the Ardzy files (as install_board_files.sh puts them on a card)"
bash "$HERE/scripts/install_board_files.sh" $W/stage >/dev/null
rm -rf $W/stage/etc/systemd/system/*.wants           # (links: a running board has its services switched on already)
find $W/stage -name '__pycache__' -type d -prune -exec rm -rf {} +

echo "== the image: $(basename "$BASE") with these files"
xz -dc "$BASE" > $W/sdcard.img
LOOP=$(losetup -f --show -P $W/sdcard.img)
mount ${LOOP}p2 $W/mnt
OLDREL=$(cat $W/mnt/etc/ardzy-release)
echo "base: $(echo $OLDREL | tr '\n' ' ')"
bash "$HERE/scripts/install_board_files.sh" $W/mnt
sed -i "s|^  ARDZY .*Zynq like an Arduino .*|  ARDZY $VER BETA  -  Zynq like an Arduino  (Antminer S9 board, XC7Z010, 512 MB, Debian 13)|" $W/mnt/etc/motd
sed -e "s/^ARDZY_VERSION=.*/ARDZY_VERSION=$VER/" -e "s/^BUILD_DATE=.*/BUILD_DATE=$TODAY/" $W/mnt/etc/ardzy-release > $W/release.txt
grep -q '^BOARD=' $W/release.txt || sed -i '1a BOARD=s9' $W/release.txt     # (images before 0.3 did not say it)
cp $W/release.txt $W/mnt/etc/ardzy-release
mkdir -p $W/stage/etc && cp $W/mnt/etc/motd $W/stage/etc/motd      # (the welcome text names the version)
sync; umount $W/mnt; losetup -d $LOOP; LOOP=
NAME=Ardzy-$VER-sdcard.img
mv $W/sdcard.img $W/$NAME
( cd $W && sha256sum $NAME ) > $W/sums.txt
xz -T0 -6 -f -k $W/$NAME
xz -t $W/$NAME.xz && echo "xz archive test OK"
( cd $W && sha256sum $NAME.xz ) >> $W/sums.txt
cp $W/$NAME.xz "$REL/"
cp $W/sums.txt "$REL/SHA256SUMS-$VER.txt"

echo "== the update bundle"
B=$W/bundle; mkdir -p $B
cp -a $W/stage $B/rootfs
python3 - "$B" "$VER" "$TODAY" "$W/release.txt" <<'EOF'
import json, sys
b, ver, today, rel = sys.argv[1:]
release = dict(l.strip().split('=', 1) for l in open(rel) if '=' in l)
json.dump({'version': ver, 'date': today, 'reboot': False, 'restart_web': True, 'release': release,
           'notes': 'Ardzy %s: the Ardzy files (signal analyzer, board profiles, libraries). Same kernel: no restart.' % ver},
          open(b + '/manifest.json', 'w'), indent=1)
EOF
( cd $B && find . -type f ! -name sha256sums.txt -printf '%P\n' | sort | xargs -d '\n' sha256sum > sha256sums.txt )
OUT="$REL/Ardzy-$VER-update.tar.gz"
tar czf "$OUT" --owner=0 --group=0 -C $B .
sha256sum "$OUT" | sed "s|  .*/|  |" > "$OUT.sha256"
echo "update bundle: $(basename "$OUT") ($(du -h "$OUT" | cut -f1), $(find $B/rootfs -type f | wc -l) files)"
cat "$REL/SHA256SUMS-$VER.txt"; echo "image: $REL/$NAME.xz"
rm -rf $W
