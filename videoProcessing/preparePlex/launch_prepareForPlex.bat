@echo off
set "arg=%1"

net session >nul 2>&1
if %errorLevel% NEQ 0 (
    echo Running as admin...
    powershell -Command "Start-Process '%~f0' -Verb RunAs -ArgumentList '%arg%'"
    exit /b
)

cd /d "%~dp0"
echo %~dp0
"C:\Users\shape\AppData\Local\Programs\Python\Python311\python.exe" "prepareForPlex.py" "%arg%"