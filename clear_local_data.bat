@echo off
setlocal

for /f "delims=" %%R in ('git rev-parse --show-toplevel 2^>nul') do set "REPO_ROOT=%%R"
if not defined REPO_ROOT (
  echo This script must be run from inside the git repository.
  exit /b 1
)

cd /d "%REPO_ROOT%" || exit /b 1

if not exist temp mkdir temp
if not exist extracted mkdir extracted

echo This will delete all contents inside temp\ and extracted\.
echo The temp\ and extracted\ folders themselves will be kept.
echo.
choice /m "Continue"
if errorlevel 2 (
  echo Cancelled.
  exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($d in @('temp','extracted')) { New-Item -ItemType Directory -Force -Path $d | Out-Null; Get-ChildItem -LiteralPath $d -Force | Remove-Item -Recurse -Force }"
if errorlevel 1 exit /b 1

if not exist temp mkdir temp
if not exist extracted mkdir extracted

echo Done.
