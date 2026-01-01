If WScript.Arguments.Count <> 1 Then
    MsgBox "Expected 1 arguments, got " & WScript.Arguments.Count, vbCritical
    WScript.Quit 1
End If

Set objShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

arg1 = WScript.Arguments(0)

logDir = scriptDir & "\logs"
If Not fso.FolderExists(logDir) Then
    fso.CreateFolder logDir
End If

dt = Date()
curYear = Year(dt)
curMonth = Right("0" & Month(dt), 2)
curDay = Right("0" & Day(dt), 2)
curHour   = Right("0" & Hour(dt), 2)
curMinute = Right("0" & Minute(dt), 2)

' Build log filename
logFile = logDir & "\syncAndroid_" & curYear & "-" & curMonth & "-" & curDay & "_" & curHour & "-" & curMinute & ".log"

cmd = "cmd /c python """ & scriptDir & "\syncAndroid.py"" """ & arg1 & """ """ & logFile & """ 2>&1"
objShell.Run cmd, 0, True
