# REMOVED_FILTERS: Inventory of Bypassed and Removed Legacy Entry Gates

## Overview

To transform the legacy day-trading bot into a dedicated, high-frequency GOLD (XAUUSD) scalping engine, all legacy entry gating mechanisms that artificially restrict, delay, or prevent rapid trade execution have been bypassed or converted into non-blocking directional scoring providers.

Global Backward-Compatibility Flag:
```yaml
legacy_filters:
  LEGACY_FILTERS_ENABLED: false
```

- When **`LEGACY_FILTERS_ENABLED: false`** (Default): All legacy entry filters are completely bypassed. The scalping engine operates continuously on live sub-second market ticks without waiting for candle closures, session killzones, news clear windows, or multi-timeframe confluence locks.
- When **`LEGACY_FILTERS_ENABLED: true`**: The original day-trading gating behavior is restored for all legacy workflows.

> **CRITICAL SAFETY DISTINCTION**:
> Safety and execution controls (protective stop-loss placement, hard 2.0% risk cap, margin level >= 300%, max open positions ceiling of 12, equity drawdown circuit breaker of 30%, spread protection <= 80 points, and the emergency kill switch) are **NOT** legacy filters. They remain 100% active and strictly enforced at all times regardless of `LEGACY_FILTERS_ENABLED`.

---

## Detailed Filter Inventory

| Filter Name | Original File Path | Original Function / Class | How It Affected Trade Entry | Status | Behavior when `LEGACY_FILTERS_ENABLED=true` |
|---|---|---|---|---|---|
| **High-Impact News Blackout Gate** | `src/core/news_filter.py`<br>`src/core/orchestrator.py` | `NewsFilterEngine.is_trading_allowed()`<br>`TradingBotOrchestrator._execute_approved_candidate()` | Blocked new orders during CPI, NFP, FOMC, and other red-folder news release windows (before and after). | **Bypassed** | Blocks trades within configured news blackout windows (`NEWS_BLACKOUT`). |
| **Setup Quality Gate** | `src/smc/setup_quality_gate.py`<br>`src/core/orchestrator.py` | `SetupQualityGate.evaluate()` | Rejected trade candidates failing ICT rulebook thresholds (min confluence score 55-75, discount/premium location, OB displacement ATR mult). | **Bypassed / Converted to Scoring** | Enforces hard failure rejections and blocks trades with `QUALITY_GATE_REJECTED`. |
| **SCALP HTF Agreement Filter** | `src/smc/strategy_engine.py`<br>`src/core/orchestrator.py` | `SmcStrategyEngine.check_scalp_htf_agreement()` | Required M1/M5 scalp direction to match H1/H4 macro market structure trend bias. | **Bypassed** | Blocks counter-trend scalps with `UNCLEAR_STRUCTURE`. |
| **Weekend Market Holding Gate** | `src/core/orchestrator.py` | `TradingBotOrchestrator.run_cycle_for_symbol()` | Blocked order submission after Friday afternoon (e.g. 21:00/22:00 UTC) to prevent weekend gap exposure. | **Bypassed** | Disallows new trades after Friday close hour with `SESSION_FILTER`. |
| **Meta-Labeling Machine Learning Filter** | `src/learning/meta/meta_classifier.py`<br>`src/core/orchestrator.py` | `MetaLabelingController.evaluate_candidate()` | Filtered candidates if random forest / gradient boosting model predicted probability of success < 50%. | **Bypassed** | Drops signals when ML meta-classifier outputs non-proceed verdict (`META_LABELING_FILTER`). |
| **Active Mode Frequency Controls** | `src/execution/active_mode.py`<br>`src/core/orchestrator.py` | `ActiveTradingEngine.verify_prohibitions()` | Enforced mandatory time cooldowns between trades and rate limits per hour/session. | **Bypassed** | Rejects signals when trade frequency or cooldown limits are breached (`PROHIBITION_BLOCKED`). |
| **Structure Confirmation (BOS after CHoCH)** | `src/execution/order_manager.py` | `OrderManager.run_pre_trade_checklist()` | Required a Change of Character (CHoCH) to be followed by a verified Break of Structure (BOS) before opening. | **Bypassed** | Blocks entries trapped in unconfirmed CHoCH states (`Structure confirmed check failed`). |
| **Anti-Chasing Price Drift Filter** | `src/execution/order_manager.py` | `OrderManager.run_pre_trade_checklist()` | Blocked market execution if live ask/bid drifted beyond 1.0x planned risk from candidate signal entry price. | **Bypassed** | Blocks drifted orders with `Anti-Chasing V14: Price drifted > max extension`. |
| **Strict Entry Quality Minimum R:R** | `src/execution/order_manager.py` | `OrderManager.run_pre_trade_checklist()` | Re-calculated live Reward-to-Risk against live fill price; rejected any trade where live R:R fell below 1:1.5 or 1:2.0. | **Bypassed** | Blocks trades where live R:R drops below threshold with `Live fill R:R < min`. |
| **Monte Carlo Replay Gate** | `src/risk/replay_gate.py`<br>`src/execution/order_manager.py` | `MonteCarloReplayGate.evaluate_plan()` | Ran simulated historical candle replays across recent bars; rejected setups failing historical simulation win rate. | **Bypassed** | Rejects trade candidates with `Replay Gate failed`. |
| **Trading Session & Killzone Gating** | `src/core/sessions.py`<br>`src/execution/order_manager.py` | `TradingSessionEngine.get_session_info()` | Blocked trading outside active London, New York, or Asian killzone hours. | **Bypassed** | Blocks trades outside authorized session killzones (`Session active check failed`). |
| **Session Affinity Matrix** | `src/core/session_affinity.py`<br>`src/execution/order_manager.py` | `SessionAffinityEngine.is_symbol_allowed()` | Whitelisted specific pairs per session (e.g. only JPY during Asian, only EUR/GBP during London). | **Bypassed** | Blocks pairs not listed for current session (`Symbol allowed for session`). |
| **Daily Swap Rollover / Handover Blackout** | `src/core/sessions.py`<br>`src/execution/order_manager.py` | `TradingSessionEngine.get_session_info()` | Paused order entries during daily 21:55-22:10 UTC broker swap rollover and session handovers. | **Bypassed** | Blocks entries during swap rollover blackout window. |
| **Fast Watchdog Rate Limiter & Cooldown** | `src/execution/watchdog.py`<br>`src/execution/order_manager.py` | `FastWatchdog.can_open_new_trade()` | Implemented post-trade cooldowns (e.g. 60-120 seconds) and per-symbol hourly trade caps. | **Bypassed** | Blocks trades exceeding watchdog frequency limits. |
| **Closed-Candle Confirmation Requirement** | `src/core/orchestrator.py`<br>`src/execution/fast_mode_engine.py` | `closed_candles_only: true` | Required candles to complete and close before evaluating setups, introducing multi-minute delays. | **Bypassed / Replaced with Tick Loop** | Strictly evaluates signals only upon completed candle close. |
| **Single-Position-Per-Symbol Restriction** | `src/core/orchestrator.py`<br>`src/execution/order_manager.py` | `Pre-check item 8: Conflicting / duplicate active position` | Prevented opening a second position on the same symbol while one was already active. | **Replaced by Basket Engine** | Allows only 1 position per symbol at a time. |

---

## Active Safety Controls (Always Enforced)

The following controls remain strictly active in all operating modes:

1. **Mandatory Protective Stop-Loss (`SL_POINTS = 300.0`)**: Every order must carry a verified protective stop-loss. Unprotected orders are rejected or liquidated immediately.
2. **Hard Risk Ceiling (Rule R9.1)**: Single trade risk is hard-capped at 2.0% in code.
3. **Margin Protection (`MIN_MARGIN_LEVEL = 300.0%`)**: Verified against current and projected margin requirements before order dispatch.
4. **Maximum Open Positions (`MAX_OPEN_POSITIONS = 12`)**: Hard account-wide ceiling.
5. **Maximum Aggregate Lots (`MAX_TOTAL_LOTS = 1.00`)**: Projected total lots check.
6. **Equity Drawdown Stop (`MAX_DD_PCT = 30.0%`)**: Emergency liquidation of scalper positions followed by a 60-minute pause.
7. **Abnormal Spread Protection (`SPREAD_MAX_POINTS = 80.0`)**: Prevents entries during illiquid spread spikes.
8. **Emergency Kill Switch (`STOP.flag`)**: Instantaneous halt and position liquidation on command.
9. **DEMO_MODE Default (`DEMO_MODE = true`)**: Hard prohibition against real-money execution unless explicitly confirmed.
10. **Manual Position Management Subsystem**: Strictly isolates and preserves manual trades with independent tracking.
