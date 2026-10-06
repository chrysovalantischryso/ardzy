#!/bin/bash
# Step 7: system update bundle for boards already running Ardzy (installed by the Ardzy app or
# "ardzy update"): kernel + boot script (tried once, automatic return if it fails), kernel modules,
# the Debian packages that are new since an older Ardzy, and all Ardzy files.
#   out/release/Ardzy-<ver>-update.tar.gz
# Optional: OLD_PKGS=<file with the package list of an older board> (dpkg-query -W -f '${Package}\n')
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
sed -i 's/\r$//' "$HERE/scripts/ensure_arm_chroot.sh"; bash "$HERE/scripts/ensure_arm_chroot.sh"   # ARM chroot (dpkg-query, apt)
VER=${ARDZY_VERSION:-0.2}
WORK=/root/s9v2
ROOTFS=$WORK/rootfs
B="$HERE/out/boot"
S=$WORK/bundle
REL="$HERE/out/release"
rm -rf $S && mkdir -p $S/boot $S/debs $S/rootfs "$REL"

echo "== boot files"
cp "$B/zImage" "$B/system.dtb" "$B/boot.scr" $S/boot/
KVER=$(ls $WORK/out/modules/lib/modules/)
( cd $WORK/out/modules/lib/modules && tar czf $S/modules.tgz $KVER )

echo "== packages new since the older image"
OLD=${OLD_PKGS:-$HERE/out/update/old_packages.txt}
if [ -f "$OLD" ]; then
  chroot $ROOTFS dpkg-query -W -f '${Package}\n' | sort > $S/new.txt
  sed 's/\r$//' "$OLD" | sort > $S/old.txt
  NEW=$(comm -23 $S/new.txt $S/old.txt | tr '\n' ' ')
  rm -f $S/new.txt $S/old.txt
  echo "new packages: $NEW"
  if [ -n "$NEW" ]; then
    cp /usr/bin/qemu-arm-static $ROOTFS/usr/bin/
    cp --remove-destination -L /etc/resolv.conf $ROOTFS/etc/resolv.conf
    chroot $ROOTFS /bin/bash -c "apt-get update -qq && cd /tmp && rm -f /tmp/*.deb && apt-get download $NEW >/dev/null 2>&1; ls /tmp/*.deb | wc -l"
    mv $ROOTFS/tmp/*.deb $S/debs/ 2>/dev/null || true
    ln -sf ../run/systemd/resolve/stub-resolv.conf $ROOTFS/etc/resolv.conf
    rm -f $ROOTFS/usr/bin/qemu-arm-static; rm -rf $ROOTFS/var/lib/apt/lists/*
  fi
else
  echo "no package list of an older board ($OLD): no packages in the bundle"
fi

echo "== Ardzy files"
cp -r "$HERE/board/." $S/rootfs/
mkdir -p $S/rootfs/usr/lib/ardzy && cp -r "$HERE/arduino" $S/rootfs/usr/lib/ardzy/
find $S/rootfs -name '__pycache__' -type d -prune -exec rm -rf {} +
for f in etc/motd etc/systemd/zram-generator.conf etc/systemd/journald.conf.d/ardzy.conf; do
  [ -f $ROOTFS/$f ] && mkdir -p $S/rootfs/$(dirname $f) && cp $ROOTFS/$f $S/rootfs/$f
done
find $S/rootfs -type l -delete                      # services are enabled by the manifest instead

cat > $S/manifest.json <<EOF
{
  "version": "$VER",
  "date": "$(date +%Y-%m-%d)",
  "notes": "Ardzy $VER: Arduino C++ sketches and libraries, FPGA instruments (pin-control v2), board settings file, safe kernel updates, compressed swap.",
  "enable": ["ardzy-config.service"],
  "reboot": true,
  "release": {"ARDZY_VERSION": "$VER", "BUILD_DATE": "$(date +%Y-%m-%d)", "UBOOT": "2026.07", "KERNEL": "$KVER",
              "DEBIAN": "$(cat $ROOTFS/etc/debian_version)"}
}
EOF
( cd $S && find . -type f ! -name sha256sums.txt -printf '%P\n' | sort | xargs -d '\n' sha256sum > sha256sums.txt )
OUT="$REL/Ardzy-$VER-update.tar.gz"
( cd $S && tar czf "$OUT" --owner=0 --group=0 . )
ls -l "$OUT"
echo "$(sha256sum "$OUT" | cut -d' ' -f1)  $(basename "$OUT")" > "$OUT.sha256"
echo BUNDLE_OK
