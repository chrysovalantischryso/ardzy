# Third-party software in Ardzy

Ardzy uses and ships the following software made by other people. Each keeps its own license;
the license of Ardzy itself (GPL-3.0-or-later, Copyright (C) 2026 chryso, see `LICENSE`) covers only the files
written for Ardzy.

## Inside this repository

| Part | Where | License |
|---|---|---|
| Blockly (Google / Raspberry Pi Foundation) | `pc_app/ui/vendor/blockly` | Apache-2.0 (`LICENSE.txt` next to it) |
| CodeMirror 5 (Marijn Haverbeke and others) | `pc_app/ui/vendor/codemirror.min.*`, `addon_*`, `mode_*` | MIT |
| ArduinoCore-API (Arduino) | `arduino/core/api` | LGPL-2.1 (`LICENSE.txt` next to it) |
| Zynq PS7 init for U-Boot | `uboot/ps7_init_gpl.c` | GPL-2.0 (as in U-Boot) |
| nextpnr patch | `pc_app/fpga/nextpnr_ardzy.patch` | ISC (as nextpnr) |

## Inside the Windows app (Release zip)

| Part | License | Source |
|---|---|---|
| Yosys | ISC | https://github.com/YosysHQ/yosys |
| nextpnr (himbaechel, xilinx) | ISC | https://github.com/YosysHQ/nextpnr |
| Project X-Ray database (zynq7 subset) | CC0-1.0 | https://github.com/f4pga/prjxray-db |
| Icarus Verilog | GPL-2.0-or-later | https://github.com/steveicarus/iverilog |
| MSYS2 runtime DLLs used by the tools above | various free licenses | https://www.msys2.org |
| Python, pywebview, pyserial, numpy, PyAudioWPatch, PyInstaller | PSF, BSD-3, BSD-3, BSD-3, MIT, GPL with bootloader exception | https://pypi.org |

## Inside the SD card image (Release file)

| Part | License | Source |
|---|---|---|
| U-Boot 2026.07 | GPL-2.0 | https://source.denx.de/u-boot/u-boot |
| Linux 6.18 (Xilinx tree, tag xilinx-v2026.1) | GPL-2.0 | https://github.com/Xilinx/linux-xlnx |
| Debian 13 (trixie) packages | many free licenses, see `/usr/share/doc/*/copyright` on the card | https://www.debian.org |

The scripts in `scripts/` download and build all of these from their official sources, so the
complete source for everything on the SD card image can be rebuilt from this repository.

## Not included

Nothing from the original Bitmain firmware is part of this repository or of the Ardzy images.
The optional fallback boot file (`fallback/BOOT_fallback.bin`, made from the board's original SD card)
is kept out of the repository on purpose.

"Antminer" and "Bitmain" are trademarks of Bitmain Technologies. Ardzy is a hobby project and is not
made or supported by Bitmain, Xilinx/AMD or Arduino.
