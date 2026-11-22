# Deployment Instructions & Operational Risk Guide (v3.0.0)

## 1. Safety & Execution Mode Policy

> [!IMPORTANT]
> The system defaults to **`DEMO_MODE: true`** (`execution_mode: DEMO`) with `allow_real_trading: false` and `require_live_confirmation: true` in `config/scalper.yaml`. **Live trading is blocked by default and requires explicit manual operator approval** (`--confirm-live` CLI flag plus `allow_real_trading: true` in `config/scalper.yaml`) only after out-of-sample backtesting, stress testing, and multi-session MT5 Demo validation have been reviewed.

---

## 2. Prerequisites & Environment Setup

1. **MetaTrader 5 Terminal**:
   - Installed at `C:\Program Files\MetaTrader 5\terminal64.exe` (MetaEditor at `C:\Program Files\MetaTrader 5\metaeditor64.exe`).
   - Logged into Demo account (`JustMarkets-Demo3`, Login `1200057798`, `TRADE_MODE_DEMO`).
   - Ensure `XAUUSD.m` and `BTCUSD.m` are visible in the **Market Watch** window and **Algo Trading** is enabled.
2. **Python Virtual Environment**:
   ```powershell
   cd "c:\Users\Gackstone_Baraka\Downloads\MT5 001"
   .\.venv\Scripts\python.exe --version
   ```

---

## 3. Compiling & Deploying the MQL5 Expert Advisor

1. Compile `mql5/Experts/PythonBridgeEA.mq5` using MetaEditor:
   ```powershell
   & "C:\Program Files\MetaTrader 5\metaeditor64.exe" /compile:"c:\Users\Gackstone_Baraka\Downloads\MT5 001\mql5\Experts\PythonBridgeEA.mq5" /log:"c:\Users\Gackstone_Baraka\Downloads\MT5 001\compile.log"
   ```
2. Verify `0 errors, 0 warnings` in `compile.log`.
3. Copy both `.mq5` and `.ex5` to the active MT5 Terminal `MQL5\Experts\` folder and attach `PythonBridgeEA` to an `XAUUSD.m` (M1) chart.

---

## 4. Running Automated Verification & Reports

1. **Run the 109-test automated suite**:
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests\test_gold_scalper.py tests\test_btc_scalper.py tests\test_market_scheduler.py tests\test_manual_management.py tests\test_master_scalping_upgrade.py -v
   ```
2. **Regenerate all 5 verification & benchmark reports**:
   ```powershell
   .\.venv\Scripts\python.exe scripts\generate_master_reports.py
   ```
   Output files in `reports/`:
   - `reports/realistic_backtest_report.json`
   - `reports/stress_test_report.json`
   - `reports/execution_latency_report.json`
   - `reports/risk_validation_report.json`
   - `reports/demo_execution_report.json`

---

## 5. Starting the Dual-Market Scalping Engine (DEMO Mode)

```powershell
# Run in DEMO mode (enforces TRADE_MODE_DEMO check on connected MT5 account)
.\.venv\Scripts\python.exe scripts\run_gold_scalper.py --config config\scalper.yaml
```

### Emergency Kill Switch
To immediately close all active scalper baskets and halt trading at any time:
```powershell
New-Item -Path "c:\Users\Gackstone_Baraka\Downloads\MT5 001\STOP.flag" -ItemType File -Force
```

---

## 6. Unresolved Operational Risks & Live Readiness Notes

1. **Profitability Is Never Guaranteed**: Historical backtest and simulated stress test performance do not guarantee future live profitability. Real broker liquidity during tier-1 macroeconomic releases (NFP, FOMC, CPI) or weekend crypto exchange outages can cause slippage exceeding modeled assumptions.
2. **Minimum Account Equity for Risk-Budget Sizing**: Because `XAUUSD.m` has `contract_size = 100` (`0.01` lot = `1 oz`), a `300`-point (`$3.00`) stop loss plus spread/commission represents `~$3.35` risk per `0.01` lot. Under strict risk-budget sizing (`STANDARD = 0.25%`), accounts smaller than `$1,500` will have `min_lot = 0.01` rejected when `strict_min_lot_rejection` is active unless a tighter SL or `AGGRESSIVE_DEMO` profile is selected.
3. **Broker Weekend Maintenance Windows**: Even on 24/7 crypto brokers, `BTCUSD.m` may enter `SYMBOL_TRADE_MODE_CLOSEONLY` or `DISABLED` during scheduled Sunday server maintenance. The `MarketScheduler` detects this via `spec.trade_mode` and blocks new entries while continuing to monitor existing positions once quotes resume.
4. **Host / VPS Network Continuity**: If both the Python engine and the MT5 terminal lose internet connectivity simultaneously, only server-side stop-loss levels (`sl` sent with each `order_send`) protect open positions at the broker. Always keep `protective_sl.enforce_immediate_placement: true` enabled.
