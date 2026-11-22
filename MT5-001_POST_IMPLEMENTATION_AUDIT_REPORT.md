# MT5-001 — POST-IMPLEMENTATION INDEPENDENT VERIFICATION & REMAINING POSITION-CAP AUDIT REPORT

**Date:** 2026-11-16  
**Project Root:** `C:\Users\Gackstone_Baraka\Downloads\MT5 001`  
**Branch:** `feature/specialization-gold-jpy-btc`

---

## 1. Repository-Wide Position-Cap Search & Verification

Static search across `src\**\*.py`, `agent\*.py`, `agent\*.json`, `companion\service\**\*.py`, `companion\src\**\*.ts`, `companion\src\**\*.tsx`, `config\*.json`, and `scripts\*.py`:

| Symbol / Key | Location | Status | Classification |
|---|---|---|---|
| `3/3` / `Maximum simultaneous positions` | All active source files | **0 matches** | Eliminated |
| `max_concurrent_positions_global` | `config/fast_mode.json:87` (`100`) | Inert config key; `src/risk/fast_risk_guard.py:371` removed fallback `3` | Eliminated from execution |
| `max_concurrent_positions_per_symbol` | `src/execution/active_mode.py:70` (`0`), `src/core/config.py:287` (`100`) | `0` = dynamic; `287` is inert config field | Eliminated from execution |
| `max_positions_per_symbol` | `src/risk/directional_exposure.py:69` (`0`), `src/core/instruments.py`, `config/instruments.json` (`100`) | `0` = dynamic risk-budget driven; `100` is inert schema field | Eliminated from execution |
| `max_concurrent_session_positions` | `src/risk/session_risk.py:35` | Enforcement gate removed at `session_risk.py:104` | Eliminated from execution |
| `max_simultaneous_positions` | `config/risk_config.json:14`, `src/core/config.py:179` (`100`), `companion/service/trading/btcusd_sample_service.py:64` (`1`) | Ignored by `OrderManager`/`DynamicPortfolioCapacityEngine`; `btcusd_sample_service.py` is an isolated sample-test service | Eliminated from main execution |

---

## 2. Modified & Created Files (Complete List)

- `src/risk/portfolio_capacity.py` *(new)*
- `src/execution/order_manager.py`
- `src/execution/bridge_client.py`
- `src/execution/active_mode.py`
- `src/execution/continuous_scalper.py`
- `src/adapters/live_mt5_broker.py`
- `src/core/config.py`
- `src/core/orchestrator.py`
- `src/core/symbol_universe.py`
- `src/core/broker_resolver.py`
- `src/core/market_data.py`
- `src/risk/fast_risk_guard.py`
- `src/risk/directional_exposure.py`
- `src/risk/session_risk.py`
- `src/monitoring/health_monitor.py`
- `config/settings.json`, `config/risk_config.json`, `config/fast_mode.json`, `config/symbols.json`, `config/instruments.json`
- `agent/mt5_bot_agent.py`, `agent/local_limits.json`
- `companion/service/configuration/config_service.py`, `companion/service/orchestration/engine_controller.py`
- `companion/src/types/index.ts`, `companion/src/services/ipc.ts`, `companion/src/components/SettingsModal.tsx`, `companion/src/components/screens/ExecutionRiskScreens.tsx`
- `tests/test_remediation_compliance.py` *(new)*, `tests/test_dynamic_position_layering.py` *(new)*

---

## 3. Before-and-After Code References for Removed Count Restrictions

1. **`src/execution/order_manager.py` (`run_pre_trade_checklist` & `execute_signal`):**
   - *Before:* Ad-hoc `8.0%` aggregate check, ignored `portfolio_risk.evaluate_new_order_permission()`, no execution lock around risk reservation.
   - *After:* Enforces `DynamicPortfolioCapacityEngine.evaluate_capacity()` (free margin, margin level >= 150%, margin utilization <= 80%, 6.0% aggregate budget, 4.0% per-instrument canonical budget), enforces `portfolio_risk.evaluate_new_order_permission()`, and reserves `_in_flight_risk_usd` under `self._execution_lock` (`threading.RLock()`).
2. **`src/risk/fast_risk_guard.py:370-374`:**
   - *Before:* `max_global = int(risk_cfg.get("max_concurrent_positions_global", 3))`, `max_per_sym = int(risk_cfg.get("max_concurrent_positions_per_symbol", 1))`, `allow_stacking = False`.
   - *After:* Removed `max_global` / `max_per_sym` caps; `allow_stacking` defaults to `True`.
3. **`src/risk/session_risk.py:104`:**
   - *Before:* `if len(active_positions) >= self.max_concurrent: return False, ...` (`max_concurrent=2`).
   - *After:* Removed blocking condition.
4. **`src/risk/directional_exposure.py:69` & `src/execution/active_mode.py:70-71`:**
   - *Before:* `max_positions_per_symbol = 3`, `max_total_concurrent_positions = 3`, `max_concurrent_positions_per_symbol = 1`.
   - *After:* Defaulted to `0` (dynamic risk-capacity driven).

---

## 4. Actual Runtime Configuration Values (`AppConfig.load_from_dir('config')`)

Observed directly from Python:
```python
{
  'execution_mode': 'DEMO',
  'live_trading_enabled': False,
  'strict_three_symbol_universe': True,
  'symbols': ['XAUUSD', 'BTCUSD', 'USDJPY'],
  'risk_percentage': 1.0,
  'max_aggregate_open_risk_percent': 6.0,
  'max_symbol_risk_percent': 4.0,
  'max_margin_utilization_percent': 80.0,
  'min_margin_level_percent': 150.0,
  'legacy_filters_enabled': False,
  'dry_run': False
}
```

---

## 5. Test Output & Real MT5 Demo vs. Simulated Classification

| Test / Check | Type | Result | Evidence |
|---|---|---|---|
| **Live MT5 Demo Terminal State + 4th Setup Pre-Check** | **Real MT5 Demo Read + Mocked Order Submission** (Real broker order NOT submitted) | **Pre-check PASSED** | Connected to `JustMarkets-Demo` (`2002270203`, `Equity: $1907.31`, `FreeMargin: $1901.42`) with 3 real open positions (`2643265025 BTCUSD.m`, `2643265317 USDJPY.m`, `2643340826 XAUUSD.m`). 4th `XAUUSD.m` SELL setup passed `OrderManager.run_pre_trade_checklist()` with `remaining_risk_capacity_usd: $101.16`. |
| `tests/test_dynamic_position_layering.py` (12 tests: A–L) | **Simulated / Mocked MT5 Execution** | **12/12 PASSED** | Verified 4th position after 3 open, layered `BTCUSD.m`, multi-instrument coexistence, `RISK_BUDGET_EXHAUSTED`, duplicate signal block, independent `$20` close, `INSUFFICIENT_MARGIN`, 3-symbol whitelist, config persistence, MT5 reconciliation, concurrent threads, restart recovery. |
| `tests/test_remediation_compliance.py` (22 tests) | **Simulated / Mocked MT5 Execution** | **22/22 PASSED** | Verified unconditional 3-symbol lockdown, `BridgeClient`/`LiveMT5Broker` boundary rejection of `EURUSD`/`GBPUSD`/`US30`/`US100`/`NAS100`, portfolio safety halts, 8th–10th entries. |
| `tests/test_specialized_three_instrument_universe.py` (26), `test_unrestricted_positions_and_spread.py` (8), `test_companion_control_service.py` (7) | **Simulated / Mocked MT5 Execution** | **41/41 PASSED** | Total **75/75 PASSED** in post-audit run (11.97s). |
| Companion Frontend (`npx tsc --noEmit`) | **Static Typecheck** | **PASSED (exit 0)** | Zero TypeScript errors. |

---

## 6. Windows Deployment Command (Launches Updated Python Source, Not Stale `.exe`)

```powershell
cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001"
.\.venv\Scripts\python.exe scripts\run_bridge_server.py
.\.venv\Scripts\python.exe scripts\start_bot.py
.\.venv\Scripts\python.exe companion\service\main.py --host 127.0.0.1 --port 8765
```
*(In a separate terminal for the Companion UI: `cd "C:\Users\Gackstone_Baraka\Downloads\MT5 001\companion"; npm run dev`.)*
