#!/bin/bash
# Step 0: ARM's official GCC 14 cross compiler (U-Boot 2026 needs GCC >= 10; Ubuntu 20.04 has 9)
set -euo pipefail
mkdir -p /opt/toolchains && cd /opt/toolchains
for v in 14.3.rel1 14.2.rel1; do
  f=arm-gnu-toolchain-$v-x86_64-arm-none-linux-gnueabihf
  if [ ! -d $f ]; then
    wget -q https://developer.arm.com/-/media/Files/downloads/gnu/$v/binrel/$f.tar.xz || continue
    tar xf $f.tar.xz && rm -f $f.tar.xz
  fi
  ln -sfn /opt/toolchains/$f /opt/toolchains/arm
  break
done
/opt/toolchains/arm/bin/arm-none-linux-gnueabihf-gcc --version | head -1
