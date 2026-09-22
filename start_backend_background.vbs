' Backend (main.py) background mein — hidden window + log file (crash dikhe ga)
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.Run "cmd /c python main.py > backend_server.log 2>&1", 0, False
Set WshShell = Nothing
Set fso = Nothing