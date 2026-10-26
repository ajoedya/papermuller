@echo off
setlocal
title Papermuller
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" goto setup
".venv\Scripts\python.exe" -c "import sys, pypdf, docx, fontTools; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 goto run

:setup
call "%~dp0Setup.bat" --no-pause
if errorlevel 1 goto failed

:run
echo Starting Papermuller on this laptop...
echo Keep this window open while using the app. Press Ctrl+C to stop.
".venv\Scripts\python.exe" app.py
set "PAPERMULLER_EXIT=%ERRORLEVEL%"
popd
if not "%PAPERMULLER_EXIT%"=="0" pause
exit /b %PAPERMULLER_EXIT%

:failed
popd
pause
exit /b 1
