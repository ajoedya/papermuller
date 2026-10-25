@echo off
title Research Harness
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python is not installed.
  echo  Download it from python.org/downloads and tick "Add Python to PATH" during installation.
  echo.
  pause
  exit /b
)
python app.py
pause
