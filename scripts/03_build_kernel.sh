#!/bin/bash
# Step 3: Linux kernel (Xilinx linux-xlnx, tag xilinx-v2026.1) + our clean S9 device tree
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC=/root/s9v2/src/linux-xlnx
OUT=/root/s9v2/out/linux
MODS=/root/s9v2/out/modules
export ARCH=arm CROSS_COMPILE=/opt/toolchains/arm/bin/arm-none-linux-gnueabihf-

cp "$HERE/kernel/zynq-antminer-s9.dts" $SRC/arch/arm/boot/dts/xilinx/
cd $SRC
# NAND safety patch: the pl35x driver forces an ON-FLASH bad block table, and the kernel would
# CREATE and WRITE such a table on the chip if it does not find one (below the partition level,
# so a read-only partition does not prevent it). The original Bitmain NAND must never be written:
# use an in-RAM table built by only READING the factory bad-block markers.
F=drivers/mtd/nand/raw/pl35x-nand-controller.c
sed -i 's|\tchip->bbt_options = NAND_BBT_USE_FLASH;|\tchip->bbt_options = 0;\t/* Ardzy: no on-flash BBT, never write to the NAND */|' $F
grep -q 'Ardzy: no on-flash BBT' $F || { echo "NAND safety patch NOT applied: stop"; exit 1; }
if grep -q 'bbt_options = NAND_BBT_USE_FLASH' $F; then echo "driver still forces NAND_BBT_USE_FLASH: stop"; exit 1; fi
echo "NAND safety patch applied"
make -s O=$OUT xilinx_zynq_defconfig
cp "$HERE/kernel/s9.config" /root/s9v2/s9.config     # merge_config.sh can't handle spaces in paths
scripts/kconfig/merge_config.sh -m -O $OUT $OUT/.config /root/s9v2/s9.config >/dev/null
make -s O=$OUT olddefconfig
make -s O=$OUT LOCALVERSION=-s9 -j"$(nproc)" zImage modules
# base device tree with __symbols__ so overlays can refer to &fpga_full etc.
dtc -@ -I dts -O dtb -o $OUT/zynq-antminer-s9.dtb \
  <(cpp -nostdinc -undef -x assembler-with-cpp -D__DTS__ \
        -I $SRC/include -I $SRC/arch/arm/boot/dts -I $SRC/arch/arm/boot/dts/xilinx \
        $SRC/arch/arm/boot/dts/xilinx/zynq-antminer-s9.dts) 2> >(grep -v Warning >&2 || true)
rm -rf $MODS && make -s O=$OUT LOCALVERSION=-s9 INSTALL_MOD_PATH=$MODS INSTALL_MOD_STRIP=1 modules_install

mkdir -p "$HERE/out/boot"
cp $OUT/arch/arm/boot/zImage "$HERE/out/boot/zImage"
cp $OUT/zynq-antminer-s9.dtb "$HERE/out/boot/system.dtb"
cp $OUT/.config "$HERE/kernel/kernel.config.used"
echo "kernel: $(cat $OUT/include/config/kernel.release)"
for o in OF_CONFIGFS FPGA_MGR_ZYNQ_FPGA OF_FPGA_REGION CGROUP_BPF AUTOFS_FS UIO_PDRV_GENIRQ CADENCE_WATCHDOG; do
  grep -q "^CONFIG_$o=y" $OUT/.config && echo "  $o=y" || echo "  $o MISSING"
done
ls -l "$HERE/out/boot"
echo KERNEL_OK
