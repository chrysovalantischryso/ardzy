#!/bin/bash
# Step 4: Debian 13 (trixie) armhf root filesystem + our kernel modules + the S9 tools
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
sed -i 's/\r$//' "$HERE/scripts/ensure_arm_chroot.sh"; bash "$HERE/scripts/ensure_arm_chroot.sh"   # ARM chroot after a WSL restart
WORK=/root/s9v2
ROOTFS=$WORK/rootfs
SUITE=trixie
MIRROR=http://deb.debian.org/debian
HOSTNAME_S9=ardzy                  # http://ardzy.local and PuTTY ardzy.local
ROOT_PASS=root                  # change after first login: passwd

PKGS="systemd-sysv,udev,dbus,openssh-server,avahi-daemon,libnss-mdns,iproute2,iputils-ping,\
ca-certificates,wget,curl,nano,less,htop,sudo,kmod,procps,psmisc,file,unzip,\
systemd-timesyncd,cloud-guest-utils,parted,e2fsprogs,dosfstools,\
python3,python3-numpy,i2c-tools,device-tree-compiler,build-essential,git,mtd-utils,ethtool,\
bash-completion,locales"

export DEBIAN_FRONTEND=noninteractive
update-binfmts --enable qemu-arm >/dev/null 2>&1 || true
[ -e /proc/sys/fs/binfmt_misc/qemu-arm ] || { echo "qemu-arm binfmt not registered"; exit 1; }

# Debian's own debootstrap + keyring (Ubuntu 20.04's are too old for trixie)
mkdir -p $WORK/tools && cd $WORK/tools
if [ ! -x ds/usr/sbin/debootstrap ]; then
  wget -q $MIRROR/pool/main/d/debootstrap/debootstrap_1.0.141_all.deb -O ds.deb
  wget -q $MIRROR/pool/main/d/debian-archive-keyring/debian-archive-keyring_2025.1_all.deb -O kr.deb
  dpkg-deb -x ds.deb ds && dpkg-deb -x kr.deb kr
fi
export DEBOOTSTRAP_DIR=$WORK/tools/ds/usr/share/debootstrap

if [ "${SKIP_DEBOOTSTRAP:-0}" != 1 ]; then
echo "== debootstrap $SUITE armhf"
rm -rf $ROOTFS && mkdir -p $ROOTFS
$WORK/tools/ds/usr/sbin/debootstrap --arch=armhf --variant=minbase \
  --keyring=$WORK/tools/kr/usr/share/keyrings/debian-archive-keyring.gpg \
  --include="$PKGS" $SUITE $ROOTFS $MIRROR
fi   # SKIP_DEBOOTSTRAP=1 re-runs only the configuration below

echo "== configure"
echo $HOSTNAME_S9 > $ROOTFS/etc/hostname
printf '127.0.0.1\tlocalhost\n127.0.1.1\t%s\n::1\t\tlocalhost ip6-localhost ip6-loopback\n' $HOSTNAME_S9 > $ROOTFS/etc/hosts
cat > $ROOTFS/etc/fstab <<'EOF'
/dev/mmcblk0p2  /       ext4  defaults,noatime  0 1
/dev/mmcblk0p1  /boot   vfat  defaults          0 2
EOF
cat > $ROOTFS/etc/apt/sources.list <<EOF
deb $MIRROR $SUITE main contrib non-free non-free-firmware
deb $MIRROR $SUITE-updates main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security $SUITE-security main contrib non-free non-free-firmware
EOF
mkdir -p $ROOTFS/etc/systemd/network
cat > $ROOTFS/etc/systemd/network/10-eth.network <<'EOF'
[Match]
Name=eth* en*

[Network]
DHCP=yes
LinkLocalAddressing=yes
MulticastDNS=no
EOF
# DNS: systemd-resolved takes the DNS server from DHCP (router), public DNS as fallback.
# (Without it /etc/resolv.conf would keep the build PC's WSL-only DNS 10.255.255.254.)
# mDNS (ardzy.local) stays with avahi, so resolved's own mDNS/LLMNR are off.
mkdir -p $ROOTFS/etc/systemd/resolved.conf.d
cat > $ROOTFS/etc/systemd/resolved.conf.d/ardzy.conf <<'EOF'
[Resolve]
FallbackDNS=1.1.1.1 9.9.9.9 8.8.8.8
MulticastDNS=no
LLMNR=no
EOF
mkdir -p $ROOTFS/etc/ssh/sshd_config.d
echo "PermitRootLogin yes" > $ROOTFS/etc/ssh/sshd_config.d/10-root.conf
rm -f $ROOTFS/etc/ssh/ssh_host_*

# first boot: unique SSH keys + grow the root partition to the whole SD card
cat > $ROOTFS/usr/local/sbin/ardzy-firstboot <<'EOF'
#!/bin/sh
ssh-keygen -A
if growpart /dev/mmcblk0 2; then resize2fs /dev/mmcblk0p2; fi
systemctl disable ardzy-firstboot.service
EOF
chmod +x $ROOTFS/usr/local/sbin/ardzy-firstboot
cat > $ROOTFS/etc/systemd/system/ardzy-firstboot.service <<'EOF'
[Unit]
Description=Ardzy first boot (SSH keys, grow root partition)
Before=ssh.service
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/ardzy-firstboot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

echo "== kernel modules"
KVER=$(ls /root/s9v2/out/modules/lib/modules/)
mkdir -p $ROOTFS/usr/lib/modules
rm -rf $ROOTFS/usr/lib/modules/*          # old kernel versions out
cp -a /root/s9v2/out/modules/lib/modules/$KVER $ROOTFS/usr/lib/modules/
rm -f $ROOTFS/usr/lib/modules/$KVER/build $ROOTFS/usr/lib/modules/$KVER/source

echo "== Ardzy tools (ardzy command, python library, web page, services)"
bash "$HERE/scripts/install_board_files.sh" $ROOTFS
mkdir -p $ROOTFS/opt/ardzy/projects $ROOTFS/var/lib/ardzy $ROOTFS/lib/firmware/ardzy

cat > $ROOTFS/etc/motd <<'EOF'

  ARDZY 0.2 BETA  -  Zynq like an Arduino  (Antminer S9 board, XC7Z010, 512 MB, Debian 13)
  -------------------------------------------------------------------------------
  ardzy list         your projects           ardzy load <name>    run one (sketch, Python, C, FPGA)
  ardzy status       what is running         ardzy log -f         program output
  ardzy config       board settings          ardzy pin-control    FPGA pins ready for I/O and Tools
  ardzy help         all commands            web page             http://<name>.local
  Settings file: /boot/ardzy.txt (also editable on a PC, or from the Ardzy app)

EOF
# Ardzy 0.2: compressed swap in RAM, and logs that do not wear out the SD card
cat > $ROOTFS/etc/systemd/zram-generator.conf <<'EOF'
[zram0]
zram-size = min(ram / 2, 256)
compression-algorithm = lz4
swap-priority = 100
EOF
mkdir -p $ROOTFS/etc/systemd/journald.conf.d
cat > $ROOTFS/etc/systemd/journald.conf.d/ardzy.conf <<'EOF'
[Journal]
SystemMaxUse=64M
RuntimeMaxUse=16M
MaxRetentionSec=1month
EOF

echo "== chroot setup"
cp /usr/bin/qemu-arm-static $ROOTFS/usr/bin/
# apt inside the chroot needs a working DNS: use the build PC's for the moment
# (the end of the chroot step links /etc/resolv.conf back to systemd-resolved)
cp --remove-destination /etc/resolv.conf $ROOTFS/etc/resolv.conf
chroot $ROOTFS /bin/bash -e <<CHROOT
# extra tools: NAND inspection/backup (nanddump, mtdinfo), Ethernet speed (ethtool),
# Ardzy 0.2: compressed swap in RAM (zram generator), Python serial ports, rsync
EXTRA="mtd-utils ethtool systemd-zram-generator python3-serial rsync"
if ! dpkg -s \$EXTRA >/dev/null 2>&1; then
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \$EXTRA >/dev/null
fi
echo "root:$ROOT_PASS" | chpasswd
sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen >/dev/null
echo 'LANG=en_US.UTF-8' > /etc/default/locale
ln -sf /usr/share/zoneinfo/Europe/Athens /etc/localtime
depmod $KVER
systemctl enable systemd-networkd systemd-timesyncd ssh avahi-daemon \
  ardzy-firstboot serial-getty@ttyPS0 ardzy-autoload ardzy-bootok.timer ardzy-web ardzy-board ardzy-config
systemctl mask systemd-networkd-wait-online
# installed last: its postinst turns /etc/resolv.conf into a link to the resolved stub
if ! dpkg -s systemd-resolved >/dev/null 2>&1; then
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq systemd-resolved >/dev/null
fi
systemctl enable systemd-resolved
ln -sf ../run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
apt-get clean
CHROOT
rm -f $ROOTFS/usr/bin/qemu-arm-static
# the result must NOT point at the build PC's DNS
[ "$(readlink $ROOTFS/etc/resolv.conf)" = "../run/systemd/resolve/stub-resolv.conf" ] || { echo "resolv.conf not linked to resolved"; exit 1; }
rm -rf $ROOTFS/var/lib/apt/lists/* $ROOTFS/var/log/*.log
du -sh $ROOTFS
echo ROOTFS_OK
