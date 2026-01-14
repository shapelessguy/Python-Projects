Set objShell = CreateObject("WScript.Shell")
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

pipCmd = "python -m pip install --upgrade --user --quiet --no-deps -r " & requirementsPath
exitCode = installShell.Run("cmd /c " & pipCmd, 0, True)

If exitCode <> 0 Then
    MsgBox "Error installing dependencies!"
End If

cmd = "cmd /c python -u """ & scriptPath & """ startup > """ & logFile & """ 2>&1"
objShell.Run cmd, 0, True

