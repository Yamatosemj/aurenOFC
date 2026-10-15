@echo off
setlocal
cd /d "%~dp0..\.."

echo ========================================
echo AUREN - INSTALACAO DAS DEPENDENCIAS
echo ========================================

echo.
call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 exit /b 1
%AUREN_PYTHON% -m pip install -r requirements.txt

set "AUREN_EXIT_CODE=%ERRORLEVEL%"
echo.
if "%AUREN_EXIT_CODE%"=="0" (
    echo Dependencias instaladas com sucesso.
) else (
    echo Falha ao instalar as dependencias. Codigo: %AUREN_EXIT_CODE%
)
echo.
pause
exit /b %AUREN_EXIT_CODE%
