# MT5 001 — Trading Decision-Making Engine
**Forensic Technical Intelligence Audit**  
**Classification:** Algorithmic Decision Architecture & Execution Logic  
**System Target:** MT5 001 Automated Trading System  
**Auditor:** Principal Quantitative Trading Systems Architect & Senior Algorithmic Trading Engineer  
**Date of Audit:** November 2026  

---

## 1. Complete Decision Pipeline Sequence

The decision-making architecture of **MT5 001** is a deterministic, multi-stage filtration pipeline with quantitative statistical modulation. It processes market data sequentially through **15 strict, ordered stages**:

```
 1. Market Data Ingestion & Timeframe Sync (W1, D1, H4, H1, M30, M15, M5, M1)
                        │
                        ▼
 2. Data Integrity & Staleness Gate (Max age <= 180s; bar count check)
                        │
                        ▼
 3. Market Regime & Session Filtering (Bull/Bear Trend, Ranging, Volatility)
                        │
                        ▼
 4. Multi-Timeframe Structural Bias Mapping (W1->D1->H4->H1 Direction)
                        │
                        ▼
 5. Candidate Opportunity Scanning:
    ├─ Continuous Scalper (M1/M5/M15 Momentum, Pullback, Sweep/Breakout)
    └─ SMC Strategy Engine Fallback (W1/D1 Sweeps, Order Blocks, FVGs)
                        │
                        ▼
 6. Confluence Scoring & Quality Filtering (Score >= 55.0 Scalp / 75.0 SMC)
                        │
                        ▼
 7. Setup Quality Gate Verification (Phase 2 Hard Gates G1 through G8)
                        │
                        ▼
 8. Secondary Statistical Meta-Labeling (Logistic Platt Prob >= 0.45)
                        │
                        ▼
 9. Volatility Target & Kelly Modulator (GARCH/EWMA Vol Scale, Quarter-Kelly)
                        │
                        ▼
10. Deterministic Lot Sizing & Floor Check ($5 Floor, R9 2.0% Hard Cap)
                        │
                        ▼
11. Pre-Trade Portfolio Risk Authorization (Daily/Weekly Loss, Drawdown, Cooldowns)
                        │
                        ▼
12. Order Assembly & Idempotency Tagging (Unique REQ_ID, Magic, Slippage Limit)
                        │
                        ▼
13. IPC Bridge Dispatch & MQL5 Gatekeeper (Native spread, margin, login checks)
                        │
                        ▼
14. Broker Execution & Post-Fill Reconciliation (IOC/FOK fill, Ticket Logging)
                        │
                        ▼
15. Position Lifecycle Management ($5 Profit Target, BE, Trailing SL, CUSUM Feedback)
```

---

## 2. Decision Logic Engine: Complete Pseudocode

The following pseudocode captures the exact end-to-end decision algorithm implemented in `src/core/orchestrator.py`, `src/execution/continuous_scalper.py`, `src/smc/strategy_engine.py`, `src/smc/setup_quality_gate.py`, and `src/risk/position_sizing.py`:

```python
def evaluate_symbol_decision_cycle(symbol):
    # -------------------------------------------------------------
    # STAGE 1 & 2: DATA ACQUISITION & INTEGRITY GATE
    # -------------------------------------------------------------
    candles = market_data.get_all_timeframes(symbol) # W1, D1, H4, H1, M15, M5, M1
    m15 = candles[Timeframe.M15]
    
    if len(m15) < 20 or len(candles[Timeframe.M1]) < 12:
        return reject("NO_SETUP", "INSUFFICIENT_DATA", "History below minimum required bars")
    
    bar_time = m15[-1].time
    if (current_time_utc() - bar_time).seconds > 180:
        return reject("TRADE_SKIPPED", "STALE_DATA", "Latest candle older than 180 seconds")

    # -------------------------------------------------------------
    # STAGE 3: REGIME & VOLATILITY CLASSIFICATION
    # -------------------------------------------------------------
    regime, metrics = classify_market_regime(candles[Timeframe.M5])
    if regime == MarketRegime.HIGH_VOLATILITY and metrics["volatility_ratio"] >= 2.5:
        return reject("TRADE_SKIPPED", "EXCESSIVE_VOLATILITY", "ATR expanded > 2.5x historical norm")

    # -------------------------------------------------------------
    # STAGE 4 & 5: SCALPING CANDIDATE GENERATION
    # -------------------------------------------------------------
    candidate = None
    if config.trading_mode == "CONTINUOUS_SCALPING":
        candidate = continuous_scalper.evaluate_models(
            symbol=symbol,
            candles_m1=candles[Timeframe.M1],
            candles_m5=candles[Timeframe.M5],
            candles_m15=candles[Timeframe.M15],
            candles_h1=candles[Timeframe.H1]
        )
        # Evaluates:
        # Model 1: Momentum Continuation (EMA9/21 + displacement close)
        # Model 2: Pullback Scalp (FVG / OB / OTE 50%-79% / EMA21 zone + turn candle)
        # Model 3: Sweep / Breakout Scalp (Swing extreme sweep rejection or range expansion)

    # -------------------------------------------------------------
    # STAGE 5B: SMC FALLBACK (If no scalping setup triggered)
    # -------------------------------------------------------------
    if candidate is None:
        mtf_ctx = mtf_analyzer.analyze(symbol, candles)
        candidate = strategy_engine.scan_for_opportunities(mtf_ctx, m15)
        # Evaluates:
        # Weekly/Daily Liquidity Sweeps (PWL/PWH/PDL/PDH)
        # M15 SMC Order Block / FVG mitigations with HTF trend alignment

    if candidate is None:
        return outcome("NO_SETUP", "NO_PATTERN_DETECTED")

    # -------------------------------------------------------------
    # STAGE 6: CONFLUENCE SCORING & IDEMPOTENCY CHECK
    # -------------------------------------------------------------
    if is_duplicate_signal(candidate.id):
        return reject("TRADE_SKIPPED", "DUPLICATE_SIGNAL", "Signal already executed on this bar")

    required_score = 55.0 if candidate.is_scalp else 75.0
    profile_score = get_instrument_profile(symbol).min_confidence
    effective_min_score = max(required_score, profile_score)

    if candidate.score < effective_min_score:
        return reject("TRADE_SKIPPED", "LOW_CONFLUENCE", f"Score {candidate.score:.1f} < {effective_min_score:.1f}")

    # -------------------------------------------------------------
    # STAGE 7: SETUP QUALITY GATE VERIFICATION (G1 - G8)
    # -------------------------------------------------------------
    if config.smc_rulebook.gate_mode == "ENFORCE":
        verdict = setup_quality_gate.evaluate(candidate, mtf_ctx, m15)
        if not verdict.passed:
            return reject("TRADE_SKIPPED", "GATE_REJECTED", f"Hard gates failed: {verdict.hard_fails}")

    # -------------------------------------------------------------
    # STAGE 8 & 9: META-LABELING, GARCH VOLATILITY & KELLY MODULATION
    # -------------------------------------------------------------
    size_multiplier = 1.0

    if config.feature_flags.meta_labeling and not config.feature_flags.shadow_mode:
        m_ok, m_mult, m_reason = meta_labeling.evaluate_candidate(m15, candidate)
        if not m_ok:
            return reject("TRADE_SKIPPED", "META_LABELING_FILTER", m_reason)
        size_multiplier *= m_mult

    if config.feature_flags.volatility_targeting:
        vol_forecast = advanced_volatility.forecast(symbol, candles)
        size_multiplier *= min(1.0, vol_forecast.recommended_size_scale)

    kelly_risk_pct = None
    if config.feature_flags.kelly_sizing:
        kelly_eval = kelly_engine.evaluate(win_rate, reward_to_risk, tier.target_risk_pct, tier.ceiling_pct)
        if not kelly_eval.is_tradable:
            return reject("TRADE_SKIPPED", "KELLY_NEGATIVE_EXPECTANCY", kelly_eval.reason)
        kelly_risk_pct = kelly_eval.applied_risk_pct

    # -------------------------------------------------------------
    # STAGE 10: DETERMINISTIC LOT SIZING & CAPITAL FLOOR GUARD
    # -------------------------------------------------------------
    sizing = sizing_engine.calculate_lot_size(
        account=account,
        symbol_info=symbol_info,
        entry_price=candidate.entry_price,
        stop_loss=candidate.stop_loss,
        take_profit=candidate.take_profit,
        kelly_risk_pct=kelly_risk_pct,
        volatility_scale=size_multiplier
    )

    if not sizing.is_approved:
        return reject("TRADE_SKIPPED", "SIZING_REJECTED", sizing.rejection_reason)

    # -------------------------------------------------------------
    # STAGE 11: PORTFOLIO RISK AUTHORIZATION
    # -------------------------------------------------------------
    permitted, risk_reason = portfolio_risk.evaluate_new_order_permission(
        candidate=candidate,
        account=account,
        active_positions=order_manager.get_active_positions(),
        proposed_monetary_risk=sizing.monetary_risk,
        proposed_volume=sizing.volume
    )

    if not permitted:
        return reject("TRADE_SKIPPED", "PORTFOLIO_RISK_REJECTED", risk_reason)

    # -------------------------------------------------------------
    # STAGE 12 - 14: ORDER SUBMISSION & MT5 EXECUTION
    # -------------------------------------------------------------
    req_id = generate_unique_request_id(symbol)
    order_result = bridge.execute_trade(
        symbol=symbol,
        order_type=candidate.direction,
        volume=sizing.volume,
        stop_loss=candidate.stop_loss,
        take_profit=candidate.take_profit,
        request_id=req_id,
        magic=config.magic_number
    )

    if order_result.status == "SUCCESS":
        continuous_scalper.mark_signal_executed(candidate.id, symbol, candidate.entry_price, candidate.direction)
        alerts.alert_trade_opened(order_result)
        return outcome("TRADE_SENT", f"Opened {candidate.direction} {sizing.volume} lots on {symbol}")
    else:
        return reject("TRADE_ERROR", "BROKER_REJECTED", order_result.message)
```

---

## 3. Decision Matrix: Operational Cause-and-Effect Analysis

### What causes the bot to ENTER BUY?
1. **Model Qualification**:
   - *Momentum Continuation:* M5 candle closes bullish with body >= 45% of range and body >= 0.35 ATR, closing above previous high, with EMA9 > EMA21.
   - *Pullback Scalp:* Pullback into 38.2%–79% OTE or Bullish FVG with confirming bullish turn candle.
   - *Liquidity Sweep Reversal:* Candle pierces swing low or PDL/PWL and closes back above the level.
2. **Confluence Approval**: Total weighted score >= 55.0 (scalp) or >= 75.0 (SMC).
3. **Structure & Zone Gates (G1, G2, G6)**: H4/D1 trend is clear bullish (or counter-trend allowed with scalp agreement); entry is in Discount (<50% equilibrium).
4. **Valid Stop Loss (G8 & R9)**: Structural stop loss placed below recent low; SL > 0.
5. **Reward-to-Risk (G7)**: Net monetary gain at TP divided by monetary loss at SL >= 1.20 (scalp) or >= 2.00 (SMC).
6. **Risk Clearance**: Capital base >= $5.00; sizing volume >= minimum lot (0.01); actual risk <= 2.0% hard cap; account drawdown < 80% safety buffer; daily/weekly limits not breached.

### What causes the bot to ENTER SELL?
1. **Model Qualification**:
   - *Momentum Continuation:* M5 candle closes bearish with body >= 45% of range and body >= 0.35 ATR, closing below previous low, with EMA9 < EMA21.
   - *Pullback Scalp:* Pullback into 38.2%–79% OTE or Bearish FVG with confirming bearish turn candle.
   - *Liquidity Sweep Reversal:* Candle pierces swing high or PDH/PWH and closes back below the level.
2. **Confluence Approval**: Total weighted score >= 55.0 (scalp) or >= 75.0 (SMC).
3. **Structure & Zone Gates**: H4/D1 trend is clear bearish; entry is in Premium (>50% equilibrium).
4. **Valid Stop Loss**: Structural stop loss placed above recent high; SL > 0.
5. **Reward-to-Risk & Risk Clearance**: Identical strict risk validations as BUY.

---

### What causes the bot to REJECT a Trade?

| Rejection Condition | Source File & Line | Trigger Mechanism & Explanation |
| :--- | :--- | :--- |
| **No Stop Loss (R9.2 Violation)** | `order_manager.py:457-460` | `candidate.stop_loss <= 0.0`. Immediate non-negotiable rejection. |
| **Excessive Risk (> 2.0% R9 Cap)** | `position_sizing.py:316-337` | Calculated monetary risk / capital base > 2.0%. Hard-coded code ceiling. |
| **Insufficient Capital (< $5.00)** | `position_sizing.py:133-157` | Account balance or equity < $5.00 USD. Below operating capital floor. |
| **Min Lot Over-Risk (Small Account)** | `position_sizing.py:280-309` | 0.01 lot on the given SL distance risks > 2.0% of account equity. |
| **Toxic Spread (> 35% of SL)** | `PythonBridgeEA.mq5:2570-2580` | Live Ask-Bid spread exceeds 35% of SL distance or broker max spread cap. |
| **Insufficient R:R (< 1.2 or 2.0)** | `PythonBridgeEA.mq5:2593-2605` | Net expected monetary reward divided by monetary risk < min R:R ratio. |
| **Ranging Structure (R1 Gate G1)** | `setup_quality_gate.py:143-162` | Both H4 and D1 trends labeled `RANGING` without clear HH/HL or LH/LL. |
| **Counter-Trend Conflict (G6)** | `setup_quality_gate.py:242-263` | BUY proposed while H4/D1 is in strong bearish trend (counter-trend blocked). |
| **Breakout Chasing (R2 Gate G5)** | `setup_quality_gate.py:230-240` | Attempting to enter at the extreme of an extended breakout candle without pullback. |
| **Free Margin Depletion** | `PythonBridgeEA.mq5:2686-2704` | Required margin (`OrderCalcMargin`) > 50%–70% of free margin. |
| **Max Simultaneous Positions** | `portfolio_risk.py:418-422` | Number of open positions >= `max_simultaneous_positions` (default 3). |
| **Daily Loss Limit Breached** | `portfolio_risk.py:424-432` | Realized daily loss >= `max_daily_loss_percent` (2.0%–4.0%). |
| **Consecutive Losses Limit (3)** | `portfolio_risk.py:251-254` | 3 consecutive closed trade losses trigger circuit breaker halt. |
| **Symbol Cooldown Active** | `portfolio_risk.py:356-363` | 2 consecutive losses on this symbol trigger automated 15-minute cooldown. |
| **Safety Buffer Triggered** | `portfolio_risk.py:377-379` | Account drawdown reaches 80% of daily or total limit (e.g. 3.2% on 4% limit). |
| **Duplicate Signal Key** | `continuous_scalper.py:128-131` | A signal with the same symbol, timeframe, direction, and bar timestamp already executed. |
| **Watchdog Heartbeat Timeout** | `PythonBridgeEA.mq5:2492-2497` | Native EA has not received a heartbeat ping from Python for > 30 seconds. |

---

### What causes the bot to REDUCE Position Size?
1. **Reduced History Mode**: If a symbol has fewer bars than standard warm-up (e.g. BTCUSD.m), risk is cut by 50% (`InpReducedHistoryRiskFactor = 0.50`).
2. **Consecutive Loss Streak (2 Losses)**: When 2 consecutive losses occur, `effective_risk_multiplier` cuts base risk to 0.5x (`portfolio_risk.py:280-285`).
3. **Mild Drawdown Throttle**: If account drawdown approaches the safety buffer, `DrawdownThrottle` applies a 0.6x or 0.3x multiplier (`drawdown_throttle.py`).
4. **High Volatility Target Scaling**: When GARCH(1,1) or EWMA indicates extreme volatility expansion, `recommended_size_scale` compresses lot size (`volatility.py:200-240`).
5. **CUSUM Strategy Decay (2.5$\sigma$)**: When the sequential CUSUM test detects performance drift exceeding 2.5 standard deviations, risk is automatically halved (`decay_guard.py:40-60`).

---

### What causes the bot to STOP Trading?
1. **Hard Drawdown Lockout**: Realized daily loss >= daily limit (e.g. 4.0%) or total drawdown >= total limit (e.g. 8.0%). Triggers permanent circuit breaker for the day.
2. **3 Consecutive Losses**: Triggers automated pause for 30 minutes.
3. **Emergency Kill Switch**: Operator sends `/killswitch` via Telegram or clicks Kill Switch in Companion GUI. Closes all trades and halts engine.
4. **Capital Below Floor**: Account equity drops below $5.00 USD.
5. **CUSUM Decay Alarm (3.0$\sigma$)**: Cumulative underperformance exceeds 3.0 sigmas, indicating structural edge decay. Requires manual `/run` to resume.
6. **Bridge Watchdog Disconnection**: Socket loss between Python and MQL5 exceeding 30 seconds.

### What causes the bot to RESUME Trading?
1. **Daily Reset (00:00 Server Time)**: Daily loss counters, trade counts, and daily starting equity reset at midnight UTC/server time.
2. **Consecutive Loss Cooldown Expiry**: After 30 minutes, `_auto_recover_consecutive_loss_breaker()` automatically restores trading permission (`portfolio_risk.py:308-335`).
3. **Operator Override**: Sending `/run` or `/unpause` via Telegram or Companion GUI clears software pause flags.
4. **Symbol Cooldown Expiry**: 15-minute timer elapses following 2 losses on a specific asset.

---
**Audit Verification:** Decision pipeline, pseudocode, and trigger conditions verified against orchestrator and execution codebases.
