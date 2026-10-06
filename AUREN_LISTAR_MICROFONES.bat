@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" voice\list_devices.py
) else (
    py -3 voice\list_devices.py
)
pause
