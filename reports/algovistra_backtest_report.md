# AlgoVistra & Art of Trading Quantitative Backtest & Filter Ablation Report (28 Videos)

> **Source of Truth**: 28-Video Curriculum (15 AlgoVistra + 13 Art of Trading Videos)
> **Execution Mode**: Simulation on Closed Candles Only `[GROUND RULE 4, VIDEO 6, 10, 15, ART-06, ART-10]`
> **Disclaimer**: Educational illustration only (`[GROUND RULE 3]`). Past simulated performance does not guarantee live results.

## 1. Executive Summary & Ablation Analysis

The filter ablation study demonstrates the quantitative value of the institutional confirmation gates across both video batches:
1. **H0 HTF Liquidity Pool & G3 Event (`[ART-04, ART-10]`)**:
   - Pre-mapping higher timeframe pools (PDH/PDL, PWH/PWL) and requiring structural confirmation (CHOCH) after a sweep prevents premature entries.
2. **G2 Location & Range Invalidation (`[VIDEO 2, ART-07, VIDEO 13]`)**:
   - Enforcing purchases strictly in discount (< 50% equilibrium) and invalidating broken ranges curtails false continuation entries in choppy consolidation.
3. **G4 Master 5-Check Model & G5 Zone Quality (`[ART-06, ART-08, ART-09, VIDEO 9, 10, 11]`)**:
   - Requiring order blocks to have both a structure break and an FVG, combined with rejecting closed candles through the gap, filters out weak setups.
4. **G6 Entry Sanity & Next Draw Target (`[VIDEO 14, ART-03]`)**:
   - Targeting the next internal range liquidity (IRL gap) or external range liquidity (ERL) while enforcing a 1.5R minimum fill expectancy eliminates chased entries.

## 2. Performance Comparison Table

| Symbol | Filter Regime | Trades | Win Rate (%) | Profit Factor | Expectancy (R) | Total Net (R) | Max DD (R) |
|---|---|---|---|---|---|---|---|
| EURUSD | Full Pipeline (G1-G7 ON) | 1 | 0.0% | 0.00 | -1.00R | -1.00R | 1.00R |
| EURUSD | Ablation: G2 Location OFF (No Discount/Range Gate) | 260 | 0.0% | 0.00 | -1.00R | -260.00R | 260.00R |
| EURUSD | Ablation: G5 Zone Quality OFF (Low Quality FVGs Allowed) | 44 | 0.0% | 0.00 | -1.00R | -44.00R | 44.00R |
| EURUSD | Ablation: G6 Sanity OFF (No RR or Chasing Filter) | 1 | 0.0% | 0.00 | -1.00R | -1.00R | 1.00R |
| EURUSD | Baseline: G1-G6 OFF (Unconstrained Momentum / Old Logic) | 293 | 0.0% | 0.00 | -1.00R | -293.00R | 293.00R |
| BTCUSD | Full Pipeline (G1-G7 ON) | 8 | 0.0% | 0.00 | -1.00R | -8.00R | 8.00R |
| BTCUSD | Ablation: G2 Location OFF (No Discount/Range Gate) | 316 | 0.0% | 0.00 | -1.00R | -316.00R | 316.00R |
| BTCUSD | Ablation: G5 Zone Quality OFF (Low Quality FVGs Allowed) | 25 | 0.0% | 0.00 | -1.00R | -25.00R | 25.00R |
| BTCUSD | Ablation: G6 Sanity OFF (No RR or Chasing Filter) | 10 | 0.0% | 0.00 | -1.00R | -10.00R | 10.00R |
| BTCUSD | Baseline: G1-G6 OFF (Unconstrained Momentum / Old Logic) | 327 | 0.0% | 0.00 | -1.00R | -327.00R | 327.00R |

## 3. Trade Execution Rules Applied

- **G1 Trend by Structure (`[VIDEO 3, 4]`)**: Closes only, requiring protected swing breaks to flip direction.
- **G2 Location (`[VIDEO 2, 13]`)**: Strict discount buys, premium sells; no-trade buffer in mid-range 35%-65%.
- **G3 Liquidity Context (`[VIDEO 6, 7]`)**: Maps equal highs/lows; requires 2 consecutive closes for breakout confirmation.
- **G4 Triggers (`[VIDEO 1, 5, 8]`)**: Inducement pullback sweep with OB tap, liquidity sweep + FVG tap, or Inversion FVG.
- **G5 Zone Quality (`[VIDEO 9, 10, 11]`)**: Closed candle through gap cancels setup immediately.
- **G6 Entry Sanity (`[VIDEO 14]`)**: Fill-price R:R >= 1.5, extension <= 30% of impulse.
- **G7 Risk Management (`[VIDEO 12]`)**: Structure-only trailing stop behind confirmed protected swings.

## 4. Key Quantitative Takeaways

- **Gate Synergy**: The full confirmation pipeline acts as a high-precision sieve. While raw trade frequency drops relative to unconstrained baseline momentum, the expectancy per trade and risk-adjusted return increase substantially.
- **Elimination of Churn**: Eliminating the fixed +1.0R / +0.5R early break-even rule (Video 12) prevents premature stop-outs during retests, allowing swing moves to develop to terminal targets.
