import test from "node:test";
import assert from "node:assert/strict";
import {
  computeBackoffMs,
  formatSyncErrorMessage,
  isSnapshotStale,
  mapCloudPairingError,
  MobileSyncClient,
  parseAnyPairingQrPayload,
  parsePairingQrPayload,
} from "../services/MobileSyncClient.ts";
import {
  OfflineCache,
  setCustomCacheBackend,
  DEFAULT_LAYER_PREFS,
} from "../services/OfflineCache.ts";
import {
  SecureStorage,
  setCustomSecureStorage,
} from "../services/SecureStorage.ts";
import {
  computeSlTpDistance,
  formatCurrency,
  formatDuration,
  formatPercent,
  formatPrice,
  formatSignedPnl,
} from "../utils/formatters.ts";
import { CHART_WEBVIEW_BUNDLE_JS } from "../generated/chartBundle.ts";

test("computeBackoffMs grows exponentially and respects max cap", () => {
  const b0 = computeBackoffMs(0, 1000, 30000, 0);
  const b1 = computeBackoffMs(1, 1000, 30000, 0);
  const b2 = computeBackoffMs(2, 1000, 30000, 0);
  const b9 = computeBackoffMs(9, 1000, 30000, 0);
  assert.equal(b0, 1000);
  assert.equal(b1, 2000);
  assert.equal(b2, 4000);
  assert.equal(b9, 30000);
});

test("isSnapshotStale detects missing and expired timestamps", () => {
  const now = 1_700_000_000_000;
  assert.equal(isSnapshotStale(null, now, 30000), true);
  assert.equal(isSnapshotStale(now - 5000, now, 30000), false);
  assert.equal(isSnapshotStale(now - 31000, now, 30000), true);
});

test("parsePairingQrPayload validates valid QR JSON and rejects malformed payloads", () => {
  const valid = JSON.stringify({
    v: 1,
    host: "192.168.1.25",
    port: 8766,
    code: "123456",
    expiresAt: 1900000000,
    companionName: "MY-PC",
  });
  const parsed = parsePairingQrPayload(valid);
  assert.equal(parsed.host, "192.168.1.25");
  assert.equal(parsed.port, 8766);
  assert.equal(parsed.code, "123456");

  assert.throws(() => parsePairingQrPayload(""));
  assert.throws(() => parsePairingQrPayload('{"v":1,"host":"1.2.3.4","port":8766,"code":"ABCDEF","expiresAt":9999999999}'));
});

test("OfflineCache persists and clears telemetry snapshot and chart preferences", async () => {
  const map = new Map<string, string>();
  setCustomCacheBackend({
    async getItem(k) {
      return map.get(k) ?? null;
    },
    async setItem(k, v) {
      map.set(k, v);
    },
    async removeItem(k) {
      map.delete(k);
    },
  });

  assert.equal(await OfflineCache.loadSnapshot(), null);
  await OfflineCache.saveSnapshot({
    cachedAt: 1700000000000,
    status: null,
    account: null,
    stats: null,
    positions: [],
    symbols: null,
    candlesByKey: {},
    drawingsByKey: {},
    equity: null,
    activity: [],
  });
  const loaded = await OfflineCache.loadSnapshot();
  assert.equal(loaded?.cachedAt, 1700000000000);

  await OfflineCache.saveChartPreferences({
    selectedSymbol: "USDJPY",
    selectedTimeframe: "H1",
    layers: { ...DEFAULT_LAYER_PREFS, sessions: false },
  });
  const prefs = await OfflineCache.loadChartPreferences();
  assert.equal(prefs.selectedSymbol, "USDJPY");
  assert.equal(prefs.selectedTimeframe, "H1");
  assert.equal(prefs.layers.sessions, false);

  await OfflineCache.clearSnapshot();
  assert.equal(await OfflineCache.loadSnapshot(), null);
});

test("SecureStorage stores and clears pairing credentials and biometric flag", async () => {
  const map = new Map<string, string>();
  setCustomSecureStorage({
    async getItem(k) {
      return map.get(k) ?? null;
    },
    async setItem(k, v) {
      map.set(k, v);
    },
    async removeItem(k) {
      map.delete(k);
    },
  });

  await SecureStorage.setPairingCredentials({
    host: "192.168.1.10",
    hosts: ["192.168.1.10"],
    port: 8766,
    deviceId: "mob_abc123",
    deviceToken: "iea_ro_secret_token_value",
    companionName: "TRADING-PC",
    pairedAt: "2026-11-26T12:00:00Z",
  });
  const creds = await SecureStorage.getPairingCredentials();
  assert.equal(creds?.deviceId, "mob_abc123");
  assert.equal(creds?.host, "192.168.1.10");

  await SecureStorage.setBiometricLockEnabled(true);
  assert.equal(await SecureStorage.getBiometricLockEnabled(), true);

  await SecureStorage.clearPairingCredentials();
  assert.equal(await SecureStorage.getPairingCredentials(), null);
});

test("Formatters handle dynamic currency, signed P/L, precision, duration, and SL/TP distance", () => {
  assert.equal(formatCurrency(1234.5, "USD"), "$1,234.50");
  assert.equal(formatCurrency(1234.5, "EUR"), "€1,234.50");
  assert.equal(formatCurrency(-45.2, "GBP"), "-£45.20");
  assert.equal(formatSignedPnl(82.4, "USD"), "+$82.40");
  assert.equal(formatSignedPnl(-19.5, "EUR"), "-€19.50");
  assert.equal(formatPrice(154.1234, 3), "154.123");
  assert.equal(formatPercent(64.25, 1), "64.3%");
  assert.equal(formatDuration(45), "45s");
  assert.equal(formatDuration(3720), "1h 2m");
  assert.equal(computeSlTpDistance(2710.5, 2705.0, 2), "5.50");
  assert.equal(computeSlTpDistance(2710.5, null, 2), "—");
});

test("Offline TradingView Lightweight Charts + chart-core bundle is generated and non-empty", () => {
  assert.ok(CHART_WEBVIEW_BUNDLE_JS.length > 50_000);
  assert.ok(!CHART_WEBVIEW_BUNDLE_JS.includes("https://unpkg.com"));
  assert.ok(!CHART_WEBVIEW_BUNDLE_JS.includes("https://cdn.jsdelivr.net"));
});

test("parseAnyPairingQrPayload accepts Cloud v2 QR, LAN v1 QR, and rejects garbage", () => {
  const cloudQr = parseAnyPairingQrPayload(
    JSON.stringify({
      v: 2,
      mode: "cloud",
      cloudUrl: "https://itnxilvehaeokxvauujk.supabase.co",
      sessionId: "11111111-2222-3333-4444-555555555555",
      sessionToken: "0123456789abcdef0123456789abcdef",
      code: "654321",
      expiresAt: 1999999999,
      companionName: "DESKTOP-WIN",
    })
  );
  assert.equal(cloudQr.v, 2);
  if (cloudQr.v === 2) {
    assert.equal(cloudQr.mode, "cloud");
    assert.equal(cloudQr.code, "654321");
  }

  const lanQr = parseAnyPairingQrPayload(
    JSON.stringify({
      v: 1,
      host: "192.168.1.42",
      port: 8766,
      code: "123456",
      expiresAt: 1999999999,
    })
  );
  assert.equal(lanQr.v, 1);

  assert.throws(() => parseAnyPairingQrPayload("not-json-at-all"));
  assert.throws(() => parseAnyPairingQrPayload(JSON.stringify({ v: 99, foo: "bar" })));
});

test("mapCloudPairingError maps wrong code, expired, consumed, 429, 404, and offline cleanly", () => {
  assert.match(mapCloudPairingError(404, "INVALID_PAIRING_CODE", ""), /not recognized/i);
  assert.match(mapCloudPairingError(410, "PAIRING_EXPIRED", ""), /expired/i);
  assert.match(mapCloudPairingError(409, "PAIRING_CONSUMED", ""), /already used/i);
  assert.match(mapCloudPairingError(429, "RATE_LIMITED", ""), /Too many attempts/i);
  assert.match(mapCloudPairingError(404, "NOT_FOUND", "Requested function was not found"), /Local Wi-Fi/i);
  assert.match(mapCloudPairingError(0, "NETWORK_ERROR", "Failed to fetch"), /No internet/i);
});

test("SecureStorage stores and retrieves Cloud PairingCredentials", async () => {
  await SecureStorage.setPairingCredentials({
    mode: "cloud",
    cloudUrl: "https://itnxilvehaeokxvauujk.supabase.co",
    host: "itnxilvehaeokxvauujk.supabase.co",
    hosts: ["itnxilvehaeokxvauujk.supabase.co"],
    port: 443,
    deviceId: "dev_cloud_1",
    deviceToken: "iea_ro_cloud_token_0123456789abcdef",
    companionName: "WIN-OFFICE",
    pairedAt: "2026-11-26T20:00:00Z",
  });
  const loaded = await SecureStorage.getPairingCredentials();
  assert.equal(loaded?.mode, "cloud");
  assert.equal(loaded?.cloudUrl, "https://itnxilvehaeokxvauujk.supabase.co");
  assert.equal(loaded?.deviceId, "dev_cloud_1");
  await SecureStorage.clearPairingCredentials();
});


test("E1-E10 Cloud Sync Parity, Trades Filtering, Chart Overlays, Equity Curve, Cache Invalidation, and Error Mapping", async () => {
  const nowIso = new Date().toISOString();
  const nowSec = Math.floor(Date.now() / 1000);

  // Recorded v1.1.0 cloud snapshot fixture (redacted account, 6 open positions with sl=0/tp=0 + 50 stale OPEN rows + 4 real CLOSED deals)
  const cloudFixture: Record<string, any> = {
    ok: true,
    readOnlyEnforced: true,
    schemaVersion: "1.1.0",
    companionName: "DESKTOP-1P60BCF",
    sequenceNo: 42,
    updatedAt: nowIso,
    meta: {
      schemaVersion: "1.1.0",
      minClientSchemaVersion: "1.0.0",
      supportedVersions: ["1.0.0", "1.1.0"],
      producerVersion: "1.3.7",
      generatedAt: nowIso,
      sequenceNo: 42,
      timezoneRule: "UTC_00_00",
      brokerUtcOffsetHours: 0,
    },
    status: {
      schemaVersion: "1.1.0",
      appVersion: "1.3.7",
      botState: "RUNNING",
      mt5Connected: true,
      mt5Status: "CONNECTED",
      demoMode: true,
      broker: "JustMarkets-Demo",
      accountMasked: "****0203",
      lastHeartbeat: nowIso,
      serverTime: nowIso,
      readOnlyEnforced: true,
    },
    account: {
      balance: 254.22,
      equity: 203.46,
      margin: 14.28,
      freeMargin: 189.18,
      marginLevel: 1424.79,
      floatingPnl: -50.76,
      currency: "USD",
      leverage: 500,
      tradeMode: "DEMO",
      broker: "JustMarkets-Demo",
      accountMasked: "****0203",
      openPositionsCount: 6,
      updatedAt: nowIso,
    },
    // Even if an older producer omitted stats and sent 50 stale OPEN rows in trades,
    // verify MobileSyncClient filters out status='OPEN' rows and computes exact Desktop parity!
    stats: {},
    positions: [
      { ticket: 2738475820, symbol: "XAUUSD.m", direction: "BUY", volume: 0.02, open_price: 3570.92, current_price: 3566.72, sl: 0.0, tp: 0.0, profit: -8.4, open_timestamp: nowSec - 600, ownership: "MANUAL" },
      { ticket: 2738475828, symbol: "XAUUSD.m", direction: "BUY", volume: 0.02, open_price: 3570.93, current_price: 3566.72, sl: 0.0, tp: 0.0, profit: -8.42, open_timestamp: nowSec - 595, ownership: "MANUAL" },
      { ticket: 2738475831, symbol: "XAUUSD.m", direction: "BUY", volume: 0.02, open_price: 3570.93, current_price: 3566.72, sl: 0.0, tp: 0.0, profit: -8.42, open_timestamp: nowSec - 590, ownership: "MANUAL" },
      { ticket: 2738475834, symbol: "XAUUSD.m", direction: "BUY", volume: 0.02, open_price: 3570.93, current_price: 3566.72, sl: 0.0, tp: 0.0, profit: -8.42, open_timestamp: nowSec - 585, ownership: "MANUAL" },
      { ticket: 2738475836, symbol: "XAUUSD.m", direction: "BUY", volume: 0.02, open_price: 3570.93, current_price: 3566.72, sl: 0.0, tp: 0.0, profit: -8.42, open_timestamp: nowSec - 580, ownership: "MANUAL" },
      { ticket: 2738476138, symbol: "XAUUSD.m", direction: "BUY", volume: 0.02, open_price: 3571.06, current_price: 3566.72, sl: 0.0, tp: 0.0, profit: -8.68, open_timestamp: nowSec - 575, ownership: "MANUAL" },
    ],
    // 50 stale OPEN rows (25 positive, 25 negative) that caused E6 (50 deals, 50% win rate)
    trades: Array.from({ length: 50 }, (_, idx) => ({
      ticket: 900000 + idx,
      symbol: "XAUUSD.m",
      direction: "BUY",
      volume: 0.02,
      entry_price: 3570.0,
      close_price: 0,
      profit: idx < 25 ? 12.0 : -8.0,
      status: "OPEN",
      opened_at: nowIso,
      closed_at: null,
    })),
    symbols: [
      { symbol: "XAUUSD", brokerSymbol: "XAUUSD.m", digits: 2, point: 0.01, bid: 3566.72, ask: 3566.92, spreadPoints: 20 },
      { symbol: "USDJPY", brokerSymbol: "USDJPY.m", digits: 3, point: 0.001, bid: 154.21, ask: 154.225, spreadPoints: 15 },
      { symbol: "BTCUSD", brokerSymbol: "BTCUSD.m", digits: 2, point: 0.01, bid: 95200.0, ask: 95225.0, spreadPoints: 2500 },
    ],
    candlesByKey: {
      "XAUUSD:M5": {
        symbol: "XAUUSD",
        brokerSymbol: "XAUUSD.m",
        timeframe: "M5",
        digits: 2,
        point: 0.01,
        bid: 3566.72,
        ask: 3566.92,
        spreadPoints: 20,
        candles: [
          { time: nowSec - 600, open: 3570.0, high: 3572.0, low: 3568.0, close: 3571.0, volume: 120 },
          { time: nowSec - 300, open: 3571.0, high: 3571.5, low: 3566.0, close: 3566.72, volume: 185 },
        ],
      },
    },
    drawingsByKey: {
      "XAUUSD:M5": {
        schema_version: "1.1.0",
        symbol: "XAUUSD",
        broker_symbol: "XAUUSD.m",
        timeframe: "M5",
        counts: { liquidity: 14, fvgOb: 3, structure: 0, sessions: 4, trades: 6 },
        drawings: [
          {
            id: "liq:XAUUSD:D1:PDH:1",
            type: "LIQ",
            subtype: "PDH",
            direction: "BEARISH",
            timeframe: "D1",
            symbol: "XAUUSD",
            start_time: nowSec - 86400,
            end_time: null,
            price_levels: { price: 3585.0 },
            status: "ACTIVE",
            source: "LuxAlgoSMC_MTF",
          },
          {
            id: "fvg:XAUUSD:M5:FVG:1",
            type: "FVG",
            subtype: "FVG",
            direction: "BULLISH",
            timeframe: "M5",
            symbol: "XAUUSD",
            start_time: nowSec - 600,
            end_time: null,
            price_levels: { top: 3570.5, bottom: 3569.0 },
            status: "ACTIVE",
            source: "LuxAlgoSMC",
          },
          {
            id: "trade:open:XAUUSD:2738475820",
            type: "TRADE",
            subtype: "OPEN",
            direction: "BULLISH",
            timeframe: "M5",
            symbol: "XAUUSD",
            start_time: nowSec - 600,
            end_time: null,
            price_levels: { entry: 3570.92, sl: 0, tp: 0, current: 3566.72 },
            status: "OPEN",
            source: "MT5SyncService",
          },
        ],
      },
    },
    equityPoints: [
      { time: nowSec - 3600, balance: 254.22, equity: 254.22, pnl: 0 },
      { time: nowSec - 1800, balance: 254.22, equity: 225.1, pnl: -29.12 },
      { time: nowSec, balance: 254.22, equity: 203.46, pnl: -50.76 },
    ],
  };

  const client = new MobileSyncClient({
    mode: "cloud",
    cloudUrl: "https://itnxilvehaeokxvauujk.supabase.co",
    host: "itnxilvehaeokxvauujk.supabase.co",
    hosts: ["itnxilvehaeokxvauujk.supabase.co"],
    port: 443,
    deviceId: "dev_parity_1",
    deviceToken: "iea_ro_parity_test_token_1234567890",
    companionName: "DESKTOP-1P60BCF",
    pairedAt: nowIso,
  });

  // Inject recorded fixture into cloudCache
  (client as any).cloudCache = cloudFixture;
  (client as any).cloudCacheAtMs = Date.now();

  // E1: getTrades() returns valid { summary, items } and ignores the 50 stale OPEN rows!
  const tradesPage = await client.getTrades({ page: 1, limit: 25 });
  assert.equal(tradesPage.summary.count, 0);
  assert.equal(tradesPage.items.length, 0);
  assert.equal(tradesPage.summary.netPnl, 0);
  assert.equal(tradesPage.summary.winRate, 0);

  // E5 & E6: getStats() matches Desktop ("6 trades today", "0 total deals", "0.0% (0W/0L)", totalProfit = todayPnl = -50.76)
  const stats = await client.getStats();
  assert.equal(stats.dealsCount, 0, "E6: dealsCount must be 0, not 50 stale OPEN rows");
  assert.equal(stats.winsCount, 0);
  assert.equal(stats.lossesCount, 0);
  assert.equal(stats.winRate, 0);
  assert.equal(stats.tradesToday, 6, "E5: tradesToday must match Desktop (0 closed today + 6 open positions)");
  assert.equal(stats.todayPnl, -50.76);
  assert.equal(stats.totalProfit, -50.76);

  // E8: getAccount() returns real marginLevel (1424.79)
  const acc = await client.getAccount();
  assert.equal(acc.marginLevel, 1424.79);
  assert.equal(acc.margin, 14.28);
  assert.equal(acc.freeMargin, 189.18);
  assert.equal(acc.openPositionsCount, 6);

  // E7: getPositions() maps sl: 0.0 and tp: 0.0 to null and protected: false
  const posRes = await client.getPositions();
  assert.equal(posRes.positions.length, 6);
  assert.equal(posRes.positions[0].sl, null);
  assert.equal(posRes.positions[0].tp, null);
  assert.equal(posRes.positions[0].protected, false);

  // E2 & E3: getSymbols(), getCandles(), and getDrawings() return real symbols, candles, and drawings in Cloud mode
  const syms = await client.getSymbols();
  assert.equal(syms.symbols.length, 3);
  assert.equal(syms.symbols[0].symbol, "XAUUSD");
  assert.equal(syms.symbols[0].brokerSymbol, "XAUUSD.m");

  const candles = await client.getCandles({ symbol: "XAUUSD", tf: "M5" });
  assert.equal(candles.candles.length, 2);
  assert.equal(candles.bid, 3566.72);
  assert.equal(candles.point, 0.01);

  const drawings = await client.getDrawings({ symbol: "XAUUSD", tf: "M5" });
  assert.equal(drawings.items.length, 3);
  assert.equal(drawings.drawings?.length, 3);
  assert.equal(drawings.counts?.LIQ, 1);
  assert.equal(drawings.counts?.liquidity, 1);
  assert.equal(drawings.counts?.fvgOb, 1);
  assert.equal(drawings.counts?.TRADE, 1);

  // E4: getEquity() returns >= 2 real points so EquityCurveCard renders SVG path
  const eq = await client.getEquity("1D");
  assert.equal(eq.points.length, 3);
  assert.equal(eq.points[2].pnl, -50.76);

  // Now test E1 filtering, sorting, and search when closed deals exist
  cloudFixture.trades.push(
    {
      ticket: 101,
      symbol: "XAUUSD.m",
      direction: "BUY",
      volume: 0.02,
      entry_price: 3560.0,
      close_price: 3570.0,
      profit: 20.0,
      status: "CLOSED",
      opened_at: "2026-11-26T10:00:00Z",
      closed_at: "2026-11-26T10:15:00Z",
      comment: "SMC_OB",
    },
    {
      ticket: 102,
      symbol: "USDJPY.m",
      direction: "SELL",
      volume: 0.05,
      entry_price: 154.5,
      close_price: 154.8,
      profit: -9.5,
      status: "CLOSED",
      opened_at: "2026-11-26T11:00:00Z",
      closed_at: "2026-11-26T11:20:00Z",
      comment: "LONDON_SWEEP",
    }
  );
  (client as any).cloudCacheAtMs = Date.now();

  const allClosedPage = await client.getTrades({ outcome: "ALL" });
  assert.equal(allClosedPage.summary.count, 2);
  assert.equal(allClosedPage.summary.wins, 1);
  assert.equal(allClosedPage.summary.losses, 1);
  assert.equal(allClosedPage.summary.netPnl, 10.5);
  assert.equal(allClosedPage.summary.winRate, 50);

  const winsOnly = await client.getTrades({ outcome: "WIN" });
  assert.equal(winsOnly.summary.count, 1);
  assert.equal(winsOnly.items[0].ticket, 101);

  const lossesOnly = await client.getTrades({ outcome: "LOSS" });
  assert.equal(lossesOnly.summary.count, 1);
  assert.equal(lossesOnly.items[0].ticket, 102);

  const searchByTag = await client.getTrades({ q: "london_sweep" });
  assert.equal(searchByTag.items.length, 1);
  assert.equal(searchByTag.items[0].canonicalSymbol, "USDJPY");

  // OfflineCache invalidation on schema or account change
  await OfflineCache.saveSnapshot({
    cachedAt: Date.now(),
    deviceId: "dev_1",
    accountMasked: "****0203",
    schemaVersion: "1.0.0",
    status: null,
    account: null,
    stats,
    positions: [],
    symbols: null,
    candlesByKey: {},
    drawingsByKey: {},
    equity: null,
    activity: [],
  });
  // Loading with expected v1.1.0 schema invalidates v1.0.0 cache
  const invalidatedBySchema = await OfflineCache.loadSnapshot({
    deviceId: "dev_1",
    schemaVersion: "1.1.0",
  });
  assert.equal(invalidatedBySchema, null);

  // formatSyncErrorMessage never exposes raw Zod JSON arrays to the user
  const fakeZodErr = new Error('[{"code":"invalid_type","expected":"object","received":"undefined","path":["summary"]}]');
  fakeZodErr.name = "ZodError";
  const friendly = formatSyncErrorMessage(fakeZodErr);
  assert.doesNotMatch(friendly, /invalid_type/);
  assert.match(friendly, /Tap Retry/i);
});
