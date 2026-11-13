@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Python 3 is required.
  pause
  exit /b 1
)
py tools\build-source-windows.py
if errorlevel 1 echo Source build did not finish. See the output above.
pause
