# Stop only RTO processes (python.exe or pythonw.exe running RTO scripts)
$logs = Split-Path -Parent $MyInvocation.MyCommand.Path    # .../attendancelogs
$sys  = Split-Path -Parent $logs                           # .../attendancefetchingsystem
$root = Split-Path -Parent $sys                            # .../backend
$auto = "$sys\attendancefetchingmethod\auto_attendance.py"

Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | Where-Object {
    $_.CommandLine -like "*$auto*" -or
    $_.CommandLine -like "*$root\main.py*" -or
    $_.CommandLine -like "*$root\auto_attendance.py*"
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force
    Write-Host "Stopped PID $($_.ProcessId)"
}

# Tell the frontend instantly (RED + STOP log line)
python "$logs\notify_stopped.py" "Manual stop (stop_background.bat)"
Write-Host "Done - only RTO processes stopped (other python processes safe)"