import test from "node:test";
import assert from "node:assert/strict";
import {
  AccountStateSchema,
  PositionSchema,
  TradeDealSchema,
  SmcZoneSchema,
  KpiSummarySchema,
  PairingQrPayloadSchema,
  DeviceTokenPayloadSchema,
  TelemetrySnapshotSchema,
  assertReadOnlyScope,
  assertOperationPermitted,
  FORBIDDEN_OPERATIONS,
} from "../src/index.ts";

test("AccountStateSchema validates valid account and rejects negative balance", () => {
  const valid = {
    balance: 10500.5,
    equity: 10620.0,
    margin: 500,
    freeMargin: 10120,
    currency: "USD",
    leverage: 100,
    serverTime: 1763800000,
    accountNumber: "123456",
    syncedAt: new Date().toISOString(),
    isLive: false,
  };
  const parsed = AccountStateSchema.parse(valid);
  assert.equal(parsed.balance, 10500.5);

  assert.throws(() => {
    AccountStateSchema.parse({ ...valid, balance: -10 });
  });
});

test("PositionSchema validates positions and rejects invalid type", () => {
  const valid = {
    ticket: 99120,
    symbol: "XAUUSD",
    type: "BUY",
    volume: 0.1,
    openPrice: 2650.5,
    currentPrice: 2655.0,
    sl: 2640.0,
    tp: 2670.0,
    profit: 45.0,
    swap: -0.5,
    openTime: 1763800000,
  };
  const parsed = PositionSchema.parse(valid);
  assert.equal(parsed.symbol, "XAUUSD");

  assert.throws(() => {
    PositionSchema.parse({ ...valid, type: "HOLD" });
  });
});

test("SmcZoneSchema validates FVG, OB, IFVG with centered labels", () => {
  for (const label of ["FVG", "OB", "IFVG"] as const) {
    const zone = {
      id: `zone-${label}-1`,
      type: label,
      direction: "BULL",
      timeframe: "M5",
      symbol: "XAUUSD",
      top: 2655.0,
      bottom: 2650.0,
      startTime: 1763800000,
      endTime: null,
      status: "UNMITIGATED",
      label,
    };
    const parsed = SmcZoneSchema.parse(zone);
    assert.equal(parsed.label, label);
  }
});

test("DeviceTokenPayloadSchema rejects non-read-only scopes", () => {
  const valid = {
    sub: "device-uuid-1234",
    accountMasked: "123***56",
    scopes: ["telemetry:read"],
    iat: 1763800000,
    exp: 1763886400,
  };
  const parsed = DeviceTokenPayloadSchema.parse(valid);
  assert.equal(parsed.sub, "device-uuid-1234");

  assert.throws(() => {
    DeviceTokenPayloadSchema.parse({
      ...valid,
      scopes: ["telemetry:read", "trade:execute"],
    });
  });
});

test("Security guardrails strictly forbid mutation operations", () => {
  assert.equal(assertReadOnlyScope(["telemetry:read"]), true);

  assert.throws(() => {
    assertReadOnlyScope(["telemetry:read", "admin"]);
  });

  for (const op of FORBIDDEN_OPERATIONS) {
    assert.throws(
      () => assertOperationPermitted(op),
      /Strict Read-Only Enforcement/
    );
  }

  // Allowed read-only operation does not throw
  assert.doesNotThrow(() => assertOperationPermitted("fetch_telemetry"));
});

test("TelemetrySnapshotSchema validates complete sanitized state snapshot", () => {
  const snapshot = {
    version: 1,
    timestamp: 1763800000,
    account: {
      balance: 10000,
      equity: 10050,
      margin: 100,
      freeMargin: 9950,
      currency: "USD",
      leverage: 100,
      serverTime: 1763800000,
      accountNumber: "123456",
      syncedAt: new Date().toISOString(),
      isLive: false,
    },
    positions: [],
    recentDeals: [],
    kpis: {
      balance: 10000,
      equity: 10050,
      todayPnl: 50,
      totalProfit: 1250,
      winRate: 68.5,
      todayTradesCount: 3,
      totalDealsCount: 42,
      calculatedAt: 1763800000,
    },
    zones: {
      XAUUSD: [],
    },
  };

  const parsed = TelemetrySnapshotSchema.parse(snapshot);
  assert.equal(parsed.kpis.winRate, 68.5);
});
