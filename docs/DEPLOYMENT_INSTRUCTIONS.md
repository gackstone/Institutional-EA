# Deployment Instructions & Operational Risk Guide (Consolidated Modern Architecture)

## 1. Safety & Execution Mode Policy

> [!IMPORTANT]
> The system defaults to **`execution_mode: "DEMO"`** with **`"LIVE_TRADING_ENABLED": false`** and **`"LEGACY_FILTERS_ENABLED": false`** in `config/settings.json`.
> - **Live trading is blocked by default**: `PortfolioRiskEngine` and `scripts/promotion_check.py` refuse to trade a `REAL` account while `LIVE_TRADING_ENABLED` is `false`.
> - **Strategy-based entry filters are disabled by default** (`LEGACY_FILTERS_ENABLED=false`), while **all account-level risk and broker execution safety controls remain strictly active at all times**.

---

## 2. Unified Modern Architecture & Pipeline Flow

- **Application Entry Point**: `scripts/start_bot.py`
- **Process Supervisor**: `scripts/supervisor.py` / `scripts/start_supervisor.bat`
- **Bridge Server**: `scripts/run_bridge_server.py` + `mql5/Experts/PythonBridgeEA.mq5`
- **Authoritative Configuration**: `config/settings.json`, `config/strategy_config.json`, `config/account_profiles.json`, `config/risk_config.json`
- **Unfiltered Signal-to-Risk Execution Pipeline**:
  `Market Data → Strategy Signal Generation → Risk Validation → Broker Execution Validation → Order Submission → Broker Confirmation → Position Management`

---

## 3. Pre-Launch Operator Checklist (`STOP.flag` & MT5 Terminal)

1. **MetaTrader 5 Terminal**:
   - Installed at `C:\Program Files\MetaTrader 5\terminal64.exe` (MetaEditor at `C:\Program Files\MetaTrader 5\metaeditor64.exe`).
   - Logged into DEMO account (`JustMarkets-Demo3`, `TRADE_MODE_DEMO`).
   - Ensure `XAUUSD.m` and `BTCUSD.m` (and any additional configured symbols) are visible in **Market Watch** and **Algo Trading** is enabled.
2. **Manual Kill Switch (`STOP.flag`)**:
   - If `STOP.flag` exists in the repository root, `PortfolioRiskEngine` latches the manual kill switch and blocks new trade entries until `STOP.flag` is removed and the kill switch is cleared.
   - To clear `STOP.flag` when ready for DEMO trading:
     ```powershell
     Remove-Item "c:\Users\Gackstone_Baraka\Downloads\MT5 001\STOP.flag" -Force -ErrorAction SilentlyContinue
     ```
   - To re-engage the emergency kill switch at any time:
     ```powershell
     New-Item -Path "c:\Users\Gackstone_Baraka\Downloads\MT5 001\STOP.flag" -ItemType File -Force
     ```

---

## 4. Compiling & Deploying the MQL5 Expert Advisor

1. Compile `mql5/Experts/PythonBridgeEA.mq5` using MetaEditor:
   ```powershell
   & "C:\Program Files\MetaTrader 5\metaeditor64.exe" /compile:"c:\Users\Gackstone_Baraka\Downloads\MT5 001\mql5\Experts\PythonBridgeEA.mq5" /log:"c:\Users\Gackstone_Baraka\Downloads\MT5 001\compile.log"
   ```
2. Verify `0 errors, 0 warnings` in `compile.log`.
3. Attach `PythonBridgeEA` to a single chart in MetaTrader 5 (e.g., `XAUUSD.m` M15).

---

## 5. Running Automated Verification & Promotion Gate Audit

1. **Run the full automated regression suite**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -q
   ```
2. **Run the Bridge Server Preflight Check**:
   ```powershell
   .\.venv\Scripts\python.exe scripts\run_bridge_server.py --check-only
   ```
3. **Run the Promotion Gate Evaluator**:
   ```powershell
   .\.venv\Scripts\python.exe scripts\promotion_check.py
   ```

---

## 6. Verified Launch Commands (DEMO Mode)

### Option A: Supervised Launch (Bridge Server + Trading Bot with Auto-Restart & Heartbeat)
```powershell
scripts\start_supervisor.bat --visible
```

### Option B: Standalone Bot Dry-Run / Simulation Mode
```powershell
.\.venv\Scripts\python.exe scripts\start_bot.py --dry-run
```

### Option C: Direct DEMO Execution (Bridge Server + Bot)
```powershell
# Terminal 1: Start TCP/ZeroMQ Bridge Server
.\.venv\Scripts\python.exe scripts\run_bridge_server.py

# Terminal 2: Start Modern Trading Bot in DEMO mode
.\.venv\Scripts\python.exe scripts\start_bot.py
```
