@echo off
setlocal
cd /d "%~dp0..\.."

call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 exit /b 1

%AUREN_PYTHON% voice\main.py
set "AUREN_EXIT_CODE=%ERRORLEVEL%"
echo.
echo ========================================
echo AUREN VOICE ENGINE V3 - CODIGO: %AUREN_EXIT_CODE%
echo ========================================
pause
exit /b %AUREN_EXIT_CODE%
