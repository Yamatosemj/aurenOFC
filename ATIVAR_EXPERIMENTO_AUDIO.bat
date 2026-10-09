@echo off
setlocal
cd /d "%~dp0"
set "AUREN_EXPERIMENT_CAPABILITY_AUDIO=1"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" main.py
) else (
    py -3 main.py
)

exit /b %ERRORLEVEL%
