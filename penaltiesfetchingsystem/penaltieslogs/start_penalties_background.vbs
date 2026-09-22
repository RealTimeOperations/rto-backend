Set fso = CreateObject("Scripting.FileSystemObject")
logsDir   = fso.GetParentFolderName(WScript.ScriptFullName)
sysDir    = fso.GetParentFolderName(logsDir)
methodDir = sysDir & "\penaltiesfetchingmethod"

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = methodDir
WshShell.Run "python.exe """ & methodDir & "\penalties_auto.py""", 0, False
Set WshShell = Nothing