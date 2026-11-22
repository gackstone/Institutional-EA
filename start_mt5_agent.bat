@echo off
setlocal enabledelayedexpansion
title ArcadeFx MT5 Bot Agent - Windows VPS Launcher
cd /d "%~dp0"

echo ========================================================
echo   ARCADEFx MT5 BOT AGENT - VPS AUTO-START LAUNCHER
echo ========================================================
echo   Outbound-Only Cloud Connection: https://arcadefx.live
echo   Zero Open Inbound Ports. Local Limits Enforced.
echo ========================================================
echo.

:: 1. Initialize environment (check Python in venv or system PATH)
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
    echo [ENV] Using virtual environment Python: .venv\Scripts\python.exe
) else (
    set "PYTHON_EXE=python"
    echo [ENV] Using system Python
)

:: Test Python availability
%PYTHON_EXE% --version >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python not found in PATH or virtual environment!
    echo Please install Python 3.10+ and make sure it is added to PATH.
    pause
    exit /b 1
)

:: 2. Launch the ArcadeFX MT5 Bot Agent with provided arguments
echo [STARTUP] Initializing ArcadeFX MT5 Bot Agent...
%PYTHON_EXE% agent\mt5_bot_agent.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [AGENT_EXIT] Agent exited with status code %ERRORLEVEL%.
    pause
)
endlocal
