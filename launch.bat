@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
  py desktop_app.py
  exit /b %errorlevel%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python desktop_app.py
  exit /b %errorlevel%
)

echo Python was not found. Install Python 3.10 or newer, then run this file again.
pause
exit /b 1
