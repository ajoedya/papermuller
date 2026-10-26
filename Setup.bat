@echo off
setlocal
title Papermuller - Setup
pushd "%~dp0"
if errorlevel 1 exit /b 1

if exist ".venv\Scripts\python.exe" goto check_environment
set "PAPERMULLER_PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 set "PAPERMULLER_PY=py -3"
if defined PAPERMULLER_PY goto create_environment
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 set "PAPERMULLER_PY=python"
if defined PAPERMULLER_PY goto create_environment
echo Python 3.11 or newer was not found.
echo Install Python from https://www.python.org/downloads/windows/
echo Enable "Add python.exe to PATH", then run Setup.bat again.
goto failed

:create_environment
echo Creating the local Python environment...
%PAPERMULLER_PY% -m venv ".venv"
if errorlevel 1 goto failed

:check_environment
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 (
  echo The existing .venv needs Python 3.11 or newer.
  echo Rename .venv and run Setup.bat again. Your .env and research files can stay.
  goto failed
)
echo Installing dependencies. Internet access is required...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
if exist ".env" goto ready
copy "env.example" ".env" >nul
if errorlevel 1 goto failed

:ready
echo.
echo Setup complete. Run Start.bat to open Papermuller.
echo Existing settings, API keys, PDFs, and projects were preserved.
popd
if /I not "%~1"=="--no-pause" pause
exit /b 0

:failed
echo.
echo Setup did not finish. Check the error above before trying again.
popd
if /I not "%~1"=="--no-pause" pause
exit /b 1
