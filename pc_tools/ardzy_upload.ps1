<#
  ardzy_upload.ps1 - "Arduino upload" for the Antminer S9 board.

  Copies a project folder to the board and runs it:
    - the FPGA design (.bit). If the folder has no .bit, the newest one from a
      Vivado project inside it (*.runs\impl_1\*.bit) is used.
    - your program: main.py, *.c/*.h, Makefile or run.sh
    - optional devices.dtsi / overlay.dts

  Usage:
    powershell -ExecutionPolicy Bypass -File ardzy_upload.ps1 -Path <project folder> [-Name blink] [-Default] [-Log]
  Settings (board name, password) are read from ardzy_config.txt next to this script.
#>
param(
  [string]$Path = '.',
  [string]$Name = '',
  [switch]$Default,
  [switch]$Log
)
$ErrorActionPreference = 'Stop'

# ---- settings
$cfg = @{ Board = 'ardzy.local'; User = 'root'; Password = 'root' }
$cfgFile = Join-Path $PSScriptRoot 'ardzy_config.txt'
if (Test-Path $cfgFile) {
  foreach ($line in Get-Content $cfgFile) {
    if ($line -match '^\s*(\w+)\s*=\s*(.*?)\s*$') { $cfg[$Matches[1]] = $Matches[2] }
  }
}
$target = "$($cfg.User)@$($cfg.Board)"
$plink = (Get-Command plink.exe -ErrorAction SilentlyContinue).Source
$pscp = (Get-Command pscp.exe -ErrorAction SilentlyContinue).Source
if (-not $plink) { $plink = 'C:\Program Files\PuTTY\plink.exe'; $pscp = 'C:\Program Files\PuTTY\pscp.exe' }
if (-not (Test-Path $plink)) { throw 'PuTTY (plink/pscp) not found. Install PuTTY from https://www.putty.org' }

# ---- project
$dir = (Resolve-Path $Path).Path.TrimEnd('\')
if (-not $Name) { $Name = Split-Path $dir -Leaf }
$Name = ($Name -replace '[^A-Za-z0-9_.-]', '_')

$files = @()
$bit = Get-ChildItem "$dir\*" -File -Include *.bit, *.bin -ErrorAction SilentlyContinue |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $bit) {
  $bit = Get-ChildItem $dir -Recurse -Filter *.bit -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\impl_\d+\\' } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
}
if ($bit) { $files += $bit.FullName }
foreach ($pat in 'main.py', '*.py', '*.c', '*.h', 'Makefile', 'run.sh', 'devices.dtsi', 'overlay.dts', '*.txt', '*.json', '*.csv') {
  Get-ChildItem $dir -File -Filter $pat -ErrorAction SilentlyContinue | ForEach-Object {
    if ($files -notcontains $_.FullName -and $_.Name -ne 'ardzy_config.txt') { $files += $_.FullName }
  }
}
if (-not $files) { throw "Nothing to upload in $dir (need a .bit and/or main.py / .c / run.sh)" }

Write-Host ''
Write-Host "  Ardzy upload: project '$Name' -> $($cfg.Board)" -ForegroundColor Green
foreach ($f in $files) { Write-Host "    $(Split-Path $f -Leaf)" }
if ($bit) { Write-Host "    (FPGA design: $($bit.FullName), $([int]((Get-Date) - $bit.LastWriteTime).TotalMinutes) min old)" -ForegroundColor DarkGray }

# accept the board's SSH key (it changes when the SD card is re-flashed)
cmd /c "echo y| `"$plink`" -ssh -pw `"$($cfg.Password)`" $target exit" 2>$null | Out-Null

$remote = "/opt/ardzy/projects/$Name"
& $plink -batch -pw $cfg.Password $target "rm -rf $remote && mkdir -p $remote"
if ($LASTEXITCODE) { throw "Cannot reach the board at $($cfg.Board). Is it on? Check ardzy_config.txt." }
& $pscp -batch -q -pw $cfg.Password @files "${target}:$remote/"
if ($LASTEXITCODE) { throw 'copy failed' }

$opt = ''
if ($Default) { $opt = '--default' }
& $plink -batch -pw $cfg.Password $target "ardzy load $Name $opt"
if ($LASTEXITCODE) { throw 'load failed (see the message above)' }

Write-Host ''
Write-Host "  Done. Web page: http://$($cfg.Board)" -ForegroundColor Green
if ($Log) {
  Write-Host '  Program output (close the window or press Ctrl+C to stop watching):' -ForegroundColor Green
  & $plink -batch -pw $cfg.Password $target 'ardzy log -f'
}
