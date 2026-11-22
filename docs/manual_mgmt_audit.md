# Phase 0 Audit: Manual-Position Adoption & Professional Trade Management

> **Document Version:** 1.0.0  
> **Status:** Phase 0 Completed — Awaiting User Approval  
> **Branch:** `feature/manual-trade-management`  
> **Classification Tagging:** `[SAFETY]` (Protective controls & invariants), `[VIDEO/KNOWLEDGE]` (Transferred SMC strategy skills), `[ASSUMPTION]` (Engineering defaults requiring backtest/paper validation).  
> **Disclaimer:** Software engineering analysis for an educational and algorithmic trading system. Not financial advice.

---

## Executive Summary

The MT5 Bot codebase possesses a rich suite of pure strategy skills (AlgoVistra 15 videos + Art of Trading 13 videos, 26 verified unit tests) and a multi-tier risk architecture. However, **prior to this audit, the bot was architected under the implicit assumption that every position returned by the MT5 terminal belonged to the bot**.

Under existing code paths, if a user opens a manual position on their desktop or mobile MT5 terminal while the bot is active, the bot's trade manager would:
1. Subject the user's manual position to automatic `$5.00+` scalper profit-taking, break-even ratchets, or session-end flattening.
2. Contaminate internal risk statistics (daily drawdown, decay guard, win-rate metrics) with the manual position's PnL.
3. Potentially liquidate the manual position during an agent `close_all` command or kill switch event.

This audit documents the entire codebase landscape, maps all dangerous code paths, details account and protocol invariants (Hedging vs Netting, Cent accounts, broker symbol suffixes), specifies the exact isolation guards required, and presents a **GO** recommendation subject to strict read-only `OBSERVE` mode activation.

---

## 1. Comprehensive Repository Architecture Map

| Architectural Layer | Key Modules & Source Files | Operational Function & Role |
| :--- | :--- | :--- |
| **MT5 Connection Layer** | `src/execution/bridge_client.py`<br>`src/adapters/live_mt5_broker.py`<br>`src/adapters/broker_interface.py`<br>`mql5/Experts/PythonBridgeEA.mq5`<br>`MetaTrader5` (Direct C-API) | Low-latency TCP socket bridge (port 5555) interfacing with `PythonBridgeEA.mq5` via JSON wire format. Direct `MetaTrader5` Python package optionally used for market data and deal history queries (`history_deals_get`). |
| **Main Loop / Scheduler** | `src/core/orchestrator.py`<br>`agent/mt5_bot_agent.py`<br>`main.py` | `TradingOrchestrator` runs continuous multi-symbol scalping/swing evaluation loops. Calls `manage_active_positions()` at the end of each cycle. `mt5_bot_agent.py` exposes background loop with cloud telemetry and command polling. |
| **Signal Engine (Transferred Skills)** | `src/engine/pipeline.py`<br>`src/engine/skills/`<br>`src/smc/`<br>`src/patterns/` | Orchestrates 25 pure functional skills (`trend_by_structure`, `protected_swing_marker`, `swing_hierarchy`, `five_check_model`, `premium_discount_filter`, `liquidity_pools_bsl_ssl`, `range_liquidity_loop`, `sweep_breakout_classifier`, `fvg_detector`, `order_block_detector`, `entry_quality_guard`, `structure_momentum_monitor`, `stop_management_policy`, etc.) from H0 HTF POOL MAP down to G7. |
| **Risk & Sizing Module** | `src/risk/position_sizing.py`<br>`src/risk/portfolio_risk.py`<br>`src/risk/fit_engine.py`<br>`src/risk/fast_risk_guard.py`<br>`src/risk/prop_firm.py` | Strict position sizing derived from stop distance `[ART-12]`. Daily loss caps, margin floor monitor (150%), equity velocity kill switch, prop-firm maximum trailing drawdown guards. |
| **Order Executor** | `src/execution/order_manager.py`<br>`src/execution/watchdog.py`<br>`src/execution/fast_exit_manager.py` | Pre-Trade Checklist validator, R9.3 stop widening rejection (`NEVER move SL further away`), ticket assignment, order routing, TCA trade cost analytics. |
| **Trade Manager** | `src/risk/trade_management.py` | Position lifecycle manager: calculates Net Floating Profit (gross + commission + swap), dynamic $5+ profit ratchet, break-even at +1.0R (or +0.5R scalping), structural trailing stops, time-stops, session-end flatten. |
| **Config Layer** | `src/core/config.py`<br>`config/strategy.yaml`<br>`config/risk_config.json`<br>`config/settings.json`<br>`config/account_profiles.json` | Strongly typed dataclasses (`AppConfig`, `RiskConfig`, `SymbolConfig`). Central YAML and JSON config files defining magic numbers, risk percentages, session windows. |
| **Logging & Alerting** | `src/notifications/telegram_service.py`<br>`src/notifications/alerts.py`<br>`src/execution/analytics/tca.py` | Structured Python logging, transaction cost analysis (TCA), Telegram broadcast engine with role-based routing (Admin vs Operator) and HTML templates. |
| **Test Suite & Mocks** | `tests/test_algovistra_skills.py`<br>`tests/test_broker_adapters.py`<br>`tests/test_execution_bridge.py`<br>`src/adapters/sim_broker.py` | 50+ unit/integration tests executable via `python -m unittest`. `SimBroker` provides full in-memory execution simulation with slippage, margin checks, commissions, and SL/TP triggers. |

---

## 2. Trade Identification & Ownership Analysis

### Current Mechanism
1. **Magic Number Assignment:**
   - Bot orders are tagged with `config.magic_number` (default `100101`) during order dispatch in `src/execution/order_manager.py:614` and MQL5 `PythonBridgeEA.mq5:2237`.
   - Bot orders carry comment tags (e.g. `MT5_SMC_BOT` or `EURUSD.m_M15_...`).

### The Critical Flaw: Universal Position Ingestion
Despite stamping magic numbers on outbound orders, **the inbound position ingestion pipelines completely discard magic number filtering**:
- In `mql5/Experts/PythonBridgeEA.mq5:2304-2328`, the `POSITIONS` command loops through `PositionsTotal()` and serializes **every position on the MT5 account** into JSON, returning all manual trades, copy-trades, and external EA trades to Python.
- In `src/execution/order_manager.py:642`, `get_active_positions()` returns `self.bridge.get_positions()`, which returns all account positions without filtering by `magic == config.magic_number`.
- In `src/core/orchestrator.py:864`, `manage_active_positions()` retrieves this unfiltered list and directly iterates over it.

---

## 3. Dangerous Code Paths & Accidental Modification Hazards

The following five specific locations in the current codebase represent **active hazards** that would modify or close manual positions if manual positions exist on the logged-in account:

### Hazard 1: Orchestrator Active Lifecycle Management
- **File & Lines:** [src/core/orchestrator.py#L910-L950](file:///c:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/core/orchestrator.py#L910-L950)
- **Mechanism:** The loop iterates over `active_positions = list(self.order_manager.get_active_positions())` without checking `pos.magic`. It invokes:
  ```python
  actions = self.trade_manager.evaluate_position(pos, sym_info, recent_bars, scalp_mode=scalp_mode)
  for act in actions:
      if act.action_type == "FULL_CLOSE":
          self.bridge.close_order(ticket=act.ticket)
  ```
- **Consequence:** If the user opens a manual position and it reaches the bot's configured $5.00 scalper profit target, or if session-end flatten triggers (`enable_session_end_flatten=True`), **the bot will close the user's manual trade without warning!**
- **Action Required:** `[SAFETY]` Restrict `manage_active_positions()` strictly to positions classified as `BOT_OWN` (or explicitly adopted manual positions under active management policy).

### Hazard 2: Risk Metrics & Account Cache Contamination
- **File & Lines:** [src/core/orchestrator.py#L868-L908](file:///c:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/core/orchestrator.py#L868-L908)
- **Mechanism:** The orchestrator maintains `self._active_positions_cache`. When a position drops out of `active_positions` (e.g. user manually closes their trade on their phone), the orchestrator calculates `realized_pnl` from deals and executes:
  ```python
  self.portfolio_risk.record_trade_result(profit=realized_pnl, volume=closed_pos.volume, symbol=closed_pos.symbol)
  self.decay_guard.add_trade(r_outcome)
  self.continuous_scalper.on_position_closed_or_rejected(closed_pos.symbol, was_closed=True)
  ```
- **Consequence:** A manual discretionary loss or profit alters the bot's daily loss counter, trips the bot's strategy decay guard, or alters the scalper's symbol state machine.
- **Action Required:** `[SAFETY]` Isolate closed deal accounting so only `BOT_OWN` tickets update the bot's internal strategy metrics and state machines.

### Hazard 3: Agent Unfiltered Remote Close-All
- **File & Lines:** [agent/mt5_bot_agent.py#L527-L560](file:///c:/Users/Gackstone_Baraka/Downloads/MT5%20001/agent/mt5_bot_agent.py#L527-L560)
- **Mechanism:** When receiving a `close_all` command from cloud telemetry, it executes:
  ```python
  positions = self.bridge.get_positions()
  for pos in positions:
      res = self.bridge.close_order(pos.ticket)
  # Fallback:
  positions = mt5.positions_get()
  for p in positions:
      # closes position p.ticket unconditionally!
  ```
- **Consequence:** Every manual trade, swing investment, or hedge position on the account is instantly liquidated.
- **Action Required:** `[SAFETY]` `close_all` must default to closing only `BOT_OWN` positions (`p.magic == config.magic_number`). Any manual trade closure must require an explicit separate parameter `include_manual=True` with audit logging.

### Hazard 4: Reset State Denial of Service
- **File & Lines:** [src/core/orchestrator.py#L258-L264](file:///c:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/core/orchestrator.py#L258-L264)
- **Mechanism:**
  ```python
  positions = self.order_manager.get_active_positions()
  if positions:
      return False, f"Cannot reset state while {len(positions)} positions are still open."
  ```
- **Consequence:** If the user has a long-term manual swing position open, the bot operator is completely blocked from resetting the bot's daily intraday state.
- **Action Required:** `[SAFETY]` Check only bot-owned positions: `[p for p in positions if p.magic == self.config.magic_number]`.

### Hazard 5: FastRiskGuard Margin Emergency Flatten
- **File & Lines:** [src/risk/fast_risk_guard.py#L295-L315](file:///c:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/risk/fast_risk_guard.py#L295-L315)
- **Mechanism:** When account margin level drops below 150%, `must_flatten_immediately` is flagged. If the execution loop responds by flattening all tickets indiscriminately, manual positions are caught.
- **Action Required:** `[SAFETY]` FastRiskGuard must prioritize bot-owned positions first and respect `manual_mgmt` policy.

---

## 4. Account Assumptions & Broker Invariants

| Invariant | Broker Behavior | Bot Impact & Required Handling |
| :--- | :--- | :--- |
| **Hedging vs Netting** | **Hedging:** Multiple positions permitted per symbol, each with a distinct ticket.<br>**Netting:** Exactly one position per symbol. Any new deal modifies the single volume-weighted position ticket. | `[SAFETY]` In **Netting** accounts, the bot CANNOT safely add to or manage manual positions without altering the single shared ticket! The manual management module MUST detect `account_info().margin_mode == 1` (NETTING) and automatically force mode to **OBSERVE ONLY** for Netting accounts to prevent accidental position blending. |
| **Account Type (Real vs Demo)** | `account_info().trade_mode` returns:<br>`0 = DEMO`<br>`1 = CONTEST`<br>`2 = REAL` | `[SAFETY]` **Never run against a REAL account unless `allow_real_account_management: true` is explicitly configured.** If `trade_mode == REAL` (or 2) and the flag is false, force mode to `OBSERVE` and emit a security alert. |
| **Symbol Suffixes & Prefixes** | Brokers append suffixes (e.g. `EURUSD.m`, `GBPUSD.pro`, `BTCUSD_i`, `EURUSD+`). | `[DERIVED]` Detection must match base symbols via `resolve_broker_symbol()` or strip suffixes (`re.split(r'[^A-Za-z0-9]', symbol)`) to align with strategy configurations. |
| **Filling Modes** | Brokers require specific filling policies: `FOK` (Fill or Kill), `IOC` (Immediate or Cancel), or `RETURN`. | `[DERIVED]` Any order or modification must verify `symbol_info.filling_mode` (or bitmask `SYMBOL_FILLING_MODE`) before sending orders to avoid MT5 retcode `10030` (`TRADE_RETCODE_INVALID_FILL`). |
| **Server Time vs UTC** | Brokers operate on server time (typically UTC+2 or UTC+3 EET/EEST). | `[DERIVED]` MT5 deals and rates timestamps must be normalized using `g_broker_utc_offset` or `datetime.fromtimestamp(ts, tz=timezone.utc)`. Never compare raw broker local time with `datetime.now(timezone.utc)`. |
| **Cent Accounts** | Brokers (e.g. Exness, FBS) use USC/EUC where $100.00 displays as 10,000 cents. | `[SAFETY]` AccountInfo already auto-detects `is_cent_account` and scales balance. Position sizing calculations must ensure cent scaling factors are not applied twice. |

---

## 5. Position Classification Logic

Every open position and historical deal must be classified using the following deterministic rule hierarchy (first match wins):

```
                                  [ Open Position ]
                                          |
                        +-----------------+-----------------+
                        |                                   |
             Does pos.magic ==                         pos.magic !=
             config.magic_number?                   config.magic_number
                        |                                   |
                     [ YES ]                             [ NO ]
                        |                                   |
                   ==> BOT_OWN                    Does pos.magic == 0?
                                                            |
                                              +-------------+-------------+
                                              |                           |
                                           [ YES ]                     [ NO ]
                                              |                           |
                                      Query Deal Reason             ==> OTHER_EA
                                    (via history_deals)
                                              |
                          +-------------------+-------------------+
                          |                                       |
                   Deal reason in                        Deal reason == EXPERT
                CLIENT / MOBILE / WEB                             |
                          |                                  ==> OTHER_EA
                   Is Symbol Allowed &
                  No "#bot:off" comment?
                          |
                    +-----+-----+
                    |           |
                 [ YES ]     [ NO ]
                    |           |
                 ==> MANUAL  ==> EXCLUDED
```

### Detailed Classification Specification

1. **`BOT_OWN`**:
   - `pos.magic == config.magic_number` (default `100101`) OR ticket is present in persisted bot trade registry (`state/active_bot_trades.json`).
   - *Action:* Managed by bot's normal automated scalper/swing trade manager.
2. **`MANUAL`**:
   - `pos.magic == 0` AND opening deal reason in `DEAL_REASON_CLIENT` (desktop terminal), `DEAL_REASON_MOBILE` (iOS/Android), or `DEAL_REASON_WEB` (WebTrader).
   - *Fallback:* If deal history is unavailable, `pos.magic == 0` defaults to `MANUAL`.
   - *Action:* Managed strictly according to `manual_management.yaml` mode (`OBSERVE`, `PROTECT`, `ASSIST`, `FULL`).
3. **`OTHER_EA`**:
   - `pos.magic != 0` AND `pos.magic != config.magic_number`, OR opening deal reason is `DEAL_REASON_EXPERT`.
   - *Action:* Strictly hands-off. Never modify, close, or add to external EA positions.
4. **`EXCLUDED`**:
   - Symbol is not in `config.allowed_symbols`, OR position comment contains `#bot:off` or `#ignore`.
   - *Action:* Ignored completely.
5. **`UNKNOWN`**:
   - Any ticket failing above deterministic classification.
   - *Action:* Treated as `OBSERVE` only; never modified.

---

## 6. Trade Management Modes & User Supremacy Invariants

### Operational Modes
1. **`OBSERVE` (Default):**
   - Zero broker modifications or orders.
   - Evaluates positions against the 28-video strategy skills (`five_check_model`, `entry_quality_guard`, `structure_momentum_monitor`, `stop_management_policy`).
   - Logs what the bot *would* do and surfaces rich recommendations in Telegram / chat.
2. **`PROTECT`:**
   - Adopts orphaned positions (manual positions opened with `stop_loss == 0.0`).
   - Calculates structure-based SL using `protected_swing_marker` + ATR buffer and places it at the broker.
   - Moves SL to Break-Even when structure reaches +1.0R.
   - **Never closes or scales positions.**
3. **`ASSIST`:**
   - All `PROTECT` capabilities plus:
   - Trails stops behind confirmed swing pivots (`swing_hierarchy`, `structure_momentum_monitor`).
   - Sends Telegram alerts on target exhaustion or structural reversal.
4. **`FULL`:**
   - All `ASSIST` capabilities plus:
   - Automated structural scaling / add-ons (strictly on winners that have already banked risk to BE, never on losers).
   - Automated profit taking on momentum stall / higher timeframe liquidity sweep.

### User Supremacy Invariants `[SAFETY]`
1. **Tighten-Only Rule:** The bot may **ONLY** move a stop loss closer to current price (reducing risk). It is mathematically forbidden from widening a stop loss or removing a stop loss.
2. **User Override Lockout:** If the user manually edits the SL, TP, or volume of an adopted position in MT5, the bot **immediately detects the discrepancy, cedes control, and locks itself out of managing that ticket for 30 minutes** (configurable `user_override_lockout_minutes: 30`).
3. **Kill Switch / Emergency Pause:** If a file `state/PAUSE` exists, or `pause_all: true` is set, the manual management loop immediately halts all order modifications.
4. **No Pyramiding Losers:** No martingale, no averaging down, no grid. Adding to a position is only permitted if the original position is in profit and its stop is at break-even or better.

---

## 7. State Persistence & Audit Logging Architecture

1. **State Persistence (`state/manual_positions.json`):**
   - Must persist:
     - `ticket`: MT5 position ticket ID.
     - `symbol`: Instrument.
     - `direction`: BUY / SELL.
     - `open_price`, `initial_sl`, `current_sl`.
     - `adoption_time`: Timestamp when adopted.
     - `assigned_mode`: Active mode (`OBSERVE`, `PROTECT`, etc.).
     - `last_bot_sl_update`: Timestamp and price of last bot modification.
     - `user_override_detected`: Boolean flag.
     - `lockout_until`: Timestamp until which bot cannot touch the position.
     - `add_ons_count`: Number of scale-ins executed (max 1 [ASSUMPTION]).
   - File updates use atomic write (`tempfile` + `os.replace`) to prevent file corruption during crashes.

2. **Audit Journaling (`logs/manual_management_audit.log`):**
   - Every state change, inspection, adoption, SL modification, or user override is written to a dedicated structured JSON-lines audit log.

---

## 8. Test & Simulation Strategy

1. **Unit Testing (`tests/test_manual_management.py`):**
   - Use `SimBroker` and mock adapters to verify all 13 core scenarios:
     - Detection & classification (`BOT_OWN` vs `MANUAL` vs `OTHER_EA`).
     - Adopting naked positions (missing SL) in `PROTECT` mode.
     - R9.3 stop-loss tightening invariant (rejection of widening).
     - User override detection and 30-minute lockout enforcement.
     - Real account lockout guard (`ALLOW_REAL_ACCOUNT_MANAGEMENT=false`).
     - Netting account forced `OBSERVE` mode.
     - Add-on restriction (refusal to add to losing position).
     - Atomic state file persistence across bot restart.
2. **Replay Validation Harness (`scripts/run_manual_replay.py`):**
   - Replays historical M15/M5 bars to verify trailing stops and break-even triggers against real price action.

---

## 9. Risk Matrix & Mitigations

| Risk Description | Severity | Likelihood | Mitigation Strategy |
| :--- | :---: | :---: | :--- |
| **Accidental closure of manual swing trade** | **CRITICAL** | High (in current code) | Decouple `orchestrator.py` position loop. Implement Magic Number segregation guard. |
| **Loss of capital on REAL account** | **CRITICAL** | Medium | Hard block against `account_info().trade_mode == REAL` unless `ALLOW_REAL_ACCOUNT_MANAGEMENT=true`. Default mode `OBSERVE`. |
| **Fighting the User (Bot moves SL, User moves it back, Bot moves it again)** | **HIGH** | High | User Override Lockout: detect broker SL change not issued by bot, freeze bot actions on ticket for 30 min. |
| **Position doubling on Netting account** | **HIGH** | Medium | Auto-detect Netting mode (`margin_mode == 1`) and downgrade to `OBSERVE` only. |
| **State file corruption during power outage** | **MEDIUM** | Low | Atomic write using temporary files and rename. |
| **Broker rejection (Retcode 10013 / 10030)** | **MEDIUM** | Medium | Pre-validate stops level, freeze level, and filling mode before sending `modify_order`. |

---

## 10. Go / No-Go Recommendation

### Recommendation: **GO FOR IMPLEMENTATION (Phase 1)**
**Conditions for GO:**
1. **Safety First:** The system must default to `OBSERVE` mode (read-only monitoring and logging).
2. **First Commit:** Immediately deploy the isolation guards in `orchestrator.py`, `order_manager.py`, and `agent/mt5_bot_agent.py` so that bot-own trades and manual trades are strictly partitioned before any management feature is activated.
3. **Real Account Barrier:** Real accounts are hard-locked from write operations unless explicit environment variables and config flags are set.
4. **All Changes on Feature Branch:** All work proceeds on `feature/manual-trade-management` and requires user pull-request review before merging to `main`.

---
*End of Phase 0 Audit. Awaiting user approval to proceed with Phase 1 implementation.*
