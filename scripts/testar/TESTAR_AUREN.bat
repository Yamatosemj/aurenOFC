@echo off
setlocal
cd /d "%~dp0..\.."

rem Sem argumentos: somente L0 e L1 (descoberta e verificacoes sem API).
rem L2 pode alterar o Windows; L4/L5 podem utilizar API e alterar desktop.
rem Camadas com efeitos exigem escolha explicita via --camada ou --completo.
set "AUREN_TEST_ARGS=%*"
if "%~1"=="" (
    set "AUREN_TEST_ARGS=--camada L0,L1"
    echo [INFO] Teste padrao seguro: somente camadas L0 e L1.
    echo [INFO] L2, L4 e L5 nao serao executadas automaticamente.
)

rem Mesmo interpretador dos atalhos de instalacao e inicializacao.
call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 exit /b 1

rem Preflight de dependencias obrigatorias antes de carregar o Auren.
%AUREN_PYTHON% -c "import jsonschema, openai"
if errorlevel 1 (
    echo.
    echo [ERRO] Dependencias Python ausentes ou incompletas.
    echo Execute scripts\instalar\INSTALAR_AUREN.bat e rode este teste novamente.
    echo.
    exit /b 1
)

%AUREN_PYTHON% testes_auren.py %AUREN_TEST_ARGS%

set "AUREN_EXIT_CODE=%ERRORLEVEL%"
echo.
echo ========================================
echo AUREN - CODIGO DE SAIDA: %AUREN_EXIT_CODE%
echo ========================================
pause
exit /b %AUREN_EXIT_CODE%
