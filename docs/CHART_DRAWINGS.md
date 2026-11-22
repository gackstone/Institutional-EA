# Institutional EA — Chart Drawings Architecture & Data Contract (`PART D`)

> **Branch:** `chore/audit-chart-copy`  
> **Chart Library:** TradingView Lightweight Charts (`lightweight-charts` `^5.3.0`, `createChart` + `CandlestickSeries` + synchronized SVG/HTML overlay layer)  
> **Primary Files:** `companion/src/components/LiveTradingChart.tsx`, `companion/src/services/dashboardDataAdapter.ts`, `companion/src/utils/tradeChartMath.ts`

---

## 1. End-to-End Drawing Pipeline (Bot -> Control Service -> Companion Chart)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Strategy & SMC Detection Layer (Python src/smc/ + MQL5 EA)           │
│    - src/smc/liquidity.py: LiquidityZone (PDH, PDL, PWH, PWL, EQH, EQL) │
│    - src/smc/fvg_ob.py: FairValueGap (FVG, IFVG), OrderBlock (OB)       │
│    - src/smc/market_structure.py: MarketStructureEvent (BOS, CHoCH, MSS)│
│    - src/core/schedule_mode.py: Sessions (Asia, London, NY, Overlap)    │
│    - src/execution/order_manager.py: Trade Lifecycle & Tighten-Only SL  │
│    - mql5/Experts/PythonBridgeEA.mq5: AFX_BOS_, AFX_FVG_, AFX_OB_, etc. │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. Control Service & SSE Transport (127.0.0.1:8765)                     │
│    - GET /api/status & GET /api/events (SSE stream)                     │
│    - Emits: mt5.symbols (bid/ask/digits/point), mt5.positions,          │
│      engine.last_signal, engine.last_trade, plus optional               │
│      mt5.drawings / smc_overlays payload                                │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. Companion Adapter & Multi-Timeframe Drawing Fixture                  │
│    (companion/src/services/dashboardDataAdapter.ts)                     │
│    - Normalizes broker symbol suffixes (XAUUSD.m / XAUUSDc -> XAUUSD)   │
│    - Snaps every drawing timestamp to exact candle bucket:              │
│      snappedTime = Math.floor(utcSec / tfSec) * tfSec                   │
│    - Computes causal SMC drawings directly from the active OHLC series  │
│      + live trade overlays when backend omits raw SMC arrays            │
│    - Caps active drawings per layer & prunes expired/mitigated items    │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. Synchronized Z-Ordered Renderer (LiveTradingChart.tsx)               │
│    - z-0: Lightweight Charts Candlestick Canvas                         │
│    - z-5: Shaded Zones (Sessions, FVG/IFVG, OB, Risk/Reward boxes)      │
│           with low-opacity translucent fills so candles stay crisp      │
│    - z-10: Horizontal Level Lines (Entry, SL, Ghost SL, TP1, TP2,       │
│            PDH/PDL/PWH/PWL/EQH/EQL) + Structure Break rays (BOS/CHoCH)  │
│    - z-20: Priority-Sorted Collision-Free Axis Labels, Signal Pins,     │
│            Interactive Hover Tooltips & Compact Layer Legend            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Complete Inventory of Bot Drawing Types & Coverage Matrix

| Drawing Category | Specific Sub-Types Produced by Bot | Bot Source (`src/` / `mql5/`) | Prior UI Support | Now Supported in `LiveTradingChart.tsx` |
| :--- | :--- | :--- | :--- | :--- |
| **1. Liquidity Levels** | `PDH`, `PDL`, `PWH`, `PWL`, `EQH` (Equal Highs), `EQL` (Equal Lows), `BSL`/`SSL` sweeps | `src/smc/liquidity.py` (`LiquidityZone`), `PythonBridgeEA.mq5` (`AFX_LIQ_`) | Only `PWH`, `PDH`, `PDL`, `PWL` (missing `EQH` / `EQL` & mitigation end-time) | **Full (`PDH`, `PDL`, `PWH`, `PWL`, `EQH`, `EQL`)** — anchored to formation candle, extending to right edge (or stopping/fading at sweep candle). |
| **2. Imbalances (FVG / IFVG)** | Bullish `FVG`, Bearish `FVG`, Inverse `IFVG` (mitigated vs active) | `src/smc/fvg_ob.py` (`FairValueGap`), `PythonBridgeEA.mq5` (`AFX_FVG_`) | Only 1 static unmitigated FVG box | **Full (`Bull FVG`, `Bear FVG`, `IFVG`)** — detected from 3-candle gaps on active timeframe, spanning from formation candle to mitigation candle (faded) or current bar. |
| **3. Order Blocks (OB)** | Bullish Demand `OB`, Bearish Supply `OB` (active vs mitigated) | `src/smc/fvg_ob.py` (`OrderBlock`), `PythonBridgeEA.mq5` (`AFX_OB_`) | Only 1 static OB box | **Full (`Bull OB`, `Bear OB`)** — anchored to last opposite candle before displacement impulse, with mitigation tracking and low-opacity fill. |
| **4. Market Structure** | `BOS` (Break of Structure), `CHoCH` (Change of Character), `MSS` (Market Structure Shift) | `src/smc/market_structure.py` (`MarketStructureEvent`), `PythonBridgeEA.mq5` (`AFX_BOS_`) | Only `MSS` and `CHoCH` text pins (no `BOS` horizontal break ray) | **Full (`BOS`, `CHoCH`, `MSS`)** — draws horizontal swing-pivot break ray from swing origin to break candle + compact pill tag. |
| **5. Sessions & Killzones** | `ASIAN`, `LONDON`, `LDN/NY OVERLAP`, `NEW YORK` session boxes | `src/core/schedule_mode.py`, `config/sessions.json` | Only London & Overlap bands | **Full (`ASIA`, `LDN`, `LDN/NY`, `NY`)** — snapped to UTC session hours on intraday timeframes (`M1`–`H1`) with high/low boundary frame. |
| **6. Trade Levels & Zones** | `Entry`, `Active SL`, `Ghost Initial SL`, `Trailing/Tightened SL`, `TP1`, `TP2`, `Risk Zone`, `Reward Zone` | `src/execution/order_manager.py`, `src/manual_mgmt/assessor.py` | Supported, but zones sat in front of canvas (`z-10`) | **Full** — shaded Risk/Reward zones use subtle translucent tint (`opacity <= 0.12`) with crisp borders, ghosted initial SL, and trailing SL step markers. |
| **7. Trade Lifecycle & Signals** | `BUY`/`SELL` Signal arrows, `Entry` tag (lot, score, ticket), `BE+` lock, `50% Partial`, `Trail SL`, `Closed` | `src/core/orchestrator.py`, `engine.last_signal` | Missing standalone `Signal` markers | **Full** — includes risk-approved/blocked `Signal` markers + trade lifecycle pins with hover tooltips. |

---

## 3. Rendering Correctness & Coordinate Rules

1. **Symbol Suffix Normalization (`normalizeCanonicalSymbol`)**:
   - Strips broker suffixes (`XAUUSD.m`, `XAUUSD.pro`, `XAUUSDc`, `BTCUSD.m`, `USDJPY.m`) so any position, signal, or drawing for `XAUUSD*` maps deterministically to the `XAUUSD` chart view.
2. **Timeframe Snapping & UTC Alignment (`snapTimestampToTimeframe`)**:
   - Every drawing timestamp (`startTime`, `endTime`, `entryTime`, `breakTime`) is snapped to the active timeframe bar boundary:
     `snappedSec = Math.floor(utcSeconds / tfSeconds) * tfSeconds`
   - When a timestamp falls outside the visible bar range or across a weekend gap, the projector clamps `X` to the nearest loaded bar coordinate rather than dropping or misplacing the drawing.
3. **Priority-Aware Collision Avoidance (`resolveLabelCollisions`)**:
   - Every right-axis label carries an explicit priority weight:
     - Priority `100`: `LIVE` price + floating R
     - Priority `95`: `ENTRY` (`BUY`/`SELL` lot, score, ticket)
     - Priority `90`: `SL` (Active Stop Loss)
     - Priority `85`: `TP1` / `TP2`
     - Priority `75`: `INIT SL` (Ghosted initial stop)
     - Priority `60`: `PDH` / `PDL` / `PWH` / `PWL` / `EQH` / `EQL`
   - When more than 10 labels compete in a tight vertical price range, lower-priority labels are pruned or offset with leader lines while keeping all labels strictly inside `[minY, maxY]`.
4. **Layer Persistence & Caps**:
   - Layer toggle state (`Liq`, `FVG/OB`, `Struct`, `Sess`, `Trades`) persists in `localStorage` (`iea_chart_overlay_toggles_v1`).
   - Caps rendered items per layer (max `6` liquidity levels, `4` FVG/OB zones, `4` structure breaks, `3` session boxes, `4` trades) so 60fps pan/zoom performance never degrades.
