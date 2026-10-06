#!/bin/bash
# Newer static qemu-arm (Debian 13's qemu-user 10.0) for the ARM chroot.
# Ubuntu 20.04's qemu 4.2 breaks systemd 257's postinst ("Failed to take /etc/passwd lock").
set -euo pipefail
cd /root/s9v2/tools 2>/dev/null || { mkdir -p /root/s9v2/tools && cd /root/s9v2/tools; }
DEB=qemu-user_10.0.13+ds-0+deb13u1_amd64.deb
[ -f $DEB ] || wget -q http://deb.debian.org/debian/pool/main/q/qemu/$DEB
rm -rf qemu && dpkg-deb -x $DEB qemu
Q=$(find qemu -type f -name 'qemu-arm' | head -1)
readelf -l $Q | grep -qi interpreter && { echo "qemu-arm is not static"; exit 1; }
[ -f /usr/bin/qemu-arm-static.orig ] || cp /usr/bin/qemu-arm-static /usr/bin/qemu-arm-static.orig 2>/dev/null || true
install -m 755 $Q /usr/bin/qemu-arm-static
update-binfmts --disable qemu-arm >/dev/null 2>&1 || true
update-binfmts --enable qemu-arm || true
# After a WSL restart update-binfmts can think it is enabled while the kernel has no entry: register directly.
# The kernel decodes the \xNN escapes itself, so they must reach it as plain text.
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-arm ]; then
  MAGIC='\x7f\x45\x4c\x46\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x28\x00'
  MASK='\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff'
  echo ":qemu-arm:M::${MAGIC}:${MASK}:/usr/bin/qemu-arm-static:OCF" > /proc/sys/fs/binfmt_misc/register
fi
grep -q enabled /proc/sys/fs/binfmt_misc/qemu-arm || { echo "binfmt qemu-arm not registered"; exit 1; }
/usr/bin/qemu-arm-static --version | head -1
