# MT5-001 — SYMBOL WHITELIST ENFORCEMENT REPORT

**Date:** 2026-11-16  
**Authorized Canonical Universe:** `XAUUSD`, `BTCUSD`, `USDJPY`

---

## 1. Authoritative Policy & Explicit Suffix Mapping

- **Authoritative Service:** `src/core/symbol_universe.py` (`SpecializedSymbolUniverse`, `APPROVED_CANONICAL_SYMBOLS`, `APPROVED_CANONICAL_ALIASES`) + `src/core/broker_resolver.py` (`BrokerSymbolResolver`, `KNOWN_SUFFIXES`).
- **Explicit Mappings:**
  - `XAUUSD`, `XAUUSD.m`, `XAUUSDm`, `XAUUSD.micro`, `GOLD`, `GOLD.m` -> `XAUUSD`
  - `BTCUSD`, `BTCUSD.m`, `BTCUSDm`, `BTCUSD.micro`, `BITCOIN` -> `BTCUSD`
  - `USDJPY`, `USDJPY.m`, `USDJPYm`, `USDJPY.micro` -> `USDJPY`
- **Fail-Closed Policy:** Unknown, unmapped, or unauthorized symbols (`US30`, `US30.std`, `US100`, `NAS100`, `EURUSD`, `GBPUSD`, `UNKNOWN_SYM`, `""`) return `(False, "UNAUTHORIZED_SYMBOL: ...")`.

---

## 2. Multi-Layer Enforcement Points

| Layer | File & Function | Enforcement |
|---|---|---|
| **Config** | `src/core/config.py` (`AppConfig.load_from_dir`), `config/settings.json` | Forces `strict_three_symbol_universe = True` unconditionally; purges unauthorized symbols from `symbols.json`, `instruments.json`, `fast_mode.json`, `settings.json`. |
| **Scanner / Orchestrator** | `src/core/orchestrator.py` (`run_cycle_for_symbol`, `run_scalping_cycle_for_symbol`) | Unconditionally calls `self.symbol_universe.validate_or_reject(symbol)` before market data sync or strategy scan. |
| **Pre-Trade & Execution** | `src/execution/order_manager.py` (`run_pre_trade_checklist`, `execute_signal`) | Unconditionally validates `candidate.symbol` at both checklist and execution entry (cannot be bypassed by `prevalidated`). |
| **Broker Adapter** | `src/adapters/live_mt5_broker.py` (`send_order`) | Validates `request.symbol` before calling `BridgeClient.execute_trade()`. |
| **Final MT5 Boundary** | `src/execution/bridge_client.py` (`execute_trade`, `send_request`) | Rejects `TRADE` payloads for unauthorized symbols (`retcode=10016`) before IPC/socket send. |
| **Companion & Agent** | `companion/service/configuration/config_service.py`, `agent/mt5_bot_agent.py`, `agent/local_limits.json`, `companion/src/services/ipc.ts` | Rejects unauthorized symbols in `validate_bundle()` and restricts defaults to `XAUUSD`, `BTCUSD`, `USDJPY`. |

---

## 3. Automated Test Evidence

- `tests/test_remediation_compliance.py`: **22/22 PASSED** (verifies `XAUUSD`, `XAUUSD.m`, `BTCUSD`, `BTCUSD.m`, `USDJPY`, `USDJPY.m`, `XAUUSD.micro` accepted; `EURUSD`, `EURUSD.m`, `GBPUSD`, `US30`, `US100`, `US100.std`, `NAS100`, `UNKNOWN_SYM`, `""` rejected at `OrderManager`, `LiveMT5Broker`, and `BridgeClient` with `mock_ipc.assert_not_called()`).
- `tests/test_specialized_three_instrument_universe.py`: **26/26 PASSED**.
