import test from "node:test";
import assert from "node:assert/strict";
import {
  BULL_COLOR,
  BEAR_COLOR,
  CHART_DARK_THEME,
  CHART_TV_LIGHT_THEME,
  calculateTradeMetrics,
  calculateTradeZones,
  validateTightenOnlyStopLoss,
  resolveLabelCollisions,
  formatZoneLegend,
  computeZoneLabelPlacement,
  ZONE_LABEL_THEME,
} from "../src/index.ts";

test("chartCore theme tokens expose sampled colors and light/dark modes", () => {
  assert.equal(BULL_COLOR, "#0A997D");
  assert.equal(BEAR_COLOR, "#EE3749");
  assert.ok(CHART_DARK_THEME.background);
  assert.ok(CHART_TV_LIGHT_THEME.background);
});

test("chartCore tradeChartMath calculates R-multiples and zone boundaries", () => {
  const trade = {
    direction: "BUY" as const,
    entryPrice: 2660.0,
    initialStopLoss: 2655.0, // 5.0 pt risk
    stopLoss: 2660.5,
    tp1: 2666.25,
    tp2: 2672.5,
    currentPrice: 2667.5,
    volumeLots: 0.2,
    contractValuePerPoint: 100,
  };

  const metrics = calculateTradeMetrics(trade);
  assert.equal(metrics.initialRiskDistance, 5.0);
  assert.equal(metrics.floatingR, 1.5);
  assert.equal(metrics.isBreakEvenOrBetter, true);
});

test("chartCore enforce tighten-only stop policy", () => {
  // Tightening BUY SL (currentSl < proposedSl < currentPrice) is allowed
  const tightenBuy = validateTightenOnlyStopLoss({
    direction: "BUY",
    currentSl: 2658.0,
    proposedSl: 2662.5,
    currentPrice: 2665.0,
  });
  assert.equal(tightenBuy.allowed, true);

  // Widening BUY SL (proposedSl < currentSl) is blocked
  const widenBuy = validateTightenOnlyStopLoss({
    direction: "BUY",
    currentSl: 2658.0,
    proposedSl: 2655.0,
    currentPrice: 2665.0,
  });
  assert.equal(widenBuy.allowed, false);

  // Removing SL is blocked
  const removeSl = validateTightenOnlyStopLoss({
    direction: "BUY",
    currentSl: 2658.0,
    proposedSl: 0,
    currentPrice: 2665.0,
  });
  assert.equal(removeSl.allowed, false);
});

test("chartCore FVG / OB / IFVG zone centered labels formatting and positioning", () => {
  assert.equal(formatZoneLegend("FVG"), "FVG - Fair Value Gap");
  assert.equal(formatZoneLegend("OB"), "OB - Order Block");
  assert.equal(formatZoneLegend("IFVG"), "IFVG - Inverse Fair Value Gap");

  // Zone bounds placement math
  const placement = computeZoneLabelPlacement(100, 50, 200, 90, 800, 600, 24, 10);
  assert.ok(placement);
  assert.equal(placement.x, 150);
  assert.equal(placement.y, 70);

  // When zone is too narrow to fit text + padding, returns null
  const tooNarrow = computeZoneLabelPlacement(100, 50, 110, 90, 800, 600, 24, 10);
  assert.equal(tooNarrow, null);

  // Themes expose light and dark label colors with halos
  assert.ok(ZONE_LABEL_THEME.light.text);
  assert.ok(ZONE_LABEL_THEME.light.halo);
  assert.ok(ZONE_LABEL_THEME.dark.text);
  assert.ok(ZONE_LABEL_THEME.dark.halo);
});
