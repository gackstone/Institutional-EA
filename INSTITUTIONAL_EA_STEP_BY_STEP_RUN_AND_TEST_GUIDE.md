# Institutional EA — STEP-BY-STEP WINDOWS RUN AND TEST GUIDE

This guide explains how to install, configure, launch, test, monitor, and safely stop the **Institutional EA** trading bot and Desktop Companion on **Windows**.

---

## 1. Initial Preparation & Prerequisites

### Required Software
- **Windows 10 / 11 (64-bit)**
- **Python 3.12+** (verified in `.venv` as Python `3.12.10`)
- **Node.js 20+** and **npm** (required only for the React/Electron/Vite Companion UI in `companion/`)
- **MetaTrader 5 (MT5) Terminal** (installed and logged into a **JustMarkets Demo** hedging account)
- **Git** (optional, for checking repository status)

### Verify Installations in PowerShell
```powershell
python --version
node --version
npm --version
git --version
```

---

## 2. Project Setup

1. Open **Windows PowerShell** and navigate to the project folder:
   ```powershell
   cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
   ```
2. Inspect Git status:
   ```powershell
   git status
   ```
3. Activate the existing Python virtual environment (or create one if missing):
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```
   *(If `.venv` does not exist, create it with `python -m venv .venv`, activate it, and run `pip install -r requirements.txt`.)*
4. Install/verify Python dependencies:
   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```
5. Configure environment variables:
   - Copy `.env.example` to `.env` if `.env` does not already exist:
     ```powershell
     if (-not (Test-Path .env)) { Copy-Item .env.example .env }
     ```
   - Ensure `.env` keeps `EXECUTION_MODE=DEMO` and `BRIDGE_HOST=127.0.0.1`, `BRIDGE_PORT=5555`.
   - **Never** set `LIVE_TRADING_ENABLED=true` during demo testing.
6. Verify `config\settings.json`:
   - Confirm `"execution_mode": "DEMO"`, `"LIVE_TRADING_ENABLED": false`, `"strict_three_symbol_universe": true`, and `"symbols": ["XAUUSD", "BTCUSD", "USDJPY"]`.
7. Run the pre-flight self-check:
   ```powershell
   .venv\Scripts\python.exe scripts\selfcheck.py
   ```

---

## 3. MetaTrader 5 Terminal Setup

1. Launch **MetaTrader 5** and log in to your **JustMarkets Demo** account.
2. Confirm the bottom-right connection indicator shows an active connection (green/blue bars).
3. Enable **Algo Trading** in the MT5 toolbar (button must be green).
4. In **Market Watch** (`Ctrl+M`), verify that the three authorized instruments (and/or their broker `.m` variants such as `XAUUSD.m`, `BTCUSD.m`, `USDJPY.m`) are visible and active.
5. Confirm account mode is **Hedging** (required for independent multi-position management; Netting accounts are automatically forced into observe/dry-run safety mode by the Companion).
6. Attach `PythonBridgeEA` (`mql5\Experts\PythonBridgeEA.ex5`) to an open chart in MT5:
   - Ensure **Allow Algo Trading** and **Allow WebRequest / DLL** permissions required by the EA are enabled in MT5 **Tools -> Options -> Expert Advisors**.
   - Verify the EA connects to `127.0.0.1:5555`.
7. Verify Python can read MT5 account info (without placing any trades):
   ```powershell
   .venv\Scripts\python.exe -c "import MetaTrader5 as mt5; print('init:', mt5.initialize()); info = mt5.account_info(); print('login:', getattr(info,'login',None), 'trade_mode:', getattr(info,'trade_mode',None), 'margin_mode:', getattr(info,'margin_mode',None)); mt5.shutdown()"
   ```
   *(Expected: `init: True`, `trade_mode: 0` (DEMO), `margin_mode: 2` (HEDGING).)*

---

## 4. Starting the Backend Services (Bridge, Engine, Companion Service)

Open separate PowerShell terminals inside `C:\Users\Gackstone_Baraka\Downloads\MT5 001`:

### Terminal 1 — MT5 Bridge Server (`127.0.0.1:5555`)
```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe scripts\run_bridge_server.py
```
*Wait until you see the bridge listening on `127.0.0.1:5555` and accepting the `PythonBridgeEA` connection.*

### Terminal 2 — Trading Engine (`scripts\start_bot.py`)
For **safe dry-run** (no orders sent to MT5):
```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe scripts\start_bot.py --dry-run
```
For **controlled DEMO execution** (only after all stages in Section 8 pass):
```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe scripts\start_bot.py
```
*(You can also launch via `.\start_mt5_bot.bat` which runs `scripts\selfcheck.py` followed by `agent\mt5_bot_agent.py`.)*

### Terminal 3 — Companion Control Service (`http://127.0.0.1:8765`)
```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe companion\service\main.py --host 127.0.0.1 --port 8765
```

### Safe Shutdown
- **Graceful Engine Stop:** Create `state\engine_stop.flag` or press `Ctrl+C` in the Trading Engine terminal.
  ```powershell
  New-Item -ItemType File -Force -Path "state\engine_stop.flag"
  ```
- **Emergency Kill Switch:** Create `STOP.flag` in the project root:
  ```powershell
  New-Item -ItemType File -Force -Path "STOP.flag"
  ```

---

## 5. Starting the Companion Frontend Application

In a fourth PowerShell terminal:
```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001\companion"
npm install
npm run dev
```
- **Web UI URL:** `http://localhost:5173` (configured in `companion\vite.config.ts`).
- **Desktop Electron Mode (optional):** `npm run electron:dev`.
- **Backend API:** Connects to `http://127.0.0.1:8765` (`companion\service\main.py`).

---

## 6. Initial Health Checks

Run these PowerShell checks before trading:

```powershell
# 1. Check Companion Control Service health
Invoke-RestMethod -Uri "http://127.0.0.1:8765/health"

# 2. Verify active 3-symbol configuration & strict lockdown
.\.venv\Scripts\python.exe -c "from src.core.config import AppConfig; c = AppConfig.load_from_dir('config'); print('mode:', c.execution_mode.value, 'strict_universe:', c.strict_three_symbol_universe, 'symbols:', c.symbols, 'live_enabled:', c.live_trading_enabled)"

# 3. Check engine heartbeat file
Get-Content state\engine_heartbeat.json -ErrorAction SilentlyContinue
```

---

## 7. Running Automated Tests

All commands below must be run from `C:\Users\Gackstone_Baraka\Downloads\MT5 001`:

1. **Compliance & Remediation Regression Suite (22 tests):**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_remediation_compliance.py -v --tb=short
   ```
   *Tests:* Unconditional 3-symbol lockdown, boundary enforcement at `OrderManager`/`BridgeClient`/`LiveMT5Broker`, portfolio safety halts, real-account lock, 8th/9th/10th entries, Companion config validation.

2. **Three-Instrument Universe & Schedule Tests (26 tests):**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_specialized_three_instrument_universe.py -v --tb=short
   ```

3. **Unrestricted Positions & Spread Diagnostics (8 tests):**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_unrestricted_positions_and_spread.py -v --tb=short
   ```

4. **SMC Rulebook Golden Tests (10 tests):**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_smc_rulebook_golden.py -v --tb=short
   ```

5. **Portfolio Risk, Hedging, Dual-Mode Profit Management & Companion:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/test_risk_management.py tests/test_prop_firm_rules.py tests/test_account_mode_hedging.py tests/test_dual_mode_profit_management.py tests/test_companion_control_service.py tests/test_mt5_bot_agent.py tests/test_engine_lifecycle_fixes.py tests/test_execution_analytics.py tests/test_multi_connection_bridge.py -v --tb=short
   ```

*Expected output:* `0 failed` across all 130 tests in the suites above. If any test fails, check the traceback and verify `.venv` packages and `config/*.json` integrity before proceeding.

---

## 8. Staged Demo-Testing Procedure

1. **Stage 1 — Clean Startup:** Run `scripts\selfcheck.py` and verify 0 critical errors.
2. **Stage 2 — Universe Check:** Confirm `AppConfig.load_from_dir('config').symbols` lists only `['XAUUSD', 'BTCUSD', 'USDJPY']`.
3. **Stage 3 — Rejection Proof:** Run `pytest tests/test_remediation_compliance.py -k "unauthorized"` and confirm all unauthorized symbols are blocked.
4. **Stage 4 — MT5 Sync:** Start `run_bridge_server.py` and confirm MT5 account balance, equity, and `HEDGING` mode sync.
5. **Stage 5–9 — Dry-Run Pipeline:** Start `scripts\start_bot.py --dry-run --max-cycles 3` and inspect console logs for SMC detection, setup qualification, sizing, and simulated order execution without real/demo MT5 orders.
6. **Stage 10 — Controlled Demo Execution:** Only after Stages 1–9 pass and you explicitly authorize demo trading, run `scripts\start_bot.py` (without `--dry-run`) on your **JustMarkets Demo** account and monitor `logs\` and the Companion UI.

---

## 9. Troubleshooting

| Issue | Resolution |
|---|---|
| `ModuleNotFoundError: No module named 'src'` | Always run pytest via `.\.venv\Scripts\python.exe -m pytest ...` from the project root, not bare `pytest`. |
| `MT5 initialization failed` | Ensure the MetaTrader 5 terminal is open, logged in, and matches Python bitness (64-bit). |
| `Bridge not connected` / timeout on `5555` | Verify `scripts\run_bridge_server.py` is running and `PythonBridgeEA` is attached to an MT5 chart with Algo Trading enabled. |
| `Port 8765 or 5173 already in use` | Check existing processes with `Get-NetTCPConnection -LocalPort 8765,5173,5555` and stop stale Python/Node processes. |
| `ENGINE_DUPLICATE_START_BLOCKED` | Another `start_bot.py` instance holds the single-instance lock; stop it gracefully via `state\engine_stop.flag`. |
| `WEEKDAY_INACTIVE` on `BTCUSD` | Expected: `TradingScheduleManager` restricts `BTCUSD` to weekends unless `weekday_btc_fallback_enabled` is enabled. |
| `Netting account detected` | Companion forces `DRY-RUN` on Netting accounts; switch to a **Hedging** MT5 Demo account for independent multi-position management. |

---

## 10. Daily Operating Checklist

1. Confirm MT5 Terminal is open, connected to **JustMarkets Demo**, and **Algo Trading** is green.
2. Verify `STOP.flag` is not present unless an emergency halt is intended.
3. Start `scripts\run_bridge_server.py` (Terminal 1).
4. Start `companion\service\main.py --host 127.0.0.1 --port 8765` (Terminal 3) and `npm run dev` in `companion\` (Terminal 4).
5. Start `scripts\start_bot.py` (Terminal 2) and verify heartbeat, `DEMO` mode, `XAUUSD/BTCUSD/USDJPY` universe, and open positions in the Companion UI (`http://localhost:5173`).
6. At end of session, create `state\engine_stop.flag` (or press `Ctrl+C`) to shut down cleanly.
