@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo AUREN - INSTALACAO DAS DEPENDENCIAS
echo ========================================

echo.
if exist ".venv\Scripts\python.exe" (
    echo Usando Python do ambiente virtual: .venv
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
) else if exist "..\.venv\Scripts\python.exe" (
    echo Usando Python do ambiente virtual pai: ..\.venv
    "..\.venv\Scripts\python.exe" -m pip install -r requirements.txt
) else (
    where py >nul 2>&1
    if not errorlevel 1 (
        echo Usando Python global: py -3
        py -3 -m pip install -r requirements.txt
    ) else (
        echo Usando Python global: python
        python -m pip install -r requirements.txt
    )
)

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
