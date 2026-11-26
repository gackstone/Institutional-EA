# Institutional EA — Mobile Android App Audit & Upgrade Plan

> **Authoritative Mobile Project:** `apps/mobile` (`@institutional-ea/mobile`, v1.3.4)  
> Verified via `git log`, root `package.json` workspaces, and `.github/workflows/release.yml` (which builds `apps/mobile` into `InstitutionalEA.apk` and `InstitutionalEA.aab`). No other standalone mobile folder exists in this workspace.

---

## 1. Current Mobile Architecture Map (`apps/mobile`)

| Aspect | Current Implementation |
| --- | --- |
| **Framework** | Expo SDK `~51.0.0` + React Native `0.74.5` + React `18.2.0` + TypeScript `~5.3.3` |
| **Entry Point** | `apps/mobile/index.js` -> `apps/mobile/src/App.tsx` |
| **Navigation** | Custom tab state (`MobileTab` in `src/navigation/RootNavigator.tsx`) switching between `DASHBOARD` (Overview), `CHARTS`, `POSITIONS` (Trades), `SETTINGS` (Security). No safe-area insets library, no landscape fullscreen support (`orientation: "portrait"` in `app.json`). |
| **State Management** | Plain `useState` inside `App.tsx` with hardcoded initial values. No normalized store, no persistence/offline cache, no selectors. |
| **Chart Rendering** | `react-native-webview` (`^13.8.7`) in `src/components/ChartWebView.tsx` with an inline HTML template that is an **empty stub**. |
| **Networking** | **None.** No HTTP client, no SSE/WebSocket client, no pairing flow, no reconnect/backoff, no schema validation at runtime. |
| **Secure Storage** | `src/services/SecureStorage.ts` defaults to `MemorySecureStorage` (in-memory `Map`), never wired to Android Keystore / `expo-secure-store`. |
| **Read-Only Guard** | `src/services/ReadOnlyGuard.ts` defines `FORBIDDEN_CLIENT_ACTIONS` and `assertMobileReadOnlyAction`, not yet paired with server-side enforcement. |
| **Build Config** | `apps/mobile/app.json` + `expo-build-properties` (`minSdkVersion: 24`, `compileSdkVersion: 34`, `targetSdkVersion: 34`), `metro.config.cjs` (monorepo workspace resolution), `babel.config.cjs`, `eas.json`. Hermes is enabled by default in RN 0.74. |
| **APK Build Method** | `npx expo prebuild --platform android --non-interactive` followed by Gradle `./gradlew assembleRelease` in `apps/mobile/android` (documented in `.github/workflows/release.yml`). |

---

## 2. Root Cause: Why the Live Chart Renders EMPTY

1. **Unimplemented WebView Stub (`apps/mobile/src/components/ChartWebView.tsx`, lines 41–72):**
   - The embedded HTML loads **no charting library** (`lightweight-charts` is neither bundled nor imported).
   - Inside `<script>`, the message handler is an empty placeholder comment:
     ```js
     if (msg.action === 'UPDATE_DATA') {
       // Renders candles and FVG/OB/IFVG centered labels via shared chart-core
     }
     ```
   - Nothing ever draws to `#chart-container` or `#overlay-canvas`.
2. **Missing Candle Data (`apps/mobile/src/App.tsx`, lines 93–101):**
   - `App.tsx` never passes `candles` to `RootNavigator`, so `candles` defaults to `[]`.
3. **Android WebView Bridge & Lifecycle Gaps:**
   - React Native `WebView.postMessage()` fires on `document` in Android WebView (and `window` on iOS); listening only on `window` drops messages on Android.
   - `useEffect` posts data immediately on mount before the WebView finishes loading, losing the initial payload.

### Fix
- Bundle `lightweight-charts` v5.3.0 (`lightweight-charts.standalone.production.js`, ~198 KB) and the shared `@institutional-ea/chart-core` canvas renderer (`chartCanvasRenderer.ts`, `chartDrawingsSchema.ts`, `chartTheme.ts`, `luxalgoSmcEngine.ts`, `smcChartSettings.ts`) into a self-contained offline JS bundle generated at build time (zero CDN requests at runtime).
- Implement a two-way ready handshake (`CHART_READY` -> initial snapshot, then incremental `TICK_UPDATE` / `DRAWINGS_UPDATE` / `LAYERS_UPDATE` / `THEME_UPDATE` messages) listening on both `document` and `window`, with `requestAnimationFrame`-throttled canvas redraws for 60fps on Android 7–10 (API 24+).

---

## 3. Hardcoded / Sample / Mock Data Inventory

Every hardcoded value found in `apps/mobile/src/` (excluding unit tests):

| File | Line(s) | Hardcoded / Fake Value | Action |
| --- | --- | --- | --- |
| `apps/mobile/src/App.tsx` | 14 | `useState<ConnectionState>("CONNECTED")` | Replace with real connection state machine (`NOT_PAIRED` when unpaired). |
| `apps/mobile/src/App.tsx` | 18 | `balance: 10450.25` | Remove; populate exclusively from `/api/mobile/v1/account` or labeled cache. |
| `apps/mobile/src/App.tsx` | 19 | `equity: 10582.4` | Remove. |
| `apps/mobile/src/App.tsx` | 20 | `todayPnl: 132.15` | Remove; populate from `/api/mobile/v1/stats`. |
| `apps/mobile/src/App.tsx` | 21 | `totalProfit: 2450.8` | Remove. |
| `apps/mobile/src/App.tsx` | 22 | `winRate: 72.4` | Remove. |
| `apps/mobile/src/App.tsx` | 23 | `todayTradesCount: 4` | Remove. |
| `apps/mobile/src/App.tsx` | 24 | `totalDealsCount: 58` | Remove. |
| `apps/mobile/src/App.tsx` | 28–43 | Hardcoded `positions` array (`ticket: 104921`, `symbol: "XAUUSD"`, `BUY 0.1`, `openPrice: 2652.5`, `currentPrice: 2656.8`, `sl: 2645.0`, `tp: 2670.0`, `profit: 43.0`, `swap: -0.4`, `comment: "Inst-EA Swing FVG"`) | Remove; default to `[]` and populate from `/api/mobile/v1/positions`. |
| `apps/mobile/src/App.tsx` | 45–72 | Hardcoded `zones` array (`zone-fvg-1` 2655.0/2650.0, `zone-ob-1` 2672.0/2668.0) | Remove; default to `null` drawings feed and populate from `/api/mobile/v1/drawings`. |
| `apps/mobile/src/App.tsx` | 100 | `activeSymbol="XAUUSD"` | Replace with symbol list from `/api/mobile/v1/symbols`. |
| `apps/mobile/src/navigation/RootNavigator.tsx` | 33 | `activeSymbol = "XAUUSD"` | Remove hardcoded default symbol. |
| `apps/mobile/src/navigation/RootNavigator.tsx` | 97 | `{activeSymbol} • M5` | Replace with dynamic symbol & timeframe from companion. |
| `apps/mobile/src/navigation/RootNavigator.tsx` | 129, 137 | Hardcoded `"This device is paired..."` and `"Hardware Enclave Active"` even when unpaired/disabled | Replace with real pairing & biometric lock status. |
| `apps/mobile/src/components/ChartWebView.tsx` | 19 | `symbol = "XAUUSD"` | Remove hardcoded default symbol. |
| `apps/mobile/src/components/KpiCards.tsx` | 41, 47 | Hardcoded `$` currency prefix | Format using `account.currency` from companion payload. |
| `apps/mobile/src/components/PositionsList.tsx` | 19, 62 | Hardcoded 2-decimal precision and `$` prefix | Use symbol `digits` and account `currency` from companion payload. |

---

## 4. Windows Companion API, Stream & Desktop Chart Rendering

### Existing Local Control Service (`companion/service/api/server.py`)
- **Bind Address:** Strictly `127.0.0.1:8765` (enforced by `LocalAuthManager.validate_bind_host`).
- **Authentication:** Desktop session token (`Authorization: Bearer <token>`, `X-Companion-Token`, or `?token=` for SSE).
- **Relevant Desktop Endpoints:**
  - `GET /api/status` -> `{ engine, mt5, health }`
  - `GET /api/events` -> SSE stream emitting initial `{ type: "snapshot", payload: { engine, mt5, health } }` followed by real-time `EventBus` events (`mt5_snapshot`, `engine_state`, `log`, `trade_event`, etc.) with 15s keepalives.
  - `GET /api/mt5/snapshot` -> `{ connection_status, account, positions, pending_orders, symbols, last_sync_at, last_candle_times, ... }`
  - `GET /api/trades/history` -> `{ trades: [...] }` (from SQLite `CompanionRepository`)
  - `GET /api/analytics/equity` -> `{ snapshots, trades, source, fetched_at }`
  - `GET /api/market/candles?symbol&tf&count&from&to` -> `{ candles, bid, ask, spread_points, digits, point, source, stale, ... }`
  - `GET /api/chart/drawings?symbol&tf&count` -> `EngineDrawingsFeed` (`schema_version`, `symbol`, `broker_symbol`, `timeframe`, `generated_at`, `source`, `items: EngineDrawingItem[]`, `counts`, `mtf_levels`) produced by `ChartDrawingsService` (`companion/service/market/drawings_engine.py`).

### Desktop Chart Layers (`companion/src/components/LiveTradingChart.tsx` + `packages/chart-core`)
- Uses **TradingView Lightweight Charts v5.3.0** (`CandlestickSeries`) for candles + crosshair + pan/zoom.
- Overlays a synchronized `<canvas>` driven by `@institutional-ea/chart-core`:
  - `validateEngineDrawingsFeed()` validates the companion's `EngineDrawingsFeed`.
  - `projectEngineDrawings()` projects engine drawings onto screen coordinates using Lightweight Charts `timeToCoordinate` / `priceToCoordinate`.
  - `drawProjectedOverlaysToCanvas()` renders:
    - **Liq** (`LIQ`: PDH/PDL/PWH/PWL, EQH/EQL)
    - **FVG/OB** (`FVG`, `IFVG`, `OB`: filled rectangles with centered `FVG`, `OB`, `IFVG` labels)
    - **Struct** (`STRUCT`: BOS, CHoCH, MSS, Strong/Weak High/Low)
    - **Sess** (`SESS`: Asian, London, NY Overlap, New York boxes)
    - **Trades** (`TRADE`: long/short position templates with green TP zone, red SL zone, entry line, ghost initial SL, R-multiple badge)
  - `computeLuxAlgoSmc()` + `drawLuxAlgoSmcOverlaysToCanvas()` + `drawPremiumDiscountZones()` renders Premium/Discount/Equilibrium and LuxAlgo SMC structures when enabled.
- Reusing `@institutional-ea/chart-core` directly inside the mobile WebView guarantees **visual and data parity** with zero drift.

### Existing Cloud Infrastructure (Optional Future Remote-Access Proposal)
- The repo already contains `packages/cloud-contract` and `supabase/` (used for desktop authentication and subscription entitlement).
- **Proposal (not built in this task):** For out-of-LAN remote monitoring (when the phone is on cellular/outside home Wi-Fi), a future optional "Cloud Relay Mode" could publish sanitized read-only telemetry snapshots from the companion to a Supabase Realtime channel / Edge Function authenticated by the same user account and per-device read-only token, reusing the exact `/api/mobile/v1` Zod schemas. In this task, we implement **direct LAN pairing & sync** (opt-in, off by default, revocable, strictly read-only).

---

## 5. Implementation Plan & Risks

### Plan
1. **Shared Sync Contract (`packages/data-contract`):** Add versioned `/api/mobile/v1` Zod schemas (`mobileSync.ts`) for status, account, stats, positions, trades (paginated), candles, drawings (`EngineDrawingsFeed`), symbols, equity curve, SSE events, pairing QR/code payloads, and strict read-only method guards.
2. **Companion Opt-In Mobile Sync Server (`companion/service/mobile/` + minimal wiring in `companion/service/api/server.py` & desktop UI):**
   - Dedicated opt-in LAN HTTP/SSE server (default OFF, binds `0.0.0.0:8766` only when enabled by user).
   - Localhost-only management endpoints on `127.0.0.1:8765` (`/api/mobile-sync/*`) + desktop "Mobile Sync" modal with toggle, QR code, 6-digit code (5-min expiry), paired devices list, and revoke.
   - Strict read-only enforcement: only `GET` data/SSE endpoints + `POST /api/mobile/v1/pair` (rate-limited) and `POST /api/mobile/v1/unpair` (self-revoke). Every other write method/path returns `403 READ_ONLY_ENFORCED`.
   - Separate per-device tokens stored hashed (SHA-256) in SQLite; never accepted by desktop `LocalAuthManager`.
   - Automated pytest tests proving auth required, revocation works, rate-limiting works, and all mutation attempts are rejected.
3. **Mobile Data Layer & Offline Cache (`apps/mobile/src/services/`):**
   - `SecureStorage` backed by `expo-secure-store` (Android Keystore) with memory fallback for tests.
   - `OfflineCache` (labeled "Last synced <time>", never shown as live).
   - `MobileSyncClient` (Zod-validated GET + SSE stream with exponential backoff, heartbeat/stale detection, background pause/resume, request cancellation, strict read-only guard).
   - Hardcoded-data lint guard script (`scripts/check-mobile-no-hardcoded.mjs`).
4. **Offline Bundled Chart Engine (`apps/mobile/scripts/build-chart-bundle.mjs` + `ChartWebView.tsx`):**
   - Bundles `lightweight-charts` v5.3.0 + `@institutional-ea/chart-core` locally into `apps/mobile/src/generated/chartBundle.ts`.
   - Supports symbol tabs, timeframes, layer chips with counts (Liq, FVG/OB, Struct, Sess, Trades), OHLC + Bid/Ask/Spread strip, pinch-zoom, pan, double-tap reset, long-press crosshair, incremental live ticks, lazy history load on pan left, landscape fullscreen, and collapsible zone legend.
5. **Professional Interactive Mobile UI (`apps/mobile/src/`):**
   - Overview (KPI cards with Bal/Eq switch, animated transitions, detail bottom sheet, Equity/PnL curve 1D/1W/1M/All, mini live chart, active positions with detail sheet, recent bot activity feed, pull-to-refresh).
   - Charts (full interactive TradingView + SMC chart matching desktop).
   - Trades (virtualized paginated history, symbol/date/win-loss filters, sort, search, summary strip, detail sheet, "Show on Chart").
   - Security / Devices (QR scanner + manual 6-digit code pairing, companion connection info, unpair, biometric/PIN app lock via `expo-local-authentication`, cache management, version & schema info, read-only enforcement explainer).
6. **Testing, Performance & APK Build:**
   - Unit + component tests, typecheck, hardcoded-data lint guard, companion pytest tests.
   - Release APK build (`InstitutionalEA.apk`, minSdk 24, Hermes, R8 minification & resource shrinking) + SHA-256 verification.

### Key Risks & Mitigations
- **LAN HTTP vs HTTPS on Android 9+ (Cleartext Policy):** Self-signed certs on dynamic LAN IPs fail standard Android WebView/fetch trust without custom cert pinning. Mitigation: Allow cleartext HTTP *exclusively* for RFC1918 private LAN addresses via Android `network_security_config.xml` (never for public internet), combined with per-device bearer tokens, short-lived pairing codes, rate limiting, and opt-in toggle. Document trade-offs clearly in `docs/mobile-sync.md`.
- **Android 7–10 (API 24–29) WebView Performance:** Keep canvas overlays capped (same `LAYER_CAPS` as desktop), throttle updates to `requestAnimationFrame`, use incremental `series.update()`, and pause SSE when app is backgrounded.
- **No Breaking Changes to Desktop/Engine:** All companion changes are strictly additive, opt-in (off by default), and isolated to `companion/service/mobile/` plus minimal hooks in `server.py` and a new `MobileSyncModal` in the desktop UI.
