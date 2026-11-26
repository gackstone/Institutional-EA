import test from "node:test";
import assert from "node:assert/strict";
import {
  computeBackoffMs,
  isSnapshotStale,
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
