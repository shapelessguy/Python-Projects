Option Explicit

Dim WshShell, fso, scriptDir, pythonCmd, argString, i
Set WshShell = CreateObject("WScript.Shell")
Set fso       = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
argString = ""
If WScript.Arguments.Count > 0 Then
    For i = 0 To WScript.Arguments.Count - 1
        Dim thisArg : thisArg = WScript.Arguments(i)
        ' Quote if contains space or special chars (basic safe quoting)
        If InStr(thisArg, " ") > 0 Or InStr(thisArg, "&") > 0 Or InStr(thisArg, "(") > 0 Then
            thisArg = """" & Replace(thisArg, """", """""") & """"
        End If
        If argString <> "" Then argString = argString & " "
        argString = argString & thisArg
    Next
End If

pythonCmd = "python """ & scriptDir & "\move.py"" " & argString
WshShell.Run pythonCmd, 0, True