' ============================================================
'  RTO Background Launcher (attendancelogs folder version)
'  - Runs python.exe with a HIDDEN console (invisible)
' ============================================================
Option Explicit

Dim sh, fso, logsDir, sysDir, rootDir, pythonExe, out, pr, procs, wmi
Dim autoScript, mainScript

Set sh  = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

logsDir = fso.GetParentFolderName(WScript.ScriptFullName)   ' .../attendancelogs
sysDir  = fso.GetParentFolderName(logsDir)                  ' .../attendancefetchingsystem
rootDir = fso.GetParentFolderName(sysDir)                   ' .../backend

autoScript = sysDir & "\attendancefetchingmethod\auto_attendance.py"
mainScript = rootDir & "\main.py"

' IMPORTANT: run everything from the root backend folder
sh.CurrentDirectory = rootDir

Sub L(msg)
    Dim f
    Set f = fso.OpenTextFile(logsDir & "\vbs_debug.log", 8, True)
    f.WriteLine Now & "  " & msg
    f.Close
End Sub

L "VBS START - root=" & rootDir

' ---- Find python.exe by scanning PATH (in-process, no console window)
Function FindPython()
    Dim pathEnv, parts, p, cand
    pathEnv = sh.Environment("PROCESS")("PATH")
    parts = Split(pathEnv, ";")
    For Each p In parts
        If Len(p) > 0 Then
            cand = p
            If Right(cand, 1) <> "\" Then cand = cand & "\"
            If fso.FileExists(cand & "python.exe") Then
                FindPython = cand & "python.exe"
                Exit Function
            End If
        End If
    Next
    FindPython = ""
End Function

pythonExe = FindPython()
If pythonExe = "" Then
    L "ERROR: python.exe NOT FOUND in PATH"
    MsgBox "python.exe PATH mein nahi mila!", vbCritical, "RTO"
    WScript.Quit 1
End If
L "python=" & pythonExe

' ---- Check only RTO's own running processes via WMI (in-process)
out = ""
Set wmi = GetObject("winmgmts:\\.\root\cimv2")
Set procs = wmi.ExecQuery("Select CommandLine From Win32_Process Where Name='python.exe' Or Name='pythonw.exe'")
For Each pr In procs
    out = out & pr.CommandLine & vbCrLf
Next
L "running python: " & Replace(out, vbCrLf, " | ")

If InStr(1, out, autoScript, vbTextCompare) > 0 Then
    L "SKIP auto_attendance.py (already running)"
Else
    sh.Run """" & pythonExe & """ """ & autoScript & """", 0, False
    L "LAUNCHED auto_attendance.py (hidden console)"
End If

If InStr(1, out, mainScript, vbTextCompare) > 0 Then
    L "SKIP main.py (already running)"
Else
    sh.Run """" & pythonExe & """ """ & mainScript & """", 0, False
    L "LAUNCHED main.py (hidden console)"
End If

L "VBS DONE"
WScript.Quit 0