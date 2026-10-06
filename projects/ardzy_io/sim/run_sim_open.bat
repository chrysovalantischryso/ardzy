@echo off
rem Simulate the open-toolchain core (bridge + decoder + GPIO + ardzy_ctl) with Vivado's xsim.
if not defined VIV set VIV=D:\Vivado\Vivado\2021.1
set W=%TEMP%\ardzy_sim_open
if exist "%W%" rmdir /s /q "%W%"
mkdir "%W%"
copy /y "%~dp0..\ardzy_ctl.v" "%W%\" >nul
copy /y "%~dp0..\ardzy_io_top.v" "%W%\" >nul
copy /y "%~dp0..\..\..\pc_app\fpga\hdl\ardzy_axi.v" "%W%\" >nul
copy /y "%~dp0tb_open.v" "%W%\" >nul
pushd "%W%"
call "%VIV%\bin\xvlog.bat" ardzy_ctl.v ardzy_axi.v ardzy_io_top.v tb_open.v "%VIV%\data\verilog\src\glbl.v" || goto :fail
call "%VIV%\bin\xelab.bat" -L unisims_ver tb_open glbl -s tb_open_sim -debug off || goto :fail
call "%VIV%\bin\xsim.bat" tb_open_sim -R
popd
exit /b 0
:fail
popd
echo SIM_BUILD_FAILED
exit /b 1
