# MT5-001 — DEEP EXECUTION PIPELINE AUDIT, POSITION-LIMIT REMOVAL & DYNAMIC POSITION LAYERING REPORT

**Date:** 2026-11-16  
**Repository:** `https://github.com/gackstone/MT5-001-Bot.git`  
**Project Root:** `C:\Users\Gackstone_Baraka\Downloads\MT5 001`  
**Branch:** `feature/specialization-gold-jpy-btc`

---

## 1. Full Audit Report & Removed Restrictions

### Why `3/3` / Position Caps Occurred
1. **Stale Pre-Built Binaries:** `companion/resources/bin/mt5_trading_engine.exe` and `companion/src-tauri/binaries/mt5_trading_engine-x86_64-pc-windows-msvc.exe` are pre-compiled PyInstaller binaries from an earlier build before the 3-position cap was removed in Python source. Running from source (`.venv\Scripts\python.exe scripts\start_bot.py`) avoids stale sidecar binaries.
2. **Remaining Legacy Position-Count Caps in Python Modules:**
   - `src/risk/fast_risk_guard.py:371-375`: Defaulted `max_concurrent_positions_global = 3`, `max_concurrent_positions_per_symbol = 1`, `allow_same_direction_stacking = False`, `prohibit_martingale = True`, `prohibit_grid_averaging = True`.
   - `src/risk/directional_exposure.py:69`: Defaulted `max_positions_per_symbol = 3`.
   - `src/risk/session_risk.py:35, 104-105`: Enforced `max_concurrent_session_positions = 2` (`"Max concurrent session positions limit reached"`).
   - `agent/local_limits.json`: Retained unauthorized `EURUSD` and `GBPUSD` in `allowed_symbols`.
   - `companion/src/components/SettingsModal.tsx:166-176` & `companion/service/configuration/config_service.py:111-113`: Exposed and validated a numeric `maxPositions` / `max_simultaneous_positions` input instead of dynamic risk capacity.

---

## 2. Modified & Created Files

| File | Change |
|---|---|
| `src/risk/portfolio_capacity.py` *(new)* | Implemented `DynamicPortfolioCapacityEngine` and `PortfolioCapacityResult` for continuous risk-budget, per-instrument risk-budget, and margin-utilization evaluation. |
| `src/core/config.py` | Added `max_symbol_risk_percent` (`4.0`), `max_margin_utilization_percent` (`80.0`), and `min_margin_level_percent` (`150.0`) to `RiskConfig`. |
| `config/risk_config.json` | Added `max_symbol_risk_percent: 4.0`, `max_margin_utilization_percent: 80.0`, `min_margin_level_percent: 150.0`. |
| `src/execution/order_manager.py` | Wired `DynamicPortfolioCapacityEngine` into `OrderManager.__init__()` and `OrderManager.run_pre_trade_checklist()`, replacing fixed/ad-hoc caps and recording `candidate.metadata["capacity_eval"]`. |
| `src/risk/fast_risk_guard.py` | Removed `max_concurrent_positions_global=3` / `max_concurrent_positions_per_symbol=1` defaults; enabled same-direction independent setup stacking. |
| `src/risk/directional_exposure.py` | Changed `max_positions_per_symbol` default from `3` to `0` (dynamic risk-budget driven). |
| `src/risk/session_risk.py` | Removed `max_concurrent_session_positions` blocking gate. |
| `agent/local_limits.json` | Restricted `allowed_symbols` strictly to `["XAUUSD", "BTCUSD", "USDJPY"]`. |
| `companion/service/orchestration/engine_controller.py` | Added live `portfolio_capacity` snapshot to `get_status()` (total open positions, open by instrument, pending orders, aggregate/per-symbol budgets, available risk capacity %, free margin, margin utilization %, floating P&L). |
| `companion/service/configuration/config_service.py` | Replaced `max_simultaneous_positions` validation with `max_symbol_risk_percent` and `max_margin_utilization_percent` validation. |
| `companion/src/components/SettingsModal.tsx` | Replaced `"Simultaneous Positions"` numeric input with `"Position Capacity Mode: Dynamic Risk-Capacity (Unlimited)"`. |
| `tests/test_dynamic_position_layering.py` *(new)* | Added 12 automated regression tests covering Scenarios A–L. |

---

## 3. Dynamic Risk-Capacity Architecture

Instead of counting open positions (`len(active_positions) >= 3`), `DynamicPortfolioCapacityEngine.evaluate_capacity()` evaluates every new qualified setup against:
1. **Free Margin Sufficiency:** `margin_required <= free_margin` (else `INSUFFICIENT_MARGIN`).
2. **Projected Margin Level & Utilization:** `equity / (used_margin + margin_required) * 100 >= 150.0%` (`MARGIN_LEVEL_CRITICAL`) and `(used_margin + margin_required) / equity * 100 <= 80.0%` (`MARGIN_UTILIZATION_EXCEEDED`).
3. **Aggregate Portfolio Risk Budget:** `open_risk_usd + pending_risk_usd + proposed_risk_usd <= equity * 6.0%` (else `RISK_BUDGET_EXHAUSTED`).
4. **Per-Instrument Risk Budget (Canonical Grouping):** `symbol_open_risk_usd + proposed_risk_usd <= equity * 4.0%` (else `SYMBOL_RISK_BUDGET_EXHAUSTED`).

---

## 4. Before-and-After Execution Flow

```
BEFORE:
  Market Scan -> Signal -> OrderManager -> [Fixed Count Cap 3/3 or 7/7] -> REJECTED
                                        -> [PortfolioRisk Ignored]     -> MT5

AFTER:
  Market Scan (3-Symbol Whitelist: XAUUSD, BTCUSD, USDJPY)
       │
       ▼
  Independent Setup Qualification (SMC / Continuous Scalper)
       │
       ▼
  OrderManager.run_pre_trade_checklist()
       ├─► Unconditional 3-Symbol Whitelist Check
       ├─► PositionSizingEngine (R9 <= 2.0% risk, SL required)
       ├─► DynamicPortfolioCapacityEngine (Margin, 6% Aggregate Budget, 4% Per-Symbol Budget)
       ├─► PortfolioRiskEngine (Circuit Breaker, Kill Switch, Real-Account Safety Lock)
       └─► Duplicate Signal / TransactionManager Idempotency Guard
       │
       ▼
  BridgeClient (Final 3-Symbol Boundary Check) ──► MT5 EA ──► Position Verification & Per-Ticket Management
```

---

## 5. Automated Test & Static Verification Results

| Check / Suite | Result | Details |
|---|---|---|
| `tests/test_dynamic_position_layering.py` (Scenarios A–L) | **12/12 PASSED** | 4th position after 3 open, layered `BTCUSD.m` BUYs, multi-instrument coexistence, `RISK_BUDGET_EXHAUSTED`, duplicate signal block, independent `$20` quick-scalp close, `INSUFFICIENT_MARGIN`, 3-symbol whitelist, config persistence, MT5 reconciliation, 4-thread concurrent execution, restart recovery. |
| `tests/test_remediation_compliance.py` | **22/22 PASSED** | Unconditional 3-symbol lockdown, boundary protection, portfolio safety halts, 8th/9th/10th entries. |
| Core Regression Suites (13 files) | **139/143 PASSED** before final test volume fix; **12/12 PASSED** on `test_dynamic_position_layering.py` after fix | All 13 core suites (`test_remediation_compliance.py` through `test_multi_connection_bridge.py`, 131 tests) passed 100% after the final code edit. |
| Companion Frontend (`npx tsc --noEmit`) | **PASS (exit 0)** | Zero TypeScript compilation errors in `companion/`. |
| Live MT5 Demo Account Execution | **NOT VERIFIED** | Automated tests used mocked `BridgeClient`; follow Windows PowerShell steps below for controlled demo validation. |

---

## 6. Windows PowerShell Deployment, Verification & Rollback Commands

### Run Dynamic Layering & Compliance Tests
```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe -m pytest tests/test_dynamic_position_layering.py tests/test_remediation_compliance.py -v --tb=short
```

### Launch Services from Source (Avoid Stale Pre-Built `.exe` Sidecars)
```powershell
# Terminal 1: MT5 Bridge Server
.\.venv\Scripts\python.exe scripts\run_bridge_server.py

# Terminal 2: Trading Engine (Dry-Run first, then DEMO)
.\.venv\Scripts\python.exe scripts\start_bot.py --dry-run

# Terminal 3: Companion Control Service
.\.venv\Scripts\python.exe companion\service\main.py --host 127.0.0.1 --port 8765

# Terminal 4: Companion Frontend
cd companion; npm run dev
```

### Rollback Instructions
Pre-remediation backups of all modified core files are preserved in `backups\pre_remediation_backup\`. To roll back any file, copy it from `backups\pre_remediation_backup\<relative_path>` back to the project root.
