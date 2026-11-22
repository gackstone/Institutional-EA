# Institutional EA — US30 ROOT-CAUSE INVESTIGATION REPORT

**Date:** 2026-11-16  
**MT5 Demo Account:** `2002270203` (`JustMarkets-Demo`, Hedging Mode)

---

## 1. Live Forensic Evidence of the `US30.std` Position

Direct read-only inspection of the running MetaTrader 5 terminal (`mt5.positions_get()`) and 7-day deal history (`mt5.history_deals_get()`) established the exact origin of the unauthorized `US30.std` position:

- **Ticket:** `2643437551`
- **Symbol:** `US30.std`
- **Direction:** `SELL` (`type = 1`)
- **Volume:** `0.03`
- **Magic Number:** `100101`
- **Order Comment:** `SCALP_SMC_MODEL_2_BOS_FVG`
- **Open Timestamp:** `2026-11-16T20:06:26+00:00`
- **Floating Profit at Inspection:** `+$0.66`
- **Historical `US30.std` Deals (last 7 days):** 24 deals, including entries with comments `SCALP_FAST_SCALP`, `SCALP_SMC_MODEL_2_BOS_FVG`, and `SCALP_SMC_MODEL_3_OB_RETEST` under `magic = 100101`.
- **Action Taken:** Preserved open for operator review (not closed automatically).

---

## 2. Originating Process & Root Cause

Inspection of running Windows processes (`Get-CimInstance Win32_Process`) revealed **stale pre-compiled PyInstaller executables** running from `companion\release\win-unpacked\resources\bin\`:

| PID | Executable | Command Line |
|---|---|---|
| `9524` | `mt5_trading_engine.exe` | `"C:\Users\Gackstone_Baraka\Downloads\MT5 001\companion\release\win-unpacked\resources\bin\mt5_trading_engine.exe"` |
| `1616` | `mt5_bot_agent.exe` | `"C:\Users\Gackstone_Baraka\Downloads\MT5 001\companion\release\win-unpacked\resources\bin\mt5_bot_agent.exe" --daemon` |
| `2976` | `mt5_bridge_server.exe` | `"C:\Users\Gackstone_Baraka\Downloads\MT5 001\companion\release\win-unpacked\resources\bin\mt5_bridge_server.exe"` |
| `10832` | `mt5_bridge_server.exe` | `"C:\Users\Gackstone_Baraka\Downloads\MT5 001\companion\release\win-unpacked\resources\bin\mt5_bridge_server.exe"` |

### Why `US30.std` Bypassed the Three-Symbol Restriction
1. **Stale Packaged Binary (`PID 9524`):** `mt5_trading_engine.exe` was compiled prior to the source-code remediations. In that build:
   - `config/settings.json` had `"strict_three_symbol_universe": false`.
   - `ContinuousScalpingEngine.__init__()` defaulted to `["BTCUSD.m", "EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "US100.std", "US30.std"]`.
   - `OrderManager` and `BridgeClient` did not unconditionally enforce `SpecializedSymbolUniverse.validate_or_reject()`.
   - The old `3/3` simultaneous position cap was also active in that binary, explaining why the live terminal simultaneously showed 3 open positions (`2643265025 BTCUSD.m`, `2643265317 USDJPY.m`, `2643437551 US30.std`) and `Maximum simultaneous positions reached (3/3)`.

---

## 3. Remediation & Prevention

1. Unconditional three-symbol enforcement (`XAUUSD`, `BTCUSD`, `USDJPY`) is now compiled into the Python source across `AppConfig`, `TradingBotOrchestrator`, `OrderManager`, `LiveMT5Broker`, `BridgeClient`, `MarketDataEngine`, `ContinuousScalpingEngine`, `HealthMonitor`, `agent/mt5_bot_agent.py`, and `ConfigurationService`.
2. **Deployment Rule:** Always stop stale `companion\release\win-unpacked\resources\bin\*.exe` processes and launch directly from the updated Python source (`.venv\Scripts\python.exe scripts\start_bot.py`) until sidecars are rebuilt.
