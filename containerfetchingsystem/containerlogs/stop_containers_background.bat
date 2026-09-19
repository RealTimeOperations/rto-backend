@echo off
setlocal
rem BASE = .../containerfetchingsystem/containerlogs/ (yehi folder)
set "BASE=%~dp0"
set "PIDFILE=%BASE%containers.pid"
set "LOGFILE=%BASE%containers_auto.log"

if not exist "%PIDFILE%" (
    echo Containers server already stopped hai.
    goto :eof
)

set /p PID=<"%PIDFILE%"
taskkill /PID %PID% /F >nul 2>&1
del "%PIDFILE%" >nul 2>&1

echo [%date% %time%] PROCESS STOPPED - stopped by stop_containers_background.bat >> "%LOGFILE%"
curl -s -m 3 -X POST http://localhost:8000/containers/mark-stopped >nul 2>&1
echo Containers server stop ho gaya.
endlocal