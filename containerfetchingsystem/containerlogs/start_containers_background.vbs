' ============================================================
'  Containers Auto Fetch — Windows background process (hidden)
' ============================================================
Set fso = CreateObject("Scripting.FileSystemObject")
logsDir   = fso.GetParentFolderName(WScript.ScriptFullName)   ' .../containerlogs
sysDir    = fso.GetParentFolderName(logsDir)                  ' .../containerfetchingsystem
methodDir = sysDir & "\containerfetchingmethod"

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = methodDir
WshShell.Run "python.exe """ & methodDir & "\containers_auto.py""", 0, False
Set WshShell = Nothing