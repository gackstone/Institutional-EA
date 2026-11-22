import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildEngineDrawingsParityFixture,
  buildParityDebugReport,
  shouldIncludeDrawingForTimeframe,
  validateEngineDrawingsFeed,
} from "../chartDrawingsSchema.ts";
import {
  hitTestProjectedDrawings,
  projectEngineDrawings,
  type CandlePoint,
  type CoordinateProjector,
} from "../chartCanvasRenderer.ts";

function makeSyntheticCandles(
  symbol: "XAUUSD" | "USDJPY" | "BTCUSD",
  timeframe: "M1" | "M5" | "M15" | "H1" | "H4",
  anchorTimeSec = 1763568000
): CandlePoint[] {
  const basePrice = symbol === "XAUUSD" ? 2650.0 : symbol === "USDJPY" ? 154.5 : 91500.0;
  const step = symbol === "XAUUSD" ? 2.5 : symbol === "USDJPY" ? 0.15 : 220.0;
  const tfSec =
    timeframe === "M1"
      ? 60
      : timeframe === "M5"
      ? 300
      : timeframe === "M15"
      ? 900
      : timeframe === "H1"
      ? 3600
      : 14400;

  const candles: CandlePoint[] = [];
  for (let i = 100; i >= 0; i--) {
    const t = anchorTimeSec - i * tfSec;
    const wave = Math.sin(i / 8) * step * 2.5;
    const o = basePrice + wave;
    const c = o + (i % 2 === 0 ? step * 0.4 : -step * 0.35);
    candles.push({
      time: t,
      open: o,
      high: Math.max(o, c) + step * 0.6,
      low: Math.min(o, c) - step * 0.6,
      close: c,
      volume: 100,
    });
  }
  return candles;
}

function makeLinearProjector(candles: CandlePoint[], plotWidth = 1000, plotHeight = 500): CoordinateProjector {
  const minT = candles[0].time;
  const maxT = candles[candles.length - 1].time;
  const allPrices = candles.flatMap((c) => [c.high, c.low]);
  const span = Math.max(1e-4, Math.max(...allPrices) - Math.min(...allPrices));
  const minP = Math.min(...allPrices) - span * 0.8;
  const maxP = Math.max(...allPrices) + span * 0.8;

  return {
    candles,
    plotWidth,
    plotHeight,
    timeToX: (t: number) => {
      if (t < minT || t > maxT) return null;
      return ((t - minT) / Math.max(1, maxT - minT)) * plotWidth;
    },
    priceToY: (p: number) => {
      return (1 - (p - minP) / Math.max(1e-6, maxP - minP)) * plotHeight;
    },
  };
}

test("Parity across all 3 symbols x 5 timeframes: rendered drawings equal validated engine items", () => {
  const symbols: Array<"XAUUSD" | "USDJPY" | "BTCUSD"> = ["XAUUSD", "USDJPY", "BTCUSD"];
  const tfs: Array<"M1" | "M5" | "M15" | "H1" | "H4"> = ["M1", "M5", "M15", "H1", "H4"];

  for (const sym of symbols) {
    for (const tf of tfs) {
      const feed = buildEngineDrawingsParityFixture(sym, tf);
      const validated = validateEngineDrawingsFeed(feed, sym, tf);
      assert.equal(validated.malformedFeed, false);
      assert.equal(validated.dropped.length, 0);
      assert.equal(validated.counts.liquidity, 3);
      assert.equal(validated.counts.fvgOb, 2);
      assert.equal(validated.counts.structure, 2);
      assert.equal(validated.counts.trades, 3);

      const candles = makeSyntheticCandles(sym, tf);
      const projector = makeLinearProjector(candles);
      const projected = projectEngineDrawings(
        validated.items,
        { liquidity: true, fvgOb: true, structure: true, sessions: true, trades: true },
        projector
      );

      // Every non-session drawing in the fixture is inside the candle range and must project 1:1
      const nonSessEngine = validated.items.filter((d) => d.type !== "SESS");
      const nonSessProjected = projected.filter((p) => p.item.type !== "SESS");
      assert.equal(
        nonSessProjected.length,
        nonSessEngine.length,
        `${sym} ${tf}: expected ${nonSessEngine.length} projected drawings, got ${nonSessProjected.length}`
      );

      // Verify exact Y coordinate parity for LIQ & STRUCT & TRADE
      for (const proj of nonSessProjected) {
        if (proj.item.type === "LIQ" || proj.item.type === "STRUCT") {
          const expectedY = projector.priceToY(proj.item.price_levels.price!);
          assert.equal(proj.y1, expectedY);
        }
        if (proj.item.type === "TRADE") {
          assert.equal(proj.entryY, projector.priceToY(proj.item.price_levels.entry!));
        }
      }

      const report = buildParityDebugReport(
        validated.items,
        new Set(projected.map((p) => p.item.id))
      );
      assert.equal(report.length, validated.items.length);
    }
  }
});

test("Timeframe hierarchy: HTF drawings appear on LTF, LTF drawings are hidden on HTF", () => {
  assert.equal(shouldIncludeDrawingForTimeframe("D1", "M5", "LIQ"), true);
  assert.equal(shouldIncludeDrawingForTimeframe("H1", "M15", "FVG"), true);
  assert.equal(shouldIncludeDrawingForTimeframe("M5", "H1", "FVG"), false);
  assert.equal(shouldIncludeDrawingForTimeframe("M1", "M15", "STRUCT"), false);
  assert.equal(shouldIncludeDrawingForTimeframe("M5", "H4", "TRADE"), true);
  assert.equal(shouldIncludeDrawingForTimeframe("M5", "H4", "SESS"), true);
});

test("Validation rejects wrong-symbol, malformed prices, inverted FVG bounds, and duplicate IDs", () => {
  const feed = buildEngineDrawingsParityFixture("XAUUSD", "M5");
  const badItems: any[] = [
    ...feed.drawings,
    // Duplicate ID
    { ...feed.drawings[0] },
    // Wrong symbol
    { ...feed.drawings[0], id: "wrong-sym", symbol: "BTCUSD.m" },
    // Inverted FVG (top <= bottom)
    {
      id: "bad-fvg",
      type: "FVG",
      subtype: "FVG",
      symbol: "XAUUSD",
      timeframe: "M5",
      start_time: 1763560000,
      end_time: null,
      price_levels: { top: 2640, bottom: 2650 },
      direction: "BULLISH",
      status: "ACTIVE",
      source: "FvgObEngine",
    },
    // NaN price
    {
      id: "nan-liq",
      type: "LIQ",
      subtype: "PDH",
      symbol: "XAUUSD",
      timeframe: "D1",
      start_time: 1763560000,
      end_time: null,
      price_levels: { price: Number.NaN },
      direction: "BEARISH",
      status: "ACTIVE",
      source: "WeeklyDailyEngine",
    },
  ];

  const validated = validateEngineDrawingsFeed({ ...feed, drawings: badItems }, "XAUUSD.m", "M5");
  assert.equal(validated.dropped.length, 4);
  assert.equal(validated.items.length, feed.drawings.length);
});

test("Layer toggles hide and show exact drawing groups and hitTest prioritizes TRADE over SESS", () => {
  const feed = buildEngineDrawingsParityFixture("XAUUSD", "M15");
  const candles = makeSyntheticCandles("XAUUSD", "M15");
  const projector = makeLinearProjector(candles);

  const onlyTrades = projectEngineDrawings(
    feed.drawings,
    { liquidity: false, fvgOb: false, structure: false, sessions: false, trades: true },
    projector
  );
  assert.equal(onlyTrades.length, 3);
  assert.ok(onlyTrades.every((p) => p.item.type === "TRADE"));

  const all = projectEngineDrawings(
    feed.drawings,
    { liquidity: true, fvgOb: true, structure: true, sessions: true, trades: true },
    projector
  );
  const openTrade = all.find((p) => p.item.subtype === "OPEN")!;
  const hit = hitTestProjectedDrawings(
    (openTrade.x1 + openTrade.x2) / 2,
    openTrade.entryY!,
    all
  );
  assert.equal(hit?.item.id, openTrade.item.id);
});
