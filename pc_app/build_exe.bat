@echo off
rem Builds Ardzy.exe (folder dist\Ardzy). Needs: python -m pip install pywebview pyinstaller pyserial pyaudiowpatch numpy
rem Built in a temp folder first, then copied over dist\Ardzy, so a running Ardzy (or a program
rem started from it) cannot break the build by locking files.
rem Inside: the UI, project templates, the built-in FPGA toolchain (tools\fpga, made by
rem fpga\make_toolchain.sh) + the Ardzy FPGA library (fpga\hdl), and the Arduino examples.
cd /d "%~dp0"
if not exist "%~dp0tools\fpga\bin\nextpnr-himbaechel.exe" (echo tools\fpga missing: run fpga\make_toolchain.sh first & exit /b 1)
python make_icon.py
set OUT=%TEMP%\ardzy_dist
if exist "%OUT%" rmdir /s /q "%OUT%"
python -m PyInstaller --noconfirm --windowed --name Ardzy --icon "%~dp0ardzy.ico" ^
  --add-data "%~dp0ui;ui" --add-data "%~dp0templates;templates" ^
  --add-data "%~dp0fpga\hdl;fpga\hdl" --add-data "%~dp0tools\fpga;tools\fpga" ^
  --add-data "%~dp0fpga\simlib;fpga\simlib" --add-data "%~dp0tools\icarus;tools\icarus" ^
  --add-data "%~dp0..\arduino\examples;arduino\examples" --add-data "%~dp0..\fpga_projects;fpga_projects" ^
  --add-data "%~dp0..\projects\ardzy_io;starter\ardzy_io" --add-data "%~dp0..\projects\blink;starter\blink" ^
  --add-data "%~dp0..\projects\board_hello;starter\board_hello" --add-data "%~dp0..\projects\fpga_ramtest;starter\fpga_ramtest" ^
  --add-data "%~dp0..\projects\fpga_selftest;starter\fpga_selftest" --add-data "%~dp0..\projects\leds_python;starter\leds_python" ^
  --paths "%~dp0fpga" --hidden-import fasm2bit --hidden-import aes67_pc --hidden-import pyaudiowpatch --hidden-import numpy ^
  --distpath "%OUT%" --workpath "%TEMP%\ardzy_pyi" --specpath "%TEMP%\ardzy_pyi" ^
  --hidden-import serial.tools.list_ports ardzy_app.py
if not exist "%OUT%\Ardzy\Ardzy.exe" (echo BUILD FAILED & exit /b 1)
robocopy "%OUT%\Ardzy" "%~dp0dist\Ardzy" /MIR /R:1 /W:1 /NFL /NDL /NJH /NJS /NP >nul
echo.
echo OK: dist\Ardzy\Ardzy.exe
