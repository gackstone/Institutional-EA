import assert from "node:assert/strict";
import test from "node:test";
import {
  calculateTradeMetrics,
  calculateTradeZones,
  computeScheduleAndSession,
  maskAccountNumber,
  normalizeCanonicalSymbol,
  type RawPriceLabelItem,
  resolveLabelCollisions,
  snapTimestampToCandle,
  validateTightenOnlyStopLoss,
} from "../tradeChartMath.ts";

test("calculateTradeMetrics computes accurate R-multiples, risk distance, and break-even status for BUY", () => {
  const m = calculateTradeMetrics({
    direction: "BUY",
    entryPrice: 2660.0,
    initialStopLoss: 2655.0, // 5.00 pt initial risk = 1R
    stopLoss: 2660.5, // tightened to BE + 0.50 pt
    tp1: 2666.25, // +6.25 pt = +1.25R
    tp2: 2672.5, // +12.50 pt = +2.50R
    currentPrice: 2667.5, // +7.50 pt = +1.50R
    volumeLots: 0.2,
    contractValuePerPoint: 100,
  });

  assert.equal(m.initialRiskDistance, 5.0);
  assert.equal(m.floatingR, 1.5);
  assert.equal(m.tp1R, 1.25);
  assert.equal(m.tp2R, 2.5);
  assert.equal(m.slMoved, true);
  assert.equal(m.isBreakEvenOrBetter, true);
  assert.equal(m.floatingPnlUsd, 150.0);
});

test("calculateTradeMetrics computes accurate R-multiples for SELL trade", () => {
  const m = calculateTradeMetrics({
    direction: "SELL",
    entryPrice: 154.5,
    initialStopLoss: 154.75, // 0.25 pt initial risk = 1R
    stopLoss: 154.75,
    tp1: 154.25, // +1.00R
    tp2: 153.875, // +2.50R
    currentPrice: 154.375, // +0.50R
    volumeLots: 0.2,
    contractValuePerPoint: 650,
  });

  assert.equal(m.initialRiskDistance, 0.25);
  assert.equal(m.floatingR, 0.5);
  assert.equal(m.tp1R, 1.0);
  assert.equal(m.tp2R, 2.5);
  assert.equal(m.slMoved, false);
  assert.equal(m.isBreakEvenOrBetter, false);
});

test("calculateTradeZones computes shaded risk/reward bounds and ghost initial SL", () => {
  const zones = calculateTradeZones({
    direction: "BUY",
    entryPrice: 2662.5,
    initialStopLoss: 2657.5,
    stopLoss: 2663.0, // Moved above entry
    tp1: 2668.75,
    tp2: 2675.0,
  });

  assert.equal(zones.riskZone.valid, true);
  assert.equal(zones.riskZone.topPrice, 2662.5);
  assert.equal(zones.riskZone.bottomPrice, 2657.5);
  assert.equal(zones.rewardZoneTp1.valid, true);
  assert.equal(zones.rewardZoneTp1.topPrice, 2668.75);
  assert.equal(zones.rewardZoneTp1.bottomPrice, 2662.5);
  assert.equal(zones.rewardZoneTp2.valid, true);
  assert.equal(zones.rewardZoneTp2.topPrice, 2675.0);
  assert.equal(zones.ghostInitialSlPrice, 2657.5);
});

test("validateTightenOnlyStopLoss enforces tighten-only stop policy (never widen or remove SL)", () => {
  // 1. Removing SL (proposedSl = 0) must be blocked
  const removeCheck = validateTightenOnlyStopLoss({
    direction: "BUY",
    currentSl: 2658.0,
    proposedSl: 0,
    currentPrice: 2665.0,
  });
  assert.equal(removeCheck.allowed, false);
  assert.match(removeCheck.reason, /TIGHTEN_ONLY_POLICY/);

  // 2. Widening BUY SL (proposedSl < currentSl) must be blocked
  const widenBuy = validateTightenOnlyStopLoss({
    direction: "BUY",
    currentSl: 2658.0,
    proposedSl: 2655.0,
    currentPrice: 2665.0,
  });
  assert.equal(widenBuy.allowed, false);

  // 3. Tightening BUY SL (currentSl < proposedSl < currentPrice) must be allowed
  const tightenBuy = validateTightenOnlyStopLoss({
    direction: "BUY",
    currentSl: 2658.0,
    proposedSl: 2662.5,
    currentPrice: 2665.0,
  });
  assert.equal(tightenBuy.allowed, true);

  // 4. Widening SELL SL (proposedSl > currentSl) must be blocked
  const widenSell = validateTightenOnlyStopLoss({
    direction: "SELL",
    currentSl: 154.5,
    proposedSl: 154.8,
    currentPrice: 154.2,
  });
  assert.equal(widenSell.allowed, false);

  // 5. Tightening SELL SL (currentPrice < proposedSl < currentSl) must be allowed
  const tightenSell = validateTightenOnlyStopLoss({
    direction: "SELL",
    currentSl: 154.5,
    proposedSl: 154.35,
    currentPrice: 154.2,
  });
  assert.equal(tightenSell.allowed, true);
});

test("resolveLabelCollisions prevents label overlap and clipping while preserving vertical price order", () => {
  const raw: RawPriceLabelItem[] = [
    { id: "tp2", price: 2675.0, idealY: 100, label: "TP2", tone: "tp2" },
    { id: "tp1", price: 2674.8, idealY: 104, label: "TP1", tone: "tp1" },
    { id: "live", price: 2674.5, idealY: 107, label: "LIVE", tone: "live" },
    { id: "entry", price: 2674.2, idealY: 110, label: "ENTRY", tone: "entry" },
    { id: "sl", price: 2674.0, idealY: 112, label: "SL", tone: "sl" },
    { id: "ghost", price: 2670.0, idealY: 495, label: "INIT SL", tone: "ghost_sl" },
  ];

  const resolved = resolveLabelCollisions(raw, {
    minY: 10,
    maxY: 450,
    minGapPx: 24,
    defaultHeightPx: 20,
  });

  assert.equal(resolved.length, 6);

  // Verify no clipping outside [minY + 10, maxY - 10] = [20, 440]
  for (const item of resolved) {
    assert.ok(item.resolvedY >= 20, `Label ${item.id} clipped top: ${item.resolvedY}`);
    assert.ok(item.resolvedY <= 440, `Label ${item.id} clipped bottom: ${item.resolvedY}`);
  }

  // Verify strict minimum vertical separation >= 24px between adjacent labels
  for (let i = 1; i < resolved.length; i++) {
    const gap = resolved[i].resolvedY - resolved[i - 1].resolvedY;
    assert.ok(gap >= 23.9, `Labels ${resolved[i - 1].id} and ${resolved[i].id} overlap (gap=${gap})`);
  }
});

test("maskAccountNumber and computeScheduleAndSession return expected schedule modes", () => {
  assert.equal(maskAccountNumber(50920001), "****0001");
  assert.equal(maskAccountNumber(0), "****0001");

  // Weekday: Wednesday 14:00 UTC -> WEEKDAY_GOLD_MODE & LDN/NY OVERLAP
  const wed = new Date("2026-11-18T14:00:00Z");
  const wedInfo = computeScheduleAndSession(wed);
  assert.equal(wedInfo.scheduleMode, "WEEKDAY_GOLD_MODE");
  assert.equal(wedInfo.sessionName, "LDN/NY OVERLAP");
  assert.deepEqual(wedInfo.activeInstruments, ["XAUUSD", "USDJPY"]);

  // Weekend: Sunday 12:00 UTC -> WEEKEND_BTC_MODE & WEEKEND CRYPTO 24/7
  const sun = new Date("2026-11-22T12:00:00Z");
  const sunInfo = computeScheduleAndSession(sun);
  assert.equal(sunInfo.scheduleMode, "WEEKEND_BTC_MODE");
  assert.equal(sunInfo.sessionName, "WEEKEND CRYPTO 24/7");
  assert.deepEqual(sunInfo.activeInstruments, ["BTCUSD"]);
});

test("normalizeCanonicalSymbol strips broker suffixes and snapTimestampToCandle snaps to bar boundaries", () => {
  assert.equal(normalizeCanonicalSymbol("XAUUSD.m"), "XAUUSD");
  assert.equal(normalizeCanonicalSymbol("XAUUSD.pro"), "XAUUSD");
  assert.equal(normalizeCanonicalSymbol("USDJPY.m"), "USDJPY");
  assert.equal(normalizeCanonicalSymbol("BTCUSDc"), "BTCUSD");

  const candles = [1700000000, 1700000300, 1700000600, 1700000900];
  assert.equal(snapTimestampToCandle(1700000440, 300, candles), 1700000300);
  // Clamps to earliest/latest loaded candle across weekend gaps
  assert.equal(snapTimestampToCandle(1699900000, 300, candles), 1700000000);
  assert.equal(snapTimestampToCandle(1700050000, 300, candles), 1700000900);
});
