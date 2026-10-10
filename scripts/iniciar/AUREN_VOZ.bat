@echo off
setlocal
cd /d "%~dp0..\.."

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" voice\main.py
) else (
    py -3 voice\main.py
)

set "AUREN_EXIT_CODE=%ERRORLEVEL%"
echo.
echo ========================================
echo AUREN VOICE ENGINE V3 - CODIGO: %AUREN_EXIT_CODE%
echo ========================================
pause
exit /b %AUREN_EXIT_CODE%
