@echo off
setlocal

for /f "delims=" %%R in ('git rev-parse --show-toplevel 2^>nul') do set "REPO_ROOT=%%R"
if not defined REPO_ROOT (
  echo This script must be run from inside the git repository.
  exit /b 1
)

cd /d "%REPO_ROOT%" || exit /b 1

for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":5173 .*LISTENING"') do (
  for /f "tokens=1 delims=," %%N in ('tasklist /FI "PID eq %%P" /FO CSV /NH') do (
    if /I "%%~N"=="python.exe" taskkill /PID %%P /F >nul
  )
)

ping -n 2 127.0.0.1 >nul

netstat -ano -p tcp | findstr /R /C:":5173 .*LISTENING" >nul
if not errorlevel 1 (
  echo Could not start because port 5173 is still in use by a non-Python process.
  echo Close the process using that port, then run this script again.
  exit /b 1
)

python server.py
