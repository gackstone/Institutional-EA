@echo off
setlocal
title Arcade Fx - MT5 Bot & Bridge Supervisor
cd /d "%~dp0\.."

echo =========================================================================
echo   ARCADE FX — AUTONOMOUS MT5 BOT & BRIDGE SUPERVISOR
echo =========================================================================
echo.

where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    set "PY_CMD=pythonw"
) else (
    set "PY_CMD=python"
)

REM If user passed --visible or --debug, use python with console
if "%1"=="--visible" (
    python scripts\supervisor.py --visible
    goto :end
)
if "%1"=="--debug" (
    python scripts\supervisor.py --visible
    goto :end
)

echo Starting Arcade Fx Supervisor in background mode (zero console popups)...
echo Streaming logs to logs\supervisor.log, logs\bridge.log, logs\bot.log.
echo To run in interactive debug mode with visible console: scripts\start_supervisor.bat --visible
echo.

start "" %PY_CMD% scripts\supervisor.py

:end
if %ERRORLEVEL% neq 0 (
    echo.
    echo Supervisor exited with code %ERRORLEVEL%.
    pause
)
