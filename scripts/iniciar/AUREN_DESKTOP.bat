@echo off
setlocal
cd /d "%~dp0..\..\desktop\electron"
if not exist "node_modules\electron\cli.js" (
    echo Electron ainda nao instalado.
    echo Execute uma vez: cd desktop\electron ^&^& npm install
    pause
    exit /b 1
)
call npm start
if errorlevel 1 (
    echo.
    echo Falha ao iniciar o Auren Desktop.
    pause
)
endlocal
