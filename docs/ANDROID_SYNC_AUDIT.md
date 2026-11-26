# Institutional EA — Windows → Android Companion Cloud Sync Deep Audit

**Audit Date:** 2026-11-27  
**Repository:** `https://github.com/gackstone/Institutional-EA` (`fix/android-sync-audit` from `main`)  
**Scope:** Read-Only Android Companion App (`v1.3.6`, Sync Schema `v1.0.0`) paired to Windows Companion (`v1.3`) in **Cloud (Cross-Network) Mode** via Supabase.  
**Audit Methodology:** Evidence-driven, read-only end-to-end code & live runtime inspection across Producer (Windows/Python/Electron), Transport/Backend (Supabase PostgreSQL + Edge Functions), Shared Contracts (`@institutional-ea/data-contract`), and Consumer (Android React Native/Expo).

---

## 1. Baseline Test Counts (Recorded Before Any Edits)

| Suite | Command | Passed | Failed | Notes |
|---|---|---:|---:|---|
| **Windows Companion Unit Tests** | `npm run test:desktop` | **49** | 0 | Trade math, TV light theme, topbar control state, chart drawings parity, startup safety, LuxAlgo SMC, dashboard cleanliness, cloud auth/security, cloud mobile pairing & sync |
| **Shared Data Contract Tests** | `npm test --workspace=@institutional-ea/data-contract` | **9** | 0 | Account, Position, SMC Zone, Device Token, Security, Mobile Status, Pairing QR, Read-Only HTTP guard |
| **Shared Chart Core Tests** | `npm test --workspace=@institutional-ea/chart-core` | **4** | 0 | Theme tokens, R-multiples, tighten-only stop policy, FVG/OB centered labels |
| **Shared Cloud Contract Tests** | `npm test --workspace=@institutional-ea/cloud-contract` | **4** | 0 | Binance USDT TRC20 config, subscription entitlement, TXID validation, password policy |
| **Android Mobile Unit Tests** | `npm run test:mobile` | **14** | 0 | Theme tokens, SecureStorage, ReadOnlyGuard, backoff, stale detection, QR parsing, OfflineCache, formatters, chart bundle |
| **Total Monorepo JS/TS Tests** | `npm run test:all` | **80** | 0 | All 80 pass |
| **Python Mobile Sync & Companion Suite** | `.venv\Scripts\python.exe -m pytest tests/test_mobile_sync_server.py tests/test_chart_drawings_engine.py tests/test_luxalgo_smc.py tests/test_market_feed.py tests/test_no_hardcoded_market_data.py` | **35** | 0 | Mobile sync server, chart drawings, LuxAlgo SMC, market feed |
| **Python Full Quantitative Suite** | `.venv\Scripts\python.exe -m pytest` | **708** | 53* | *Legacy tests using `EURUSD`/`GBPUSD` blocked by unconditional 3-symbol lockdown (`XAUUSD`, `USDJPY`, `BTCUSD`), documented in `INSTITUTIONAL_EA_FINAL_TEST_RESULTS.md` |

---

## 2. End-to-End Architecture & Data Chain Map

### 2.1 Producer (Windows Companion Side)

There are **two distinct telemetry production paths** on Windows:

1. **Python Local Control Service (`companion/service/api/server.py` + `companion/service/mobile/sync_server.py` + `companion/service/mt5/sync_service.py` + `companion/service/market/drawings_engine.py`)**:
   - `MT5SyncService.sync_all()` (`companion/service/mt5/sync_service.py:337-504`) connects to MetaTrader 5, reads `mt5.account_info()`, `mt5.positions_get()`, `mt5.orders_get()`, discovers the 3 symbols (`XAUUSD.m`, `USDJPY.m`, `BTCUSD.m`), records balance snapshots via `self.repo.record_balance_snapshot()` (line 471), and upserts every open MT5 position into SQLite `trade_records` with `status="OPEN"` (lines 747-763).
   - **Critical Finding in `MT5SyncService.sync_all()`:** It **never queries `mt5.history_deals_get()`** to backfill or reconcile closed MT5 deals into `trade_records` (`status="CLOSED"`). As a result, `companion_control.db` on the live machine contains **184 rows in `trade_records`, all 184 with `status='OPEN'` and `closed_at=None`**, while live MT5 terminal history has **407 closed deals** (`entry IN (1, 2)`).
   - `ChartDrawingsService.get_drawings(symbol, timeframe, count)` (`companion/service/market/drawings_engine.py:829-877`) fetches real MT5 candles (`M1`..`H4` plus `D1`/`W1`/`MN1` for MTF highs/lows), runs `detect_luxalgo_smc()`, computes session boxes (`_build_session_drawings`), projects open positions / pending signals / closed trades, and returns `{ schema_version: "1.0", symbol, broker_symbol, timeframe, generated_at, counts: { liquidity, fvgOb, structure, sessions, trades }, drawings: [...] }`.
   - `MobileSyncManager` (`companion/service/mobile/sync_server.py:258-1088`) serves the **LAN fallback** endpoints (`/api/mobile/v1/status`, `/account`, `/stats`, `/positions`, `/trades`, `/symbols`, `/candles`, `/drawings`, `/equity`, `/activity`, `/events`), **not** the Cloud Relay.

2. **Electron Renderer Cloud Publisher (`companion/src/App.tsx:535-583` → `companion/electron/preload.cjs` → `companion/electron/main.cjs:3325-3332` → `companion/electron/cloudAuthManager.cjs:817-837`)**:
   - Every **15 seconds**, `App.tsx:542-575` executes `pushSnapshot()` and calls `api.cloudMobilePushSnapshot(...)`.
   - Look at what `App.tsx:547-571` actually sends:
     ```ts
     await api.cloudMobilePushSnapshot({
       sequenceNo: cloudSyncSeqRef.current,
       status: {
         botState: effectiveStatus.engine.state,
         mt5Connected: effectiveStatus.mt5.connection_status === "CONNECTED",
         demoMode: effectiveStatus.mt5.account.demo_verified,
         broker: effectiveStatus.mt5.account.broker,
         accountMasked: effectiveStatus.mt5.account.account_number
           ? `****${String(effectiveStatus.mt5.account.account_number).slice(-4)}`
           : "DEMO",
         readOnlyEnforced: true,
       },
       account: {
         balance: effectiveStatus.mt5.account.balance,
         equity: effectiveStatus.mt5.account.equity,
         floatingPnl: Number(
           (effectiveStatus.mt5.account.equity - effectiveStatus.mt5.account.balance).toFixed(2)
         ),
         currency: effectiveStatus.mt5.account.currency || "USD",
         openPositionsCount: effectiveStatus.mt5.positions.length,
       },
       positions: effectiveStatus.mt5.positions,
       trades: normalized.recentTrades.slice(0, 50),
       signals: (sigRes.signals || []).slice(0, 40),
     });
     ```
   - **What is omitted by `App.tsx:547-571`:**
     - `stats` is **never sent** (`body.stats` is `undefined`).
     - `symbols` is **never sent** (`body.symbols` is `undefined`).
     - `account.margin`, `account.freeMargin`, `account.marginLevel`, `account.leverage` are **never sent**.
     - `candles` (per symbol and timeframe) are **never sent**.
     - `drawings` / `overlays` / `trade_markers` are **never sent**.
     - `equity_snapshots` (`balanceSnapshots`) are **never sent** (even though `App.tsx:137,337` already loads `balanceSnapshots` into state!).
     - `trades` sends `normalized.recentTrades.slice(0, 50)`, which comes from `/api/analytics/equity` → `ctx.repo.get_trade_records(limit=500)` (`companion/service/api/server.py:291`), which returns **unfiltered `trade_records` rows (all 184 of which have `status='OPEN'`)**!

### 2.2 Transport / Backend (Supabase)

- **Database Schema (`supabase/migrations/20261126000003_mobile_cloud_pairing_sync.sql`)**:
  - `public.mobile_pairing_sessions` (lines 5-24): stores hashed 6-digit pairing codes (`code_hash`), `session_token_hash`, `claim_nonce_hash`, `status`, `issued_token_once` (wiped on first poll), `attempt_count`, `expires_at`.
  - `public.mobile_paired_devices` (lines 29-45): stores `token_hash`, `scope TEXT NOT NULL DEFAULT 'read_only' CHECK (scope = 'read_only')`, `status CHECK (status IN ('active', 'revoked'))`, `token_expires_at`, `last_seen_at`.
  - `public.companion_telemetry_snapshots` (lines 49-64): stores one row per `(user_id, companion_device_id)` with columns:
    - `sequence_no BIGINT`
    - `status_json JSONB`
    - `account_json JSONB`
    - `stats_json JSONB`
    - `positions_json JSONB`
    - `orders_json JSONB`
    - `trades_json JSONB`
    - `signals_json JSONB`
    - `symbols_json JSONB`
    - `updated_at TIMESTAMPTZ`
  - **Missing Backend Columns in `companion_telemetry_snapshots`**: There are no columns (or sub-payloads) for `candles_json`, `drawings_json` (overlays + trade markers), `equity_json` (equity curve snapshots), or `meta_json` (schema version, producer version, sync diagnostics).
- **Edge Function `supabase/functions/mobile-sync/index.ts`**:
  - Enforces `if (bearer.startsWith("iea_ro_")) { if (req.method !== "GET") return 403 READ_ONLY_VIOLATION }` (lines 31-40).
  - Looks up `mobile_paired_devices` by SHA-256 `token_hash`, checks `status === "active"`, `scope === "read_only"`, and `token_expires_at > now` (lines 42-55).
  - Returns the single snapshot row from `companion_telemetry_snapshots` (lines 62-83).
  - **CORS Headers Gap (`supabase/functions/_shared/auth.ts:6-10`)**: `Access-Control-Allow-Methods` only lists `"POST, OPTIONS"`, omitting `"GET"`.
  - **Unpair Gap (`supabase/functions/mobile-pairing/index.ts:336-344`)**: `action === "revoke"` requires a Windows user JWT (`requireAuthenticatedUser(req)` at line 189). There is **no `unpair_self` action** for an Android device authenticating with its own `iea_ro_*` token, and `MobileSyncClient.unpair()` (`apps/mobile/src/services/MobileSyncClient.ts:683-687`) simply does `if (this.isCloudMode()) { this.cloudCache = null; return; }` without notifying the server!

### 2.3 Consumer (Android Companion App)

- **API Client (`apps/mobile/src/services/MobileSyncClient.ts`)**:
  - In Cloud mode (`this.isCloudMode() === true`), every method (`getStatus`, `getAccount`, `getStats`, `getPositions`, `getSymbols`, `getCandles`, `getDrawings`, `getTrades`, `getEquity`, `getActivity`) reads from `fetchCloudSnapshot()` (`/functions/v1/mobile-sync`), which caches the snapshot for 3.5 seconds.
  - Because `App.tsx` in Windows Companion only pushed a tiny subset of fields and `MobileSyncClient.ts` has multiple broken or stubbed Cloud-mode adapters, every screen on Android breaks or diverges from desktop.

---

## 3. Root-Cause Analysis for Symptoms E1–E10

### E1 — Trades screen shows red raw Zod validation error (`summary` undefined, `items` undefined)

- **Symptom:** Red raw validation error on Trades tab: `ZodError: invalid_type, expected: object, received: undefined, path: ["summary"]` and `expected: array, received: undefined, path: ["items"]`. Deals / Net P&L / Win rate show `"—"`.
- **Exact Request/Response Path:**
  `TradesScreen.tsx:81` → `client.getTrades(...)` → `MobileSyncClient.ts:597-627` (Cloud mode branch) → `MobileTradesPageSchema.parse(...)` (`packages/data-contract/src/mobileSync.ts:122-136`).
- **Failing Component:** `apps/mobile/src/services/MobileSyncClient.ts:619-626` and `apps/mobile/src/screens/TradesScreen.tsx:96-98,369-378`.
- **Proof (`file:line` & Reproduced Payload):**
  - `packages/data-contract/src/mobileSync.ts:122-136` defines `MobileTradesPageSchema`:
    ```ts
    export const MobileTradesPageSchema = z.object({
      page: z.number().int().positive(),
      limit: z.number().int().positive(),
      total: z.number().int().nonnegative(),
      hasMore: z.boolean(),
      currency: z.string().min(1).max(12),
      summary: z.object({
        count: z.number().int().nonnegative(),
        netPnl: z.number().finite(),
        winRate: z.number().min(0).max(100),
        wins: z.number().int().nonnegative(),
        losses: z.number().int().nonnegative(),
      }),
      items: z.array(MobileTradeRecordSchema),
    });
    ```
  - Yet `apps/mobile/src/services/MobileSyncClient.ts:619-626` passes:
    ```ts
    return MobileTradesPageSchema.parse({
      page: 1,
      limit: mapped.length || 20,
      total: mapped.length,
      hasMore: false,
      currency: String(snap.account?.currency || "USD"),
      trades: mapped, // <-- WRONG KEY! Schema requires `summary` and `items`, NOT `trades`!
    });
    ```
  - Furthermore, `MobileSyncClient.ts:598-627` completely ignores the `params` argument (`page`, `limit`, `symbol`, `outcome`, `from`, `to`, `sort`, `q`), and `TradesScreen.tsx:98,371` renders `err.message` (which for a `ZodError` is the raw JSON array of Zod issues) directly into `<Text style={[styles.errorText, { color: tokens.loss }]}>{error}</Text>`.
- **Classification:** `SHAPE_MISMATCH` + `CLIENT_BUG`
- **Proposed Fix:**
  1. Publish authoritative closed trade history + summary from producer/backend.
  2. In `MobileSyncClient.getTrades()`, apply all filters (`symbol`, `outcome`, `from`, `to`, `sort`, `q`) and pagination (`page`, `limit`), compute `summary: { count, netPnl, winRate, wins, losses }`, and pass `items` (never `trades`) to `MobileTradesPageSchema.parse()`.
  3. Sanitize all errors in `TradesScreen` and across all screens via a human-friendly error mapper so raw Zod JSON is never rendered to users.
- **Risk:** Low (purely fixes broken Cloud-mode response construction and error display).

---

### E2 — Charts screen shows "Waiting for symbols...", "No candles available from companion yet", and all overlay chips 0

- **Symptom:** Charts tab shows `"Waiting for symbols…"`, `"No candles available from companion yet"`, and overlay chips `Liq (0)`, `FVG/OB (0)`, `Struct (0)`, `Sess (0)`, `Trades (0)` while desktop shows `XAUUSD.m` M5 candles with `Liq 14, FVG/OB 3, Struct 0, Sess 4, Trades 6`.
- **Exact Request/Response Path:**
  1. Symbols: `companion/src/App.tsx:547-571` → `mobile-sync/index.ts:133` → `MobileSyncClient.ts:532-542` → `ChartsScreen.tsx:119-122`.
  2. Candles: `App.tsx:203` → `MobileSyncClient.ts:545-559` → `MobileCandlesResponseSchema.parse(...)`.
  3. Drawings/Overlays: `App.tsx:204` → `MobileSyncClient.ts:574-584` → `ChartsScreen.tsx:94-103` → `ChartWebView.tsx` → `chartEntry.ts:170`.
- **Failing Components & Proof (`file:line`):**
  1. **Symbols never published (`NOT_PUBLISHED`):** `companion/src/App.tsx:547-571` never includes `symbols` in `cloudMobilePushSnapshot(...)`. Therefore `companion_telemetry_snapshots.symbols_json` defaults to `'[]'::jsonb` (`20261126000003_mobile_cloud_pairing_sync.sql:61`), and `MobileSyncClient.getSymbols()` returns `symbols: []`.
  2. **Candles hardcoded to empty & invalid schema (`NOT_PUBLISHED` + `SHAPE_MISMATCH`):**
     - `companion/src/App.tsx:547-571` never publishes candles to the cloud.
     - Worse, `apps/mobile/src/services/MobileSyncClient.ts:549-559` is a hardcoded stub in Cloud mode:
       ```ts
       if (this.isCloudMode()) {
         return MobileCandlesResponseSchema.parse({
           symbol: params.symbol,
           brokerSymbol: params.symbol,
           timeframe: params.tf,
           digits: params.symbol.includes("JPY") ? 3 : 2,
           candles: [],
           quote: null,
           statusReason: "CLOUD_TELEMETRY_MODE",
         });
       }
       ```
     - Even if called, `MobileCandlesResponseSchema` (`packages/data-contract/src/mobileSync.ts:149-163`) requires `point: z.number().positive()`, `bid: z.number().finite().nullable()`, `ask: z.number().finite().nullable()`, `spreadPoints: z.number().finite().nullable()`, none of which are provided in that stub — causing `MobileCandlesResponseSchema.parse()` to throw a `ZodError` caught silently in `apps/mobile/src/App.tsx:213-224`!
  3. **Drawings/Overlays hardcoded to empty AND three-way schema mismatch (`NOT_PUBLISHED` + `SHAPE_MISMATCH`):**
     - First, `companion/src/App.tsx:547-571` never publishes chart drawings to the cloud, and `MobileSyncClient.ts:578-584` stubs `getDrawings()` in Cloud mode to return `{ symbol: params.symbol, timeframe: params.tf, items: [] }`.
     - Second, even in LAN mode or when drawings are present, there is a **three-way contract mismatch** between Producer (`drawings_engine.py`), Data Contract (`MobileDrawingsResponseSchema`), ChartsScreen (`ChartsScreen.tsx`), and WebView (`chartEntry.ts` / `chartDrawingsSchema.ts`):
       - Python `compute_drawings_from_candles()` (`companion/service/market/drawings_engine.py:793-811`) returns:
         `counts: { "liquidity": ..., "fvgOb": ..., "structure": ..., "sessions": ..., "trades": ... }` and array key `"drawings": final_drawings`.
       - `MobileDrawingsResponseSchema` (`packages/data-contract/src/mobileSync.ts:182-192`) expects array key `"items": z.array(MobileDrawingItemSchema)` (not `"drawings"`!).
       - `ChartsScreen.tsx:48-58,94-103` looks up `drawings.counts?.[k]` using uppercase keys `["LIQ"]`, `["FVG", "OB"]`, `["STRUCT"]`, `["SESS"]`, `["TRADE"]` — whereas `drawings.counts` uses camelCase keys `liquidity`, `fvgOb`, `structure`, `sessions`, `trades`! Because `drawings.counts` is truthy, `if (drawings.counts)` enters line 98 and sums `drawings.counts["LIQ"]` (`undefined` → `0`), so **every overlay chip always renders `(0)`** even if drawings exist!
       - `chartEntry.ts:170` calls `validateEngineDrawingsFeed(drawingsFeed, symbol, timeframe)` (`packages/chart-core/src/chartDrawingsSchema.ts:142`), which checks `!Array.isArray((rawFeed as any).drawings)` — so if the object has `items` instead of `drawings`, WebView drops all drawings as `"Malformed feed envelope (missing drawings array)"`!
- **Classification:** `NOT_PUBLISHED` + `SHAPE_MISMATCH` + `CLIENT_BUG`
- **Proposed Fix:**
  1. Publish `symbols`, multi-timeframe `candles`, and `drawings` (overlays + trade markers) from Windows Companion to the Cloud Relay.
  2. Unify the drawings contract in v1.1.0 so both `drawings` and `items` (and both camelCase `{ liquidity, fvgOb, structure, sessions, trades }` and uppercase `{ LIQ, FVG, OB, STRUCT, SESS, TRADE }` count maps) are normalized and present.
  3. Update `ChartsScreen.tsx:94-103` and `MobileSyncClient.getCandles()` / `getDrawings()` to return real cloud-synced candles and drawings.
- **Risk:** Medium (must keep cloud payload sizes bounded per symbol/timeframe).

---

### E3 — Overview > Live Chart shows "Waiting for live candles from companion"

- **Symptom:** Mini Live Chart on Overview tab shows `"Waiting for live candles from companion"` while desktop streams live candles.
- **Exact Request/Response Path:**
  `OverviewScreen.tsx:122-142` checks `activeSymbol && candlesData && candlesData.candles.length > 0`. `activeSymbol` and `candlesData` come from `apps/mobile/src/App.tsx:256-265` (`fetchFullSnapshot` → `client.getSymbols()` + `fetchChartData(nextSym, selectedTimeframe)`).
- **Failing Component & Proof (`file:line`):**
  Same root cause as E2: `client.getSymbols()` in Cloud mode receives `symbols: []` (because `companion/src/App.tsx:547-571` does not push `symbols`), so `nextSym` is `null`; and even if `selectedSymbol` was cached, `client.getCandles()` in Cloud mode (`MobileSyncClient.ts:549-559`) throws a `ZodError` on missing `point`/`bid`/`ask`/`spreadPoints` and has `candles: []`.
- **Classification:** `NOT_PUBLISHED` + `SHAPE_MISMATCH`
- **Proposed Fix:** Same as E2 — once `symbols` and `candles` are published and parsed in Cloud mode, `nextSym` defaults to `XAUUSD` (or first symbol) and `OverviewScreen` renders the live mini chart immediately.
- **Risk:** Low.

---

### E4 — Overview > Equity Curve shows "No history yet / Waiting for equity snapshots from companion"

- **Symptom:** Overview > Equity Curve card always shows `"No history yet"` and `"Waiting for equity snapshots from companion"`.
- **Exact Request/Response Path:**
  `OverviewScreen.tsx:88-94` → `EquityCurveCard.tsx:31-34,70,103-108` → `App.tsx:244,378` → `MobileSyncClient.ts:641-658`.
- **Failing Component & Proof (`file:line`):**
  1. `EquityCurveCard.tsx:32,70,103` requires **`points.length >= 2`** to draw an SVG line/area path; when `points.length < 2`, it renders `"No history yet"` and `"Waiting for equity snapshots from companion"`.
  2. Look at `apps/mobile/src/services/MobileSyncClient.ts:641-651`:
     ```ts
     async getEquity(range: "1D" | "1W" | "1M" | "ALL" = "1W", signal?: AbortSignal): Promise<MobileEquityResponse> {
       if (this.isCloudMode()) {
         const snap = await this.fetchCloudSnapshot(signal);
         const bal = Number(snap.account?.balance || 0);
         const eq = Number(snap.account?.equity || bal);
         return MobileEquityResponseSchema.parse({
           range,
           currency: String(snap.account?.currency || "USD"),
           points: bal > 0 || eq > 0 ? [{ time: Math.floor(Date.now() / 1000), balance: bal, equity: eq, pnl: eq - bal }] : [],
         });
       }
     ```
     In Cloud mode, `getEquity()` is hardcoded to return **at most 1 synthetic point** (`points.length === 1`)! And `points.length < 2` is always true for 1 point!
  3. Meanwhile, on the Windows machine, SQLite `balance_snapshots` in `companion_control.db` already has **12,117 real equity snapshots**, and `companion/src/App.tsx:137,337` already fetches `res.snapshots` (`setBalanceSnapshots(res.snapshots || [])`), but `App.tsx:547-571` **never publishes `equity` / `balanceSnapshots`** to `cloudMobilePushSnapshot`!
- **Classification:** `NOT_PUBLISHED` + `CLIENT_BUG`
- **Proposed Fix:**
  1. Publish real downsampled/bounded equity curve points (supporting `1D`, `1W`, `1M`, `ALL` windows + trade close points) from Windows Companion to the Cloud snapshot.
  2. In `MobileSyncClient.getEquity(range)`, filter/slice the published `equity` points by the requested `range` (`1D`, `1W`, `1M`, `ALL`).
- **Risk:** Low.

---

### E5 & E6 — Overview stats disagree between Desktop and Android ("0 trades today" vs "6 trades today"; Android "50 deals total, 50.0% 25W/25L" vs Desktop "0 total deals, 0.0% 0W/0L")

- **Symptom:**
  - **E5:** Android shows `"0 trades today"` while Today P/L is a non-zero loss and Open Positions = 6; Desktop says `"6 trades today"`.
  - **E6:** Android shows `"50 deals total"`, win rate `"50.0% (25W/25L)"`, and a non-zero Total Profits; Desktop shows `"0 total deals"`, win rate `"0.0% (0W/0L)"`, and total profits equal to today's P/L only.
- **Exact Request/Response Path & Proof (`file:line` + Live SQLite Database Verification):**
  We traced both apps against the live SQLite database `%LOCALAPPDATA%\InstitutionalEA\Institutional EA Companion\data\companion_control.db`:
  1. **What is in `companion_control.db` right now?**
     - `MT5SyncService._reconcile_positions()` (`companion/service/mt5/sync_service.py:747-763`) calls `self.repo.upsert_trade_record({ ..., "status": "OPEN" })` on every sync cycle for open MT5 positions.
     - Nothing in `MT5SyncService` ever marks closed positions as `"CLOSED"` in `trade_records` or imports `mt5.history_deals_get()`.
     - Consequently, `trade_records` in `companion_control.db` has **184 rows, all 184 with `status = 'OPEN'` and `closed_at = None`**.
     - Querying the **most recent 50 rows** (`SELECT profit, status FROM trade_records ORDER BY id DESC LIMIT 50`) in `companion_control.db` yields:
       - **Count:** `50`
       - **Rows with `profit > 0`:** `25`
       - **Rows with `profit < 0`:** `25`
  2. **Why Desktop shows `0 total deals`, `0.0% (0W/0L)`, and `6 trades today`:**
     - In `companion/src/components/screens/CoreTradingScreens.tsx:295-300`, Desktop filters `dash.recentTrades`:
       ```ts
       const closedTrades = (dash.recentTrades || []).filter(
         (t) =>
           String(t.status || "").toUpperCase().includes("CLOSED") || Boolean(t.closed_at)
       );
       ```
     - Because all 184 rows in `trade_records` have `status: "OPEN"` and `closed_at: null`, `closedTrades` on Desktop has length **`0`**!
     - Thus Desktop displays:
       - `closedCount`: **`0 total deals`**
       - `winRatePct`: **`0.0% (0W / 0L)`**
       - `totalProfitsVal` (line 327-332): when `closedTrades.length === 0`, Desktop falls back to `kpis.todayPnlUsd ?? kpis.floatingPnl ?? 0` (which equals Today's floating P/L!).
       - `todayTradesCount` (line 316): `const todayTradesCount = closedToday.length + activePositions.length;` = `0 + 6` = **`6 trades today`**!
  3. **Why Android shows `50 deals total`, `50.0% (25W/25L)`, and `0 trades today`:**
     - In `companion/src/App.tsx:569`, Windows Companion pushes:
       ```ts
       trades: normalized.recentTrades.slice(0, 50),
       ```
       Wait: `normalized.recentTrades` is the **unfiltered** `trades` array from `/api/analytics/equity` (`repo.get_trade_records(limit=500)`), where **every row has `status: "OPEN"`**, sliced to `.slice(0, 50)` — i.e. **50 rows (25 with `profit > 0` and 25 with `profit < 0`)**!
     - And `companion/src/App.tsx:547-571` **does not push `stats` at all** (`snap.stats` is `{}`).
     - Then on Android, `MobileSyncClient.getStats()` (`apps/mobile/src/services/MobileSyncClient.ts:479-498`) runs:
       ```ts
       const s = snap.stats || {};
       const trades = Array.isArray(snap.trades) ? snap.trades : [];
       const wins = trades.filter((t: any) => Number(t.pnl ?? t.profit ?? 0) > 0).length;
       const losses = trades.filter((t: any) => Number(t.pnl ?? t.profit ?? 0) < 0).length;
       const total = trades.reduce((acc: number, t: any) => acc + Number(t.pnl ?? t.profit ?? 0), 0);
       return MobileStatsSchema.parse({
         todayPnl: Number(s.todayPnl ?? snap.account?.floatingPnl ?? 0),
         totalProfit: Number(s.totalProfit ?? total),
         winRate: Number(s.winRate ?? (wins + losses > 0 ? (wins / (wins + losses)) * 100 : 0)),
         dealsCount: Number(s.dealsCount ?? trades.length),
         tradesToday: Number(s.tradesToday ?? 0),
         winsCount: Number(s.winsCount ?? wins),
         lossesCount: Number(s.lossesCount ?? losses),
         ...
       });
       ```
     - Look at what that computes from the 50 pushed `"OPEN"` rows:
       - `dealsCount`: `trades.length` = **`50`** (`"50 deals total"`)!
       - `winsCount`: **`25`**, `lossesCount`: **`25`** → `winRate`: `25 / 50 * 100` = **`50.0% (25W/25L)`**!
       - `totalProfit`: sum of `profit` across those 50 open position snapshots!
       - `tradesToday`: `Number(s.tradesToday ?? 0)` = **`0`** (`"0 trades today"`), while `todayPnl` falls back to `snap.account?.floatingPnl` (the floating loss on the 6 open positions)!
- **Mystery Solved 100% with Zero Guessing:**
  The `"50 deals total / 50.0% (25W/25L)"` on Android is **not** mock or hardcoded seed data — it is the `normalized.recentTrades.slice(0, 50)` slice of the 184 stale `status='OPEN'` rows in `companion_control.db`, evaluated by Android's fallback client-side calculation in `MobileSyncClient.getStats()` without filtering for `status === 'CLOSED'`, while `s.tradesToday` defaulted to `0` because `stats` was never published by `companion/src/App.tsx`!
- **Classification:** `CALCULATION_DIFFERENCE` + `NOT_PUBLISHED` + `STALE_OR_SEEDED_DATA` (stale `OPEN` rows in `trade_records` never reconciled against MT5 closed deals).
- **Proposed Fix:**
  1. **Reconcile real MT5 closed deals in `MT5SyncService.sync_all()`:** Query `mt5.history_deals_get()` for closed deals (`DEAL_ENTRY_OUT` / `DEAL_ENTRY_INOUT`), upsert closed deal records into `trade_records` with `status="CLOSED"`, `closed_at`, `close_price`, `profit`, `commission`, `swap`, and transition any previously `"OPEN"` row in `trade_records` whose ticket is no longer in `mt5.positions_get()` to `"CLOSED"` (or remove stale orphan `OPEN` rows that aren't open in MT5).
  2. **Single Source of Truth for Aggregates (`stats` / `summary`):** Compute `stats` once on the Producer (`todayPnl`, `totalProfit`, `winRate`, `dealsCount`, `tradesToday`, `winsCount`, `lossesCount`, `openPositionsCount`) using explicit, identical definitions across Desktop and Android, and publish `stats` in the cloud snapshot.
  3. **Delete Divergent Client Calculations:** Both Desktop and Android must consume the authoritative `stats` summary and only treat `status === "CLOSED"` records as closed deals.
  4. **Key OfflineCache by `(deviceId, accountMasked, schemaVersion)`:** Invalidate cached snapshots automatically when the account, device, or schema version changes.

---

### E7 — Overview > Active Positions show `SL —` and `TP —` (SAFETY FINDING VERIFIED AGAINST LIVE MT5)

- **Symptom:** Active Positions on Android show `SL —` and `TP —`.
- **Verification Against Live MT5 Terminal & Desktop:**
  We queried the live MetaTrader 5 terminal (`mt5.positions_get()`) directly and found **6 open `XAUUSD.m` BUY positions**:
  - `#2738475820`: `XAUUSD.m` BUY 0.02 @ `3570.92`, **`sl: 0.0`, `tp: 0.0`**, `magic: 0`
  - `#2738475828`: `XAUUSD.m` BUY 0.02 @ `3570.93`, **`sl: 0.0`, `tp: 0.0`**, `magic: 0`
  - `#2738475831`: `XAUUSD.m` BUY 0.02 @ `3570.93`, **`sl: 0.0`, `tp: 0.0`**, `magic: 0`
  - `#2738475834`: `XAUUSD.m` BUY 0.02 @ `3570.93`, **`sl: 0.0`, `tp: 0.0`**, `magic: 0`
  - `#2738475836`: `XAUUSD.m` BUY 0.02 @ `3570.93`, **`sl: 0.0`, `tp: 0.0`**, `magic: 0`
  - `#2738476138`: `XAUUSD.m` BUY 0.02 @ `3571.06`, **`sl: 0.0`, `tp: 0.0`**, `magic: 0`
- **Two Separate Findings on E7:**
  1. **Tier-1 Safety Finding (Real MT5 Positions Have `sl=0.0, tp=0.0`):** The 6 currently open `XAUUSD.m` positions in MT5 (`magic=0`, manual/unprotected) genuinely have **no Stop Loss (`0.0`) and no Take Profit (`0.0`)** set on the broker terminal. Per Hard Rule 2 & Section 5 (E7): **we must NOT alter trading or silently modify these positions**. Instead, we must surface a visible `"NO SL/TP"` warning badge on Android (`PositionsList.tsx`) matching Desktop's red `"NO SL"` warning (`ExecutionRiskScreens.tsx:160`), and report this as a Tier-1 Safety Finding.
  2. **Secondary Sync Bug When SL/TP *Are* Present:** In `MobileSyncClient.ts:514-515`:
     ```ts
     sl: p.sl !== undefined && p.sl !== null ? Number(p.sl) : null,
     tp: p.tp !== undefined && p.tp !== null ? Number(p.tp) : null,
     ```
     When `p.sl` is `0` (as MT5 reports when unset), `MobileSyncClient` sets `sl: 0` (instead of `null`). In `PositionsList.tsx:114`, `item.sl ? ... : "—"` treats `0` as falsy so the card row shows `"—"`, **but in the Position Detail Modal (`PositionsList.tsx:160-161`)**, `formatPrice(selected.sl, selected.digits)` formats `0` as **`"0.00"`** instead of `"NO SL"`! And if a position uses `stop_loss` / `take_profit` keys instead of `sl` / `tp`, `p.sl` is `undefined`.
- **Classification:** `SAFETY_FINDING (True MT5 state: sl=0.0, tp=0.0 on 6 positions)` + `SHAPE_MISMATCH` (`sl: 0` vs `null` & `stop_loss`/`take_profit` normalization).
- **Proposed Fix:**
  1. Normalize `sl` and `tp` in both producer and `MobileSyncClient.getPositions()`: read `p.sl ?? p.stop_loss` and `p.tp ?? p.take_profit`, and convert `<= 0` to `null`.
  2. When `sl === null` or `tp === null` on an open position, render an explicit high-visibility `"NO SL"` / `"NO TP"` warning badge on Android (`PositionsList.tsx` card and detail sheet) instead of silent `"—"` or `"0.00"`.
  3. Highlight the 6 unprotected `XAUUSD.m` positions in the Tier-1 Safety Finding section of this report.

---

### E8 — Overview shows Margin Level `"—"` while Desktop/MT5 has `1424.79%`

- **Symptom:** Overview secondary strip on Android shows `Margin Level —` while MT5 has `margin_level = 1424.79%` (`margin = $14.28`, `free_margin = $189.18`).
- **Exact Request/Response Path:**
  `companion/src/App.tsx:559-567` → `mobile-sync/index.ts:127` → `MobileSyncClient.ts:455-476` → `KpiCards.tsx:222-226`.
- **Failing Component & Proof (`file:line`):**
  Look at `companion/src/App.tsx:559-567`:
  ```ts
  account: {
    balance: effectiveStatus.mt5.account.balance,
    equity: effectiveStatus.mt5.account.equity,
    floatingPnl: Number(
      (effectiveStatus.mt5.account.equity - effectiveStatus.mt5.account.balance).toFixed(2)
    ),
    currency: effectiveStatus.mt5.account.currency || "USD",
    openPositionsCount: effectiveStatus.mt5.positions.length,
  },
  ```
  `companion/src/App.tsx` **omits `margin`, `freeMargin`, `marginLevel`, `leverage`, `tradeMode`, `broker`, and `accountMasked`** from the `account` object it pushes to the cloud!
  Therefore, in `MobileSyncClient.ts:463-465`:
  ```ts
  margin: Number(acc.margin || 0),
  freeMargin: Number(acc.freeMargin || 0),
  marginLevel: Number(acc.marginLevel || 0),
  ```
  `acc.marginLevel` is `undefined` → `0`. And in `KpiCards.tsx:224`:
  ```tsx
  {account && account.marginLevel > 0 ? formatPercent(account.marginLevel, 0) : "—"}
  ```
  Because `account.marginLevel` is `0`, `KpiCards.tsx` renders `"—"`!
- **Classification:** `NOT_PUBLISHED`
- **Proposed Fix:**
  1. Include `margin`, `freeMargin` (`free_margin`), `marginLevel` (`margin_level`), `leverage`, `tradeMode` (`trade_mode`), `broker`, and `accountMasked` in the cloud publisher payload.
  2. In `MobileSyncClient.getAccount()`, read `acc.marginLevel ?? acc.margin_level` (and compute `(equity / margin) * 100` if `margin > 0` and `marginLevel` was 0). When `openPositionsCount === 0` and `margin === 0`, display `"n/a"` cleanly.
- **Risk:** Low.

---

### E9 — Trades filter chips show two chips selected at once ("Losses" and "ALL") and sort label is clipped ("Sort: Old...")

- **Symptom:** On the Trades screen, two filter chips appear selected simultaneously (`"Losses"` and `"ALL"`), and the sort chip label is clipped (`"Sort: Old..."`). Also filter state is local `useState` inside `TradesScreen` and does not survive tab switches or rotation cleanly.
- **Exact Request/Response Path & Proof (`file:line`):**
  Look at `apps/mobile/src/screens/TradesScreen.tsx:215-327`:
  - All 4 distinct controls — **Symbol filter** (`["ALL", ...symbols]`), **Outcome filter** (`["ALL", "WIN", "LOSS"]`), **Date Range filter** (`["ALL", "1D", "1W", "1M"]`), and **Sort button** (`"Sort: Oldest"`) — are placed inside **one single undifferentiated `<ScrollView horizontal contentContainerStyle={styles.chipRow}>`** with no group separators or labels!
  - Even worse:
    - Symbol filter has a chip labeled **`"ALL"`** (line 220).
    - Outcome filter has `"All Results"`, `"Wins"`, `"Losses"` (line 272) — styled with `tokens.accentLight` / `tokens.accent`.
    - Date Range filter has a chip labeled **`"ALL"`** (line 278) — styled with the **exact same `tokens.accentLight` / `tokens.accent` border and background** as the Outcome filter right next to it (`["All Results", "Wins", "Losses", "ALL", "1D", "1W", "1M"]`)!
    - So when Outcome = `"Losses"` and Date Range = `"ALL"` (the default), the chip row displays:
      `[All Results] [Wins] [Losses (SELECTED)] [ALL (SELECTED)] [1D] [1W] [1M]` — making `"Losses"` and `"ALL"` look like two selected options in the same filter group!
    - Furthermore, the Sort chip at the end of the row (lines 308-326) is clipped by the horizontal scroll / container edge (`"Sort: Old..."`).
- **Classification:** `UI_STATE_BUG`
- **Proposed Fix:**
  1. Separate the filter controls into clearly labeled, distinct single-select segmented rows/groups (Row 1: Search + Sort pill with full unclipped label; Row 2: Symbol group `All Symbols | XAUUSD | USDJPY | BTCUSD` and Outcome group `All | Wins | Losses`; Row 3: Period group `All Time | 24H | 7D | 30D`), enforcing mutual exclusion (` exactly one active option per group`).
  2. Persist filter state across screen rotation / re-renders (via hoisted/persisted state in `OfflineCache` or `App.tsx`).
- **Risk:** Low.

---

### E10 — Header banner shows "Live / RUNNING" while most panels are empty or stale

- **Symptom:** Top header shows green dot `Live` + `RUNNING` badge, and `ConnectionBanner` is hidden (`if (state === "LIVE" && !isShowingCache) return null;`), even when `updatedAt` in the cloud snapshot is hours old or panels failed to load.
- **Exact Request/Response Path & Proof (`file:line`):**
  1. Look at `apps/mobile/src/App.tsx:164,211,302`:
     Whenever `pollCloudLoop` (`MobileSyncClient.ts:721-740`) fetches `/functions/v1/mobile-sync` over HTTP 200, `App.tsx:302` executes:
     ```ts
     setLastSyncedMs(Date.now());
     setIsShowingCache(false);
     setStreamConnected(true);
     setStreamError(false);
     ```
     Notice the bug: `setLastSyncedMs(Date.now())` sets `lastSyncedMs` to **the phone's current wall-clock time when the HTTP GET returned**, **NOT** `Date.parse(snap.updatedAt)` (when the Windows Companion actually published data to Supabase)!
  2. Therefore, even if the Windows Companion app was closed 3 days ago, Supabase `companion_telemetry_snapshots` still returns the 3-day-old row with HTTP 200 every 5 seconds, and Android sets `lastSyncedMs = Date.now()` and `streamConnected = true`!
  3. Then `deriveConnectionState()` (`apps/mobile/src/App.tsx:390-404`) checks `isSnapshotStale(lastSyncedMs, Date.now(), 35_000)` — which compares `Date.now()` against `Date.now()` (always `0ms < 35000ms`), and returns **`"LIVE"`**!
  4. And `ConnectionBanner.tsx:34-36` hides the banner completely when `state === "LIVE" && !isShowingCache`!
- **Classification:** `CLIENT_BUG` + `UI_STATE_BUG`
- **Proposed Fix:**
  1. Track **two distinct timestamps**:
     - `lastPollAtMs`: when the Android client last reached the Cloud/LAN server.
     - `producerUpdatedAtMs`: `Date.parse(snap.updatedAt || status.lastHeartbeat)` — when the Windows Companion producer actually generated the telemetry snapshot.
  2. Derive connection state honestly from **producer data freshness**:
     - If `producerUpdatedAtMs` is null or `Date.now() - producerUpdatedAtMs > STALE_THRESHOLD_MS (45_000)`, connection state MUST be `"STALE"` (`"Data delayed · Companion last updated <time>"`), never `"LIVE"`.
     - If any core stream has a fetch/parse error, show a visible warning/retry state.
     - Show per-panel freshness / state (`loading`, `empty (valid)`, `stale`, `error`) and a complete **Sync Diagnostics** card on the `Security` screen.
- **Risk:** Low.

---

## 4. Additional Audited Areas (Per Phase 1 Requirements)

| Area | Current State & Proof | Audit Finding / Required Action |
|---|---|---|
| **Auth / Pairing Token Lifecycle & Refresh** | `mobile_paired_devices` (`20261126000003_mobile_cloud_pairing_sync.sql:41`) sets `token_expires_at = now() + INTERVAL '90 days'`. `mobile-sync/index.ts:53-55` checks expiry and returns `401 TOKEN_EXPIRED`. However, `MobileSyncClient.unpair()` (`MobileSyncClient.ts:683-687`) does **not** revoke the token server-side in Cloud mode! | Add server-side `action: "unpair_self"` in `mobile-pairing/index.ts` (or `mobile-sync`) authenticated by the device's `iea_ro_*` token so "Unpair Device" on Android immediately sets `status = 'revoked'` in `mobile_paired_devices`. Also add sliding expiry refresh on active valid heartbeats or explicit expiry diagnostics. |
| **Clock / Timezone Handling (UTC vs Broker Time)** | `MT5SyncService` detects `broker_utc_offset_sec` (`sync_service.py:511,623`) and converts candle & tick timestamps to UTC epoch seconds. `build_stats_payload` (`sync_server.py:505`) uses UTC date `datetime.now(timezone.utc).strftime("%Y-%m-%d")`. | Formalize UTC ISO-8601 (`YYYY-MM-DDTHH:mm:ss.sssZ`) and UTC epoch seconds across all v1.1.0 payloads, with `"today"` explicitly defined as `00:00:00 UTC` to `23:59:59.999 UTC` (and `brokerUtcOffsetHours` included in `meta`). |
| **Pagination & Filtering** | LAN `build_trades_payload` (`sync_server.py:581-700`) supports `page`, `limit`, `symbol`, `outcome`, `from`, `to`, `sort`, `q`. Cloud `MobileSyncClient.getTrades()` (`MobileSyncClient.ts:598-627`) ignores all query params and fails Zod validation. | Publish up to 200 closed trades to cloud snapshot and execute identical filter/sort/search/pagination logic in `MobileSyncClient.getTrades()` (and server-side when query params are passed to `mobile-sync`). |
| **Payload Sizes** | Currently `companion_telemetry_snapshots` stores only ~5 KB because candles, drawings, and equity are missing. Adding 5 timeframes × 3 symbols × 160 candles + drawings naively could be ~250–400 KB per push. | Cap cloud-published candles to 120 bars for active/intraday timeframes (`M1`, `M5`, `M15`, `H1`, `H4`) across the 3 symbols (`XAUUSD`, `USDJPY`, `BTCUSD`) with compact numeric rounding, cap drawings per layer, and cap equity snapshots to 250 downsampled points so full snapshot stays under ~120 KB. |
| **SSE / Cloud Polling Reconnect Behaviour** | `MobileSyncClient.pollCloudLoop` (`MobileSyncClient.ts:721-759`) uses `computeBackoffMs` (exponential backoff + 15% jitter) on error, and 5s interval on success, but does not pass `sinceSeq` or handle network switch triggers. | Track `lastCloudSequence`, last event time per stream, consecutive failure count, and last error code in client diagnostics; expose `getDiagnostics()` for the Security screen. |
| **Raw Validation Error Surfacing** | `TradesScreen.tsx:98,371` puts `err.message` directly into `<Text>`, displaying raw `ZodError` JSON arrays to the user. | Add `formatSyncErrorMessage(err)` in `MobileSyncClient.ts` that maps `ZodError`, `MobileSyncError`, HTTP status codes, and network timeouts to concise human messages while logging technical details (redacted). |
| **Mock / Fixture / Seed Data Reachability** | Checked `apps/mobile/src` and `companion/src`: no mock market data is injected in production paths, **except** `MobileSyncClient.getEquity()` (`MobileSyncClient.ts:649`) which synthesizes a 1-point array from current balance/equity, and `companion_control.db` having 184 unclosed `status='OPEN'` rows in `trade_records`. | Remove the 1-point fake fallback when real snapshots exist, and reconcile `trade_records` with real MT5 closed deal history. |

---

## 5. Summary Matrix of Root Causes (E1–E10)

| ID | Screen | Classification | Failing File : Line | Root Cause Summary |
|---|---|---|---|---|
| **E1** | Trades | `SHAPE_MISMATCH` + `CLIENT_BUG` | `apps/mobile/src/services/MobileSyncClient.ts:619-626`, `TradesScreen.tsx:98,371` | `getTrades()` in Cloud mode passes `{ trades: mapped }` instead of `{ summary, items }` to `MobileTradesPageSchema.parse()`, throwing a `ZodError` rendered raw in `TradesScreen`. |
| **E2** | Charts | `NOT_PUBLISHED` + `SHAPE_MISMATCH` + `CLIENT_BUG` | `companion/src/App.tsx:547-571`, `MobileSyncClient.ts:532-595`, `ChartsScreen.tsx:48-58,94-103` | Windows `App.tsx` never pushes `symbols`, `candles`, or `drawings` to cloud. `MobileSyncClient.getCandles()` & `getDrawings()` are hardcoded empty stubs in Cloud mode. `ChartsScreen.tsx` looks up `drawings.counts["LIQ"]` instead of `drawings.counts["liquidity"]`. |
| **E3** | Overview > Live Chart | `NOT_PUBLISHED` + `SHAPE_MISMATCH` | `companion/src/App.tsx:547-571`, `MobileSyncClient.ts:549-559` | Same as E2: `symbols` and `candles` are not published to cloud and `getCandles()` throws a `ZodError` / returns `[]` in Cloud mode. |
| **E4** | Overview > Equity Curve | `NOT_PUBLISHED` + `CLIENT_BUG` | `companion/src/App.tsx:547-571`, `MobileSyncClient.ts:641-651`, `EquityCurveCard.tsx:32,103` | Windows `App.tsx` loads `balanceSnapshots` (12,117 rows in SQLite) but never pushes them to cloud. `MobileSyncClient.getEquity()` returns only 1 point, while `EquityCurveCard` requires `points.length >= 2`. |
| **E5** | Overview > Today Trades | `NOT_PUBLISHED` + `CALCULATION_DIFFERENCE` | `companion/src/App.tsx:547-571`, `MobileSyncClient.ts:492`, `CoreTradingScreens.tsx:316` | Windows `App.tsx` never pushes `stats`. Android defaults `tradesToday` to `0`, whereas Desktop computes `closedToday.length + activePositions.length` (`0 + 6 = 6`). |
| **E6** | Overview > Total Deals & Win Rate | `CALCULATION_DIFFERENCE` + `STALE_OR_SEEDED_DATA` | `companion/service/mt5/sync_service.py:747-763`, `companion/src/App.tsx:569`, `MobileSyncClient.ts:483-495` | `MT5SyncService` inserts open positions into `trade_records` with `status='OPEN'` (184 rows in live DB) and never syncs closed MT5 deals. Windows pushes `.slice(0, 50)` of those `OPEN` rows (which have 25 positive and 25 negative floating P/Ls). Desktop filters for `status === 'CLOSED'` (`0 deals`), while Android's fallback in `getStats()` counts all 50 `OPEN` rows (`50 deals, 25W/25L = 50.0%`). |
| **E7** | Overview > Active Positions SL/TP | `SAFETY_FINDING` + `SHAPE_MISMATCH` | Live MT5 Terminal (`6 XAUUSD.m positions`), `MobileSyncClient.ts:514-515`, `PositionsList.tsx:114,160` | **Safety Finding:** All 6 open `XAUUSD.m` positions in MT5 (`#2738475820`..`#2738476138`, `magic=0`) genuinely have `sl=0.0, tp=0.0`. Secondary bug: `MobileSyncClient` maps `sl: 0` instead of `null`, causing the detail modal to display `0.00` instead of a warning badge. |
| **E8** | Overview > Margin Level | `NOT_PUBLISHED` | `companion/src/App.tsx:559-567`, `KpiCards.tsx:224` | Windows `App.tsx` omits `margin`, `freeMargin`, `marginLevel`, and `leverage` when pushing `account` to cloud, so `marginLevel` is `0` on Android and renders `"—"`. |
| **E9** | Trades > Filter Chips & Sort | `UI_STATE_BUG` | `apps/mobile/src/screens/TradesScreen.tsx:215-327` | Symbol (`ALL`), Outcome (`Losses`), Date Range (`ALL`), and Sort (`Sort: Oldest`) are all in a single unseparated horizontal row with identical active styling, making `"Losses"` and `"ALL"` (date range) look dual-selected and clipping `"Sort: Old..."`. |
| **E10** | Header > Live / RUNNING Banner | `CLIENT_BUG` + `UI_STATE_BUG` | `apps/mobile/src/App.tsx:302,390-404`, `ConnectionBanner.tsx:34-36` | Android sets `lastSyncedMs = Date.now()` on every HTTP 200 poll instead of checking `snap.updatedAt`, so stale/empty cloud snapshots always appear `"LIVE"`. |


---

## 6. Phase 2: Sync Contract v1.1.0 Specification (Contract-First Design)

### 6.1 Version Negotiation & Compatibility (`v1.0.0` ↔ `v1.1.0`)

- **Current Schema Version:** `1.1.0` (`MOBILE_SYNC_SCHEMA_VERSION = "1.1.0"`).
- **Supported Versions:** `["1.0.0", "1.1.0"]`.
- **Handshake / `/meta` Envelope:**
  Every Cloud and LAN sync response includes `meta`:
  ```json
  {
    "schemaVersion": "1.1.0",
    "minClientSchemaVersion": "1.0.0",
    "supportedVersions": ["1.0.0", "1.1.0"],
    "producerVersion": "1.3.7",
    "generatedAt": "2026-11-27T00:00:00.000Z",
    "sequenceNo": 42,
    "timezoneRule": "UTC_00_00",
    "brokerUtcOffsetHours": 0
  }
  ```
- **Backward Compatibility Rules:**
  - `v1.0.0` Android clients ignore unknown top-level keys (`meta`, `candlesByKey`, `drawingsByKey`, `equityPoints`) and continue reading `status`, `account`, `stats`, `positions`, `trades`, `signals`, `symbols`.
  - `v1.1.0` Android clients degrade gracefully when connected to a `v1.0.0` producer (defaulting missing `meta.schemaVersion` to `"1.0.0"` and showing honest empty states instead of raw validation errors).
  - If `checkSyncSchemaCompatibility()` detects a major version mismatch (e.g., `2.x` vs `1.x`), the UI displays a clear `"Update Needed"` banner instead of throwing raw Zod errors.

### 6.2 Units & Conventions

1. **Timestamps:**
   - Envelope / metadata / trade lifecycle timestamps (`updatedAt`, `generatedAt`, `openedAt`, `closedAt`, `lastHeartbeat`, `serverTime`): **UTC ISO-8601** (`YYYY-MM-DDTHH:mm:ss.sssZ`).
   - Chart candle bars (`Candle.time`), drawing coordinates (`start_time`, `end_time`), position `openTime`, and equity curve points (`EquityPoint.time`): **UTC Unix epoch seconds** (integer).
2. **Symbol Naming & Precision:**
   - Every symbol record carries **both** canonical symbol (`XAUUSD`, `USDJPY`, `BTCUSD`) and broker symbol (`XAUUSD.m`, `USDJPY.m`, `BTCUSD.m`), plus `digits` (`XAUUSD`: 2, `USDJPY`: 3, `BTCUSD`: 2) and `point` (`0.01`, `0.001`, `0.01`).
3. **"Today" Definition (Explicit Timezone Rule):**
   - `"Today"` is defined strictly as the current **UTC calendar day** (`00:00:00.000Z` through `23:59:59.999Z`, `timezoneRule: "UTC_00_00"`).
   - Both Windows Companion (`dashboardDataAdapter.ts` / `CoreTradingScreens.tsx` / `sync_server.py`) and Android (`MobileSyncClient.ts`) use this single UTC-day boundary.

### 6.3 Single Definitions for Financial & Trade Aggregates

Computed **once** on the Producer (`MT5SyncService` + `MobileSyncManager` / `dashboardDataAdapter.ts`) and shipped in `stats` and `trades.summary`:

| Metric | Single Authoritative Definition |
|---|---|
| **Deal (`CLOSED` Trade Record)** | A completed MT5 closing execution (`DEAL_ENTRY_OUT` or `DEAL_ENTRY_INOUT`, or a reconciled `trade_records` row with `status === "CLOSED"` and non-null `closed_at`), with net realized P/L = `profit + commission + swap`. Open positions (`status === "OPEN"`) are **never** counted as closed deals. |
| **Position (`OPEN` Position)** | A currently open MT5 position from `mt5.positions_get()`, carrying `ticket`, `symbol`, `canonicalSymbol`, `type` (`BUY`/`SELL`), `volume`, `openPrice`, `currentPrice`, `sl` (`null` when unset/`<= 0`), `tp` (`null` when unset/`<= 0`), `protected` (`sl !== null && sl > 0`), `profit` (floating P/L), `swap`, `openTime`, `ownership` (`BOT_OWN` / `MANUAL` / `OTHER_EA`). |
| **`dealsCount` (Total Closed Deals)** | `closedDeals.length` (count of closed deals only). |
| **`winsCount` / `lossesCount`** | `winsCount = closedDeals.filter(d => d.pnl > 0).length`; `lossesCount = closedDeals.filter(d => d.pnl < 0).length`. |
| **`winRate` (%)** | `winsCount + lossesCount > 0 ? round((winsCount / (winsCount + lossesCount)) * 100, 1) : 0.0`. |
| **`todayRealizedPnl`** | Sum of `pnl` for all closed deals where `closedAt` falls within today's UTC date (`YYYY-MM-DD`). |
| **`todayPnl` (Today P/L)** | `round(todayRealizedPnl + floatingPnl, 2)` — matches Windows Companion Dashboard KPI `"Today P/L"` (`closedPnlToday + floatingPnl` in `dashboardDataAdapter.ts:424-425`). |
| **`tradesToday`** | `todayClosedCount + openPositionsCount` — matches Windows Companion Dashboard KPI `"<N> trades today"` (`closedToday.length + activePositions.length` in `CoreTradingScreens.tsx:316`). Both `todayClosedCount` and `openPositionsCount` are also shipped in `stats` for the detail sheet breakdown. |
| **`totalProfit` (Total Profits)** | When `dealsCount > 0`: `round(sum(d.pnl for d in closedDeals), 2)`. When `dealsCount === 0`: `todayPnl` (matches `CoreTradingScreens.tsx:327-332`). |
| **`marginLevel` (%)** | `account.margin_level` from MT5 (`(equity / margin) * 100` when `margin > 0`, or `0` when no margin is used). Rendered as `"XX%"` when `marginLevel > 0`, and `"n/a"` when `margin === 0`. |


---

## 7. Phase 4: Cloud Mode Security Review

### 7.1 Row-Level Security (RLS) & Database Constraints
- **Tables Verified:**
  - `public.mobile_pairing_sessions` (`supabase/migrations/20261126000003_mobile_cloud_pairing_sync.sql:5-24,67,71-76`): RLS enabled; `USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id)`.
  - `public.mobile_paired_devices` (`20261126000003_mobile_cloud_pairing_sync.sql:29-45,68,78-83`): RLS enabled; DB constraint `scope TEXT NOT NULL DEFAULT 'read_only' CHECK (scope = 'read_only')` makes it impossible to insert a device row with write privileges.
  - `public.companion_telemetry_snapshots` (`20261126000003_mobile_cloud_pairing_sync.sql:49-64,69,85-89` + `20261127000005_mobile_sync_v1_1_telemetry_columns.sql`): RLS enabled; `FOR SELECT USING (auth.uid() = user_id)`. No direct table write policy exists for anon or mobile roles.
- **Cross-Device & Cross-Tenant Isolation:**
  - In `supabase/functions/mobile-sync/index.ts:42-68`, a mobile token (`iea_ro_*`) is hashed with SHA-256 (`tokenHash = await sha256Hex(bearer)`), matched against `mobile_paired_devices` where `status === "active"` and `scope === "read_only"`, and then queries `companion_telemetry_snapshots` filtered strictly by **both** `.eq("user_id", device.user_id)` and `.eq("companion_device_id", device.companion_device_id)`. A paired Android device can never read another user's or another companion's data.
- **Strict Read-Only Enforcement (Client + Server):**
  - **Client:** `assertMobileHttpReadOnly(method, path)` (`packages/data-contract/src/mobileSync.ts`) is invoked before every HTTP request in `MobileSyncClient.ts` and rejects any non-GET request (except `/api/mobile/v1/pair`, `/api/mobile/v1/unpair`, `/functions/v1/mobile-pairing`) with `READ_ONLY_ENFORCED`. `ReadOnlyGuard.ts` blocks all `FORBIDDEN_CLIENT_ACTIONS`.
  - **Server (Cloud):** `supabase/functions/mobile-sync/index.ts:31-40` unconditionally rejects any `req.method !== "GET"` carrying an `iea_ro_*` token with HTTP `403 READ_ONLY_VIOLATION`.
  - **Server (LAN):** `companion/service/mobile/sync_server.py:930-980` unconditionally rejects `PUT`, `PATCH`, `DELETE`, and any `POST` other than `/api/mobile/v1/pair` and `/api/mobile/v1/unpair` with HTTP `403 READ_ONLY_ENFORCED`.
- **Service-Role Key Isolation:**
  - `SUPABASE_SERVICE_ROLE_KEY` is read exclusively inside the Deno Edge runtime (`supabase/functions/_shared/auth.ts:21`) via `Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")`.
  - Build-time generators (`scripts/generate_companion_public_config.mjs`) explicitly block `service_role` and `sb_secret_` keys from entering Windows Companion or Android bundles.

### 7.2 Token Storage, Rotation, Expiry & Server-Side Revocation
- **Storage:** Android stores `deviceToken` exclusively in hardware-backed Android Keystore (`expo-secure-store`) via `SecureStorage.ts:117-121`, never in `AsyncStorage` (`OfflineCache.ts`) or logs.
- **One-Time Pairing & Hashing:** Plaintext `iea_ro_*` tokens are never persisted in `mobile_paired_devices` (only `token_hash` SHA-256 is stored). During pairing handoff, `issued_token_once` is wiped (`issued_token_once: null, consumed_at: nowIso`) on the single `poll` call that retrieves it (`mobile-pairing/index.ts:165-171`).
- **Server-Side Unpair Revocation:** Added `action === "unpair_self"` to `supabase/functions/mobile-pairing/index.ts:186-211` and wired `MobileSyncClient.unpair()` (`apps/mobile/src/services/MobileSyncClient.ts:814-837`) so tapping **Unpair Device** on Android immediately marks the device row `status = 'revoked'` in Supabase in addition to wiping local Keystore credentials.

### 7.3 Payload Minimisation & Secret Scanning
- **Minimisation Verified:**
  - Account number is always masked (`_mask_account_number` / `****0203` style) before leaving the producer (`sync_server.py:54-60,468,494`, `companion/src/App.tsx:582`).
  - Zero MT5 passwords, broker login credentials, `.env` values, Telegram bot tokens, or desktop session tokens are included in `build_cloud_bundle()` or any `/api/mobile/v1/*` payload.
- **Automated Payload Secret Scanner Test:** Added in Phase 5 (`tests/test_mobile_sync_server.py` and `apps/mobile/src/__tests__/mobileDataLayer.test.ts`) to scan the entire serialized `build_cloud_bundle()` JSON for forbidden keys (`password`, `secret`, `service_role`, `telegram_bot_token`, raw unmasked account numbers).

### 7.4 Transport Security
- `claimCloudPairing()` (`MobileSyncClient.ts:194-196`) enforces `https://` for all non-loopback cloud URLs (`INSECURE_URL` thrown otherwise).
- No certificate validation bypass (`rejectUnauthorized: false` or trust-all) exists anywhere in the Android or Windows codebase.
