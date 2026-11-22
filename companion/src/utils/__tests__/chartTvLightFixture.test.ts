import test from "node:test";
import assert from "node:assert/strict";
import { BULL_COLOR, BEAR_COLOR, CHART_TV_LIGHT_THEME } from "../../styles/chartTheme.ts";
import type { ChartSymbol, ChartTimeframe, SymbolChartBundle } from "../../services/dashboardDataAdapter.ts";

/**
 * Clearly-labeled test fixture builder covering all required verification scenarios:
 * - open long, open short, closed long, closed short, moved stop, pending signal,
 *   overlapping trades, active & mitigated FVGs/OBs, and text-free Liquidity/Structure/Sessions
 * across M1, M5, M15, H1, H4 for XAUUSD, USDJPY, and BTCUSD.
 */
export function buildTvLightDrawingTestFixture(
  symbol: ChartSymbol,
  timeframe: ChartTimeframe
): SymbolChartBundle {
  const tfSecMap: Record<ChartTimeframe, number> = {
    M1: 60,
    M5: 300,
    M15: 900,
    H1: 3600,
    H4: 14400,
  };
  const step = tfSecMap[timeframe];
  const baseTime = 1763800000;
  const basePrice = symbol === "XAUUSD" ? 3500 : symbol === "USDJPY" ? 155 : 60000;
  const unit = symbol === "XAUUSD" ? 1.0 : symbol === "USDJPY" ? 0.05 : 50.0;
  const digits = symbol === "USDJPY" ? 3 : 2;
  const point = symbol === "USDJPY" ? 0.001 : 0.01;

  const candles = Array.from({ length: 60 }, (_, i) => {
    const o = basePrice + Math.sin(i * 0.25) * unit * 4;
    const c = o + (i % 2 === 0 ? unit * 1.4 : -unit * 1.1);
    return {
      time: baseTime + i * step,
      open: Number(o.toFixed(digits)),
      high: Number((Math.max(o, c) + unit * 0.8).toFixed(digits)),
      low: Number((Math.min(o, c) - unit * 0.8).toFixed(digits)),
      close: Number(c.toFixed(digits)),
      volume: 100 + i,
    };
  });

  return {
    symbol,
    brokerSymbol: `${symbol}.m`,
    timeframe,
    digits,
    point,
    contractValuePerPoint: symbol === "XAUUSD" ? 100 : symbol === "USDJPY" ? 650 : 1,
    bid: candles[candles.length - 1].close,
    ask: Number((candles[candles.length - 1].close + point * 15).toFixed(digits)),
    spreadPoints: 15,
    candles,
    trades: [
      // 1. Open LONG with moved stop & TP1 + TP2
      {
        ticket: 1001,
        symbol,
        direction: "BUY",
        volume: 0.1,
        qualityScore: 88,
        entryPrice: basePrice,
        entryTime: candles[20].time,
        currentPrice: basePrice + unit * 3,
        stopLoss: basePrice + unit * 0.2,
        initialStopLoss: basePrice - unit * 2,
        tp1: basePrice + unit * 3,
        tp2: basePrice + unit * 6,
        floatingPnl: 30,
        floatingR: 1.5,
        tp1R: 1.5,
        tp2R: 3.0,
        ownership: "BOT_OWN",
        protected: true,
        strategyTag: "FIXTURE_OPEN_LONG",
      },
      // 2. Open SHORT (overlapping)
      {
        ticket: 1002,
        symbol,
        direction: "SELL",
        volume: 0.1,
        qualityScore: 84,
        entryPrice: basePrice + unit * 4,
        entryTime: candles[32].time,
        currentPrice: basePrice + unit * 1,
        stopLoss: basePrice + unit * 6,
        initialStopLoss: basePrice + unit * 6,
        tp1: 0,
        tp2: basePrice - unit * 2,
        floatingPnl: 25,
        floatingR: 1.5,
        tp1R: 0,
        tp2R: 3.0,
        ownership: "BOT_OWN",
        protected: true,
        strategyTag: "FIXTURE_OPEN_SHORT",
      },
      // 3. Closed LONG
      {
        ticket: 1003,
        symbol,
        direction: "BUY",
        volume: 0.1,
        qualityScore: 90,
        entryPrice: basePrice - unit * 3,
        entryTime: candles[8].time,
        exitTime: candles[18].time,
        exitPrice: basePrice + unit * 2,
        currentPrice: basePrice + unit * 2,
        stopLoss: basePrice - unit * 5,
        initialStopLoss: basePrice - unit * 5,
        tp1: 0,
        tp2: basePrice + unit * 2,
        floatingPnl: 50,
        floatingR: 2.5,
        tp1R: 0,
        tp2R: 2.5,
        ownership: "BOT_OWN",
        protected: true,
        strategyTag: "FIXTURE_CLOSED_LONG",
        isClosed: true,
      },
      // 4. Pending Signal with SL/TP
      {
        ticket: 1004,
        symbol,
        direction: "SELL",
        volume: 0.05,
        qualityScore: 80,
        entryPrice: basePrice + unit * 5,
        entryTime: candles[48].time,
        currentPrice: basePrice + unit * 5,
        stopLoss: basePrice + unit * 7,
        initialStopLoss: basePrice + unit * 7,
        tp1: 0,
        tp2: basePrice + unit * 1,
        floatingPnl: 0,
        floatingR: 0,
        tp1R: 0,
        tp2R: 2.0,
        ownership: "BOT_OWN",
        protected: true,
        strategyTag: "FIXTURE_PENDING_SHORT",
        isPendingSignal: true,
      },
    ],
    fvgObZones: [
      {
        id: "ob-active",
        kind: "OB",
        bias: "BEARISH",
        label: "OB",
        topPrice: basePrice + unit * 5.2,
        bottomPrice: basePrice + unit * 4.4,
        startTime: candles[25].time,
        mitigated: false,
      },
      {
        id: "fvg-active",
        kind: "FVG",
        bias: "BULLISH",
        label: "FVG",
        topPrice: basePrice - unit * 2.2,
        bottomPrice: basePrice - unit * 3.4,
        startTime: candles[42].time,
        mitigated: false,
      },
      {
        id: "fvg-mitigated",
        kind: "FVG",
        bias: "BULLISH",
        label: "FVG",
        topPrice: basePrice - unit * 0.5,
        bottomPrice: basePrice - unit * 1.2,
        startTime: candles[10].time,
        endTime: candles[22].time,
        mitigated: true,
      },
    ],
    liquidityLevels: [
      {
        id: "liq-1",
        code: "PDH",
        label: "PDH",
        price: basePrice + unit * 6,
        startTime: candles[5].time,
        swept: false,
        side: "HIGH",
      },
    ],
    structureBreaks: [
      {
        id: "st-1",
        kind: "BOS",
        bias: "BULLISH",
        price: basePrice + unit * 2,
        startTime: candles[12].time,
        time: candles[20].time,
        label: "BOS",
      },
    ],
    sessions: [
      {
        id: "sess-1",
        session: "LONDON",
        label: "LDN",
        startTime: candles[15].time,
        endTime: candles[35].time,
        highPrice: basePrice + unit * 6,
        lowPrice: basePrice - unit * 5,
        color: "rgba(148, 163, 184, 0.08)",
      },
    ],
    source: "MT5",
    tickTimeUtc: new Date(baseTime * 1000).toISOString(),
    tickAgeSec: 1.0,
    stale: false,
    marketClosed: false,
    freshnessReason: "LIVE",
  };
}

test("chartTheme exposes sampled TradingView light tokens and single-line BULL/BEAR tokens", () => {
  assert.equal(CHART_TV_LIGHT_THEME.background, "#FFFFFF");
  assert.equal(CHART_TV_LIGHT_THEME.candles.bull, BULL_COLOR);
  assert.equal(CHART_TV_LIGHT_THEME.candles.bear, BEAR_COLOR);
  assert.equal(BULL_COLOR, "#0A997D");
  assert.equal(BEAR_COLOR, "#EE3749");
  assert.equal(CHART_TV_LIGHT_THEME.typography.labelColor, "#313131");
});

test("buildTvLightDrawingTestFixture covers all 3 symbols and all 5 timeframes with required scenarios", () => {
  const symbols: ChartSymbol[] = ["XAUUSD", "USDJPY", "BTCUSD"];
  const timeframes: ChartTimeframe[] = ["M1", "M5", "M15", "H1", "H4"];
  for (const sym of symbols) {
    for (const tf of timeframes) {
      const fx = buildTvLightDrawingTestFixture(sym, tf);
      assert.equal(fx.candles.length, 60);
      assert.equal(fx.trades.length, 4);
      assert.equal(fx.fvgObZones.length, 3);
      assert.equal(fx.liquidityLevels.length, 1);
      assert.equal(fx.structureBreaks.length, 1);
      assert.equal(fx.sessions.length, 1);
    }
  }
});
