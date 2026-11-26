# Android Companion `v1.3.7` & Sync Contract `v1.1.0` — On-Device Acceptance Checklist

This checklist validates the end-to-end remediation of symptoms **E1–E10** across the Windows Desktop Companion (`v1.3.7`) and Android Read-Only Companion (`v1.3.7`, Sync Schema `v1.1.0`).

---

## 1. Functional & Cross-Device Parity Acceptance Matrix

| Area | Check | Pass Criteria | Tested (✓/✗) |
|---|---|---|---|
| **Overview** | Balance / Equity / Free Margin / Margin Level | Matches desktop within 1 sync cycle (`≤ 5 s`); Margin Level shows `X.XX%` when positions are open or `n/a` when 0 positions are open (never `"—"` when MT5 reports a positive margin level). | [x] |
| **Overview** | Today P/L + `"N trades today"` | Matches desktop (`todayRealizedPnl + floatingPnl`, `tradesToday = todayClosedCount + openPositionsCount`) using UTC day boundary (`00:00:00Z`). | [x] |
| **Overview** | Total Deals + Win Rate | Matches desktop closed-deal history strictly (`status = 'CLOSED'` only); open positions in `trade_records` are never counted as closed deals. | [x] |
| **Overview** | Active Positions (`SL` / `TP`) | Displays real MT5 `sl` / `tp` prices when set (`> 0`), or renders high-visibility `"NO SL"` / `"NO TP"` warning badges when `sl` or `tp` is `0`/`null` in MT5. | [x] |
| **Overview** | Live Chart preview | Renders current primary symbol (`XAUUSD.m` M5) candles from the cloud bundle (`candlesByKey["XAUUSD.m:M5"]`). | [x] |
| **Overview** | Equity Curve | Renders latest equity points (`equityPoints`) across `1D / 1W / 1M / ALL`, or explicit empty state when `< 2` points exist. | [x] |
| **Charts** | Symbol selector (`XAUUSD.m`, `USDJPY.m`, `BTCUSD.m`) | Populated from companion `symbols` list; switching symbol updates candles and overlays immediately. | [x] |
| **Charts** | Timeframe selector (`M1`, `M5`, `M15`, `H1`, `H4`) | Loads real candles for each timeframe from `candlesByKey["<symbol>:<tf>"]` (or LAN `/api/mobile/v1/candles`). | [x] |
| **Charts** | Overlay chips (`Liq`, `FVG/OB`, `Struct`, `Sess`, `Trades`) | Counts match desktop drawings engine output (`normalizeDrawingsCounts`); toggling hides/shows each layer cleanly. | [x] |
| **Charts** | Trade markers on chart | Active positions (`ENTRY`, `SL`, `TP`) appear at exact price levels on the corresponding symbol chart. | [x] |
| **Trades** | Loads without error | Zero raw Zod JSON errors; `MobileTradesPageSchema` (`{ summary, items, nextCursor }`) validates cleanly. | [x] |
| **Trades** | Filters (`Symbol`, `Result`, `Period`) + `Sort` + `Search` | Each filter group (`Symbol`, `Result`, `Period`) has its own labeled row with exactly **one** active chip per group; `Sort:` label is never clipped; filter state persists across screen rotation and navigation. | [x] |
| **Trades** | Summary row (`Trades`, `Win Rate`, `Net P/L`, `PF`) | Matches filtered closed items (`status = 'CLOSED'`) and aligns with Overview KPIs when unfiltered (`ALL`). | [x] |
| **Trades** | Empty state (`0 closed deals`) | Shows clean `"No closed trades match the current filters"` message with `0` summary values — never a red validation banner. | [x] |
| **Security** | Read-only enforced | Zero order-entry, close, modify, or engine-control endpoints exist; `ReadOnlyGuard` blocks non-`GET` methods on mobile and `mobile-sync` returns `HTTP 403 READ_ONLY_VIOLATION` for any non-read action. | [x] |
| **Security** | Sync Diagnostics card | Shows `App Version: 1.3.7`, `Schema Version: 1.1.0`, `Last Sync Age`, `Sequence #`, `Device ID (masked)`, `Account (masked)`, and payload item counts (`Positions`, `Trades`, `Symbols`, `Candle Keys`, `Equity Pts`). | [x] |
| **Security** | Unpair device | Calls `mobile-pairing` with `action: "unpair_self"` (`Authorization: Bearer iea_ro_*`), revokes token server-side (`status = 'revoked'`), clears `SecureStore` and `OfflineCache`, and returns to Pairing screen. | [x] |
| **Failure drill** | Airplane mode (`> 30 s`) | Top banner transitions to amber `Data Delayed · Last update Xs ago` / `Reconnecting`; cached snapshot remains readable without raw stack traces. | [x] |
| **Failure drill** | Desktop Companion closed | Banner transitions from `Live` to `Data Delayed` once producer snapshot age (`snap.updatedAt` / `status.lastHeartbeat`) exceeds `60 s`, even while Supabase HTTP polls return `200 OK`. | [x] |
| **Failure drill** | Token revoked / expired | `HTTP 401/403` clears session and transitions cleanly to Pairing screen with friendly notice. | [x] |

---

## 2. Automated Verification Commands

Run all commands from the repository root to verify contract, desktop, mobile, and Python producer parity:

```powershell
# 1. Full Monorepo JS/TS Test Suite (Companion, Data-Contract, Chart-Core, Cloud-Contract, Mobile)
npm run test:all

# 2. TypeScript Typechecks & Zero-Hardcoded-Data Linter
npm --workspace=companion exec -- tsc --noEmit
npm --workspace=@institutional-ea/mobile run typecheck
npm --workspace=@institutional-ea/mobile run lint:no-hardcoded

# 3. Python Producer, Market Feed, Drawings Engine & Mobile Sync Server Tests
.\.venv\Scripts\python.exe -m pytest tests/test_mobile_sync_server.py tests/test_chart_drawings_engine.py tests/test_luxalgo_smc.py tests/test_market_feed.py tests/test_no_hardcoded_market_data.py -q

# 4. Cross-Platform Brand & Version Consistency Validator
.\.venv\Scripts\python.exe scripts/verify-brand-assets.py
```
