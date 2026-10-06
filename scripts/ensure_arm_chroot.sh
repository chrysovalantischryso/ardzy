#!/bin/bash
# Make sure ARM programs run in the rootfs chroot (qemu-arm-static through binfmt_misc).
# A WSL restart drops the kernel's binfmt entry; this puts it back. Called by 04 and 07.
# The static qemu itself is installed once by 00_qemu.sh.
set -eu
[ -x /usr/bin/qemu-arm-static ] || { echo "qemu-arm-static missing: run 00_qemu.sh first"; exit 1; }
[ -e /proc/sys/fs/binfmt_misc/register ] || mount binfmt_misc -t binfmt_misc /proc/sys/fs/binfmt_misc
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-arm ]; then
  update-binfmts --enable qemu-arm >/dev/null 2>&1 || true
fi
# The kernel decodes the \xNN escapes itself, so they must reach it as plain text.
if [ ! -e /proc/sys/fs/binfmt_misc/qemu-arm ]; then
  MAGIC='\x7f\x45\x4c\x46\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x28\x00'
  MASK='\xff\xff\xff\xff\xff\xff\xff\x00\xff\xff\xff\xff\xff\xff\xff\xff\xfe\xff\xff\xff'
  echo ":qemu-arm:M::${MAGIC}:${MASK}:/usr/bin/qemu-arm-static:OCF" > /proc/sys/fs/binfmt_misc/register
fi
grep -q enabled /proc/sys/fs/binfmt_misc/qemu-arm || { echo "binfmt qemu-arm not registered"; exit 1; }
