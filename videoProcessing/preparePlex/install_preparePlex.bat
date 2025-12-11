@echo off
REM Ensure running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

pip install colorama
pip install requests
pip install dotenv

set "REG_PATH=HKCR\Folder\shell\preparePlex"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Prepare Plex" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0film.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%~dp0launch_prepareForPlex.bat\" %%V" /f

set "REG_PATH=HKCR\Directory\Background\shell\preparePlex"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Prepare Plex" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0film.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%~dp0launch_prepareForPlex.bat\" %%V" /f

powershell -Command "Write-Host 'Context menu preparePlex created successfully!' -ForegroundColor Green"