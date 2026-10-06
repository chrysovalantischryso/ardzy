#!/bin/bash
# Rebuild the 0.2 image (05) + update bundle (07), then the emulator test. Logs in /root/s9v2/*.log
set -eo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
for f in 05_make_image.sh 07_update_bundle.sh test_os2_qemu.sh install_board_files.sh test_legacy_update_qemu.sh; do sed -i 's/\r$//' "$S/$f"; done
echo "== 05 image";  bash "$S/05_make_image.sh"   > /root/s9v2/make_image.log 2>&1 || { tail -30 /root/s9v2/make_image.log; exit 1; }
tail -3 /root/s9v2/make_image.log
echo "== 07 bundle"; bash "$S/07_update_bundle.sh" > /root/s9v2/bundle.log 2>&1 || { tail -30 /root/s9v2/bundle.log; exit 1; }
tail -3 /root/s9v2/bundle.log
sha256sum /root/s9v2/ardzy_debian13.img | tee /root/s9v2/tested_image.sha256
echo "== emulator test"
bash "$S/test_os2_qemu.sh" > /root/s9v2/test_os2.log 2>&1 || true
cat /root/s9v2/test_os2.log
