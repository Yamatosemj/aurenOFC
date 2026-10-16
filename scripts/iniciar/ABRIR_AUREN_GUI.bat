@echo off
setlocal
cd /d "%~dp0..\.."
call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 (
    pause
    exit /b 1
)
%AUREN_PYTHON% interface_auren.py
set "AUREN_EXIT_CODE=%ERRORLEVEL%"
if not "%AUREN_EXIT_CODE%"=="0" (
    echo.
    echo Nao foi possivel abrir a interface. Confira o Python e a instalacao do Auren.
    pause
)
exit /b %AUREN_EXIT_CODE%
