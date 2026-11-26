# Institutional-EA — ICT/SMC Market Intelligence Audit & Specification (Videos 0010–0019)

> **Operational & Empirical Boundary:** The 10 educational videos (`0010–0019`) illustrate discretionary ICT/SMC price-action structures without prescribing universal numerical constants. All thresholds in `config/strategy_config.json["ict_intelligence"]` are configurable operational starting defaults validated via chronological out-of-sample walk-forward testing. New intelligence deploys in **`SHADOW` mode by default** and never overrides the risk engine, `DEMO` lock, `LIVE_TRADING_ENABLED=false`, or Rule R9.3 (tighten-only stops).

---

## 1. Phase 1 Technical Audit — Reused vs. Extended vs. New Capabilities

| Module / Concept | Video(s) | Existing Coverage in Repo | Decision |
| --- | --- | --- | --- |
| **A. HTF Liquidity & Quarterly Context** | `0010`, `0012` | `WeeklyDailyEngine` (`PWH/PWL/PDH/PDL`), `LiquidityEngine` (`BSL/SSL/EQH/EQL`), `SessionLiquidityEngine`, `video_primitives.detect_equal_clusters` | **Reuse + Extend**: Add 60-day highs/lows (`D60_HIGH`/`D60_LOW`), ~3–4 month `QuarterlyContext` (range, equilibrium, quadrant, exhaustion context without auto-signalling), and enriched `LiquidityLevel` metadata (`swept`, `distance_atr`, `scope`, `relevance_to_bias`). |
| **B. Liquidity Sweep Detection** | `0010`, `0011`, `0012`, `0013`, `0015` | `video_primitives.classify_sweep_vs_breakout`, `detect_confirmed_sweep` | **Reuse + Extend**: Add 4-way `SweepState` (`CONFIRMED_SWEEP`, `POTENTIAL_SWEEP`, `GENUINE_BREAKOUT`, `UNCONFIRMED_RAID`), wick penetration/rejection ratios, closed-candle-only guard, and post-sweep displacement check. |
| **C. Market Structure Intelligence** | `0010`, `0012`, `0013` | `MarketStructureEngine`, `StructureConfirmationMachine`, `video_primitives.detect_mss_with_displacement` | **Reuse + Extend**: Classify `LIQUIDITY_SWEEP` vs `STRUCTURAL_BREAKOUT` vs `DIRECTIONAL_TRANSITION` (displacement-confirmed MSS) vs `TEMPORARY_PULLBACK` vs `WICK_ONLY_PENETRATION`. |
| **D. Displacement Quality & FVG/CE** | `0013`, `0015` | `FvgObEngine.detect_fvgs`, `video_primitives.detect_fvgs_with_ce` | **Reuse + Extend**: Add 7-factor `DisplacementAssessment` (body/range, ATR expansion, directional consistency, close location, expansion vs prior bars, resulting FVG imbalance, structural level broken) to reject weak candles. |
| **E. Advanced Institutional Blocks** | `0015–0019` | `FvgObEngine` (OB), `video_primitives.detect_flipped_breakers` (Breaker) | **Reuse + Add Distinct Lifecycles**: Separate `OrderBlock`, `BreakerBlock` (`0019`, sweep + smashed OB + trapped traders), `MitigationBlock` (`0018`, failed OB without external sweep + trapped traders), `PropulsionBlock` (`0016`, opposing candle into parent OB + displacement + 50% mean threshold), and `RejectionBlock` (`0017`, pronounced wick zone body-to-extreme + midpoint entry), plus failed-setup state transitions. |
| **F. ICT Unicorn Model** | `0011` | `S7_STACKED_BREAKER_IFVG` (Breaker + IFVG) | **Add Distinct Model**: True `UnicornSetup` requiring liquidity sweep → displacement through OB → Breaker transition → newly created FVG overlapping Breaker → entry inside overlap, SL beyond sweep extreme. |
| **G. Optimal Trade Entry (OTE)** | `0014` | `video_primitives.compute_bos_anchored_ote` (`0.62–0.79`, `0.705`) | **Reuse + Gate**: Pair BOS-anchored OTE with displacement quality, liquidity context, and R:R validation; never enter on a blind 70.5% touch. |
| **H. Liquidity Targets & Fib Extensions** | `0012`, `0013` | `video_primitives.get_draw_on_liquidity`, `validate_draw_on_liquidity` | **Reuse + Extend**: Add `compute_fib_extensions` (`-1.0`, `-1.5`, `-2.0`, `-2.5`) with documented anchoring (`origin -> extreme`), preferring earlier structural liquidity pools (`PDH/PDL`, `PWH/PWL`, `D60_HIGH/LOW`) over forced Fib extensions. |
| **Scoring, Lifecycle & Rejection** | All | `SetupQualityGate` (`G1–G8`), `video_setups.score_video_setup` | **Add Explainable Pipeline**: 5 lifecycle states (`POTENTIAL`, `DEVELOPING`, `CONFIRMED`, `HIGH_QUALITY`, `INVALIDATED`), anti-double-counting weights, and 11 explicit `RejectionCode` values. |
| **Validation & Shadow Mode** | All | `src/learning/validation/statistics.py`, `monte_carlo.py`, `walk_forward.py` | **Reuse**: Chronological OOS walk-forward comparison with spread/commission/slippage, DSR, Monte Carlo, and per-model performance tracking. |

---

## 2. Video-Derived Trading Knowledge Specification (0010–0019)

1. **`0010` — Quarterly Liquidity & MSS**: Track 60-day highs/lows (`D60_HIGH`, `D60_LOW`) and 60–90 day quarterly range (`QuarterlyContext`: high, low, equilibrium, current quadrant). A run above/below a major high/low followed by opposing displacement and body-close MSS signals potential trend exhaustion/transition. Quarterly context is a *contextual* bias/exhaustion factor, never an automatic standalone entry trigger.
2. **`0011` — ICT Unicorn Model**: (1) BSL/SSL sweep → (2) opposing displacement smashing through a prior OB (converting it into a Breaker) → (3) fresh FVG created by that displacement overlapping the Breaker zone → (4) entry inside `[max(breaker.low, fvg.bottom), min(breaker.high, fvg.top)]` → (5) SL beyond sweep extreme → (6) target opposing liquidity.
3. **`0012` — HTF Liquidity Targets**: Old daily highs/lows (`PDH`/`PDL`, multi-day swings) act as external liquidity draws. Execution on M15/M5 aligns with the HTF draw and avoids premature countertrend entries prior to sweep + displacement.
4. **`0013` — Fib Extensions (`-2.0`) & FVG CE**: After SSL/BSL sweep + displacement + swing break + FVG creation, entry refines to FVG Consequent Encroachment (50% midpoint) and profit objectives project via Fibonacci extensions (`-2.0` convention: `extreme + 2.0 * (extreme - origin)` for longs, `extreme - 2.0 * (origin - extreme)` for shorts, where `origin` is the swing low/high and `extreme` is the impulse high/low) unless an earlier opposing liquidity pool offers a more realistic barrier.
5. **`0014` — Optimal Trade Entry (OTE)**: Retracement of a confirmed BOS impulse leg into `62%–79%` (sweet spot `70.5%`), gated by displacement, structure, liquidity context, and minimum R:R.
6. **`0015` — Displacement Quality & Valid OBs**: Sweeps alone do not confirm entries. Displacement is scored across 7 measurable factors; weak candles or missing FVG imbalance disqualify institutional OBs. Failed OBs are explicitly marked `INVALIDATED`.
7. **`0016` — Propulsion Block**: Last opposing candle trading *into* an existing parent OB followed by strong displacement away. Mean threshold = `(open + close) / 2` or `(high + low) / 2` (configurable, default body/range midpoint `(high + low) / 2`). Prefer revisiting the Propulsion Block over the older parent OB.
8. **`0017` — Rejection Block**: Pronounced candle wicks around significant liquidity (`wick_ratio >= min_wick_ratio`). Bearish zone = `[highest_body_top, wick_high]`; Bullish zone = `[wick_low, lowest_body_bottom]`. Entry at zone midpoint; invalidation beyond wick extreme.
9. **`0018` — Mitigation Block**: Failed OB where price closes decisively beyond its defining boundary *without* first sweeping an external high/low. Marks original OB `INVALIDATED`, flags trapped traders, and creates a `MitigationBlock` for retest continuation.
10. **`0019` — Breaker Block & Trapped Traders**: External BSL/SSL sweep followed by decisive body-close breakdown through the prior OB. Marks original OB `INVALIDATED`, flags trapped traders, and reclassifies the zone as a `BreakerBlock`.

---

## 3. Setup Scoring Methodology & Anti-Double-Counting

Normalized 0–100 score built from independent, configurable component budgets:
- **Higher-Timeframe & Quarterly Context** (15 pts)
- **Liquidity Sweep Quality** (12 pts)
- **Displacement Strength** (15 pts)
- **Structural Confirmation — MSS/BOS** (12 pts — **anti-double-counting**: MSS and BOS derived from the same structural break share this single 12-pt cap and are never summed twice)
- **FVG / Imbalance Quality** (10 pts)
- **Institutional Zone Validity** (12 pts — OB / Breaker / Mitigation / Propulsion / Rejection / Unicorn overlap; capped at 12 pts)
- **Entry Precision — OTE / CE / Zone Retest** (8 pts)
- **Liquidity Target & R:R Quality** (10 pts)
- **Regime & Execution Conditions** (6 pts)

Lifecycle classification:
- `INVALIDATED`: Any hard rejection code triggered (e.g. `OB_INVALIDATED`, `UNFINISHED_CANDLE`, `TARGET_ALREADY_REACHED`, `WICK_ONLY_BREAK`).
- `POTENTIAL`: Liquidity event detected, awaiting displacement/structure.
- `DEVELOPING`: Liquidity + displacement or structure present, awaiting entry zone/confirmation.
- `CONFIRMED`: All structural requirements satisfied, score ≥ `confirmed_score_threshold` (default `55.0`), no hard rejections.
- `HIGH_QUALITY`: `CONFIRMED` + score ≥ `high_quality_score_threshold` (default `72.0`).

---

## 4. Risk Preservation, Shadow Mode, Promotion & Rollback Procedure

- **Risk Authority**: `ICTIntelligenceEngine` only produces scored `ICTSetupEvaluation` / `SignalCandidate` objects. Final sizing, drawdown caps, daily loss caps, DEMO lock (`LIVE_TRADING_ENABLED=false`), and R9.3 tighten-only stops remain strictly under `RiskManager` and `OrderManager`. Lot sizes are **never** scaled up by setup confidence score (`never_scale_lot_by_score: true`).
- **Default Deployment (`SHADOW`)**: `config/strategy_config.json["ict_intelligence"]["mode"] = "SHADOW"` and `"allow_live_orders": false`. In Shadow Mode, setups are evaluated, logged with full audit metadata, and tracked in `ICTModelPerformanceTracker` without submitting broker orders.
- **Promotion Gate**: Promote an individual setup model from `SHADOW` to `DEMO_EXECUTE` only after out-of-sample walk-forward validation confirms positive expectancy after spread/commission/slippage, acceptable drawdown, and passing Deflated Sharpe Ratio (DSR) / Monte Carlo stress checks (`src/learning/validation/`).
- **Instant Rollback**: Set `config/strategy_config.json["ict_intelligence"]["enabled"] = false` or `"mode": "SHADOW"` (zero impact on existing `StrategyEngine` or `VideoSetupEngine`).
