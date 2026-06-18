@echo off
REM Dubbelklik dit bestand om alles te starten (Windows).
cd /d "%~dp0"

set "PYTHON_EXE="

where python >nul 2>nul
if not errorlevel 1 set "PYTHON_EXE=python"

if not defined PYTHON_EXE (
  where py >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=py"
)

if not defined PYTHON_EXE (
  set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
  if exist "%CODEX_PYTHON%" set "PYTHON_EXE=%CODEX_PYTHON%"
)

if not defined PYTHON_EXE (
  echo Python is niet gevonden. Installeer Python 3 en start dit bestand opnieuw.
  pause
  exit /b 1
)

"%PYTHON_EXE%" run.py
pause
