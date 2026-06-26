@echo off
cd /d "%~dp0"

set "PYTHON_EXE="

if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"

if defined PYTHON_EXE goto run

where python >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=python"

if not defined PYTHON_EXE (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=py"
)

if not defined PYTHON_EXE (
  echo Python is niet gevonden. Installeer Python 3 en start dit bestand opnieuw.
  pause
  exit /b 1
)

:run
"%PYTHON_EXE%" run.py
pause
