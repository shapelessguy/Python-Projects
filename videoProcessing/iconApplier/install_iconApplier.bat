@echo off
REM Ensure running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM Registry path for the right-click background menu
set "REG_PATH=HKCR\Folder\shell\iconSetter"

REM Create the key
reg add "%REG_PATH%" /f

REM Set the MUIVerb (the text that appears in the menu)
reg add "%REG_PATH%" /v "MUIVerb" /d "Set Icon" /f

REM Set the icon (full path to your .ico or .exe with icon)
reg add "%REG_PATH%" /v "Icon" /d "%~dp0icon.ico" /f

REM Create the command subkey
reg add "%REG_PATH%\command" /f

REM Set the command to run your EXE
reg add "%REG_PATH%\command" /ve /d "\"%~dp0launch_apply_icon.bat\" %%V" /f


REM Registry path for the right-click background menu
set "REG_PATH=HKCR\Directory\Background\shell\iconSetter"

REM Create the key
reg add "%REG_PATH%" /f

REM Set the MUIVerb (the text that appears in the menu)
reg add "%REG_PATH%" /v "MUIVerb" /d "Set Icon" /f

REM Set the icon (full path to your .ico or .exe with icon)
reg add "%REG_PATH%" /v "Icon" /d "%~dp0icon.ico" /f

REM Create the command subkey
reg add "%REG_PATH%\command" /f

REM Set the command to run your EXE
reg add "%REG_PATH%\command" /ve /d "\"%~dp0launch_apply_icon.bat\" %%V" /f


powershell -Command "Write-Host 'Context menu iconApplier created successfully!' -ForegroundColor Green"