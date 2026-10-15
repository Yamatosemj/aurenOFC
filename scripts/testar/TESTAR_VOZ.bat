@echo off
setlocal
cd /d "%~dp0..\.."
call "%~dp0..\lib\SELECIONAR_PYTHON.cmd"
if errorlevel 1 exit /b 1
%AUREN_PYTHON% -m pytest tests\test_voice.py -q
set "AUREN_EXIT_CODE=%ERRORLEVEL%"
pause
exit /b %AUREN_EXIT_CODE%
