# Institutional EA Companion — Troubleshooting Guide

## 1. Where Logs Live
All runtime logs are stored in rotating files (5 MB max per file, secrets redacted) under:
```text
%LOCALAPPDATA%\InstitutionalEA\Institutional EA Companion\logs\
```
Key log files:
- `control_service.log` — Python Control Service HTTP API, MT5 auto-connect, and sync loop logs.
- `control_service_launcher.log` — Electron process spawn, `/health` readiness probes, exit codes, and auto-restart events.
- `engine_lifecycle.log` — Trading engine and bridge supervisor events.

## 2. `Service offline. Retrying...` (Top Bar `SVC OFFLINE`)
- **What happens**: Electron automatically retries starting the Control Service up to 5 times with exponential backoff.
- **Manual recovery**: Click the **Reconnect** button directly inside the `SVC` pill in the top bar.
- **Check port conflicts**: Run `netstat -ano | findstr 8765`. If another application holds `8765`, Electron automatically selects the next free localhost port (`8766–8785`).
- **Safety note**: If the Control Service is offline, `Pause`, `Stop`, and `Close All` will fail honestly (never faking success). Manage any open positions directly inside MetaTrader 5.

## 3. `MT5 Not Connected` or `Waiting for MT5 Candles`
- Open **MT5 Terminal** in the sidebar and click **Scan**, then **Sync MT5**.
- Ensure `terminal64.exe` is running and logged into a **DEMO** account.
- Open **System Health** and click **Re-run Self-Check** to see exact Pass/Warn/Fail status for MT5 connection, DEMO lock, required symbols (`XAUUSD.m`, `USDJPY.m`, `BTCUSD.m`), ZMQ 5555/5556, EA asset, and last candle times.
- On weekends, `XAUUSD.m` and `USDJPY.m` show **Market Closed** (broker market closed) while `BTCUSD.m` remains **LIVE**.

## 4. `Deploy EA` Issues
- **Refused (not DEMO)**: Switch your MT5 terminal to a DEMO account and click **Sync MT5** first.
- **Compile error**: Check the compile log tail shown in the Deployment Report or `<MT5 Data Folder>\MQL5\Experts\PythonBridgeEA_compile.log`. Any failure automatically rolls back overwritten files from `<MT5 Data Folder>\MQL5\Backups\ea_deploy_<timestamp>\`.
- **Attaching EA to a chart**: MT5 does not provide an external IPC API to attach an EA to a running chart without restarting the terminal. After `Deploy EA` succeeds, open MT5 Navigator -> **Expert Advisors** -> right-click **Refresh** -> drag **PythonBridgeEA** onto a chart, and ensure **Algo Trading** is enabled in the MT5 toolbar.
