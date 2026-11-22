# Engine Drawings & Chart Overlay Inventory

> Generated during Part 1 inspection on branch `feat/dashboard-controls-chart-drawings`.
> Covers every drawing/setup computed by the Institutional EA trading engine, how it currently reaches (or fails to reach) the Companion Control Service, and what the Companion chart currently renders, misses, or mis-renders.

---

## 1. Engine Drawings Inventory

> **Directory note**: Top-level `engine/` and `intelligence/` are namespace packages (`__init__.py` only). All active trading engine logic lives under `src/smc/`, `src/engine/`, `src/core/`, `src/execution/`, `src/risk/`, and `mql5/Experts/PythonBridgeEA.mq5`.

### 1.1 Liquidity Levels & Pools (`LIQ`)

| Type | Source Module | Timeframes | Lookback / Thresholds | Storage / Emission | Lifecycle | Reaches Control Service Today? |
|---|---|---|---|---|---|---|
| **Weekly & Daily Reference Levels** (`PWH`, `PWL`, `PWM`, `PDH`, `PDL`, `PDM`, `CWO`, `CWH`, `CWL`, `CDO`, `CDH`, `CDL`) | `src/smc/weekly_daily.py` (`WeeklyDailyEngine.calculate_levels`, `analyze_interaction`) | Computed from `W1` & `D1`; interactions checked on `M15` (`src/smc/mtf_analyzer.py:121-124`) | >=2 `W1` & >=2 `D1` bars; filters Sunday micro-bars; `buffer_pips = 2.0` | In-memory `orchestrator.active_contexts[symbol].levels` | Stateless per scan; classifies `*_SWEEP` vs `*_ACCEPTED_BREAK` | **No** (no service route or state export) |
| **Session Liquidity** (Asia Range High/Low/Mid + London Judas Sweep) | `src/smc/session_liquidity.py` (`SessionLiquidityEngine`) | `M15` (`src/smc/strategy_engine.py:248-251`) | Asia `00:00–09:00 UTC`; London sweep `06:00–12:00 UTC`; tolerance `2.0 * pip_size` | Local variables in `SmcStrategyEngine.scan_for_opportunities` | Daily range (`AsiaRangeLevels`); `AsiaSweepEvent` when London bar wicks beyond & closes back inside | **No** |
| **Swing BSL/SSL & Equal Highs/Lows (`EQH`/`EQL`) + Sweeps** | `src/smc/liquidity.py` (`LiquidityEngine.identify_liquidity_pools`, `verify_sweep`), `src/smc/advanced_market_structure.py` (`AdvancedLiquidityMapper`) | `M15` in `SmcStrategyEngine`; `M1/M5/M15` in `ContinuousScalpingEngine` (`src/execution/continuous_scalper.py:788-867`) | `swing_lookback_bars = 5` (`config/strategy_config.json:26`), `eqh_tolerance_pips = 2.0`, `min_prominence_atr = 0.8`, `sweep_requires_close_back_inside = true`, `max_close_back_bars = 2` | In-memory only (only `liquidity_points_count` int in `SignalCandidate.metadata`) | `ACTIVE` / `RESTING` -> `SWEPT` (wick + close back inside) or `RUN` / `EXPIRED` | **No** |

### 1.2 Sessions & Killzones (`SESS`)

| Type | Source Module | Timeframes | Configured UTC Windows | Storage / Emission | Lifecycle | Reaches Control Service Today? |
|---|---|---|---|---|---|---|
| **Trading Sessions & Killzones** (Asia, London, New York, London/NY Overlap, Gold Killzones) | `src/core/sessions.py` (`TradingSessionEngine`) + `config/sessions.json` | Applies across all intraday timeframes (`M1`, `M5`, `M15`, `H1`, `H4`) | `active_profile = "ist_reference"`: Asia `00:00–09:00 UTC`, London `06:00–12:00 UTC` (KZ `07:00–10:30 UTC`), New York `12:30–17:30 UTC` (KZ `13:00–16:00 UTC`), Overlap `12:30–16:00 UTC` (Gold Overlap `12:30–16:30 UTC`). Legacy fallback: Asia `00:00–08:00`, London `08:00–16:00`, NY `13:00–21:00`, Overlap `13:00–16:00`. | Loaded from `config/sessions.json` | Repeating daily UTC windows (weekdays for FX/Gold, 24/7 UTC windows for BTC) | **No** (`dashboardDataAdapter.ts:293` hardcodes `sessions: []`) |

### 1.3 Fair Value Gaps (`FVG`, `IFVG`, `BPR`)

| Type | Source Module | Timeframes | Lookback / Thresholds | Storage / Emission | Lifecycle | Reaches Control Service Today? |
|---|---|---|---|---|---|---|
| **Fair Value Gaps & Inverse FVGs** | `src/smc/fvg_ob.py` (`FvgObEngine.detect_fvgs`), `src/smc/bpr_ifvg_helpers.py` (`detect_bpr_zones`), `src/smc/advanced_market_structure.py` (`FvgBreakerEngine`) | `W1, D1, H4, H1, M15` (`mtf_analyzer.py:188`), `M15` (`strategy_engine.py:235`), `M1/M5/M15` (`continuous_scalper.py:751-785`) | 3-candle imbalance (`c3.low > c1.high` bull / `c1.low > c3.high` bear); min gap `max(1.5 pips, 0.3 * ATR14)` (`config/strategy_config.json:27-28, 74`); optional impulse body/range `>= 0.50` | In-memory only (`fvg_count` on `TimeframeAnalysis`; `best_fvg` on `SignalCandidate`) | Created at `c2.time` -> `ACTIVE` -> `MITIGATED` (future bar reaches far boundary, `mitigation_time` recorded) -> `IFVG` (body close through far boundary) -> `INVALIDATED` | **No** |

### 1.4 Order Blocks & Breaker Blocks (`OB`)

| Type | Source Module | Timeframes | Lookback / Thresholds | Storage / Emission | Lifecycle | Reaches Control Service Today? |
|---|---|---|---|---|---|---|
| **Order Blocks & Breaker Blocks** | `src/smc/fvg_ob.py` (`FvgObEngine.detect_order_blocks`), `src/smc/advanced_market_structure.py` (`BreakerZone`) | `W1, D1, H4, H1, M15` (`mtf_analyzer.py:189`), `M15` (`strategy_engine.py:236, 275`) | Prior swing window 10 bars; `ob_requires_displacement = true` (`1.2 * ATR` or leaves FVG); `ob_requires_bos = true` (`config/strategy_config.json:34-36, 71-73`); `strength_score` in `[0.20, 1.0]` | In-memory only (`ob_count` on `TimeframeAnalysis`; `best_ob` on `SignalCandidate`) | Created at `c_ob.time` -> `ACTIVE` -> `MITIGATED` (future bar pierces far boundary) | **No** |

### 1.5 Structure Breaks & Swing Points (`STRUCT`: `BOS`, `MSS`, `CHoCH`)

| Type | Source Module | Timeframes | Lookback / Thresholds | Storage / Emission | Lifecycle | Reaches Control Service Today? |
|---|---|---|---|---|---|---|
| **BOS / MSS / CHoCH Structure Breaks** | `src/smc/market_structure.py` (`MarketStructureEngine.find_swing_points`, `analyze_structure`), `src/smc/structure_confirmation.py` (`StructureStateMachine`) | `W1, D1, H4, H1, M15` (`mtf_analyzer.py`), `M15` (`strategy_engine.py:230-233`) | `swing_lookback_bars = 5`, `bos_body_close_required = true`, `displacement_ratio_min = 0.60`, `choch_timeout_bars = 20` (`config/strategy_config.json:26, 31-32, 40, 65-67`) | In-memory only (`m15_events`, `StructureStateMachine._states`) | Swing point formed -> break candle confirms `BOS` / `CHoCH` / `MSS` -> state transitions `CHOCH_WARNING -> PULLBACK -> BOS_CONFIRMED | FAILED_TRAP` | **No** |

### 1.6 Trade Setups, Signals & Position History (`TRADES`)

| Type | Source Module | Timeframes | Parameters | Storage / Emission | Lifecycle | Reaches Control Service Today? |
|---|---|---|---|---|---|---|
| **Open MT5 Positions** | `companion/service/mt5/sync_service.py:262-411, 583-652` | Displayed on all TFs | `ticket`, `symbol`, `direction`, `volume`, `entry_price`, `current_price`, `stop_loss`, `take_profit`, `floating_pnl`, `ownership` (`BOT`/`MANUAL`/`OTHER_EA`), `open_time` (missing in current JSON) | In-memory `MT5SyncService.positions` + SQLite `trade_records` + SSE `mt5_sync` | `OPEN` -> `MODIFIED` (SL/TP updates) -> `CLOSED` | **Partially** (see schema bugs below) |
| **Pending Signals** | `src/smc/strategy_engine.py`, `src/execution/continuous_scalper.py`, `companion/database/repository.py:487-526` | Signal TF (typically `M15`, `M5`, `M1`) | `entry_price`, `stop_loss`, `take_profit`, `risk_reward`, `score`, `status` | SQLite `signal_records` (`GET /api/signals`), though `TradingBotOrchestrator` currently keeps `recent_signals` in memory only | `PENDING` -> `EXECUTED` / `EXPIRED` / `REJECTED` | **Partially** (`GET /api/signals` exists, not wired to chart; `orchestrator.py` does not write to `signal_records`) |
| **Closed Trade History** | `companion/database/repository.py:350-409` | Displayed on all TFs | `ticket`, `symbol`, `direction`, `entry_price`, `exit_price`, `stop_loss`, `take_profit`, `realized_pnl`, `opened_at`, `closed_at` | SQLite `trade_records` (`GET /api/trades/history`) | `CLOSED` | **Yes in API, not wired to chart** |
| **Trailing / BE / TP1 State** | `src/risk/trade_management.py`, `src/execution/fast_exit_manager.py` | Runtime | `initial_stop_loss`, `tp1` (`1.0R`), BE trigger (`0.5R` + 5pt), progressive ratchets | In-memory on `Position` in `orchestrator.py` | Live mutation during trade | **No** (gap: `initial_sl` and `tp1` are not exported by `MT5SyncService` unless captured on first seen open) |

---

## 2. Companion Chart Audit: Rendered vs. Missing vs. Wrong

### Currently Rendered (`companion/src/components/LiveTradingChart.tsx`)
- Live OHLC candlesticks via `lightweight-charts` v5 (`GET /api/market/candles` polled every 5s).
- Header Bid/Ask/Spread/Freshness readout.
- Open MT5 position labels (partially broken — see below).

### Missing
1. **All 4 SMC drawing layers are permanently empty**: `companion/src/services/dashboardDataAdapter.ts:290-293` hardcodes:
   - `liquidityLevels: []`
   - `fvgObZones: []`
   - `structureBreaks: []`
   - `sessions: []`
2. **No backend endpoint** exists in `companion/service/api/server.py` to serve engine drawings.
3. **Closed trades & pending signals** are never passed into `buildSymbolChartBundle()`, so closed trades and pending signals never draw on the chart.
4. **Hover tooltips, click-to-pin details cards, Jump-to-Latest button, OHLC toolbar readout, and toggle count badges** are not implemented.

### Wrong / Broken
1. **Open Position Schema Mismatch**: `companion/service/mt5/sync_service.py:617-632` emits `stop_loss` and `take_profit` (and omits `open_time`), while `companion/src/services/dashboardDataAdapter.ts:241, 256-259` reads `p.sl`, `p.tp`, and `p.protected` (all `undefined`), causing SL/TP profit & loss zones to never render.
2. **Wrong Position Entry Time**: `dashboardDataAdapter.ts:246` snaps `entryTime` to `latestBarTime` instead of the position's actual MT5 open timestamp.
3. **Engine Status Schema Mismatch (Top Bar)**: `EngineController.get_status()` emits `state`, `stop_flag_present`, `pause_flag_present`, while the frontend reads `engine_state`, `stop_flag_active`, `pause_flag_active`.
4. **Hardcoded DOM/SVG Overlay Margins & Canvas Performance**: `LiveTradingChart.tsx` uses DOM `<div>`/`<svg>` nodes per drawing with hardcoded `right: 72px; bottom: 28px`, causing axis drift, DOM churn on ticks, and missing overlays in `takeScreenshot()`.
5. **Session Time Discrepancy**: `tradeChartMath.ts:452-460` uses hardcoded UTC windows that do not match `config/sessions.json` (`ist_reference` profile).

---

## 3. Recommended Zero-Touch Architecture for Engine Drawings

To follow **Safety Rule 5** (zero changes to trading strategy, signal detection, risk rules, or order-decision logic), the Control Service will host a **purely read-only observer module** (`companion/service/market/drawings_engine.py`) that:
1. Imports and calls the **exact engine modules** (`WeeklyDailyEngine`, `SessionLiquidityEngine`, `LiquidityEngine`, `FvgObEngine`, `MarketStructureEngine`, `TradingSessionEngine`) with the **exact parameters from `config/strategy_config.json` and `config/sessions.json`** on the live MT5 candles (W1, D1, H4, H1, M15, M5, M1).
2. Merges open MT5 positions (with real `open_time`, `stop_loss`, `take_profit`, and first-seen `initial_stop_loss` tracking in `MT5SyncService`), pending signals from `CompanionRepository.get_signals()`, and closed trades from `CompanionRepository.get_trade_history()`.
3. Exposes a single typed endpoint `GET /api/chart/drawings?symbol=...&tf=...` (snapshot) plus live SSE `chart_drawings` updates, with zero modifications to `src/smc/*`, `src/core/*`, `src/execution/*`, or `src/risk/*`.
