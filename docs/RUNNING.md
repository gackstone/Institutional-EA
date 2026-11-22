# Running Institutional EA Companion

## 1. Installed Windows App (Recommended)
1. Install using `companion\release\Institutional-EA-Companion-Setup-<version>.exe`.
2. Open **Institutional EA Companion** from the Start Menu or Desktop shortcut.
3. On startup, the app automatically:
   - Launches the bundled standalone `mt5_control_service.exe` on `127.0.0.1:8765` (or an automatic free fallback port `8766–8785` if `8765` is busy).
   - Stores SQLite state, auth token, and rotating logs in `%LOCALAPPDATA%\InstitutionalEA\Institutional EA Companion\`.
   - Auto-connects to your running **MetaTrader 5 DEMO** terminal and begins syncing account metrics, symbols (`XAUUSD.m`, `USDJPY.m`, `BTCUSD.m`), and live OHLC candles.
4. No project folder, Python installation, or `.venv` is required for the installed app.

## 2. Development Mode
From the repository root (`C:\Users\Gackstone_Baraka\Downloads\Institutional EA`):
```powershell
cd companion
npm install
npm run build
npm run dev
```
Electron automatically launches the Control Service via `.venv\Scripts\python.exe -m companion.service.main` with `--project-root` and `--data-dir`.

## 3. Running the Control Service Standalone (Debugging)
```powershell
.\.venv\Scripts\python.exe -m companion.service.main `
  --host 127.0.0.1 `
  --port 8765 `
  --project-root "C:\Users\Gackstone_Baraka\Downloads\Institutional EA" `
  --data-dir "$env:LOCALAPPDATA\InstitutionalEA\Institutional EA Companion"
```
Verify readiness:
```powershell
Invoke-WebRequest http://127.0.0.1:8765/health -UseBasicParsing
```

## 4. Rebuilding Sidecars & Windows Installer
```powershell
# 1. Rebuild standalone mt5_control_service.exe sidecar
.\.venv\Scripts\python.exe companion\packaging\build_sidecars.py

# 2. Build frontend & Windows NSIS installer
cd companion
npm run build
npm run dist:win
```

## 5. Safety Lock
- The Companion and Control Service enforce **DEMO-only** execution (`execution_mode=DEMO`, `LIVE_TRADING_ENABLED=false`).
- `Deploy EA` programmatically verifies the connected MT5 account is `DEMO` before copying or compiling any files, and always creates a timestamped backup in `<MT5 Data Folder>\MQL5\Backups\`.
