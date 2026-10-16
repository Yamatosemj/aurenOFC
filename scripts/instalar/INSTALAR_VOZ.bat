@echo off
setlocal
cd /d "%~dp0..\.."

echo ========================================
echo AUREN VOICE ENGINE V3 - INSTALACAO
echo ========================================
echo.

call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 exit /b 1

echo Instalando dependencias locais de voz...
%AUREN_PYTHON% -m pip install -r requirements-voice.txt
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
