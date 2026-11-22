# MT5 001 — Complete Trading Strategy & SMC/ICT Forensic Inventory
**Forensic Technical Intelligence Audit**  
**Classification:** Quantitative Strategy Audit & Signal Architecture Report  
**System Target:** MT5 001 Automated Trading System  
**Auditor:** Principal Quantitative Trading Systems Architect & MQL5/Python Specialist  
**Date of Audit:** November 2026  

---

## 1. Strategy Classification & Implementation Hierarchy

An exhaustive forensic code examination was conducted across `src/execution/continuous_scalper.py`, `src/smc/strategy_engine.py`, `src/smc/smc_rulebook.py`, `src/engine/pipeline.py`, `src/strategies/`, and `mql5/Experts/PythonBridgeEA.mq5`.

Trading setups in the codebase are classified into six distinct operational categories:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                               OPERATIONAL DISPOSITION TABLE                             │
├───────────────────────────────┬──────────────────────┬─────────────────────────────────┤
│ Strategy / Setup Model        │ Implementation State │ Primary Source Location         │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 1. Momentum Continuation      │ FULLY IMPLEMENTED &  │ src/execution/continuous_       │
│    Scalp (M1/M5/M15)          │ ACTIVE IN PRODUCTION │ scalper.py:366-457              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 2. Pullback Scalp             │ FULLY IMPLEMENTED &  │ src/execution/continuous_       │
│    (FVG/OB/OTE/EMA21)         │ ACTIVE IN PRODUCTION │ scalper.py:459-567              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 3. Breakout / Liquidity-      │ FULLY IMPLEMENTED &  │ src/execution/continuous_       │
│    Sweep Scalp (M1/M5/M15)    │ ACTIVE IN PRODUCTION │ scalper.py:569-648              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 4. Weekly/Daily Liquidity     │ FULLY IMPLEMENTED &  │ src/smc/strategy_engine.py:     │
│    Reversals (PWL/PWH/PDL/PDH)│ ACTIVE (FALLBACK)    │ 227-329; weekly_daily.py:1-250  │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 5. Weekly/Daily Accepted Break│ FULLY IMPLEMENTED &  │ src/smc/strategy_engine.py:     │
│    Continuations (PWH/PWL)    │ ACTIVE (FALLBACK)    │ 238-243, 290-295                │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 6. M15 SMC Order Block / FVG  │ FULLY IMPLEMENTED &  │ src/smc/strategy_engine.py:     │
│    OTE Model (R1-R8)          │ ACTIVE (FALLBACK)    │ 244-261, 296-313                │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 7. Asian Range London Judas   │ FULLY IMPLEMENTED BUT│ src/smc/session_liquidity.py:   │
│    Session Sweep              │ CONDITIONALLY GATED  │ 46-175; strategy_engine.py:218  │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 8. Candlestick & Chart Pattern│ IMPLEMENTED & WIRED  │ src/patterns/candlesticks.py;   │
│    Confluence Engine (51 Pat.)│ VIA CONFLUENCE HOOK  │ chart_patterns.py; context.py   │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 9. 28-Video Institutional EA / Art  │ FULLY IMPLEMENTED BUT│ src/engine/pipeline.py:1-650;   │
│    of Trading 7-Gate Pipeline │ DISCONNECTED FROM BOT│ src/engine/skills/* (23 files)  │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 10. CISD (Change in State     │ IMPLEMENTED IN EXT.  │ src/strategies/cisd.py:1-120    │
│     of Delivery Leg Break)    │ MODULE; UNUSED LIVE  │ (Modular pipeline disabled)     │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 11. Trendline Liquidity Sweep │ IMPLEMENTED IN EXT.  │ src/strategies/trendline_       │
│     Reversal Model            │ MODULE; UNUSED LIVE  │ liquidity.py:1-150              │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 12. Volume-Price Distribution │ IMPLEMENTED IN EXT.  │ src/strategies/volume_          │
│     Accumulation Filter       │ MODULE; UNUSED LIVE  │ distribution.py:1-90            │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 13. SMT Intermarket           │ PARTIALLY CODED;     │ src/smc/smt.py:1-55             │
│     Divergence Engine         │ ORPHANED & DISCONNECTED                               │
├───────────────────────────────┼──────────────────────┼─────────────────────────────────┤
│ 14. BPR / Unicorn Model       │ PARTIALLY CODED;     │ src/smc/bpr_ifvg_helpers.py:    │
│     (Breaker + FVG Overlap)   │ ORPHANED & DISCONNECTED                               │
└───────────────────────────────┴──────────────────────┴─────────────────────────────────┘
```

---

## 2. In-Depth Forensic Analysis of Active Strategies

### Strategy 1: Momentum Continuation Scalp
- **Primary Source:** [`src/execution/continuous_scalper.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/execution/continuous_scalper.py#L366-L457)
- **Status:** **FULLY IMPLEMENTED AND ACTIVE IN PRODUCTION**
- **Target Timeframes:** M1, M5, M15 (Primary M5)
- **Supported Instruments:** EURUSD, GBPUSD, USDJPY, XAUUSD (Gold), BTCUSD.m
- **Philosophy:** High-probability continuation in the direction of strong institutional momentum. Enters when price exhibits an impulsive displacement candle breaking beyond the previous candle's extreme while aligning with fast exponential moving averages.
- **Market Analysis Methodology:**
  - Fast trend definition: 9-period EMA (`EMA9`) and 21-period EMA (`EMA21`).
  - Volatility calibration: 14-period True Range Average (`ATR14`).
  - Multi-timeframe context: M15 and H1 directional biases (`infer_timeframe_bias`) contribute up to +20 points of weighted confluence.
- **Exact Entry Logic:**
  - **BUY Setup:**
    1. Fast moving average alignment: `last.close > ema9` and `ema9 >= (ema21 - 0.10 * atr)`.
    2. Bullish displacement body: `last.is_bullish == True`.
    3. Body-to-range ratio: `last.body / last.range >= 0.45` (strong directional expansion).
    4. Minimum impulse threshold: `last.body >= 0.35 * atr`.
    5. Extreme break: `last.close > prev.high` OR (`prev.is_bullish and last.close > prev.close`).
  - **SELL Setup:**
    1. Fast moving average alignment: `last.close < ema9` and `ema9 <= (ema21 + 0.10 * atr)`.
    2. Bearish displacement body: `last.is_bearish == True`.
    3. Body-to-range ratio: `last.body / last.range >= 0.45`.
    4. Minimum impulse threshold: `last.body >= 0.35 * atr`.
    5. Extreme break: `last.close < prev.low` OR (`prev.is_bearish and last.close < prev.close`).
- **Confluence & Quality Adjustments:**
  - Higher-Timeframe (HTF) Alignment: M15 + H1 aligned adds +20.0 pts; partial alignment adds +14.0 pts; neutral adds +10.0 pts; counter-trend adds +5.0 pts (or rejected if `require_htf_agreement=True`).
  - Candle Anatomy: Body ratio >= 0.65 adds +7.0 pts; consecutive 3-bar displacement adds +5.0 pts.
  - RSI Positioning: Wilder RSI(14) between 45–68 (buys) or 32–55 (sells) adds +4.0 pts; RSI >= 78 (buys) or <= 22 (sells) deducts -8.0 pts.
  - Anti-Chasing Filter: If position in 20-bar range >= 0.95 with weak body (<20% range) and RSI >= 78, entry is strictly rejected.
- **Exact Exit Logic:**
  - **Stop Loss:** Sourced dynamically from recent swing extreme:
    - BUY: `raw_sl = min(last.low, prev.low) - (0.35 * atr)`.
    - SELL: `raw_sl = max(last.high, prev.high) + (0.35 * atr)`.
    - Clamped between broker minimum stop distance (`stops_level * 2.5`) and maximum cap (`1.5 * atr` or instrument max). Dedicated Gold calibration enforces minimum SL of `1.2 * atr` and 150 points.
  - **Take Profit:** Fixed at `sl_distance * target_rr`, where `target_rr` defaults to 1.5R - 2.0R.

---

### Strategy 2: Pullback Scalp (FVG / Order Block / OTE 50%–79%)
- **Primary Source:** [`src/execution/continuous_scalper.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/execution/continuous_scalper.py#L459-L567)
- **Status:** **FULLY IMPLEMENTED AND ACTIVE IN PRODUCTION**
- **Target Timeframes:** M1, M5, M15
- **Philosophy:** Institutional re-accumulation / re-distribution. Price surges, creates an imbalance (FVG) or touches an Order Block / EMA21 zone within the Optimal Trade Entry (OTE) Fibonacci retracement zone (38.2%–79%), and prints a confirming reversal/turn candle.
- **Exact Entry Logic:**
  - **BUY Setup:**
    1. Active swing window: 12-candle lookback determining `swing_high` and `swing_low`.
    2. Retracement depth: `retracement = (swing_high - last.low) / (swing_high - swing_low)`.
    3. Zone qualification: `0.35 <= retracement <= 0.82` OR recent Bullish FVG touched (`last.low <= c_right.low and last.close >= c_left.high`) OR pullback into EMA21 (`abs(last.low - ema21) <= 0.45 * atr and last.close > ema21`).
    4. Turn confirmation: `last.is_bullish == True` OR lower wick rejection (`last.lower_wick / last.range >= 0.45 and last.close > prev.low`).
    5. Moving average safety: `ema9 >= (ema21 - 0.25 * atr)`.
  - **SELL Setup:**
    1. Retracement depth: `retracement = (last.high - swing_low) / (swing_high - swing_low)`.
    2. Zone qualification: `0.35 <= retracement <= 0.82` OR Bearish FVG touched OR pullback into EMA21.
    3. Turn confirmation: `last.is_bearish == True` OR upper wick rejection (`last.upper_wick / last.range >= 0.45 and last.close < prev.high`).
    4. Moving average safety: `ema9 <= (ema21 + 0.25 * atr)`.
- **Exit Logic:**
  - BUY SL: `min(last.low, prev.low) - (0.40 * atr)`.
  - SELL SL: `max(last.high, prev.high) + (0.40 * atr)`.
  - TP: Minimum 1.5R (clamped to 2.0R for Day Trade M15 setups).

---

### Strategy 3: Breakout / Liquidity-Sweep Scalp
- **Primary Source:** [`src/execution/continuous_scalper.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/execution/continuous_scalper.py#L569-L648)
- **Status:** **FULLY IMPLEMENTED AND ACTIVE IN PRODUCTION**
- **Target Timeframes:** M1, M5, M15
- **Philosophy:** Dual-mode liquidity capture. Identifies false breakout liquidity sweeps (turtle soup) when price pierces a 10-bar swing extreme and snaps back, or aggressive range expansion breakouts with expanding volume.
- **Exact Entry Logic:**
  - **Model 3A: Liquidity-Sweep Reversal (Rule R4):**
    - BUY: `last.low < prior_low and last.close > prior_low` (pierces low, closes back inside range).
    - SELL: `last.high > prior_high and last.close < prior_high` (pierces high, closes back inside range).
  - **Model 3B: Range-Expansion Breakout:**
    - BUY: `last.is_bullish and last.close > prior_high and last.body >= 0.45 * atr`.
    - SELL: `last.is_bearish and last.close < prior_low and last.body >= 0.45 * atr`.
  - **Volume Confirmation:** Requires `last.tick_volume >= 1.25 * avg_volume` for breakout validation (+3.0 pts).
- **Exit Logic:**
  - BUY SL: `min(last.low, prev.low) - (0.40 * atr)`.
  - SELL SL: `max(last.high, prev.high) + (0.40 * atr)`.
  - TP: Anchored to opposite liquidity barrier with R:R >= 1.5.

---

### Strategy 4: Weekly / Daily Liquidity Sweep Reversals & Breaks
- **Primary Source:** [`src/smc/strategy_engine.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/smc/strategy_engine.py#L227-L329), [`src/smc/weekly_daily.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/smc/weekly_daily.py#L1-L250)
- **Status:** **FULLY IMPLEMENTED AND ACTIVE (SMC FALLBACK)**
- **Target Timeframes:** W1 & D1 Context -> M15 Execution
- **Philosophy:** Canonical ICT institutional liquidity framework. Institutional market makers engineer liquidity beyond previous week high/low (PWH/PWL) and previous day high/low (PDH/PDL). A sweep without acceptance signals an aggressive multi-day reversal.
- **Reference Levels Tracked:**
  - PWH (Previous Week High), PWL (Previous Week Low), PWC (Previous Week Close), PWM (Previous Week Midpoint).
  - PDH (Previous Day High), PDL (Previous Day Low), PDC (Previous Day Close), PDM (Previous Day Midpoint).
- **Exact Entry Logic:**
  - **Bullish Reversal (`PWL_SWEEP` / `PDL_SWEEP`):**
    - M15 candle pierces PWL or PDL: `c.low < level_price`.
    - Candle body closes back above level: `c.close > level_price` (R4 close-back-inside).
    - Requires M15 Market Structure event confirming reversal (CHoCH or BOS).
    - Minimum confluence score: >= 75.0 / 100.0.
  - **Bearish Reversal (`PWH_SWEEP` / `PDH_SWEEP`):**
    - M15 candle pierces PWH or PDH: `c.high > level_price`.
    - Candle body closes back below level: `c.close < level_price`.
    - Confirmed by M15 bearish structural event.
  - **Continuation Models (`PWH_ACCEPTED_BREAK` / `PWL_ACCEPTED_BREAK`):**
    - Price breaks level and completes multiple consecutive candle closes outside the range, followed by a retest holding as support/resistance.
- **Exit Logic:**
  - Stop Loss: Placed strictly beyond the sweep wick extreme (`sweep_extreme +- 2 pips`).
  - Take Profit: Anchored at opposite daily/weekly reference pool (e.g. swept PDL targets PDH or PWM).
  - Enforces minimum R:R >= 2.0.

---

### Strategy 5: M15 Institutional SMC Order Block & FVG (Rules R1–R8)
- **Primary Source:** [`src/smc/strategy_engine.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/smc/strategy_engine.py#L244-L261), [`src/smc/fvg_ob.py`](file:///C:/Users/Gackstone_Baraka/Downloads/MT5%20001/src/smc/fvg_ob.py#L200-L380)
- **Status:** **FULLY IMPLEMENTED AND ACTIVE (SMC FALLBACK)**
- **Target Timeframes:** H4/H1 Bias -> M15 Execution
- **Philosophy:** 6-Step SMC Entry Model (Rule R8): Trend definition on HTF, pullback into discount/premium POI, LTF structural confirmation, entry on mitigation of Order Block or FVG.
- **Exact Entry Logic:**
  1. HTF Trend Alignment: H4 and H1 trend must match trade direction (Rule R1).
  2. Equilibrium Filter: Buys in Discount (<50% swing range), Sells in Premium (>50% swing range) (Rule R7).
  3. Valid Point of Interest (POI):
     - Order Block (Rule R5): Last opposing candle before displacement impulse (body >= 1.2 * ATR or leaving FVG) that breaks structure (BOS).
     - Fair Value Gap (Rule R6): 3-candle imbalance with gap >= `max(1.5 pips, 0.3 * ATR)`.
  4. LTF Confirmation: `StructureStateMachine` must confirm `BOS_CONFIRMED` following a `CHOCH_WARNING` and subsequent pullback.
  5. Confluence Scoring: Minimum score >= 75.0/100.
- **Exit Logic:**
  - SL: Sourced from OB invalidation extreme or sweep swing point.
  - TP: Next unmitigated liquidity pool (BSL/SSL/EQH/EQL) with R:R >= 2.0.

---

## 3. Dedicated SMC and ICT Forensic Audit

This section examines the mathematical and programmatic implementation of every Smart Money Concept claimed or referenced in the bot.

### A. Market Structure Forensic Audit

| SMC Concept | Implemented? | Code Location | Exact Mathematical / Programmatic Definition | Operational Reality & Limitations |
| :--- | :---: | :--- | :--- | :--- |
| **Higher Highs (HH) & Higher Lows (HL)** | **YES** | `src/smc/market_structure.py:103-106` | Symmetrical lookback window $k=5$. Current high $H_i > H_j$ for all $j \in [i-k, i-1]$ and $H_i \ge H_j$ for $j \in [i+1, i+k]$. Uptrend strictly requires $H_{\text{last}} > H_{\text{prev}}$ AND $L_{\text{last}} > L_{\text{prev}}$. | Genuinely implemented. Requires $2k+1 = 11$ bars to confirm a swing point, introducing a 5-bar lag before a swing is officially registered. |
| **Lower Highs (LH) & Lower Lows (LL)** | **YES** | `src/smc/market_structure.py:105-106` | Symmetrical lookback window $k=5$. Downtrend strictly requires $H_{\text{last}} < H_{\text{prev}}$ AND $L_{\text{last}} < L_{\text{prev}}$. | Genuinely implemented. Prevents false trend labeling in ranging markets. |
| **Break of Structure (BOS)** | **YES** | `src/smc/market_structure.py:123-173` | In an established uptrend, candle body close beyond last swing high: $C_t > H_{\text{swing}}$ (when `bos_body_close_required=True`). | Genuinely implemented. Body close strictly enforced; wicks do not trigger BOS. |
| **Change of Character (CHoCH)** | **YES** | `src/smc/market_structure.py:129-156`; `structure_confirmation.py:20-70` | First candle body close opposing the prevailing trend (e.g. in downtrend, $C_t > H_{\text{last\_LH}}$). | **Genuinely implemented as a multi-stage state machine.** CHoCH is strictly treated as an early warning (`CHOCH_WARNING`), never an immediate entry trigger. |
| **Market Structure Shift (MSS)** | **YES** | `src/smc/market_structure.py:126-153` | A structural break accompanied by institutional displacement: `c.body / c.range >= displacement_ratio_min` (0.60). | Genuinely implemented. Differentiates normal BOS from high-velocity displacement shifts. |
| **Internal vs. External Structure** | **PARTIAL** | `src/engine/skills/swing_hierarchy.py:1-120` | Classifies swings into Major (External) and Minor (Internal) based on ATR depth and bar count. | Implemented in `src/engine/skills`, but in the live production engine (`continuous_scalper`), internal structure is approximated via 12-bar swing windows. |

---

### B. Liquidity Intelligence Forensic Audit

| Liquidity Concept | Implemented? | Code Location | Exact Mathematical / Programmatic Definition | Operational Reality & Limitations |
| :--- | :---: | :--- | :--- | :--- |
| **Buy-Side Liquidity (BSL) & Sell-Side (SSL)** | **YES** | `src/smc/liquidity.py:46-125` | Unmitigated confirmed swing highs (BSL) and swing lows (SSL) registered as resting stop zones. | Genuinely implemented. Sourced from M15, H1, H4 swing extremes. |
| **Equal Highs (EQH) & Equal Lows (EQL)** | **YES** | `src/smc/liquidity.py:65-98` | Two consecutive swing highs where $\|H_1 - H_2\| \le \text{tolerance}$ ($2.0 \times \text{pip\_size}$). | Genuinely implemented. Acts as primary liquidity targets for take-profit anchoring. |
| **Liquidity Sweeps (Stop Hunts)** | **YES** | `src/smc/liquidity.py:127-185`; `smc_rulebook.py:R4` | Price pierces liquidity level ($H_t > \text{BSL}$ or $L_t < \text{SSL}$) and closes back inside range ($C_t < \text{BSL}$ or $C_t > \text{SSL}$) within 1–2 bars. | **Genuinely implemented and strictly enforced.** Prevents entering on breakouts that fail to accept outside the range. |
| **Previous Day High/Low (PDH/PDL)** | **YES** | `src/smc/weekly_daily.py:45-120` | Exact High/Low of previous completed D1 candle, filtering Sunday micro-bars. | Fully implemented and updated at 00:00 UTC daily. |
| **Previous Week High/Low (PWH/PWL)** | **YES** | `src/smc/weekly_daily.py:45-120` | Exact High/Low of previous completed W1 candle. | Fully implemented and updated weekly. |
| **Asian Session Range & Judas Swing** | **YES** | `src/smc/session_liquidity.py:46-175` | Computes Asian High/Low between 00:00–09:00 UTC. Detects London sweeps (08:00–12:00 UTC) piercing Asia extremes and closing back inside. | Fully implemented in module, but disabled when `session_liq_enabled=False` in scalping mode. |

---

### C. Institutional Price Delivery Forensic Audit

| Delivery Primitive | Implemented? | Code Location | Exact Mathematical / Programmatic Definition | Operational Reality & Limitations |
| :--- | :---: | :--- | :--- | :--- |
| **Fair Value Gap (FVG)** | **YES** | `src/smc/fvg_ob.py:45-198` | Bullish: $L_{t} > H_{t-2}$ with $(L_t - H_{t-2}) \ge \max(1.5\text{ pips}, 0.3 \times \text{ATR})$. Bearish: $H_{t} < L_{t-2}$. | Genuinely implemented. Tracks formation price, midpoint (consequent encroachment), and subsequent candle mitigation. |
| **Inverse FVG (IFVG)** | **YES** | `src/smc/fvg_ob.py:128-195` | When an active Bullish FVG is fully breached ($C_{\text{future}} < \text{bottom}$), it is inverted into a Bearish IFVG resistance zone. | Genuinely implemented and tracked in memory. |
| **Order Block (OB)** | **YES** | `src/smc/fvg_ob.py:200-380` | Bullish OB: Last bearish candle prior to a bullish impulse satisfying: 1) Body displacement $\ge 1.2 \times \text{ATR}$ or leaves FVG; 2) Impulse leg body-closes beyond prior swing high (BOS). | **Institutional-grade implementation.** Unlike naive scripts that flag every opposite candle, this strictly requires displacement and structural break. |
| **Breaker Block** | **PARTIAL** | `src/smc/fvg_ob.py:382-405`; `bpr_ifvg_helpers.py` | A failed order block that was violated by price and retested from the opposite side. | Implemented in helper functions, but rarely triggers in production due to stringent multi-bar conditions. |
| **Mitigation Blocks** | **NO** | N/A | Referenced in documentation; no dedicated detector class exists. | **NOT IMPLEMENTED.** |
| **Balanced Price Range (BPR)** | **DORMANT** | `src/smc/bpr_ifvg_helpers.py:13-110` | Geometric intersection where a bullish FVG and bearish FVG overlap in the same price range. | **Coded but disconnected.** Function `detect_bpr_zones()` exists but is never called in the live orchestrator. |
| **Unicorn Model (Breaker + FVG)** | **DORMANT** | `src/smc/bpr_ifvg_helpers.py:154-185` | Spatial overlap of an unmitigated Breaker Block and Fair Value Gap. | **Coded but disconnected.** Flag `enable_unicorn: true` exists in config, but function is never called in `orchestrator.py`. |
| **Premium & Discount Equilibrium** | **YES** | `src/smc/fvg_ob.py:408-435`; `setup_quality_gate.py:164-198` | Range equilibrium $= (H_{\text{swing}} + L_{\text{swing}}) / 2.0$. Buys require entry $< 0.50$ (Discount); Sells require entry $> 0.50$ (Premium). | Genuinely implemented. In Phase 4 ablation, G2 was moved to SHADOW (+5 soft bonus) because hard blocking eliminated valid strong-trend shallow pullbacks. |

---

### D. Advanced ICT Concepts Forensic Audit

| ICT Concept | Implemented? | Code Location | Exact Definition / Verification | Operational Status |
| :--- | :---: | :--- | :--- | :--- |
| **Optimal Trade Entry (OTE)** | **YES** | `src/smc/fvg_ob.py:415-430`; `continuous_scalper.py:498-535` | Fibonacci retracement levels: 61.8% (`0.618`), 70.5% (`0.705` optimal), 78.6% (`0.786`). | Genuinely implemented. Used in Pullback Scalping Model and SMC OTE candidate scoring. |
| **SMT Divergence** | **ORPHANED** | `src/smc/smt.py:1-55` | Correlation divergence between correlated assets (e.g. EURUSD makes lower low while GBPUSD makes higher low). | **Code exists in `smt.py` but is NOT imported or called anywhere in `src/`. Completely disconnected.** |
| **Judas Swing** | **YES** | `src/smc/session_liquidity.py:110-175` | False directional move during London open sweeping Asian session high/low before reversing into true daily expansion. | Fully implemented in session engine; active when session liquidity is enabled. |
| **Power of Three (AMD)** | **PARTIAL** | `src/engine/skills/market_phase_labeler.py` | Accumulation (Asia), Manipulation (London Judas), Distribution (New York). | Labeled in `market_phase_labeler.py`, but used purely as contextual metadata, not an explicit entry state machine. |
| **Kill Zones** | **YES** | `src/core/sessions.py:1-150` | Asian (00:00–08:00 UTC), London (07:00–10:00 UTC), New York (12:00–15:00 UTC), London Close (15:00–17:00 UTC). | Fully implemented. Used to score setup confluence (+5.0 pts during Kill Zones). |

---

## 4. Disconnected, Dormant & Experimental Strategy Modules

A critical finding of this audit is the existence of several sophisticated strategy modules that are fully coded in the repository but completely disconnected from the active production loop:

1. **The Institutional EA / Art of Trading 28-Video Pipeline (`src/engine/pipeline.py`)**:
   - Contains 23 separate skill modules implementing a 7-gate confirmation framework (H0 through G7).
   - Includes `protected_swing_marker.py`, `five_check_model.py`, `ifvg_inversion.py`, `inducement_ob_entry.py`, `range_liquidity_loop.py`, `breakout_trap_classifier.py`.
   - **Audit Finding:** This pipeline is executed ONLY in `scripts/run_institutional_ea_backtest.py` and `tests/test_institutional_ea_skills.py`, and referenced in `src/manual_mgmt/assessor.py`. The live bot engine (`scripts/start_bot.py` -> `TradingBotOrchestrator`) does NOT import or call `InstitutionalEaPipeline`.
2. **Modular Strategy Pipeline Adapters (`src/strategies/`)**:
   - `src/strategies/cisd.py` (Change in State of Delivery): Detects liquidity sweep + body close through opening price of manipulation leg.
   - `src/strategies/trendline_liquidity.py`: Generates trendlines across swings and trades false breakouts.
   - `src/strategies/volume_distribution.py`: Tick-volume accumulation filter.
   - **Audit Finding:** Gated behind `config.upgrade_enabled` and `config.modular_strategy_enabled` (both default `False`). In production, `start_bot.py` uses legacy `SmcStrategyEngine` and `ContinuousScalpingEngine`.
3. **SMT Divergence Engine (`src/smc/smt.py`)**:
   - Implements `detect_smt_divergence()`.
   - **Audit Finding:** File is completely unreferenced by any other module in `src/`. Zero production impact.
4. **BPR and Unicorn Zones (`src/smc/bpr_ifvg_helpers.py`)**:
   - Implements `detect_bpr_zones()` and `detect_unicorn_zones()`.
   - **Audit Finding:** Disconnected from `SmcStrategyEngine.scan_for_opportunities()`.

---
**Audit Verification:** Every strategy formula, condition, parameter, and operational status verified against repository source code.
