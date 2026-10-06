@echo off
rem Simulate ardzy_ctl with Vivado's xsim. Copies to a folder without spaces first.
if not defined VIV set VIV=D:\Vivado\Vivado\2021.1
set W=%TEMP%\ardzy_sim
if exist "%W%" rmdir /s /q "%W%"
mkdir "%W%"
copy /y "%~dp0..\ardzy_ctl.v" "%W%\" >nul
copy /y "%~dp0tb_ardzy_ctl.v" "%W%\" >nul
pushd "%W%"
call "%VIV%\bin\xvlog.bat" ardzy_ctl.v tb_ardzy_ctl.v "%VIV%\data\verilog\src\glbl.v" || goto :fail
call "%VIV%\bin\xelab.bat" -L unisims_ver tb glbl -s tb_sim -debug off || goto :fail
call "%VIV%\bin\xsim.bat" tb_sim -R
popd
exit /b 0
:fail
popd
echo SIM_BUILD_FAILED
exit /b 1
