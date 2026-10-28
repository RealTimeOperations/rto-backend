@echo off
chcp 65001 >nul 2>&1
title Stop All Vehicle Tracking

echo ============================================================
echo  STOPPING ALL VEHICLE TRACKING PROCESSES
echo ============================================================
echo.
echo [1/2] Vehicle Status...
call "%~dp0stop_vehiclestatus.bat"
echo.
echo [2/2] Distance Report...
call "%~dp0stop_distancereport.bat"
echo.
echo ============================================================
echo  DONE - both processes stopped.
echo ============================================================
timeout /t 3 >nul
exit /b 0