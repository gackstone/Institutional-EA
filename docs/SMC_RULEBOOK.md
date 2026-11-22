# Canonical SMC Rulebook (`Institutional EA`)

> **Single Source of Truth**: This document and [`src/smc/smc_rulebook.py`](../src/smc/smc_rulebook.py) define the canonical Smart Money Concepts (SMC) rulebook (R1–R9), default parameters, Setup Quality Gate (G1–G8), and Risk-Rule Enforcement (R9) used across the bot.
>
> **Epistemic Note**: Every rule below is treated as a **testable price-action hypothesis** with a configurable default value, evaluated empirically out-of-sample via multi-year backtests and single-gate ablation. None of these rules are assumed to be "proven" a priori.

---

## 1. The 9-Rule SMC Hypothesis Framework (R1–R9)

### R1. Market Structure
* **Definition**:
  * **Uptrend**: Higher Highs (`HH`) + Higher Lows (`HL`). Both must be present to classify a clear bullish trend.
  * **Downtrend**: Lower Highs (`LH`) + Lower Lows (`LL`). Both must be present to classify a clear bearish trend.
  * **Ranging / Unclear Structure**: Mixed swings (`HH` with `LL`, or `< 2` swing highs/lows) = `RANGING` (**NO TRADE** — *"no clear trend, wait"*).
* **Timeframe Hierarchy**: Read directional structure on Higher Timeframes (`H4` / `D1`). Small timeframes (`M1`) contain microstructure noise and do not define the primary trend.
* **Config Parameters**: `require_both_hh_hl_for_trend = true`, `ranging_structure_no_trade = true`, `htf_timeframes = ["H4", "D1"]`.

### R2. Break of Structure (BOS)
* **Definition**: A candle **BODY CLOSE** beyond the last swing point in the prevailing trend direction (above the last swing high in an uptrend; below the last swing low in a downtrend) confirms the trend remains active.
* **Wick Filter**: A wick piercing a swing high/low without a body close beyond it is **NOT** a BOS (it is a potential liquidity sweep).
* **No Breakout Chasing**: Do not enter on the breakout/displacement candle close; wait for a pullback into a Point of Interest (POI).
* **Config Parameters**: `bos_body_close_required = true`, `reject_breakout_candle_chase = true`.

### R3. Change of Character (CHoCH)
* **Definition**: The **FIRST candle body close** against the prevailing trend (e.g., in a downtrend, a body close above the most recent lower high; in an uptrend, a body close below the most recent higher low).
* **Confirmation Requirement**: One CHoCH is an early warning, **NOT** a confirmed reversal. Entries require confirmation: a pullback that holds (`HL` for bullish, `LH` for bearish) followed by a confirming `BOS` in the new direction.
* **Config Parameters**: `choch_requires_confirmation = true`, `allow_choch_only_entries = false`.

### R4. Liquidity & Sweeps
* **Definition**: Resting stop orders cluster around Equal Highs (`EQH`), Equal Lows (`EQL`), prior swing points (`BSL`/`SSL`), session highs/lows, and daily/weekly highs/lows (`PDH`/`PDL`/`PWH`/`PWL`).
* **Liquidity Sweep**: Price pierces beyond the liquidity level and quickly **CLOSES BACK INSIDE** the prior range. A candle body that closes outside and stays outside is a breakout, not a sweep.
  * Sweeping **Sell-Side Liquidity (`SSL` / `EQL` / `PDL` / `PWL`)** + closing back above the level = **Bullish** sweep signal.
  * Sweeping **Buy-Side Liquidity (`BSL` / `EQH` / `PDH` / `PWH`)** + closing back below the level = **Bearish** sweep signal.
* **Target Anchor**: Take-profit (`TP`) targets are placed at the next structural liquidity pool.
* **Config Parameters**: `sweep_requires_close_back_inside = true`, `tp_requires_liquidity_pool = true`.

### R5. Order Block (OB)
* **Definition**: The last opposite-colored candle (`bearish` before a bullish impulse; `bullish` before a bearish impulse) prior to a strong displacement move that **BREAKS structure (`BOS`/`MSS`)**.
* **Quality Filter**: Not every opposite candle is an Order Block. A valid OB requires:
  1. **Displacement**: Impulse candle body `>= ob_displacement_atr_mult * ATR` (default `1.2 * ATR`) or creation of a Fair Value Gap (`FVG`).
  2. **Structural Break**: The impulse leg breaks a prior swing high (bullish OB) or swing low (bearish OB).
* **Config Parameters**: `ob_requires_displacement = true`, `ob_displacement_atr_mult = 1.2`, `ob_requires_bos = true`.

### R6. Fair Value Gap (FVG)
* **Definition**: A 3-candle price imbalance where candle 1's high and candle 3's low do not overlap (`c3.low > c1.high` for bullish; `c3.high < c1.low` for bearish).
* **Quality Filter**: Ignore tiny microstructure gaps. Require minimum ATR-scaled gap size (`gap >= fvg_min_atr * ATR`, default `0.3 * ATR`) and an impulsive middle candle (`c2`).
* **Confluence**: An FVG overlapping or immediately adjacent to a valid Order Block (`OB + FVG`) receives a confluence score bonus.
* **Config Parameters**: `fvg_min_atr = 0.3`, `fvg_requires_impulse = true`, `ob_fvg_confluence_bonus_pts = 10.0`.

### R7. Premium / Discount Equilibrium
* **Definition**: Across the active swing range (`swing_low` to `swing_high`), `50%` (`0.50`) is equilibrium:
  * **Discount (`< 50%`)**: Below equilibrium (inexpensive — look for **BUYS** in an uptrend).
  * **Premium (`> 50%`)**: Above equilibrium (expensive — look for **SELLS** in a downtrend).
* **Config Parameters**: `pd_equilibrium = 0.5`.

### R8. Complete 6-Step Entry Model
1. **HTF Trend + BOS**: Clear `H4`/`D1` trend with a confirmed `BOS` in the trade direction.
2. **Pullback Zone**: Price pulls back into the `discount` zone (`< 50%`) for longs or `premium` zone (`> 50%`) for shorts.
3. **Liquidity Sweep**: A liquidity sweep with close-back-inside occurs in or into that zone.
4. **Point of Interest (POI)**: Identify the valid `OB` and/or `FVG` inside the zone.
5. **LTF Confirmation**: On the lower timeframe (`M15`), wait for a `CHoCH` + confirming `BOS` inside the zone.
6. **Pullback Entry, Stop & Target**: Enter on the pullback into the LTF `OB`/`FVG` (do not chase the breakout candle). Place `SL` beyond the sweep/POI extreme and `TP` at the next liquidity pool with a minimum reward-to-risk ratio `RR >= min_rr` (default `2.0`). Do not artificially inflate `TP` into empty air to fake `min_rr`.

### R9. Risk & Trade Hygiene
* **Risk Per Trade**: Default `1.0%`, hard-capped at **`2.0%`** in code regardless of external configuration files.
* **Mandatory Stop Loss**: Every order must carry a valid stop loss (`sl > 0` on the protective side of entry). Any order without an SL is rejected.
* **Never Widen a Stop Loss**: Once a position is open, no modification path may move the stop loss further away from the open/current price (increasing risk). Only breakeven and trailing adjustments in the profitable direction are permitted.
* **Explicit No-Trade Logging**: *"No setup is also a decision."* Every rejected candidate or skipped scan logs an explicit reason code (`G1_UNCLEAR_OR_RANGING_STRUCTURE`, `G3_NO_LIQUIDITY_SWEEP_WITH_CLOSE_BACK_INSIDE`, `G7_RR_BELOW_MIN_RR`, etc.).

---

## 2. Setup Quality Gate (`G1`–`G8`)

Implemented in [`src/smc/setup_quality_gate.py`](../src/smc/setup_quality_gate.py), sitting between candidate detection and order execution:

| Gate | Name | Rule(s) | Hard-Fail Condition |
| :--- | :--- | :---: | :--- |
| **G1** | Structure | R1, R2 | HTF (`H4`/`D1`) is `RANGING`/unclear or lacks a body-close `BOS` in the trade direction. |
| **G2** | Zone (P/D) | R7 | Buying in Premium (`> 0.50`) or Selling in Discount (`< 0.50`). *(Tested via ablation in Phase 4)*. |
| **G3** | Sweep | R4 | No liquidity sweep with close-back-inside prior to entry. |
| **G4** | POI Quality | R5, R6 | Neither a displacement+BOS `OrderBlock` nor an ATR-qualified `FVG` is present at the entry zone. |
| **G5** | LTF Confirmation | R2, R3, R8 | Unconfirmed lone `CHoCH` or chasing the breakout candle close without pullback. |
| **G6** | HTF Alignment | R1, R8 | Trade direction opposes the HTF (`H4`/`D1`) trend bias. |
| **G7** | Stops & Targets | R4, R8 | `SL` not beyond sweep/POI extreme, `TP` not anchored at a liquidity pool, or structural `RR < min_rr` (`2.0`). |
| **G8** | Risk Cap & SL | R9 | Missing `SL` (`sl <= 0`) or risk per trade `> 2.0%` hard cap. |
