@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %ERRORLEVEL%==0 (
    py -3 interface_auren.py
) else (
    python interface_auren.py
)
if errorlevel 1 (
    echo.
    echo Nao foi possivel abrir a interface. Confira o Python e a instalacao do Auren.
    pause
)
endlocal
