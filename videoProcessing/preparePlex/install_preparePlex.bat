@echo off
REM Ensure running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set "VLC_PATH=C:\Program Files\VideoLAN\VLC\vlc.exe"

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
where mkvmerge >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Write-Host 'ERROR: mkvmerge not found in PATH!' -ForegroundColor Red"
    pause
    exit /b 1
)
where mkvextract >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Write-Host 'ERROR: mkvextract not found in PATH!' -ForegroundColor Red"
    pause
    exit /b 1
)
if not exist "%VLC_PATH%" (
    powershell -Command "Write-Host 'ERROR: VLCx64 not found! Make sure VLC64 is installed.' -ForegroundColor Red"
    pause
    exit /b 1
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