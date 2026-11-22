# MT5-001 — FINAL EXECUTION PIPELINE AUDIT REPORT

**Date:** 2026-11-16  
**Project Root:** `C:\Users\Gackstone_Baraka\Downloads\MT5 001`  
**Branch:** `feature/specialization-gold-jpy-btc`

---

## 1. End-to-End Execution Pipeline (Remediated)

1. **Market Scanner & Orchestrator (`src/core/orchestrator.py`):** Unconditionally validates `XAUUSD`, `BTCUSD`, `USDJPY` (and explicit `.m`/`.micro` mappings).
2. **Strategy Scan (`SmcStrategyEngine`, `ContinuousScalpingEngine`):** Closed-candle SMC structure, FVG, OB, liquidity sweeps, and M1/M5/M15 scalping without position-count or spread vetoes.
3. **Pre-Trade Validation (`OrderManager.run_pre_trade_checklist`):**
   - Unconditional 3-symbol whitelist check (`UNAUTHORIZED_SYMBOL`).
   - Bridge health & market session check (`DEMO`, `REAL`, `RETAIL`, `PROP`).
   - Stop-loss presence (`SL > 0`) & broker `stops_level` / `freeze_level` check.
   - Valid `bid`/`ask` quote check (`MARKET_DATA_UNAVAILABLE`).
   - Dynamic `PositionSizingEngine` (no static `0.5` lot cap, no `$500` balance cap; R9 `<= 2.0%` risk; broker `min_lot`/`max_lot`/`lot_step`).
   - `ExecutionCostEvaluator` economic-viability check (`EXECUTION_COST_REJECTED` only if net reward fails cost).
   - `DynamicPortfolioCapacityEngine` (6.0% aggregate risk budget, 4.0% per-symbol risk budget, >= 150% margin level, <= 80% margin utilization, including `_in_flight_risk_usd`).
   - `PortfolioRiskEngine.evaluate_new_order_permission()` (circuit breakers, kill switch, real-account safety lock).
   - Duplicate signal & TransactionManager idempotency check.
4. **Atomic Execution & Final Boundary (`OrderManager.execute_signal`, `LiveMT5Broker.send_order`, `BridgeClient.execute_trade`):**
   - Acquires `OrderManager._execution_lock`, reserves risk in `_in_flight_risk_usd`, and independently re-validates the 3-symbol whitelist at `BridgeClient` before socket/IPC send.
   - Polls MT5 positions/orders before reporting `FILLED` / `PARTIALLY_FILLED` / `ACCEPTED` / `UNCONFIRMED`.
5. **Independent Position Management (`TradeManagementEngine`, `Orchestrator.manage_active_positions`):**
   - Per-ticket state machine ($20 quick-scalp close, $20 floor lock + progressive ratchets, break-even, trailing stop, partial close) operating independently of market scanning.

---

## 2. Runtime Process & MT5 Reconciliation Findings

- **Stale Binaries Identified:** `mt5_trading_engine.exe` (PID `9524`), `mt5_bot_agent.exe` (PID `1616`), and `mt5_bridge_server.exe` (PIDs `2976`, `10832`) were running from `companion\release\win-unpacked\resources\bin\`, which caused the `US30.std` SELL (`2643437551`) and `3/3` cap.
- **MT5 Demo Account Verified (Read-Only):** `JustMarkets-Demo` (`2002270203`, `Equity: $1907.31`, `FreeMargin: $1901.42`) with 3 open positions (`2643265025 BTCUSD.m`, `2643265317 USDJPY.m`, `2643340826 US30.std`).
- **4th Candidate Pre-Check Verified:** With the 3 real positions, a 4th `XAUUSD.m` SELL setup passed `OrderManager.run_pre_trade_checklist()` (`remaining_risk_capacity_usd: $101.16`). Live order submission was not sent.

---

## 3. Verified Launch Procedure (Source Mode)

Stop any stale `companion\release\win-unpacked\resources\bin\*.exe` processes, then launch from updated Python source:

```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe scripts\run_bridge_server.py
.\.venv\Scripts\python.exe scripts\start_bot.py
.\.venv\Scripts\python.exe companion\service\main.py --host 127.0.0.1 --port 8765
```

---

## 4. Automated Test & Build Summary

- **49/49 PASSED** across `test_execution_analytics.py`, `test_position_sizing.py`, `test_dynamic_position_layering.py`, `test_remediation_compliance.py`, and `test_unrestricted_positions_and_spread.py` (8.32s).
- **Companion TypeScript (`npx tsc --noEmit`):** **PASSED** (exit code 0).
- **Final Status:** **READY FOR CONTROLLED DEMO TESTING** (launch from updated Python source; stop stale `win-unpacked` binaries first; review/manage existing `US30.std` ticket `2643437551` manually).
