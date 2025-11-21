@echo off
REM --- Check for Administrator privileges ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

set "PLEX_DIR=C:\Program Files\Plex\Plex"
set "MVP64_DLL=C:\Program Files (x86)\SVP 4\mpv64\libmpv-2.dll"
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
if not exist "%MVP64_DLL%" (
    powershell -Command "Write-Host 'ERROR: Dll ''%MVP64_DLL%'' not found! Make sure SVP4 is installed together with its plugins like mvp.' -ForegroundColor Red"
    pause
    exit /b 1
)
if not exist "%PLEX_DIR%" (
    powershell -Command "Write-Host 'ERROR: Folder ''%PLEX_DIR%'' not found! Make sure Plex for Windows is installed.' -ForegroundColor Red"
    pause
    exit /b 1
)
if not exist "%VLC_PATH%" (
    powershell -Command "Write-Host 'ERROR: VLCx64 not found! Make sure VLC64 is installed.' -ForegroundColor Red"
    pause
    exit /b 1
)


echo Installing contextMenuUtilities...
call %~dp0iconApplier\install_contextMenuUtilities.bat
if %ERRORLEVEL% neq 0 (
    powershell -Command "Write-Host 'ERROR: install_contextMenuUtilities failed!' -ForegroundColor Red"
    pause
    exit /b 1
)

echo Installing applyIcon...
call %~dp0iconApplier\install_iconApplier.bat
if %ERRORLEVEL% neq 0 (
    powershell -Command "Write-Host 'ERROR: install_iconApplier failed!' -ForegroundColor Red"
    pause
    exit /b 1
)

echo Installing Plex Launcher...
call %~dp0PlexLauncher\install_plex_launcher.bat
if %ERRORLEVEL% neq 0 (
    powershell -Command "Write-Host 'ERROR: install_plex_launcher failed!' -ForegroundColor Red"
    pause
    exit /b 1
)

echo Installing preparePlex...
call %~dp0preparePlex\install_preparePlex.bat
if %ERRORLEVEL% neq 0 (
    powershell -Command "Write-Host 'ERROR: install_preparePlex failed!' -ForegroundColor Red"
    pause
    exit /b 1
)
pause