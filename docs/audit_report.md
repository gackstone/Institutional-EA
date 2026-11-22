# Phase 0 Master Audit Report: Institutional EA (Part 1) & Art of Trading (Part 2) Strategy Transfer

**Date**: 2026-11-10  
**Author**: Senior Quant-Developer Agent (Antigravity)  
**Target Repository**: `MT5 001` (MetaTrader 5 Python Algorithmic Trading Engine)  
**Scope**: 28 Videos (15 Institutional EA + 13 Art of Trading) + Institutional EA Cloud AI Coach  
**Status**: MASTER AUDIT COMPLETE — AWAITING USER APPROVAL PRIOR TO CODE MODIFICATIONS  

---

## 1. Executive Summary & Precedence Hierarchy

This master audit evaluates the entire repository against **28 strategy videos**:
- **Part 1**: 15 Institutional EA Video Cards (`[VIDEO 1]` to `[VIDEO 15]`) and Combined Confirmation Pipeline (G1 to G7).
- **Part 2**: 13 Art of Trading Video Cards (`[ART-01]` to `[ART-13]`) and Amendments (`P2-2`, `P2-4`).

### Precedence Rule
Where Part 2 states **AMENDS**, Part 2 strictly overrides Part 1:
1. **Unified CHOCH Definition**: CHOCH = first CLOSE beyond the most recent opposite swing, against the prior trend (`[VIDEO 15, ART-09, ART-10]`). BOS = close beyond prior swing in the trend's direction.
2. **Sweep Entries Require Structure Confirmation**: A sweep alone is NOT an entry. Part 1 Video 5 (`sweep_fvg_entry`) must require a subsequent CHOCH/BOS close (`[ART-06, ART-10]`).
3. **Dual-Form Breakout Confirmation**: Breakout requires either 2 consecutive closes beyond OR close beyond + retest & hold (`[VIDEO 6, ART-10]`).
4. **TRAP Flag Feeds Reversals**: A TRAP (wick through, close back inside) followed by CHOCH provides valid reversal context (`[ART-10, ART-06]`).
5. **FVG 50% Level**: Watched as a key institutional turning level, but candle close still governs invalidation (`[ART-08, VIDEO 10]`).
6. **Swing Hierarchy**: Single symmetrical fractals replaced by ranked recursive swings (STH/STL rank 1, ITH/ITL rank 2, LTH/LTL rank 3) with confirmation lag and zero repainting (`[ART-02]`). Protected low anchored to intermediate rank (`[ASSUMPTION]`).
7. **Stop Placement Precedence**: Sweep setups place stop below the sweep extreme (`[ART-06, VIDEO 5]`); OB-only setups place stop below the block (`[VIDEO 1]`). When both apply, the sweep extreme takes precedence as wider structural invalidation.
8. **Target Logic via Range Liquidity Loop**: Nearest unmitigated internal range liquidity (IRL gap) first if R:R permits, otherwise external range liquidity (ERL: EQH/EQL, PDH/PDL, PWH/PWL) (`[ART-03, ART-06]`).
9. **Mandatory Analysis Order**: Higher Timeframe (HTF) pools mapped first (`H0`), then Lower Timeframe (LTF) reaction (`G1-G7`). Order: Liquidity -> Structure -> Zone (`[ART-10, ART-09]`).
10. **Order Block Qualification**: OB candidate strictly requires BOTH a structure break (BOS) AND an imbalance (FVG). No break, no gap = just a candle (`[ART-09]`).
11. **Position Sizing from Stop**: Sizing derived strictly as `risk_amount / (stop_distance * value_per_unit)`, NEVER derived from available margin (`[ART-12]`).
12. **Forex Tick Volume Caution**: MT5 forex volume is broker tick volume, not real traded volume; no logic may assume real volume (`[ART-13]`).

---

## 2. Repository Architecture Map

```
MT5 001/
├── agent/                         # Outbound HTTPS orchestration agent for Institutional EA Cloud
│   ├── mt5_bot_agent.py           # Pairing, telemetry heartbeat, remote command polling
│   └── local_limits.json          # Hard local ceilings on cloud commands
├── config/                        # System, risk, and strategy configurations
│   ├── settings.json              # Master execution mode (DEMO), symbols, ports
│   ├── strategy.yaml              # Strategy parameters tagged with [VIDEO n], [ART-nn], [ASSUMPTION]
│   ├── strategy_config.json       # SMC/ICT feature toggles
│   ├── risk_config.json           # Risk caps, daily loss limit, be_move_mode
│   └── sessions.json              # Session definitions (London, NY AM/PM, Asian)
├── docs/                          # Architecture, rulebooks, and audit reports
│   ├── audit_report.md            # This master audit report
│   ├── changelog_knowledge.md     # Knowledge migration changelog
│   └── institutional_ea_coach_prompt.md   # Generated system prompt for Institutional EA Cloud coach
├── engine/ & src/engine/          # Institutional EA & Art of Trading Confirmation Engine
│   ├── pipeline.py                # Confirmation pipeline orchestrator (H0 -> G7)
│   ├── types.py                   # SkillResult, Context, Candle normalization
│   └── skills/                    # 15 pure function skill modules (to be expanded for Part 2)
├── knowledge/                     # Centralized Single Source of Truth
│   ├── forex_kb.json              # 28-video knowledge base, terms, lessons, caveats
│   └── coach_context.md           # Markdown context block for AI coach
├── mql5/Experts/PythonBridgeEA.mq5# Localhost TCP bridge server/client (port 5555/5556)
├── reports/                       # Validation and quantitative backtest reports
│   └── institutional_ea_backtest_report.md # Closed-candle backtest & ablation study
├── scripts/                       # Operational scripts & backtest runners
│   ├── generate_coach_prompt.py   # AI coach prompt generator
│   └── run_institutional_ea_backtest.py # Bar-replay backtest harness
├── src/                           # Core trading engine source code
│   ├── core/                      # Config, market data engine, contracts, sessions
│   ├── execution/                 # OrderManager, Pre-Trade Checklist, bridge client
│   ├── risk/                      # Position sizing, fit engine, trade management
│   ├── smc/                       # Legacy SMC modules (market_structure, fvg_ob, liquidity)
│   └── notifications/             # Telegram feeds and system alerts
└── tests/                         # Unit and integration test suites
```

---

## 3. Comprehensive 28-Video Audit & Conflict Table

Every existing strategy rule, indicator, skill, doc, and prompt is audited against Part 1 (`[VIDEO 1-15]`), Part 2 (`[ART-01 to 13]`), and the mandatory Conflict Hunt List:

| Item / Feature | Location | Current Implementation / Claim | Conflicts with Video Cards? | Required Action |
|---|---|---|---|---|
| **Swing Identification** | `src/smc/market_structure.py:30`, `src/engine/skills/protected_swing_marker.py` | Symmetrical $k=5$ fractal bar identification. Identifies all local swing points equally. | **YES — ART-02 & VIDEO 3**: "Many swing lows exist; most are noise. Replace single-fractal swings with ranked swings: STH/STL (n=1), ITH/ITL (higher STH), LTH/LTL (higher ITH). Each rank needs confirmation lag." | **AMEND / REPLACE**: Implement `swing_hierarchy` (`[ART-02]`). Mark swings with recursive rank 1/2/3 and confirmation timestamps (no repainting). Select protected swing from intermediate rank (`[ASSUMPTION]`). |
| **Liquidity Sweeps as Entry Triggers** | `src/engine/skills/sweep_fvg_entry.py`, `src/smc/strategy_engine.py` | Enters when price sweeps liquidity and taps FVG, without requiring structure break. | **YES — ART-06, ART-10 & VIDEO 7**: "A sweep alone is not enough. Not every wick is a sweep. Price must break the last lower high (CHOCH) after the sweep. Liquidity is not a signal." | **AMEND**: Update `sweep_fvg_entry` and implement `five_check_model` (`[ART-06]`). Enforce mandatory CHOCH candle close following the sweep before an entry can be generated. |
| **Order Block Qualification** | `src/smc/fvg_ob.py:210`, `src/engine/skills/inducement_ob_entry.py` | Qualifies OB if impulse has ATR displacement OR leaves an FVG. | **YES — ART-09**: "The move must break structure AND leave an imbalance (a gap). No break, no gap = just a candle." | **AMEND**: Implement `order_block_detector` (`[ART-09]`). Strictly require BOTH body-close BOS and unmitigated FVG. Reject any OB candidate lacking either. |
| **Breakout vs Trap Classifier** | `src/engine/skills/breakout_trap_classifier.py` | Requires 2 consecutive candle closes beyond level. TRAP flag emits no trade action. | **YES — AMENDED by ART-10 & ART-06**: Breakout confirmation accepts 2 forms: 2 closes beyond OR close beyond + retest & hold. A TRAP (wick through, close back inside) + CHOCH feeds reversal setups. | **AMEND**: Implement `sweep_breakout_classifier` (`[ART-10]`). Support dual breakout confirmation and use TRAP + CHOCH as reversal setup trigger. |
| **Range Invalidation on Swing Break** | `src/engine/skills/premium_discount_filter.py` | Computes 50% equilibrium from leg, but does not flag range invalidation when extreme is breached. | **YES — ART-07**: "If price closes below the swing low, structure is broken, discount was not cheap after all. Step aside and draw a new range." | **AMEND**: Add `range_valid` boolean flag to `premium_discount_filter` (`[ART-07]`). Set `range_valid=False` on closed candle beyond leg extreme; block entries until new range forms. |
| **External / Internal Liquidity Loop** | `src/smc/liquidity.py` (missing loop) | Classifies static BSL/SSL pools, but has no concept of ERL -> IRL -> ERL flow or next draw target. | **MISSING — ART-03**: "From external, price tends to draw back to internal; from internal, it draws to external. Gap is often next draw before far high." | **ADD**: Implement `range_liquidity_loop` (`[ART-03]`). Expose `next_draw` (nearest unmitigated IRL gap, else nearest ERL pool) for target selection and R:R gating. |
| **HTF Pool Mapping (H0 Gate)** | `src/engine/pipeline.py` (starts at G1) | Pipeline evaluates LTF candles without prior mapping of HTF liquidity pools. | **YES — ART-10, ART-09, ART-04**: "Mandatory analysis order: Higher-timeframe pools first (PDH/PDL, PWH/PWL), then lower-timeframe reaction. Liquidity first, then structure, then the zone." | **ADD / AMEND**: Prepend `H0 HTF POOL MAP` (`[ART-04, ART-10]`) before G1 in `InstitutionalEaEnginePipeline`. Require HTF liquidity context before evaluating LTF triggers. |
| **Market Phase Labeler** | None (missing) | Repo lacks structured 4-phase tracking. | **MISSING — ART-01**: "1 Consolidation -> 2 Expansion -> 3 Retracement -> 4 Reversal. Easy to label afterward; live, pullback and reversal look the same." | **ADD**: Implement `market_phase_labeler` (`[ART-01]`) as descriptive, lagging context in G1b. Strictly forbid standalone trade triggering on phase. |
| **Delivery Lens (IPDA)** | None (missing) | Repo has no delivery lens labeling. | **MISSING — ART-05**: "Price seeks liquidity or rebalances. Lens only. Caveat: nobody outside can prove an algorithm exists." | **ADD**: Implement `delivery_lens_context` (`[ART-05]`). Expose `{SEEKING_LIQUIDITY, REBALANCING}` labels for logging and coach explanation. |
| **Candle Anatomy & S/R Zones** | `src/patterns/`, `src/smc/` | Uses exact horizontal lines for S/R; pattern library uses rigid candlestick rules. | **YES — ART-11**: "Support/resistance are zones, not lines. Candle anatomy: body = who won, wicks = rejection. Wait for level, define risk before entry." | **ADD**: Implement `candle_anatomy` and `sr_zones` (`[ART-11]`) with ATR-based zone width (`~0.5 x ATR`). Mandatory invalidation price defined before order send. |
| **Position Sizing from Stop vs Margin** | `src/risk/fit_engine.py:165-171`, `src/risk/position_sizing.py` | `fit_engine.py` scales down lot size to fit margin limits (`final_lot * (margin_limit / margin_req)`). | **YES — ART-12**: "The contract is simple. Leverage is not. Size your trade from your stop, not from your margin. Position size = risk / (stop * tick_val)." | **CORRECT**: Refactor `fit_engine.py`. Volume must strictly derive from stop loss distance and risk cap (`[ART-12]`). Margin check serves only as a hard binary gate (reject if margin insufficient), never as a lot scaling factor. |
| **Forex Volume vs Futures Volume** | `src/core/market_data.py`, `src/smc/` | Code references `tick_volume` without documenting broker limitations. | **YES — ART-13**: "Futures on central exchange has real volume; forex has no central exchange, volume is broker tick volume. Different brokers differ." | **CORRECT / DOC**: Tag all volume references in forex as `[DERIVED: BROKER TICK VOLUME]`. Forbid algorithms that assume real centralized volume in forex (`[ART-13]`). |
| **Break-Even at +1.0R / +0.5R** | `src/risk/trade_management.py:468` | Fixed +1R / +0.5R BE move was replaced in Phase 1 with structure-only trailing stop. | **NO CONFLICT — Remediated**: Now matches `[VIDEO 12]` (`be_move_mode: "structure_only"`). | **KEEP**: Structure-only trailing behind confirmed protected swings. Fixed BE remains off by default. |
| **First Pullback Entry** | `src/execution/continuous_scalper.py` | Buys/sells immediately upon first pullback. | **YES — VIDEO 1 & ART-06**: "Do not buy the first pullback (inducement). That pullback was bait. Wait for sweep." | **REMOVE / BLOCK**: Continuous scalper first-pullback entries blocked. Only `inducement_ob_entry` or `five_check_model` permitted. |
| **Chasing Extended Moves** | `src/execution/order_manager.py` | Rejection if live fill R:R < 1.5 or extension > 30%. | **NO CONFLICT — Aligned**: Matches `[VIDEO 14]` (`entry_quality_guard`). | **KEEP & AUGMENT**: Combine with `next_draw` target from `range_liquidity_loop` (`[ART-03]`). |
| **AI Coach Knowledge Base** | `docs/institutional_ea_coach_prompt.md`, `knowledge/forex_kb.json` | Currently contains Part 1 15-video knowledge. Lacks Part 2 13-video ICT concepts, caveats, and futures modules. | **MISSING Part 2 Modules**: Lacks `five_check_model`, `swing_hierarchy`, `liquidity_pools_bsl_ssl`, `range_liquidity_loop`, `delivery_lens`, `futures_basics`, `futures_vs_forex`. | **AUGMENT**: Update `knowledge/forex_kb.json` with Part 2 modules, mandatory caveats, and regenerate `docs/institutional_ea_coach_prompt.md`. |

---

## 4. Live-Trading Hazards Analysis & Remediation Matrix

| Hazard # | Hazard Description | Risk Severity | Current Code State | Remediation Specification |
|---|---|---|---|---|
| **H-01** | **Live Mode Enabled by Default** | **CRITICAL** | `config/settings.json` set to `DEMO`, `LIVE_TRADING_ENABLED: false`. Guarded in `src/core/config.py`. | **VERIFIED**: Requires explicit `LIVE_TRADING_ENABLED=true` env var, max daily loss limit, and kill switch before live orders can transmit (`[GROUND RULE 3]`). |
| **H-02** | **Forming Candle Leakage** | **CRITICAL** | `src/data/historical_loader.py` now uses `copy_rates_from_pos(..., 1, count)` to drop bar 0. | **VERIFIED**: All pipeline decisions evaluate closed candles only (`[GROUND RULE 4, VIDEO 6, 10, 15, ART-06, ART-10]`). |
| **H-03** | **Broker UTC Offset Mismatch** | **HIGH** | `src/core/market_data.py` detects broker offset and converts rates to UTC. | **VERIFIED**: Protects session alignment (London, NY AM/PM) and daily rollover blackouts. |
| **H-04** | **Unbounded Slippage on Market Orders** | **HIGH** | `src/execution/bridge_client.py` has `deviation: int = 15` points. `order_manager.py` checks live fill R:R. | **VERIFIED**: Orders exceeding slippage limits or failing $R:R \ge 1.5$ are rejected (`[VIDEO 14]`). |
| **H-05** | **Premature Break-Even Churn** | **HIGH** | `config/risk_config.json` set to `enable_break_even: false`, `be_move_mode: "structure_only"`. | **VERIFIED**: Stop loss trails only behind confirmed protected swings following a BOS (`[VIDEO 12]`). |
| **H-06** | **Position Sizing Derived from Margin** | **HIGH** | `src/risk/fit_engine.py` adjusts lot size down to fit margin limit rather than purely stop risk. | **TO REMEDIATE**: Update `fit_engine.py` to enforce that lot size is strictly derived from stop distance (`[ART-12]`). Margin check must act purely as a pass/fail gate. |
| **H-07** | **Unqualified Order Blocks & Sweeps** | **MEDIUM** | Older SMC engine permitted OBs without FVG, and sweeps without CHOCH. | **TO REMEDIATE**: Enforce Part 2 qualification (`[ART-06, ART-09, ART-10]`): OB requires BOS + FVG; sweep requires subsequent CHOCH body close. |
| **H-08** | **Forex Volume Misrepresentation** | **MEDIUM** | Tick volume used in analysis without explicit disclaimer of non-centralized exchange liquidity. | **TO REMEDIATE**: Add broker tick volume warning tag `[DERIVED: BROKER TICK VOLUME]` and disallow volume-weighted assumptions in forex (`[ART-13]`). |

---

## 5. Master Implementation & Migration Plan (Post-Approval)

Upon your approval of this audit report, implementation will proceed systematically:

### Step 1: Single Source of Truth (`knowledge/forex_kb.json`)
- Expand `knowledge/forex_kb.json` to incorporate all 28 videos (Part 1 cards 1–15, Part 2 cards ART-01 to ART-13).
- Embed all 12 reconciliation rules, Part 2 amendments, mandatory caveats, and glossary terms.

### Step 2: Implement New Part 2 Skills (`src/engine/skills/`)
Implement pure functions with full type hints, closed-candle evaluation, and dual bullish/bearish handling:
1. `swing_hierarchy.py` (`[ART-02]`): Recursive fractal swing ranking (STH, ITH, LTH) with confirmation lag and zero repainting.
2. `liquidity_pools_bsl_ssl.py` (`[ART-04, ART-10]`): HTF liquidity pool mapping (PDH/PDL, PWH/PWL, EQH/EQL) with timeframe weights.
3. `range_liquidity_loop.py` (`[ART-03]`): External (ERL) vs Internal (IRL) classification and `next_draw` resolution.
4. `market_phase_labeler.py` (`[ART-01]`): 4-phase move tracking (Consolidation, Expansion, Retracement, Reversal) as lagging context.
5. `delivery_lens_context.py` (`[ART-05]`): IPDA delivery lens labeling (`SEEKING_LIQUIDITY`, `REBALANCING`).
6. `five_check_model.py` (`[ART-06]`): Master Setup Type A (Sweep + CHOCH + Discount + FVG/OB + Plan). All 5 or no trade.
7. `order_block_detector.py` (`[ART-09]`): Strict OB qualification requiring BOTH body-close BOS AND unmitigated FVG.
8. `sweep_breakout_classifier.py` (`[ART-10]`): Pool touch classifier (`SWEEP` with required CHOCH, `BREAKOUT_CONFIRMED` via 2 closes or retest-hold).
9. `fvg_detector.py` (`[ART-08]`): 3-candle non-overlapping imbalance detector with 50% midpoint and close invalidation.
10. `candle_anatomy.py` & `sr_zones.py` (`[ART-11]`): Body/wick ratios, rejection detection, ATR-based S/R zones.

### Step 3: Amend Existing Part 1 Skills
- Update `sweep_fvg_entry.py`: Enforce mandatory CHOCH following sweep (`[ART-06, ART-10]`).
- Update `premium_discount_filter.py`: Implement `range_valid` flag invalidated on close beyond extreme (`[ART-07]`).
- Update `inducement_ob_entry.py`: Require OB qualification with FVG (`[ART-09]`).
- Update `breakout_trap_classifier.py`: Support retest-and-hold confirmation and TRAP reversal context (`[ART-10]`).

### Step 4: Upgrade Confirmation Pipeline (`src/engine/pipeline.py`)
Implement the amended P2-4 pipeline:
```
H0  HTF POOL MAP        liquidity_pools_bsl_ssl (PDH/PDL/PWH/PWL, EQH/EQL)
G1  TREND/STRUCTURE     swing_hierarchy -> trend_by_structure + protected_swing_marker
G1b MOMENTUM FLAG       structure_momentum_monitor + market_phase_labeler
G2  LOCATION            premium_discount_filter (+range_valid) + range_location_filter
G3  LIQUIDITY EVENT     sweep_breakout_classifier (SWEEP needs CHOCH; BREAKOUT needs confirm)
G4  TRIGGER TYPE        A: five_check_model | B: inducement_ob_entry | C: ifvg_inversion
G5  ZONE QUALITY        fvg_detector + order_block_detector (BOS+gap) + quality scores
G6  ENTRY SANITY        entry_quality_guard; live R:R from next_draw target
G7  RISK/EXEC           size from stop (never margin); spread/session filters
--> ENTER               limit in zone; stop at sweep extreme (A) or block (B)
--> MANAGE              stop_management_policy (structure-only trailing)
```

### Step 5: AI Coach Update (`docs/institutional_ea_coach_prompt.md`)
- Regenerate coach prompt and context using `scripts/generate_coach_prompt.py`.
- Include 11 new modules, mandatory caveat phrases, futures mechanics, and forex volume limitations.

### Step 6: Test Suite & Backtest
- Add comprehensive synthetic unit tests for Part 2 in `tests/test_institutional_ea_skills.py` (covering FVG formulas, OB BOS+gap, sweep vs run, swing hierarchy confirmation lag, five-check all-or-nothing, range invalidation, sizing from stop).
- Update bar-replay backtester `scripts/run_institutional_ea_backtest.py` and produce refreshed report in `reports/institutional_ea_backtest_report.md`.
- Commit and push to GitHub remote `origin/main`.

---

## 6. Phase 0 Recommendation & Sign-Off Request

> **Quant-Developer Assessment**: The existing engine provides a robust foundation. Integrating the 13 Art of Trading video rules and Part 2 amendments resolves ambiguity around swing ranking (`[ART-02]`), eliminates false sweep triggers by requiring structural confirmation (`[ART-06, ART-10]`), and enforces strict institutional qualification on order blocks (`[ART-09]`).
>
> **AWAITING USER OK**: In accordance with Ground Rule 0 and Phase 0, all findings and remediation steps are detailed above. Please review and provide your approval to proceed with the code modifications.
