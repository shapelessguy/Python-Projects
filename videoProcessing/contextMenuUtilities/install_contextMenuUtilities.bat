@echo off
REM Ensure running as admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM -------------- Normal CMD

set "REG_PATH=HKCR\Directory\Background\shell\launchCMD"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with CMD" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0cmd.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "cmd.exe /k cd /d \"%%V\"" /f

set "REG_PATH=HKCR\Folder\shell\launchCMD"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with CMD" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0cmd.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "cmd.exe /k cd /d \"%%V\"" /f

REM -------------- Admin CMD

set "REG_PATH=HKCR\Directory\Background\shell\launchCMDAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with CMD (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0cmd.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -Command \"Start-Process cmd.exe -Verb RunAs -ArgumentList '/k','cd /d \"\"%%V\"\"'\"" /f

set "REG_PATH=HKCR\Folder\shell\launchCMDAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with CMD (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0cmd.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -Command \"Start-Process cmd.exe -Verb RunAs -ArgumentList '/k','cd /d \"\"%%V\"\"'\"" /f

REM -------------- Normal PowerShell

set "REG_PATH=HKCR\Directory\Background\shell\launchPowerShell"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Powershell" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0PowerShell.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -NoProfile -Command \"Start-Process powershell -ArgumentList '-NoExit','-Command Set-Location -LiteralPath \"%%V\"'\"" /f

set "REG_PATH=HKCR\Folder\shell\launchPowerShell"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Powershell" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0PowerShell.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -NoProfile -Command \"Start-Process powershell -ArgumentList '-NoExit','-Command Set-Location -LiteralPath \"%%V\"'\"" /f

REM -------------- Admin PowerShell

set "REG_PATH=HKCR\Directory\Background\shell\launchPowerShellAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Powershell (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0PowerShell.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -NoProfile -Command \"Start-Process powershell -Verb RunAs -ArgumentList '-NoExit','-Command Set-Location -LiteralPath \"%%V\"'\"" /f

set "REG_PATH=HKCR\Folder\shell\launchPowerShellAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Powershell (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0PowerShell.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -NoProfile -Command \"Start-Process powershell -Verb RunAs -ArgumentList '-NoExit','-Command Set-Location -LiteralPath \"%%V\"'\"" /f

REM -------------- Normal Git

set "REG_PATH=HKCR\Directory\Background\shell\launchGit"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Git" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0git.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"C:\Program Files\Git\git-bash.exe\" --cd=\"%%V\"" /f

set "REG_PATH=HKCR\Folder\shell\launchGit"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Git" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0git.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"C:\Program Files\Git\git-bash.exe\" --cd=\"%%V\"" /f

REM -------------- Normal VSCode

set "REG_PATH=HKCR\Directory\Background\shell\launchVSCode"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio Code" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vscode.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe\" -n \"%%V\"" /f

set "REG_PATH=HKCR\Folder\shell\launchVSCode"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio Code" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vscode.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe\" -n \"%%V\"" /f

REM -------------- Admin VSCode

set "REG_PATH=HKCR\Directory\Background\shell\launchVSCodeAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio Code (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vscode.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -Command \"Start-Process '%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe' -ArgumentList '-n','%%V' -Verb RunAs\"" /f

set "REG_PATH=HKCR\Folder\shell\launchVSCodeAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio Code (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vscode.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -Command \"Start-Process '%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe' -ArgumentList '-n','%%V' -Verb RunAs\"" /f

REM -------------- Normal Visual Studio

set "REG_PATH=HKCR\Directory\Background\shell\launchVS"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vs.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe\" \"%%V\"" /f

set "REG_PATH=HKCR\Folder\shell\launchVS"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vs.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "\"%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe\" \"%%V\"" /f

REM -------------- Admin Visual Studio

set "REG_PATH=HKCR\Directory\Background\shell\launchVSAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vs.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -Command \"Start-Process '%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe' -ArgumentList '%%V' -Verb RunAs\"" /f

set "REG_PATH=HKCR\Folder\shell\launchVSAsAdmin"
reg add "%REG_PATH%" /f
reg add "%REG_PATH%" /v "MUIVerb" /d "Open with Visual Studio (Admin)" /f
reg add "%REG_PATH%" /v "Icon" /d "%~dp0vs.ico" /f
reg add "%REG_PATH%\command" /f
reg add "%REG_PATH%\command" /ve /d "powershell -Command \"Start-Process '%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\devenv.exe' -ArgumentList '%%V' -Verb RunAs\"" /f


powershell -Command "Write-Host 'Context menu untilities created successfully!' -ForegroundColor Green"