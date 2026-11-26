# Video-Derived Forex Strategy Skills — Codebase Audit

> **Branch:** `feature/video-skills-2026-11`  
> **Scope:** 16 educational forex video strategies mapped onto the existing Institutional-EA Python engine (`XAUUSD` primary, `BTCUSD` tradable, `USDJPY` / `reference_symbols` data-only for SMT).  
> **Provenance & Epistemic Notice:** Parameters extracted from burned-in video captions and chart annotations are *engineering starting defaults for replay calibration*, not validated edges or profitability claims. Video `keepssy_fx-20261126-0012` was not provided, and `chart__tactix-20261113-0001` ends before its third confirmation (third slot implemented as configurable HTF-bias alignment, explicitly marked as *not from the video*).

---

## 1. Existing Architecture & Hard Invariants Verified

- **Safety Locks:** `LIVE_TRADING_ENABLED=false`, `execution_mode=DEMO`, REAL-account barrier, DEMO-only operating modes, and tighten-only stop policy (R9.3) in `src/risk/trade_management.py`, `src/execution/`, and `src/manual_mgmt/assessor.py`.
- **Symbol Universe (`src/core/symbol_universe.py`):** Strictly permits `APPROVED_CANONICAL_SYMBOLS = ("XAUUSD", "BTCUSD")` for trading; universally blocks `USDJPY` and unapproved symbols from execution. Optional data-only `reference_symbols` (e.g., `USDJPY`, `XAGUSD`, `DXY`, `ETHUSD`, `EURUSD`) will be read-only for SMT correlation and rejected by execution guards.
- **Unfiltered Execution (`config/strategy_config.json`):** `adaptive_entry_filters=false`, `scalping_min_confluence_score=0.0`, `min_rr=0.0`, `smc_rulebook.gate_mode="OFF"`. All new gates (draw on liquidity, SMT 3-point turn, sweep vs breakout) belong strictly to each named video setup's own detector—existing entry pathways remain completely untouched.

---

## 2. Capability-by-Capability Audit Matrix

Legend: **(a) Already exists**, **(b) Exists but partial / disagrees with definition**, **(c) Missing**

### Time, Sessions & Key Levels

| Capability | Status | Existing File / Function | Gap & Implementation Plan |
| --- | --- | --- | --- |
| NY Local Time (`America/New_York`) DST-aware ICT windows (Silver Bullet London/NY AM/NY PM, NY Killzone, NY Macro 1 & 2) | **(b) Partial** | `src/core/sessions.py` (`TradingSessionEngine`, uses `zoneinfo`) & `config/sessions.json` | Has `ist_reference` and `market_local_dst` profiles for Asia/London/NY, but lacks editable `ict_ny_windows` (`silver_bullet_london`, `silver_bullet_ny_am`, `silver_bullet_ny_pm`, `ny_killzone`, `ny_macro_1`, `ny_macro_2`) and broker-offset mapping helper. Extend `config/sessions.json` and `TradingSessionEngine`. |
| Session & Daily Key Levels (Asian H/L, London H/L, PDH/PDL/**PD Mid**, Morning H/L) | **(b) Partial** | `src/smc/session_liquidity.py` (`SessionLiquidityEngine.calculate_asia_range`), `src/smc/weekly_daily.py` (`WeeklyDailyEngine.calculate_levels` computes PDH/PDL/PDM) | `SessionLiquidityEngine` computes Asia H/L/Mid only (hardcoded 00:00-09:00 UTC). Extend `SessionLiquidityEngine` with `compute_session_key_levels()` exposing Asian H/L, London H/L, PDH/PDL/PDM, and morning H/L using `TradingSessionEngine`. |

### Core Primitives (P1–P11)

| ID | Capability | Status | Existing File / Function | Gap & Implementation Plan |
| --- | --- | --- | --- | --- |
| **P1** | Equal Highs / Equal Lows as stop clusters (`0.10 * ATR(14)`, `untapped`/`taken`) | **(b) Partial** | `src/smc/liquidity.py` (`LiquidityEngine.identify_liquidity_pools`) | Uses fixed `eqh_tolerance_pips * pip_size` and does not mark `untapped`/`taken` status. Add ATR-based tolerance option (`eqh_tolerance_atr=0.10`) and `taken`/`untapped` tracking. |
| **P2** | Sweep vs Breakout Classifier (candle formation + approach + configurable 3rd slot) | **(c) Missing** | `src/smc/liquidity.py` (`verify_sweep` only checks 1-2 bar close back) | Implement `classify_sweep_vs_breakout()` in `src/smc/video_primitives.py` (reused by `LiquidityEngine`) returning `{kind: SWEEP|BREAKOUT|UNDECIDED, score: 0-100, evidence}` with candle rejection/displacement, ATR-normalised approach overlap/slope, and configurable 3rd slot (default: HTF bias alignment, flagged as *not from video*). |
| **P3** | Confirmed Sweep (`min_pierce=0.05*ATR`, `max_bars_to_reclaim=3`, close back beyond level) | **(b) Partial** | `src/smc/liquidity.py` (`LiquidityEngine.verify_sweep`) | `verify_sweep` lacks `min_pierce` ATR threshold and caps at 2 bars. Add `detect_confirmed_sweep()` supporting `min_pierce_atr=0.05`, `max_bars_to_reclaim=3` while preserving `verify_sweep` default behaviour. |
| **P4** | MSS / BOS with Displacement (close beyond opposing swing + displacement body >= 1.0x avg body or >= 0.8x ATR + FVG) | **(b) Partial** | `src/smc/market_structure.py`, `src/smc/structure_confirmation.py` | Has BOS/CHOCH close detection, but lacks combined post-sweep MSS + displacement + FVG check in one reusable primitive. Add `detect_mss_with_displacement()` reusing existing swing/FVG detectors. |
| **P5** | FVG + CE (50% midpoint, min size `0.15 * ATR`) | **(a) Exists (extend default)** | `src/smc/fvg_ob.py` (`FvgObEngine.detect_fvgs` computes `midpoint`, default `fvg_min_atr=0.3`) | Reuse `FvgObEngine.detect_fvgs` with configurable `fvg_min_atr=0.15` for video setups; expose CE explicitly. |
| **P6** | Inversion FVG (IFVG) + "first FVG before stop hunt" priority | **(b) Partial** | `src/smc/fvg_ob.py` (`detect_fvgs` emits `is_inverse=True`) | Already flips FVG when closed through, but lacks priority tagging for "first FVG before stop hunt" (5M) and retest trigger check. Add `detect_ifvg_retest()` helper reusing `FvgObEngine`. |
| **P7** | Breaker Block (OB closed through flips bias) | **(b) Partial / Buggy** | `src/smc/bpr_ifvg_helpers.py` (`detect_breaker_blocks`) | Existing helper only checks `BUY` OBs and approximates via FVG proxy rather than actual candle closes through OB high/low, and does not flip `direction` or set `is_breaker=True`. Implement accurate bidirectional `detect_flipped_breakers()` in `src/smc/video_primitives.py` (keeping legacy function untouched for existing tests). |
| **P8** | Fibonacci with Correct Swing Anchoring ("zoom out" to BOS leg) + OTE (`0.62–0.79`, sweet spot `0.705`, FVG overlap + directional close) | **(b) Partial** | `src/smc/fvg_ob.py` (`calculate_premium_discount` computes `ote_62`, `ote_705`, `ote_79` for bullish only) | Lacks BOS-leg swing-anchor selection (rejecting minor pullbacks), bearish mirror, full standard grid (`0, 0.236, 0.382, 0.5, 0.618, 0.786, 1`), FVG-in-OTE overlap, and directional close trigger. Implement `compute_bos_anchored_ote()`. |
| **P9** | Draw on Liquidity (`get_draw_on_liquidity(direction)`) | **(c) Missing** | `src/smc/liquidity.py` (detects pools, no target selector) | Implement `get_draw_on_liquidity(direction, current_price, pools, key_levels)` selecting nearest **untapped** opposing pool (BSL/SSL, EQH/EQL, session/PD H/L, PD mid). |
| **P10** | "No draw, no trade" validator | **(c) Missing** | None | Implement `validate_draw_on_liquidity()` rejecting setups if target pool is already taken or R:R < configured `min_rr`. |
| **P11** | 3-Point Turn Validator (Sweep + SMT + MSS -> `A+` / `B` / `INVALID`) | **(b) Partial** | `src/smc/smt.py` (raw pip lag check, ignores inverse regime), `src/strategy/inverse_coordination.py` (`InverseDirectionCoordinator`, `CorrelationRegime`) | Existing `smt.py` assumes positive correlation & hardcoded `point=0.0001`. Implement `evaluate_three_point_turn()` using (A) `InverseDirectionCoordinator` (`INVERSE_STRONG`/`INVERSE_MODERATE` only) and (B) optional data-only `reference_symbols`, outputting grade `A+` / `B` / `INVALID`. |

### Named Setups (S1–S10)

| ID | Setup | Status | Module Mapping |
| --- | --- | --- | --- |
| **S1** | Raid -> Shift -> FVG -> CE ("free ICT model", 4 steps) | **(c) Missing (unified)** | `src/smc/video_setups.py` (`VideoSetupEngine`, core parameterized engine) |
| **S2** | Silver Bullet (3 NY windows, first FVG after sweep, P10, window expiry) | **(c) Missing** | `src/smc/video_setups.py` (reuses S1 + NY Silver Bullet windows) |
| **S3** | NY Macro (09:50–10:10 / 10:50–11:10 NY, cancel unfilled at window end) | **(c) Missing** | `src/smc/video_setups.py` (reuses S1 + NY Macro windows) |
| **S4** | London Judas Swing / Fake Breakout of Asian Range | **(b) Partial** | `src/smc/session_liquidity.py` detects sweep only; extend in `src/smc/video_setups.py` with MSS + FVG + CE + opposite Asian side target |
| **S5** | Asian-Range Standard-Deviation Projection Reversal (`-1/-2/-2.5 SD`, `+1/+2/+2.5 SD`) | **(c) Missing** | `src/smc/video_setups.py` (zone gate + reversal MSS + FVG above/below projection -> TP1 Asian low/high + runner) |
| **S6** | IFVG Reversal After Stop Hunt (5M FVG inverted by close through -> retest) | **(c) Missing** | `src/smc/video_setups.py` (reuses P3 + P6) |
| **S7** | Stacked Breaker + IFVG Overlap | **(c) Missing** | `src/smc/video_setups.py` (reuses P6 + P7 + overlap confluence bonus) |
| **S8** | OTE Entry After Stop Hunt + BOS (`0.705` or FVG in `0.62–0.79`) | **(c) Missing** | `src/smc/video_setups.py` (reuses P1 + P3 + P4 + P8) |
| **S9** | Hidden Demand/Supply (HTF wick-to-wick gap behind BOS -> LTF OB buy/sell limit) | **(c) Missing** | `src/smc/video_setups.py` (reuses MTF HTF->LTF refinement) |
| **S10** | Session-Level Sweep Reversals (Asia->London, London->NY, PDL/PDH->PD Mid) | **(c) Missing** | `src/smc/video_setups.py` (context/location + S1 mechanics + PD mid TP1) |

### Signal, Trade Management, Manual Adoption, Knowledge, Config & Notifications

| Area | Status | Existing File | Plan |
| --- | --- | --- | --- |
| **Signal Dataclass** | **(b) Partial** | `src/core/contracts.py` (`SignalCandidate`) | Add optional default fields: `setup_id`, `context`, `sweep_kind`, `smt_status`, `three_point_grade`, `draw_on_liquidity`, `entry_model`, `invalidation_price`, `provenance` (100% backward-compatible). |
| **Trade Management** | **(b) Partial** | `src/risk/trade_management.py` | Add runner partial-close + BE+cost buffer + structural trail helper, window-expiry pending order cancel helper, and invalidation-close check (all strictly tighten-only R9.3). |
| **Manual Adoption** | **(b) Partial** | `src/manual_mgmt/assessor.py` | Prefer sweep/raid extreme for naked manual SL when nearby, and P9 `get_draw_on_liquidity` for suggested TP, preserving User Supremacy & tighten-only. |
| **Knowledge / Skills** | **(b) Partial** | `knowledge/forex_kb.json` | Extend with P1–P11 & S1–S10 + 4 documented failure modes + `[VIDEO: <file>]` provenance; export `knowledge/exports/video_skills_2026-11.json` for `arcadefx.live` AI coach. |
| **Config** | **(b) Partial** | `config/strategy_config.json`, `config/sessions.json` | Add `video_setups` block with per-setup `enabled`, `min_rr`, `allow_b_grade`, `partial_pct`, `cancel_on_window_end`, `execution_mode_for_new_setups`, `reference_symbols`, plus fail-closed config validation. |
| **Telegram / Companion** | **(b) Partial** | `src/notifications/events.py`, `src/notifications/templates/default_templates.py`, `companion/src/components/screens/AnalyticsSignalsScreens.tsx` | Add single metadata line to `TradeSetupEvent` (Tier 1), keep skipped/invalid in Tier 3, and display `setup_id`, `three_point_grade`, `provenance` on existing Companion Signals screen. |
