@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo AUREN VOICE ENGINE V4 - INSTALACAO
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
echo O cache local do ASR sera preservado para evitar novo download desnecessario.
if exist "data\voice\asr\parakeet-tdt-0.6b-v3-ptBR-TAGARELA-onnx-int8" (
    echo Cache ASR encontrado: mantendo arquivos existentes.
) else (
    echo Cache ASR ainda nao existe; sera baixado no primeiro uso.
)

echo.
echo ========================================
echo AUREN - INSTALACAO DA VOZ V4: 0
echo ========================================
pause
exit /b 0
