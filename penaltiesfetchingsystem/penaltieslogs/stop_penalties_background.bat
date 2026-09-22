@echo off
setlocal
set "BASE=%~dp0"
set "PIDFILE=%BASE%penalties.pid"
set "LOGFILE=%BASE%penalties_auto.log"

if not exist "%PIDFILE%" (
    echo Penalties server already stopped hai.
    goto :eof
)

set /p PID=<"%PIDFILE%"
taskkill /PID %PID% /F >nul 2>&1
del "%PIDFILE%" >nul 2>&1

echo [%date% %time%] PROCESS STOPPED - stopped by stop_penalties_background.bat >> "%LOGFILE%"
curl -s -m 3 -X POST http://localhost:8000/penalties/mark-stopped >nul 2>&1
echo Penalties server stop ho gaya.
endlocal