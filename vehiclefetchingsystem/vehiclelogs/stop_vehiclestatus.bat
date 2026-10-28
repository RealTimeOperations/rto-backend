@echo off
chcp 65001 >nul 2>&1
title Vehicle Status Auto Sync - STOP
setlocal enabledelayedexpansion

set "LOGS_DIR=%~dp0"
set "PID_FILE=%LOGS_DIR%vehiclestatus.pid"
set "FLAG=%LOGS_DIR%vehiclestatus.stopped"
set "LOG_FILE=%LOGS_DIR%vehiclestatus_auto.log"

for /f "tokens=1-6 delims=/-: " %%a in ('%SystemRoot%\System32\wbem\wmic.exe OS Get localdatetime ^| find "."') do set "dt=%%a"
set "TS=%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%:%dt:~12,2%"

echo ============================================================
echo  VEHICLE STATUS AUTO SYNC - STOPPING
echo ============================================================

:: ✅ 1) FORAN log mein likho (instant visibility)
echo [%TS%] PROCESS STOPPING - stop requested from batch file>> "%LOG_FILE%"

:: ✅ 2) Stopped flag write karo (Python ~1s mein graceful exit kare ga)
echo stopped> "%FLAG%"

:: ✅ 3) Graceful wait: max 6s tak PID file gayab hone ka intezar
set /a N=0
:waitexit
if not exist "%PID_FILE%" goto :cleaned
if %N% GEQ 6 goto :forcekill
ping -n 2 127.0.0.1 >nul
set /a N+=1
goto :waitexit

:: ✅ 4) Force-kill fallback (agar graceful exit na ho)
:forcekill
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*vehiclestatus_auto.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    taskkill /PID !PID! /F /T >nul 2>&1
)

:cleaned
if exist "%PID_FILE%" del "%PID_FILE%" >nul 2>&1

for /f "tokens=1-6 delims=/-: " %%a in ('%SystemRoot%\System32\wbem\wmic.exe OS Get localdatetime ^| find "."') do set "dt2=%%a"
set "TS2=%dt2:~0,4%-%dt2:~4,2%-%dt2:~6,2% %dt2:~8,2%:%dt2:~10,2%:%dt2:~12,2%"
echo [%TS2%] PROCESS STOPPED - process terminated (batch file)>> "%LOG_FILE%"

echo  Stopped successfully.
echo ============================================================
endlocal
exit /b 0