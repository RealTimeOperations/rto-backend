' Backend (main.py) + Ngrok Tunnel background mein — hidden window + log file
Set fso = CreateObject("Scripting.FileSystemObject")
Set WshShell = CreateObject("WScript.Shell")

' Backend folder set karein
WshShell.CurrentDirectory = fso.GetParentFolderName(WScript.ScriptFullName)

' 1. Backend Server Start (python main.py)
WshShell.Run "cmd /c python main.py > backend_server.log 2>&1", 0, False

' 2. 3 Second ka wait taake backend port 8000 par fully start ho jaye
WScript.Sleep 3000

' 3. Ngrok Tunnel Start (Hidden console mein)
' (Agar aapne ngrok kisi aur folder mein rakha hai to C:\ngrok\ngrok.exe ko update kar lein)
WshShell.Run "cmd /c C:\ngrok\ngrok.exe http --url=https://provable-pulp-leotard.ngrok-free.dev 8000", 0, False

Set WshShell = Nothing
Set fso = Nothing