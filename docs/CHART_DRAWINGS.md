# Chart Drawings Data Pipeline & Schema

> Documents the single typed drawings pipeline from the Institutional EA engine through the Control Service to the Companion chart renderer.

---

## 1. End-to-End Architecture

```
Trading Engine Analyzers (read-only)          MT5SyncService & CompanionRepository
  - WeeklyDailyEngine (PDH/PDL/PWH/PWL)         - Open positions (ticket, entry, SL, initial_sl, TP, open_time)
  - SessionLiquidityEngine (Asia H/L, sweep)    - Pending signals (signal_records)
  - LiquidityEngine (EQH/EQL/BSL/SSL, sweep)    - Closed trade history (trade_records)
  - FvgObEngine (FVG/IFVG, OB/Breaker)
  - MarketStructureEngine (BOS/MSS/CHoCH)
  - config/sessions.json (Asia/LDN/NY/Overlap)
                 │                                              │
                 └──────────────────────┬───────────────────────┘
                                        ▼
            companion/service/market/drawings_engine.py (Read-Only Observer)
                                        │
                      GET /api/chart/drawings?symbol=XAUUSD&tf=M5
                                        │
                                        ▼
              companion/src/utils/chartDrawingsSchema.ts (Validator)
                                        │
                                        ▼
            companion/src/components/LiveTradingChart.tsx (Canvas Renderer)
```

- **Zero strategy mutation**: `drawings_engine.py` imports and calls the exact engine classes with the exact parameters from `config/strategy_config.json` and `config/sessions.json`. No file under `src/` is modified.

---

## 2. Typed Drawing Schema (`schema_version = "1.0"`)

```ts
interface EngineDrawingsFeed {
  schema_version: "1.0";
  symbol: string;               // Canonical symbol (e.g. "XAUUSD")
  broker_symbol?: string;       // Broker symbol (e.g. "XAUUSD.m")
  timeframe: string;            // Chart timeframe ("M1" | "M5" | "M15" | "H1" | "H4")
  generated_at: string;         // ISO-8601 UTC timestamp
  broker_utc_offset_hours?: number;
  dropped_count?: number;
  counts: {
    liquidity: number;
    fvgOb: number;
    structure: number;
    sessions: number;
    trades: number;
  };
  drawings: EngineDrawingItem[];
}

interface EngineDrawingItem {
  id: string;                   // Deterministic stable ID (prevents duplicates on live refresh)
  type: "LIQ" | "SESS" | "FVG" | "OB" | "STRUCT" | "TRADE";
  subtype: string;              // e.g. "PDH", "EQH", "ASIA", "FVG", "OB", "BOS", "OPEN", "PENDING", "CLOSED"
  symbol: string;               // Canonical symbol
  broker_symbol?: string;
  timeframe: string;            // Engine timeframe the item was computed on
  start_time: number;           // Unix epoch seconds
  end_time: number | null;      // Unix epoch seconds, or null if open/active to right edge
  price_levels: {
    price?: number;             // LIQ, STRUCT
    sweep_time?: number | null; // LIQ (swept)
    sweep_price?: number | null;
    top?: number;               // FVG, OB
    bottom?: number;            // FVG, OB
    midpoint?: number;
    high?: number | null;       // SESS
    low?: number | null;        // SESS
    entry?: number;             // TRADE
    sl?: number;                // TRADE (current stop loss)
    initial_sl?: number;        // TRADE (original SL before BE/trailing)
    tp?: number;                // TRADE
    tp1?: number;               // TRADE (1.0R partial target)
    exit?: number;              // TRADE (closed)
    current?: number;           // TRADE (open)
    pnl?: number;               // TRADE
    rr?: number;                // TRADE
    volume?: number;            // TRADE
    ticket?: number;            // TRADE
    ownership?: string;         // TRADE ("BOT" | "MANUAL" | "OTHER_EA")
  };
  direction: "BULLISH" | "BEARISH" | "NEUTRAL";
  status: "ACTIVE" | "MITIGATED" | "SWEPT" | "INVALIDATED" | "EXPIRED" | "OPEN" | "PENDING" | "CLOSED";
  source: string;               // Engine class or service name
  meta?: Record<string, any>;
}
```

---

## 3. Validation Layer Rules

Both backend (`validate_drawing_item`) and frontend (`validateEngineDrawingsFeed`) enforce:
1. Envelope must contain a `drawings` array; otherwise marked `malformedFeed: true` and surfaced as a compact warning badge (chart candles stay intact).
2. Every item must have non-empty `id` and `source`, valid `type`, finite `start_time > 2000-01-01`, and canonical `symbol` matching the active chart symbol (suffixes like `.m` normalized).
3. Price invariants:
   - `LIQ` / `STRUCT`: finite positive `price`.
   - `FVG` / `OB`: finite positive `top` and `bottom` with `top > bottom`.
   - `TRADE`: finite positive `entry`.
4. Deduplication by `id` prevents duplicate overlays during live ticks/polling.
5. Per-layer caps (`LIQ: 24, SESS: 32, FVG: 16, OB: 14, STRUCT: 24, TRADE: 30`) keep rendering locked at 60fps.

---

## 4. Timeframe Hierarchy Rules

Timeframe rank: `M1 (1) < M5 (2) < M15 (3) < M30 (4) < H1 (5) < H4 (6) < D1 (7) < W1 (8)`.
- **Higher-timeframe drawings on lower timeframes**: Shown when `rank(drawing.timeframe) >= rank(chart_tf)` (e.g., `D1` PDH/PDL, `W1` PWH/PWL, `M15` Asia Range, `H1` structure/FVG/OB appear on `M5` and `M1`).
- **Lower-timeframe drawings on higher timeframes**: Filtered out (`rank(drawing.timeframe) < rank(chart_tf)` — e.g., an `M5` FVG never clutters `H1` or `H4`).
- **Sessions (`SESS`)**: Shown on all intraday timeframes (`M1` through `H4`), respecting `config/sessions.json` UTC windows and `broker_utc_offset_hours`.
- **Trades (`TRADE`)**: Open positions, pending signals, and closed trade history are shown on all timeframes for the matching canonical symbol only.

---

## 5. Text & Interaction Rules

- **Strict Text Rule**: No permanent text on the plot except:
  1. `"LONG POSITION"` / `"SHORT POSITION"` on trade position templates.
  2. `"FVG"` / `"OB"` (or `"IFVG"`) centered inside FVG/OB rectangles.
- All other details (level names like `PDH`/`EQH`, sweep time, `BOS`/`CHoCH`, session UTC windows, trade Entry/SL/TP/R:R/P&L) appear on **hover tooltips** and **click-to-pin detail cards**, and OHLC + change appears in the **toolbar strip above the plot**.
