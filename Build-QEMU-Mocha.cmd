@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1 || (echo Python 3 is required.& pause & exit /b 1)
if "%MOCHA_DEBIAN_QCOW2%"=="" (
  echo Set MOCHA_DEBIAN_QCOW2 to a Debian 13 genericcloud amd64 qcow2 image.
  pause
  exit /b 1
)
py tools\build-source-qemu.py --base "%MOCHA_DEBIAN_QCOW2%"
if errorlevel 1 echo Build did not finish. Check the output above.
pause
