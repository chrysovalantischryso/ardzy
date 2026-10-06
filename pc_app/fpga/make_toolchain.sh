#!/bin/bash
# Assemble the Ardzy built-in FPGA toolchain (no Vivado) into pc_app/tools/fpga:
#   bin/yosys.exe (+ yosys-abc.exe + DLLs), bin/nextpnr-himbaechel.exe,
#   share/yosys/..., share/himbaechel/xilinx/chipdb-xc7z010.bin, db/zynq7 (Project X-Ray subset)
# Run inside MSYS2 UCRT64 after nextpnr is built. ARDZY_BUILD = the build folder (default D:\ardzy_build).
set -euo pipefail
APP="${ARDZY_APP:-$(cd "$(dirname "$0")/.." && pwd)}"
OUT="$APP/tools/fpga"
BUILD="${ARDZY_BUILD:-/d/ardzy_build}"
NP="$BUILD/nextpnr/build"
DB="$BUILD/prjxray-db/zynq7"
rm -rf "$OUT"
mkdir -p "$OUT/bin" "$OUT/share/himbaechel/xilinx" "$OUT/db/zynq7/mapping" "$OUT/db/zynq7/xc7z010" "$OUT/db/zynq7/xc7z010clg400-1"

# yosys + the DLLs it needs (everything from /ucrt64)
cp /ucrt64/bin/yosys.exe /ucrt64/bin/yosys-abc.exe "$OUT/bin/"
for exe in /ucrt64/bin/yosys.exe /ucrt64/bin/yosys-abc.exe; do
  ldd "$exe" | grep -i '/ucrt64/' | sed -e 's/.*=> //' -e 's/ (0x.*//' | while read -r dll; do cp -u "$dll" "$OUT/bin/"; done
done
mkdir -p "$OUT/share/yosys"
cp -r /ucrt64/share/yosys/xilinx /ucrt64/share/yosys/*.v /ucrt64/share/yosys/*.txt "$OUT/share/yosys/" 2>/dev/null || true
cp -r /ucrt64/share/yosys/include "$OUT/share/yosys/" 2>/dev/null || true
cp -r /ucrt64/share/yosys/abc9_model.v /ucrt64/share/yosys/abc9_map.v /ucrt64/share/yosys/abc9_unmap.v "$OUT/share/yosys/" 2>/dev/null || true

# nextpnr (static) + chip database
strip -o "$OUT/bin/nextpnr-himbaechel.exe" "$NP/nextpnr-himbaechel.exe"
cp "$NP/share/himbaechel/xilinx/chipdb-xc7z010.bin" "$OUT/share/himbaechel/xilinx/"

# Project X-Ray database: only what fasm2bit needs for xc7z010clg400-1
cp $DB/mapping/parts.yaml $DB/mapping/devices.yaml "$OUT/db/zynq7/mapping/"
cp $DB/xc7z010/tilegrid.json "$OUT/db/zynq7/xc7z010/"
cp $DB/xc7z010clg400-1/part.json $DB/xc7z010clg400-1/package_pins.csv $DB/xc7z010clg400-1/required_features.fasm \
   "$OUT/db/zynq7/xc7z010clg400-1/"
cp $DB/segbits_*.db $DB/ppips_*.db "$OUT/db/zynq7/"
rm -f "$OUT"/db/zynq7/*.origin_info.db
cp "$DB/../COPYING" "$OUT/db/PRJXRAY_DB_LICENSE.txt" 2>/dev/null || true

cat > "$OUT/README.txt" <<'TXT'
Ardzy built-in FPGA toolchain (no Vivado needed)
  Yosys (synthesis)          https://github.com/YosysHQ/yosys       ISC license
  nextpnr-himbaechel Xilinx  https://github.com/YosysHQ/nextpnr     ISC license (Ardzy patches, fpga/nextpnr_ardzy.patch: DNA_PORT, tristate fix, LUT RAM RAM64X1S, RAMB36 width 1/9 bits, RAMB36/18 width 9 parity)
  Project X-Ray database     https://github.com/f4pga/prjxray-db    CC0 1.0
  fasm2bit (in the app)      port of Project X-Ray fasm2frames + xc7frames2bit (ISC)
TXT
du -sh "$OUT"
"$OUT/bin/yosys.exe" -V
"$OUT/bin/nextpnr-himbaechel.exe" --version 2>&1 | head -1
echo TOOLCHAIN_OK
