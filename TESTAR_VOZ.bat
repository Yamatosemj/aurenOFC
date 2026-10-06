@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m pytest tests\test_voice.py -q
) else (
    py -3 -m pytest tests\test_voice.py -q
)
pause
