@echo off
REM Ensure running as admin (needed to write to HKCR)
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

where python >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Write-Host 'ERROR: python not found in PATH!' -ForegroundColor Red"
    pause
    exit /b 1
)
where ffmpeg >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Write-Host 'ERROR: ffmpeg not found in PATH!' -ForegroundColor Red"
    pause
    exit /b 1
)

pip install requests
pip install colorama
pip install pyqt5

set "REG_PATH=HKCR\Folder\shell\generateSrt"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Generate SRT" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0srt.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%~dp0launch_generateSrt.bat\" \"%%V\"" /f

set "REG_PATH=HKCR\Directory\Background\shell\generateSrt"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Generate SRT" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0srt.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%~dp0launch_generateSrt.bat\" \"%%V\"" /f

powershell -Command "Write-Host 'Context menu Generate SRT created successfully!' -ForegroundColor Green"
