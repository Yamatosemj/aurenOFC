@echo off
rem Uso: call "%~dp0..\lib\SELECIONAR_PYTHON.cmd" a partir de um .bat em scripts/.
rem O caller ja executou cd para a raiz do projeto.
rem Nao usa setlocal: devolve AUREN_PYTHON e AUREN_PYTHON_SOURCE ao chamador.
set "AUREN_PYTHON="
set "AUREN_PYTHON_SOURCE="

if exist ".venv\Scripts\python.exe" (
    set "AUREN_PYTHON=.venv\Scripts\python.exe"
    set "AUREN_PYTHON_SOURCE=.venv do projeto"
    goto :selected
)
if exist "..\.venv\Scripts\python.exe" (
    set "AUREN_PYTHON=..\.venv\Scripts\python.exe"
    set "AUREN_PYTHON_SOURCE=.venv da pasta pai"
    goto :selected
)

where py >nul 2>&1
if not errorlevel 1 (
    set "AUREN_PYTHON=py -3"
    set "AUREN_PYTHON_SOURCE=Python Launcher (py -3)"
    goto :selected
)
where python >nul 2>&1
if not errorlevel 1 (
    set "AUREN_PYTHON=python"
    set "AUREN_PYTHON_SOURCE=python do PATH"
    goto :selected
)

echo [ERRO] Nao foi encontrado Python: .venv do projeto, .venv pai, py -3 ou python.
echo [ERRO] Instale o Python 3 ou configure um ambiente virtual do Auren.
exit /b 1

:selected
echo [INFO] Interpretador Python: %AUREN_PYTHON_SOURCE%
exit /b 0
