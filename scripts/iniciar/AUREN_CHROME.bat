@echo off
setlocal
rem Entrada: ui\chrome_server.py (via modulo Python ui.chrome_server)
cd /d "%~dp0..\.."
call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 (
    pause
    exit /b 1
)
%AUREN_PYTHON% -m ui.chrome_server
set "AUREN_EXIT_CODE=%ERRORLEVEL%"
if not "%AUREN_EXIT_CODE%"=="0" (
    echo.
    echo Falha ao iniciar a interface Chrome do Auren.
    echo Confira o ambiente Python e os pacotes do Auren.
    pause
)
exit /b %AUREN_EXIT_CODE%
