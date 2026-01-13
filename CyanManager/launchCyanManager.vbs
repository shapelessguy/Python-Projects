Set objShell = CreateObject("WScript.Shell")
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

' Build log filename
logFile = logDir & "\CyanManager_" & curYear & "-" & curMonth & "-" & curDay & "_" & curHour & "-" & curMinute & ".log"
scriptPath = scriptDir & "\main_logic.py"

' Build command
cmd = "cmd /c python -u """ & scriptPath & """ ""startup"" > """ & logFile & """ 2>&1"

' Run hidden, wait until finished
objShell.Run cmd, 0, True
