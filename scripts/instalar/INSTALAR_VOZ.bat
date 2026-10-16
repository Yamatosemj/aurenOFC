@echo off
setlocal
cd /d "%~dp0..\.."

echo ========================================
echo AUREN VOICE ENGINE V3 - INSTALACAO
echo ========================================
echo.

if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=py -3"
)

echo Instalando dependencias locais de voz...
%PY% -m pip install -r requirements-voice.txt
if errorlevel 1 (
    echo.
    echo ERRO: a instalacao das dependencias falhou.
    exit /b %ERRORLEVEL%
)

echo.
echo Cache ASR preservado. Nenhum modelo local sera apagado pelo instalador.
echo Se faltarem arquivos do Parakeet, o proprio ASR tentara completar o download no primeiro uso.

echo.
echo ========================================
echo AUREN - INSTALACAO DA VOZ V3: 0
echo ========================================
pause
exit /b 0
