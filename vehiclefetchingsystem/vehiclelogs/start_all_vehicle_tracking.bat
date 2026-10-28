@echo off
chcp 65001 >nul 2>&1
title Start All Vehicle Tracking

echo ============================================================
echo  STARTING ALL VEHICLE TRACKING PROCESSES
echo ============================================================
echo.
echo [1/2] Vehicle Status...
call "%~dp0start_vehiclestatus.bat"
echo.
echo [2/2] Distance Report...
call "%~dp0start_distancereport.bat"
echo.
echo ============================================================
echo  DONE - both processes handled.
echo  Stop karne ke liye: stop_all_vehicle_tracking.bat
echo ============================================================
timeout /t 4 >nul
exit /b 0