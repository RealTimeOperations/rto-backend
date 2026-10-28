@echo off
chcp 65001 >nul 2>&1
title Distance Report Auto Sync - START
setlocal

set "LOGS_DIR=%~dp0"
set "METHOD_DIR=%LOGS_DIR%..\vehiclefetchingmethod"
set "SCRIPT=%METHOD_DIR%\distancereport_auto.py"
set "PID_FILE=%LOGS_DIR%distancereport.pid"
set "FLAG=%LOGS_DIR%distancereport.stopped"
set "LOG_FILE=%LOGS_DIR%distancereport_auto.log"

set "PYTHONW="
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PYTHONW set "PYTHONW=%%P"
if not defined PYTHONW set "PYTHONW=pythonw.exe"

echo ============================================================
echo  DISTANCE REPORT AUTO SYNC - STARTING
echo ============================================================

powershell -NoProfile -Command "if (Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*distancereport_auto.py*' }) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo  Already running - no action needed.
    goto :end
)

if not exist "%SCRIPT%" (
    echo  ERROR: script not found: %SCRIPT%
    goto :end
)

if exist "%FLAG%" del "%FLAG%" >nul 2>&1

for /f "tokens=1-6 delims=/-: " %%a in ('%SystemRoot%\System32\wbem\wmic.exe OS Get localdatetime ^| find "."') do set "dt=%%a"
echo [%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%:%dt:~12,2%] PROCESS STARTING - started from batch file>> "%LOG_FILE%"

echo  Python: %PYTHONW%
powershell -NoProfile -Command "Start-Process -FilePath '%PYTHONW%' -ArgumentList '%SCRIPT%' -WorkingDirectory '%METHOD_DIR%' -WindowStyle Hidden"

set /a N=0
:wait
if exist "%PID_FILE%" goto :started
if %N% GEQ 10 goto :warn
ping -n 2 127.0.0.1 >nul
set /a N+=1
goto :wait

:started
set /p NEWPID=<"%PID_FILE%"
echo  SUCCESS - running (PID: %NEWPID%)
goto :end

:warn
echo  Started - PID file pending, log check karein.

:end
echo ============================================================
endlocal
exit /b 0