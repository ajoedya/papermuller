@echo off
title Asisten Riset
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Python belum terpasang.
  echo  Unduh dari python.org/downloads dan centang "Add Python to PATH" saat memasang.
  echo.
  pause
  exit /b
)
python app.py
pause
