# MT5-001 — FINAL AUTOMATED TEST RESULTS REPORT

**Date:** 2026-11-16  
**Environment:** Windows, Python 3.12.10 (`.venv\Scripts\python.exe`), `pytest 9.2.0`

---

## 1. Post-Remediation Regression Test Suites

| Test Suite / Command | Total | Passed | Failed | Notes / Details |
|---|---|---|---|---|
| `.venv\Scripts\python.exe -m pytest tests/test_remediation_compliance.py -v --tb=short` | 22 | 22 | 0 | **PASS** — Covers all 18 mandatory compliance checks (unconditional 3-symbol lockdown, boundary enforcement, portfolio safety halts, real-account lock, 8th/9th/10th entries, Companion validation). |
| `tests/test_specialized_three_instrument_universe.py` | 26 | 26 | 0 | **PASS** — Symbol universe, broker suffix resolution, weekday/weekend schedule, inverse coordination, OrderManager & Orchestrator integration. |
| `tests/test_unrestricted_positions_and_spread.py` | 8 | 8 | 0 | **PASS** — 0, 1, 3, 7, 10, 15 active positions; wide spread diagnostics; critical margin floor preserved. |
| `tests/test_prop_firm_rules.py` | 7 | 7 | 0 | **PASS** — PROP profile rules intact. |
| `tests/test_risk_management.py` | 6 | 6 | 0 | **PASS** — R:R, capacity, circuit breaker, daily loss, shadow gate non-veto. |
| `tests/test_smc_rulebook_golden.py` | 10 | 10 | 0 | **PASS** — No lookahead bias, R1–R8 golden structure/FVG/OB/sweep/PD/TP rules. |
| `tests/test_account_mode_hedging.py` | 3 | 3 | 0 | **PASS** — Hedging ticket-level closing & multi-position counting. |
| `tests/test_dual_mode_profit_management.py` | 11 | 11 | 0 | **PASS** — QUICK_SCALP ($20 close), PROFIT_RUNNING ($20 lock + ratchets), persistence. |
| `tests/test_companion_control_service.py` | 7 | 7 | 0 | **PASS** — SQLite migrations, auth, config lock/rollback, MT5 sync, engine controller, HTTP API. |
| `tests/test_mt5_bot_agent.py` | 18 | 18 | 0 | **PASS** — Agent pairing, telemetry, signed commands, replay protection. |
| `tests/test_engine_lifecycle_fixes.py` | 4 | 4 | 0 | **PASS** — Single-instance lock, heartbeat, bridge probe/dedup. |
| `tests/test_execution_analytics.py` | 5 | 5 | 0 | **PASS** — Idempotency, limit orders, spread filter, TCA. |
| `tests/test_multi_connection_bridge.py` | 3 | 3 | 0 | **PASS** — Multi-EA concurrent connections, duplicate/stale replacement, kill switch. |
| `tests/test_execution_bridge.py` | 1 | 0 | 1 | **FAIL (Expected Legacy Behavior)** — `test_bridge_actions` calls `bridge.execute_trade(symbol="EURUSD", ...)`, which is now **correctly blocked** (`[SYMBOL_REJECT]`) by the unconditional 3-symbol lockdown at `BridgeClient`. Preserved unmodified per test-integrity rules. |
| `tests/test_pipeline_integration.py` | 1 | 0 | 1 | **FAIL (Expected Legacy Behavior)** — `test_full_pipeline_execution` calls `orchestrator.run_cycle_for_symbol("EURUSD")`, which is now **correctly blocked** (`UNAUTHORIZED_SYMBOL`) by `TradingBotOrchestrator`. Preserved unmodified per test-integrity rules. |

---

## 2. Original Audit Script Re-Run (`scratch/audit_tests.py`)

Executed `.venv\Scripts\python.exe ...\scratch\audit_tests.py` after remediation:
- **Phase 2 (Default Config Symbol Authorization):**
  - `Default config strict_three_symbol_universe = True`
  - `XAUUSD`, `USDJPY` -> `passed=True`
  - `BTCUSD` -> `passed=False` (Rejected by `TradingScheduleManager` `WEEKDAY_INACTIVE` on Monday `2026-11-16`, as designed)
  - `EURUSD`, `GBPUSD`, `US30`, `US100`, `NAS100`, `UNKNOWN_SYM` -> `passed=False` (`Pre-check failed (Universe Restriction): UNAUTHORIZED_SYMBOL`)
- **Phase 3 (0-Min & >7-Max Positions):** Entries #1 through #10 on weekday-eligible symbols (`XAUUSD`, `USDJPY`) reached mocked MT5 submission and returned `FILLED`.
- **Phase 4 (Spread Variations):** `10 pts` and `500 pts (50% of SL)` passed; extreme spreads (`2500+ pts`) failed only $20 target feasibility under the R9 2.0% risk cap.

---

## 3. Unverified Items

| Item | Status | Reason |
|---|---|---|
| **Live MT5 Terminal Order Execution** | **NOT VERIFIED** | Audit rules prohibit connecting to a live account or placing real trades. All MT5 execution tests used mocked `BridgeClient` or local `MockEA` sockets. |
| **Full Unfiltered `pytest` Run** | **NOT VERIFIED** | An initial unfiltered `pytest` run stalled at ~40% on a blocking test and was terminated; all 15 audit-relevant suites above were executed directly. |
