@echo off
REM Clears the Windows icon + thumbnail cache databases.
REM Explorer must be closed to delete them (the files are locked while it runs).

echo Closing Explorer...
taskkill /f /im explorer.exe >nul 2>&1

echo Deleting icon cache...
cd /d "%LocalAppData%\Microsoft\Windows\Explorer"
del /a /q iconcache*.db  >nul 2>&1
del /a /q thumbcache*.db >nul 2>&1

REM Legacy location (older Windows)
del /a /q "%LocalAppData%\IconCache.db" >nul 2>&1

echo Restarting Explorer...
start explorer.exe

echo.
echo Done. Icon cache cleared.
timeout /t 2 >nul
