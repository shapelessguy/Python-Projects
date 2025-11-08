@echo off
REM --- Check for Administrator privileges ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)
echo Running with administrator privileges.

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
    echo ERROR: Dll "%MVP64_DLL%" not found! Make sure SVP4 is installed together with its plugins like mvp.
    exit /b 1
)
if not exist "%PLEX_DIR%" (
    echo ERROR: Folder "%PLEX_DIR%" not found! Make sure Plex for Windows is installed.
    exit /b 1
)
if not exist "%PLEX_CONFIG_PATH%" (
    echo ERROR: Configuration file "%PLEX_CONFIG_PATH%" not found! Way to proceed unkwnown.
    exit /b 1
)

copy "%MVP64_DLL%" "%PLEX_DIR%\" /y
(
echo input-ipc-server=mpvpipe
echo hwdec-codecs=all
echo hr-seek-framedrop=no
) > "%PLEX_CONFIG_PATH%"
pause

@REM REM Optional: remove previous temporary folders if they exist
@REM if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
@REM if exist %SPEC_DIR%  rmdir /s /q %SPEC_DIR%
@REM if exist %DIST_DIR%  rmdir /s /q %DIST_DIR%

@REM REM Recreate dist folder
@REM mkdir %DIST_DIR%

@REM REM Create dist folder
@REM mkdir %DIST_DIR%

@REM REM Build EXE
@REM pip install pyinstaller
@REM pyinstaller --onefile --noconsole --distpath %DIST_DIR% --name="PlexLauncher" --icon=../plex.ico --workpath %BUILD_DIR% --specpath %SPEC_DIR% %SCRIPT%

@REM echo.
@REM echo Build complete. EXE is located in %DIST_DIR%

@REM mkdir "%PLEX_SVP_LAUNCHER_DIR%"
@REM copy "%DIST_DIR%\PlexLauncher.exe" "%PLEX_SVP_LAUNCHER_DIR%\" /y

@REM REM Delete old Plex shortcut if it exists
@REM del "%LINK_DIR%\Plex.lnk" /f /q

@REM REM Create new Plex shortcut pointing to the EXE
@REM powershell -NoProfile -Command ^
@REM   "$s=(New-Object -COM WScript.Shell).CreateShortcut('%LINK_DIR%\Plex.lnk');" ^
@REM   "$s.TargetPath='%PLEX_SVP_LAUNCHER_DIR%\PlexLauncher.exe';" ^
@REM   "$s.WorkingDirectory='%PLEX_SVP_LAUNCHER_DIR%';" ^
@REM   "$s.IconLocation='%BASE_DIR%\plex.ico,0';" ^
@REM   "$s.Save()"

@REM echo Plex shortcut recreated

@REM REM Clean up temporary folders
@REM if exist %BUILD_DIR% rmdir /s /q %BUILD_DIR%
@REM if exist %SPEC_DIR%  rmdir /s /q %SPEC_DIR%
@REM if exist %DIST_DIR%  rmdir /s /q %DIST_DIR%

@REM echo Plex link replaced
@REM pause