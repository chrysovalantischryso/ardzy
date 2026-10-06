#!/bin/bash
# Step 1: host tools + sources (run in WSL as root)
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git build-essential bc bison flex libssl-dev libgnutls28-dev \
  gcc-arm-linux-gnueabihf python3-dev python3-setuptools python3-pyelftools swig \
  u-boot-tools device-tree-compiler mtools dosfstools e2fsprogs qemu-user-static \
  binfmt-support kmod cpio rsync >/dev/null
mkdir -p /root/s9v2/src && cd /root/s9v2/src
[ -d u-boot ] || git clone -q --depth 1 -b v2026.07 https://github.com/u-boot/u-boot.git
[ -d linux-xlnx ] || git clone -q --depth 1 -b xilinx-v2026.1 https://github.com/Xilinx/linux-xlnx.git
arm-linux-gnueabihf-gcc --version | head -1
make -s -C linux-xlnx kernelversion
echo SOURCES_OK
