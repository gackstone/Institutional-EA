@echo off
setlocal enabledelayedexpansion
title Institutional MT5 Trading Bot & Institutional EA Agent
cd /d "%~dp0"

echo =======================================================================
echo   INSTITUTIONAL MT5 TRADING BOT & INSTITUTIONAL EA CLOUD AGENT LAUNCHER
echo =======================================================================
echo.

:: 1. Initialize environment
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: 2. Pre-flight Self-Check
echo [1/3] Running pre-flight diagnostic self-check...
%PYTHON_EXE% scripts\selfcheck.py
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Diagnostic self-check reported warnings or notices. Proceeding with caution...
)

:: 3. Launch Institutional EA MT5 Bot Agent
echo.
echo [2/3] Launching Institutional EA Cloud Bot Agent...
%PYTHON_EXE% agent\mt5_bot_agent.py %*

if %ERRORLEVEL% neq 0 (
    echo [ERROR] MT5 Bot Agent terminated with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

endlocal
