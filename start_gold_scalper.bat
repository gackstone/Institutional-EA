@echo off
setlocal enabledelayedexpansion
title Dedicated Gold Scalper Engine — MT5
cd /d "%~dp0"

echo =======================================================================
echo   GOLD SCALPER ENGINE — HIGH-FREQUENCY MT5 XAUUSD SCALPING SYSTEM
echo =======================================================================
echo.

:: 1. Initialize Python Environment
if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: 2. Launch Gold Scalper Engine
echo Launching Gold Scalper Engine...
%PYTHON_EXE% scripts\start_gold_scalper.py %*

if %ERRORLEVEL% neq 0 (
    echo [ERROR] Gold Scalper Engine exited with code %ERRORLEVEL%.
    pause
    exit /b %ERRORLEVEL%
)

endlocal
