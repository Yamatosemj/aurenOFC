@echo off
setlocal
rem Entrada: ui\chrome_server.py (via modulo Python ui.chrome_server)
cd /d "%~dp0..\.."
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m ui.chrome_server
) else (
    where py >nul 2>&1
    if %ERRORLEVEL%==0 (
        py -3 -m ui.chrome_server
    ) else (
        python -m ui.chrome_server
    )
)
if errorlevel 1 (
    echo.
    echo Falha ao iniciar a interface Chrome do Auren.
    echo Confira o ambiente Python e os pacotes do Auren.
    pause
)
endlocal
