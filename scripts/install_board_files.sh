#!/bin/bash
# Copy the Ardzy board files (board/) into a root file system and fix line endings,
# permissions and service links. Used by 04_build_rootfs.sh and 05_make_image.sh.
#   usage: install_board_files.sh <rootfs dir>
set -euo pipefail
R=$1
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cp -r "$HERE/board/." "$R/"
FILES="$R/usr/local/bin/ardzy $R/usr/local/sbin/ardzy-board-init $R/usr/local/sbin/ardzy-config $R/usr/local/sbin/ardzy-update
       $R/usr/lib/python3/dist-packages/ardzy.py $R/usr/lib/python3/dist-packages/ardzy_env.py
       $R/opt/ardzy/web/ardzyweb.py $R/opt/ardzy/web/hwapi.py $R/opt/ardzy/web/iotools.py $R/opt/ardzy/web/sysinfo.py $R/opt/ardzy/web/io_map.json $R/opt/ardzy/web/index.html"
UNITS="$(ls $R/etc/systemd/system/ardzy-* $R/etc/systemd/system.conf.d/*.conf)"
sed -i 's/\r$//' $FILES $UNITS                      # Windows line endings off
chmod 644 $FILES $UNITS                             # files copied from Windows are 777
chmod 755 $R/usr/local/bin/ardzy $R/usr/local/sbin/ardzy-board-init $R/usr/local/sbin/ardzy-config $R/usr/local/sbin/ardzy-update \
          $R/opt/ardzy/web/ardzyweb.py
mkdir -p $R/opt/ardzy/projects $R/var/lib/ardzy $R/lib/firmware/ardzy
# Arduino core, libraries and the sketch builder (arduino/ in the repo)
rm -rf $R/usr/lib/ardzy/arduino && mkdir -p $R/usr/lib/ardzy && cp -r "$HERE/arduino" $R/usr/lib/ardzy/
find $R/usr/lib/ardzy $R/opt/ardzy $R/usr/local/bin $R/usr/local/sbin -name '__pycache__' -type d -prune -exec rm -rf {} +
find $R/usr/lib/ardzy/arduino -type f -regex '.*[.]\(py\|h\|hpp\|c\|cpp\|ino\|txt\|properties\)' -exec sed -i 's/\r$//' {} +
chmod -R u=rwX,go=rX $R/usr/lib/ardzy
chmod 755 $R/usr/lib/ardzy/arduino/build.py
# services switched on (same as "systemctl enable", without needing a chroot)
W=$R/etc/systemd/system/multi-user.target.wants
mkdir -p $W $R/etc/systemd/system/timers.target.wants
for s in ardzy-autoload ardzy-web ardzy-board ardzy-firstboot; do
  [ -f $R/etc/systemd/system/$s.service ] && ln -sf /etc/systemd/system/$s.service $W/$s.service
done
ln -sf /etc/systemd/system/ardzy-bootok.timer $R/etc/systemd/system/timers.target.wants/ardzy-bootok.timer
mkdir -p $R/etc/systemd/system/sysinit.target.wants
ln -sf /etc/systemd/system/ardzy-config.service $R/etc/systemd/system/sysinit.target.wants/ardzy-config.service
echo "board files installed"
