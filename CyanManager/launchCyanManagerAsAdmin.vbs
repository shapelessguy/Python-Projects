Set objShell = CreateObject("Shell.Application")
Set installShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

logDir = scriptDir & "\logs"
If Not fso.FolderExists(logDir) Then
    fso.CreateFolder logDir
End If

dt = Now
curYear = Year(dt)
curMonth = Right("0" & Month(dt), 2)
curDay = Right("0" & Day(dt), 2)
curHour   = Right("0" & Hour(dt), 2)
curMinute = Right("0" & Minute(dt), 2)

logFile = logDir & "\CyanManager_" & curYear & "-" & curMonth & "-" & curDay & "_" & curHour & "-" & curMinute & ".log"
scriptPath = scriptDir & "\main_logic.py"
installDepPath = scriptDir & "\install_dependencies.bat"
requirementsPath = scriptDir & "\requirements.txt"
pythonPath = "C:\Python310\python.exe"

Dim tempDataPath
Dim app_id
Dim targetExe
Dim WshShell

If Not fso.FileExists(pythonPath) Then
    MsgBox "No executable found at " & pythonPath & ". CyanManager cannot run.", vbCritical, "Error"
    WScript.Quit
End If

tempDataPath = "C:\Temp\launchFile.txt"
app_id       = "c0a76b5a-12ab-45c5-b9d9-d693faa6e9a9"
targetExe    = scriptDir & "\tools\CyanLauncherProjects\CyanAppLauncher\bin\Release\CyanAppLauncher.exe"
Set WshShell = CreateObject("WScript.Shell")
Dim cmdLine
cmdLine = """" & targetExe & """ """ & app_id & """ """ & tempDataPath & """"
WshShell.Run cmdLine, 0, False
Set WshShell = Nothing

pipCmd = pythonPath & " -m pip install --upgrade --user --quiet --no-deps -r " & requirementsPath
exitCode = installShell.Run("cmd /c " & pipCmd, 0, True)

If exitCode <> 0 Then
    MsgBox "Error installing dependencies!"
End If

cmd = "/c " & pythonPath & " -u """ & scriptPath & """ startup > """ & logFile & """ 2>&1"
MsgBox cmd
objShell.ShellExecute "cmd.exe", cmd, "", "runas", 0


