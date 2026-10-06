@echo off
rem Upload this folder to the S9 board and run it (like Arduino 'Upload')
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\pc_tools\ardzy_upload.ps1" -Path "%~dp0." -Log
pause
