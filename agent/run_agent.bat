@echo off
setlocal
title Institutional EA - MT5 Bot Agent Runner
cd /d "%~dp0\.."

echo ========================================================
echo   INSTITUTIONAL EA MT5 BOT AGENT (OUTBOUND-ONLY ENGINE)
echo ========================================================
echo   Zero-password architecture. Runs next to local MT5.
echo   Cloud commands are strictly bounded by local_limits.json.
echo ========================================================
echo.

python agent\mt5_bot_agent.py %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo Agent stopped with error code %ERRORLEVEL%.
    pause
)
