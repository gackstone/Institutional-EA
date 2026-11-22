# Institutional EA Strategy Knowledge Migration Changelog

This document tracks all strategy rules, indicators, thresholds, and execution mechanisms migrated into the MT5 Python engine and `Institutional EA Cloud` AI coach.

Every item is classified under the Migration Protocol:
- **REPLACED**: Legacy item contradicted an Institutional EA video card. Replaced with canonical video rule.
- **CORRECTED**: Legacy item was conceptually aligned but vague, missing closed-candle validation, or misconfigured.
- **ADDED**: New Institutional EA skill/rule previously missing in the repository.
- **KEPT [ASSUMPTION] / [EXISTING]**: Non-conflicting quantitative risk, execution hygiene, or broker compatibility layers preserved.

---

## 1. Migration Records

### 1.1 Stop Loss Management & Break-Even (`[VIDEO 12]`)
* **Old Rule**: Automatically moved stop loss to breakeven (`open_price + buffer`) upon reaching `+1.0R` (or `+0.5R` in continuous scalping mode). Configured via `enable_break_even: true` in `config/risk_config.json`.
* **Video Card**: Video 12 (`stop_management_policy`). *"A trade can reach target but many traders get stopped first because they move the stop to break even too early; price does not know where you entered, and a normal pullback can revisit the entry without invalidating the setup... Move your stop when the market gives you a reason, not just because you're finally in profit."*
* **Status**: **REPLACED**.
* **New Implementation**: Default `be_move_mode = "structure_only"`. Fixed-R break-even is disabled by default (`enable_break_even: false`). Stop loss trails only when a new structural level forms that invalidates the setup if broken (e.g., a new protected low above entry after a confirmed BOS) `[DERIVED]`. Fixed-R BE preserved only as an optional, off-by-default mode tagged `[ASSUMPTION]`.

### 1.2 Premium / Discount Location Gate (`[VIDEO 2]`)
* **Old Rule**: Gate G2 was disabled (`"g2_zone_enabled": false` in `config/strategy_config.json`). When checked, it used an OR condition across M15/H1/H4 swings rather than the specific structural impulse leg.
* **Video Card**: Video 2 (`premium_discount_filter`). *"Take the last move up from the protected low to the high, cut it in half. Top half = premium (expensive), bottom half = discount (cheap). In an uptrend buy in discount, not just anywhere. A missed trade costs nothing."*
* **Status**: **CORRECTED**.
* **New Implementation**: Gate G2 is mandatory and enabled by default. Evaluates 50% equilibrium strictly across the active protected leg (`protected_low` to `swing_high` for bullish; `protected_high` to `swing_low` for bearish). Bullish entries permitted only when entry $\le 50\%$ equilibrium; bearish entries only when entry $\ge 50\%$.

### 1.3 First Pullback vs Inducement (`[VIDEO 1]`)
* **Old Rule**: Continuous scalper and legacy strategy bought the first pullback into an EMA or FVG/OB directly.
* **Video Card**: Video 1 (`inducement_ob_entry`). *"The first pullback after a push looks like the perfect buy but is bait; stops sit under it... price drops, takes the stops, and taps the order block. Do not buy the first pullback (inducement). Wait for sweep of the pullback low, then a bullish close in the block."*
* **Status**: **REPLACED**.
* **New Implementation**: Implemented `inducement_ob_entry`. Pullback lows between the OB and the new swing high are marked as inducement (`IND`). Entries require an inducement liquidity sweep, followed by a bullish close inside the Order Block.

### 1.4 Trend Definition by Structure vs Moving Averages (`[VIDEO 4]`)
* **Old Rule**: Continuous scalper used EMA9 > EMA21 crossovers to determine trend direction. Legacy market structure used fallbacks based on recent candle closes.
* **Video Card**: Video 4 (`trend_by_structure`). *"Trend is structure, not the last candle. Higher highs + higher lows = uptrend. A hard drop that stops above the last higher low changes nothing. Only a candle close below that low puts the uptrend in trouble."*
* **Status**: **REPLACED**.
* **New Implementation**: Moving-average trend filters deactivated. Trend classified as `BULL` while HH/HL structure is intact and no closed candle occurs below the last protected low; `BEAR` for mirror; otherwise `RANGE/TRANSITION`. Single large candles cannot flip trend without closing through protected levels.

### 1.5 Swing Low Identification: Protected Low vs Fractals (`[VIDEO 3]`)
* **Old Rule**: Symmetrical 5-bar fractal scanner (`find_swing_points`) marked every local peak and trough as significant swings.
* **Video Card**: Video 3 (`protected_swing_marker`). *"Many swing lows exist; most are noise. The one that counts: the low that started the move that broke the last high. Mark the low that broke something."*
* **Status**: **REPLACED**.
* **New Implementation**: Implemented `protected_swing_marker`. Filters out fractal noise; only marks the swing low that directly preceded a confirmed body-close BOS as `protected_low`.

### 1.6 Breakout vs Trap Confirmation (`[VIDEO 6]`)
* **Old Rule**: Scalping engine opened breakout trades immediately upon the first candle piercing a swing level.
* **Video Card**: Video 6 (`breakout_trap_classifier`). *"While the candle is still forming you cannot know. Do not decide; wait for the close. Trap: falls straight back inside. Breakout: close above AND the next candle closes above too. The second close is the confirmation."*
* **Status**: **REPLACED**.
* **New Implementation**: Implemented `breakout_trap_classifier`. Evaluates closed candles only. Requires two consecutive closes beyond the level for `BREAKOUT_CONFIRMED`. If price closes back inside, classified as `TRAP`. Breakout trade entries blocked until 2-close confirmation.

### 1.7 Liquidity Role: Context vs Trigger (`[VIDEO 7]`)
* **Old Rule**: Liquidity sweep models in scalper and trendline strategies triggered direct trade entries upon level penetration.
* **Video Card**: Video 7 (`liquidity_mapper`). *"Liquidity is not a signal. It tells you where to watch, not what to do."*
* **Status**: **CORRECTED**.
* **New Implementation**: `liquidity_mapper` restricted to generating watchlists for setup sweeps and anchoring Take-Profit targets (`TP` at resting buy-side/sell-side liquidity). Direct trade execution from raw liquidity levels is prohibited.

### 1.8 FVG Role: Imbalance Context vs Limit Order Magnet (`[VIDEO 11]`)
* **Old Rule**: Pending limit order manager (`limit_orders.py`) placed standing limit orders at FVG midpoints assuming price must fill them.
* **Video Card**: Video 11 (`fvg_context_guard`). *"An FVG is not a magnet. Price does not have to come back. Context tells you if the return really matters."*
* **Status**: **CORRECTED**.
* **New Implementation**: Implemented `fvg_context_guard`. Prohibits standing limit orders based solely on FVG existence. FVGs only enter trading logic when accompanied by sweep and closed-candle return confirmation.

### 1.9 FVG Quality Scoring (`[VIDEO 9]`)
* **Old Rule**: Only checked minimum ATR size (`gap >= 0.3 * ATR`). Treated gaps formed in ranges the same as impulse gaps.
* **Video Card**: Video 9 (`fvg_quality_score`). *"A gap is only as good as the move that made it. Weak: formed inside a range, nothing broken. Strong: formed when price broke the previous high with body close."*
* **Status**: **ADDED**.
* **New Implementation**: Added `fvg_quality_score`. Scores gaps: +2 for body-close BOS; +0 for range gaps (rejected by default); -1/-2 penalty if unswept liquidity sits within $N \times \text{ATR}$ below the gap `[ASSUMPTION]`.

### 1.10 FVG Return Depth & Close Classification (`[VIDEO 10]`)
* **Old Rule**: Marked FVG as mitigated whenever a candle wick touched `low <= bottom`.
* **Video Card**: Video 10 (`fvg_return_classifier`). *"Depth is not the signal; watch the close. Bullish held: candle wicks into gap but closes back above the middle (50%). Confirmed: next candle pushes away strongly. Broken: candle closes through the gap -> setup off."*
* **Status**: **ADDED / CORRECTED**.
* **New Implementation**: Added `fvg_return_classifier`. Evaluates closed candles to classify returns into `TAP`, `HELD` (close > 50%), `CONFIRMED` (strong push away `[ASSUMPTION]`), and `BROKEN` (close through gap -> immediate cancellation).

### 1.11 Inversion FVG / Failed FVG (`[VIDEO 8]`)
* **Old Rule**: Marked `is_inverse=True` when a candle closed through an FVG, but provided no retest entry confirmation logic.
* **Video Card**: Video 8 (`ifvg_inversion`). *"A close through an FVG does not kill it. Support flips to resistance (inversion). Next candle drops away = confirmation. Close back above = trap."*
* **Status**: **ADDED**.
* **New Implementation**: Added `ifvg_inversion`. Triggers short on confirmation close after inversion retest. Stop loss placed above far edge of gap `[ASSUMPTION]`; target at next opposing liquidity `[ASSUMPTION]`.

### 1.12 Middle of the Range Filtering (`[VIDEO 13]`)
* **Old Rule**: Executed scalps across all locations within a range.
* **Video Card**: Video 13 (`range_location_filter`). *"Middle of the range: far from both edges, no clear advantage. Don't force a decision. Movement is not location. Sometimes the best location is somewhere else."*
* **Status**: **ADDED**.
* **New Implementation**: Added `range_location_filter`. Detects ranges ($\ge 2$ touches at support/resistance). Outputs `NO_TRADE_MIDDLE` when price is in the 40%–60% middle band of the range `[ASSUMPTION]`.

### 1.13 Entry Quality & Anti-Chasing Guard (`[VIDEO 14]`)
* **Old Rule**: Checked price drift but permitted up to 50 points deviation without checking live reward-to-risk.
* **Video Card**: Video 14 (`entry_quality_guard`). *"Right direction, bad entry. Entering late expands risk and shrinks room to target. Don't chase the move; wait for a new setup or let it go."*
* **Status**: **ADDED**.
* **New Implementation**: Added `entry_quality_guard`. Recomputes real risk, room, and $R:R = \text{room} / \text{risk}$ from actual fill price. Rejects orders if $R:R < 1.5$ (`min_rr`) or if entry extends $> 1.0 \times \text{planned risk}$ beyond setup level `[ASSUMPTION]`. Stop loss widening strictly prohibited.

### 1.14 Impulse Momentum Decay Monitor (`[VIDEO 15]`)
* **Old Rule**: None (missing).
* **Video Card**: Video 15 (`structure_momentum_monitor`). *"New HH != strong trend. When moves get smaller this usually means the trend may end or enter a big correction. Caution flag, not a reversal trigger."*
* **Status**: **ADDED**.
* **New Implementation**: Added `structure_momentum_monitor`. Measures length of consecutive impulse legs. Flags `momentum = DECAYING` when 2–3 successive legs contract. Reduces position sizing or blocks continuation entries `[DERIVED]`; trend is never flipped until CHOCH (close through protected low).

### 1.15 Closed Candles Only & Data Ingestion Fixes (Ground Rule 4)
* **Old Implementation**: `historical_loader.py` fetched rates from pos 0 and marked bar 0 as `complete=True`. Direct MT5 polling in `market_data.py` did not adjust for broker UTC offset.
* **Ground Rule 4**: All decisions use closed candles only (Videos 6, 10, 15). Never act on a still-forming candle. Drop the last, forming bar from `copy_rates_*`.
* **Status**: **CORRECTED**.
* **New Implementation**: Data loader slices off bar 0 (`copy_rates_from_pos(..., 1, count)` or drops index 0). Ingestion applies `broker_utc_offset` across all MT5 endpoints.

### 1.16 Default Execution Mode & Live Trading Guard (Ground Rule 3)
* **Old Configuration**: `config/settings.json` specified `"execution_mode": "RETAIL"`.
* **Ground Rule 3**: Demo/paper mode by default. Live trading requires explicit `LIVE_TRADING_ENABLED=true` config flag, max daily loss limit, and kill switch.
* **Status**: **CORRECTED**.
* **New Implementation**: Default `execution_mode` set to `"DEMO"`. Mandatory `LIVE_TRADING_ENABLED=true` guard enforced in `AppConfig`. If not explicitly set to true, execution falls back safely to DEMO.


---

## 2. Part 2 "Art of Trading" Batch Migration Records (13 Videos)

### 2.1 Unified CHOCH Definition (`[VIDEO 15, ART-09, ART-10]`)
* **Amends**: Harmonizes Part 1 Video 15 and Video 4 with Part 2 Cards 09 & 10.
* **Rule**: CHOCH = the first CLOSE beyond the most recent opposite swing, against the prior trend. BOS = close beyond prior swing in the trend's direction.
* **Status**: **AMENDED / UNIFIED**.
* **Implementation**: Unified across all structure modules. Wick penetrations do not constitute CHOCH or BOS; only completed candle bodies closing beyond the swing level confirm structure shifts.

### 2.2 Liquidity Sweeps Require Structure Confirmation (`[ART-06, ART-10]`)
* **Amends**: Part 1 Video 5 (`sweep_fvg_entry`).
* **Rule**: *"A sweep alone is not enough. Not every wick is a sweep. Let structure confirm it."* [ART-06, ART-10].
* **Status**: **AMENDED**.
* **Implementation**: `sweep_fvg_entry` and `five_check_model` strictly require a CHOCH/BOS close after the sweep. A raw wick through a liquidity pool followed by a return is only a candidate sweep; it cannot trigger an entry until an opposite swing high/low is body-closed.

### 2.3 Dual Breakout Confirmation & Retest-Hold (`[VIDEO 6, ART-10]`)
* **Amends**: Part 1 Video 6 (`breakout_trap_classifier`).
* **Rule**: Two valid breakout forms: (1) close beyond + second close beyond, OR (2) close beyond + retest of the broken level that holds as support/resistance.
* **Status**: **AMENDED**.
* **Implementation**: Configurable `breakout_confirm_mode = "second_close_or_retest"` `[ASSUMPTION]`. Both forms validate that a breakout stays outside the level.

### 2.4 TRAP Flag Feeds Reversal Setups (`[ART-10, ART-06]`)
* **Amends**: Part 1 Video 6 (which stated TRAP flag produces no trade action).
* **Rule**: Wick through level, close back inside, followed by a break of the last opposite swing (CHOCH) = valid reversal context.
* **Status**: **AMENDED**.
* **Implementation**: `sweep_breakout_classifier` emits reversal setup context upon TRAP + CHOCH. Entry executes when price pulls back into a discount/premium FVG or OB.

### 2.5 Swing Hierarchy & Fractal Ranking (`[ART-02]`)
* **Amends**: Replaces single symmetrical $k=5$ fractals.
* **Rule**: Three recursive ranks: Short-Term High/Low (STH/STL, $n=1$), Intermediate-Term High/Low (ITH/ITL, STH with lower STH on each side), Long-Term High/Low (LTH/LTL, ITH with lower ITH on each side). Mark only after confirmation lag; zero repainting.
* **Status**: **REPLACED**.
* **Implementation**: Added `swing_hierarchy`. STH used for LTF entries; ITH used for structure/BOS/CHOCH and protected swings `[ASSUMPTION]`; LTH used for HTF external targets and macro bias.

### 2.6 Order Block Qualification: BOS + Imbalance Required (`[ART-09]`)
* **Amends**: Part 1 Video 1 and legacy SMC OB detection.
* **Rule**: *"The move must break structure AND leave an imbalance (a gap). No break, no gap = just a candle."* [ART-09].
* **Status**: **AMENDED**.
* **Implementation**: Added `order_block_detector`. Rejects any candidate OB unless the originating impulse leg creates a body-close BOS AND leaves an unmitigated FVG.

### 2.7 Premium / Discount Range Invalidation (`[ART-07]`)
* **Amends**: Part 1 Video 2 (`premium_discount_filter`).
* **Rule**: Range is drawn from swing low to swing high. If price closes below the swing low, structure is broken, discount was not cheap after all; step aside and draw a new range.
* **Status**: **AMENDED**.
* **Implementation**: Added `range_valid` boolean flag to `premium_discount_filter`. Closed candle beyond leg extreme immediately invalidates the active range.

### 2.8 External / Internal Range Liquidity Loop (`[ART-03]`)
* **Rule**: ERL = liquidity outside the range (EQH/EQL, PDH/PDL, PWH/PWL). IRL = FVGs and minor swings inside the range. From external, price draws to internal; from internal, it draws to external.
* **Status**: **ADDED**.
* **Implementation**: Added `range_liquidity_loop`. Classifies pools as ERL or IRL; computes `next_draw` (nearest unmitigated IRL gap, else nearest ERL pool) for target selection and R:R gating.

### 2.9 Master Template: Five-Check Trade Plan (`[ART-06]`)
* **Rule**: (1) Sweep -> (2) Structure (CHOCH) -> (3) Range (Discount) -> (4) Entry (FVG + OB) -> (5) Plan before price arrives (stop below sweep low, target equal highs). All five or no trade!
* **Status**: **ADDED (Setup Type A)**.
* **Implementation**: Added `five_check_model`. Evaluates all 5 conditions on closed candles. All 5 booleans must be true to generate a Setup Type A trade order.

### 2.10 Position Sizing Strictly from Stop Loss (`[ART-12]`)
* **Rule**: *"Size your trade from your stop, not from your margin. Position size = risk_amount / (stop_distance * value_per_unit)."* [ART-12].
* **Status**: **CORRECTED**.
* **Implementation**: Refactored `fit_engine.py` and `position_sizing.py`. Lot size is derived strictly from stop loss risk. Margin requirement serves only as an affordability barrier (pass/fail), never as a lot scaling factor.

### 2.11 Forex Broker Volume Limitation (`[ART-13]`)
* **Rule**: Futures have centralized real volume; forex has no central exchange and volume is broker tick volume.
* **Status**: **CORRECTED / TAGGED**.
* **Implementation**: Tagged all volume metrics in forex as `[DERIVED: BROKER TICK VOLUME]`. Forbid algorithms assuming real volume in spot forex.

### 2.12 Mandatory Analysis Order: H0 HTF Pools First (`[ART-10, ART-09, ART-04]`)
* **Rule**: Mark higher-timeframe pools first (PDH/PDL, PWH/PWL), then watch lower timeframe for reaction. Liquidity first, then structure, then the zone.
* **Status**: **ADDED (Pipeline H0 Gate)**.
* **Implementation**: Upgraded `InstitutionalEaEnginePipeline` with an initial `H0 HTF POOL MAP` gate prior to G1.
