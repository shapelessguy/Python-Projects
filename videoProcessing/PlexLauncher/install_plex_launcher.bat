@echo off
REM --- Check for Administrator privileges ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM -------------------------------
REM Build Plex launcher EXE
REM -------------------------------

REM Get absolute paths
set "PLEX_DIR=C:\Program Files\Plex\Plex"
set "PLEX_CONFIG_PATH=C:\Users\%USERNAME%\AppData\Local\Plex\mpv.conf"
set "MVP64_DLL=C:\Program Files (x86)\SVP 4\mpv64\libmpv-2.dll"
set "LINK_DIR=C:\ProgramData\Microsoft\Windows\Start Menu\Programs\Plex"
set "PLEX_SVP_LAUNCHER_DIR=C:\Program Files\Plex\Plex\SVP_compatible_launcher"
set "BASE_DIR=%~dp0"
set "SCRIPT=%BASE_DIR%\template_Plex_link.py"
set "BUILD_DIR=%BASE_DIR%\build_temp"
set "SPEC_DIR=%BASE_DIR%\spec_temp"
set "DIST_DIR=%BASE_DIR%\SVP_compatible_launcher"

cd /d "%BASE_DIR%"

REM Check if the folders exists
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
if not exist "%PLEX_CONFIG_PATH%" (
    powershell -Command "Write-Host 'ERROR: Configuration file ''%PLEX_CONFIG_PATH%'' not found! Way to proceed unkwnown.' -ForegroundColor Red"
    pause
    exit /b 1
)

copy "%MVP64_DLL%" "%PLEX_DIR%\" /y
(
echo input-ipc-server=mpvpipe
echo hwdec-codecs=all
echo hr-seek-framedrop=no
) > "%PLEX_CONFIG_PATH%"

REM Optional: remove previous temporary folders if they exist
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
if exist %SPEC_DIR%  rmdir /s /q %SPEC_DIR%
if exist %DIST_DIR%  rmdir /s /q %DIST_DIR%

REM Recreate dist folder
mkdir %DIST_DIR%

REM Create dist folder
mkdir %DIST_DIR%

REM Build EXE
pip install pyinstaller
pyinstaller --onefile --noconsole --distpath %DIST_DIR% --name="PlexLauncher" --icon=../plex.ico --workpath %BUILD_DIR% --specpath %SPEC_DIR% %SCRIPT%

set "PLEX_LAUNCHER=%DIST_DIR%\PlexLauncher.exe"
if not exist "%MVP64_DLL%" (
    powershell -Command "Write-Host 'ERROR: PlexLauncher.exe has not been generated.' -ForegroundColor Red"
    pause
    exit /b 1
)
powershell -Command "Write-Host 'Build complete. EXE is located in %DIST_DIR%' -ForegroundColor Green"

mkdir "%PLEX_SVP_LAUNCHER_DIR%"
copy "%PLEX_LAUNCHER%" "%PLEX_SVP_LAUNCHER_DIR%\" /y

REM Delete old Plex shortcut if it exists
del "%LINK_DIR%\Plex.lnk" /f /q

REM Create new Plex shortcut pointing to the EXE
powershell -NoProfile -Command ^
  "$s=(New-Object -COM WScript.Shell).CreateShortcut('%LINK_DIR%\Plex.lnk');" ^
  "$s.TargetPath='%PLEX_SVP_LAUNCHER_DIR%\PlexLauncher.exe';" ^
  "$s.WorkingDirectory='%PLEX_SVP_LAUNCHER_DIR%';" ^
  "$s.IconLocation='%BASE_DIR%\plex.ico,0';" ^
  "$s.Save()"
  
if not exist "%LINK_DIR%\Plex.lnk" (
    powershell -Command "Write-Host 'ERROR: Plex link has not been created.' -ForegroundColor Red"
    pause
    exit /b 1
)
powershell -Command "Write-Host 'Plex shortcut created' -ForegroundColor Green"

REM Clean up temporary folders
if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
if exist %SPEC_DIR%  rmdir /s /q %SPEC_DIR%
if exist %DIST_DIR%  rmdir /s /q %DIST_DIR%