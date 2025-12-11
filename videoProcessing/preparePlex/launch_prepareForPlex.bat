@echo off
set arg=%*

net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo Running as admin...
    powershell -Command "Start-Process '%~f0' -Verb RunAs -ArgumentList '%arg%'"
    exit /b
)

cd /d "%~dp0"
echo %~dp0
python "prepareForPlex.py" %arg%