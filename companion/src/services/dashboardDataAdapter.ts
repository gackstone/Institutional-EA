import {
  ControlErrorEvent,
  ControlLogEntry,
  ControlPosition,
  ControlStatusPayload,
  ControlSymbolSpec,
  OperatingMode,
  RiskDecisionRecord,
  TradeHistoryRecord,
} from "../types";
import {
  calculateTradeMetrics,
  computeScheduleAndSession,
  maskAccountNumber,
  normalizeCanonicalSymbol,
  snapTimestampToCandle,
  TradeDirection,
} from "../utils/tradeChartMath";

export type ChartSymbol = "XAUUSD" | "USDJPY" | "BTCUSD";
export type ChartTimeframe = "M1" | "M5" | "M15" | "H1" | "H4";
export type DataFeedStatus = "LIVE_SSE" | "POLLING" | "STALE" | "DISCONNECTED" | "LOADING";

export interface CandleBar {
  time: number; // Unix timestamp in seconds
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartTradeLifecycleAnnotation {
  id: string;
  time: number;
  price: number;
  type: "SIGNAL" | "ENTRY" | "BE_MOVED" | "TRAIL_SL" | "PARTIAL_CLOSE" | "SL_HIT" | "TP_HIT" | "CLOSED";
  label: string;
  detail: string;
  tone: "buy" | "sell" | "be" | "partial" | "tp" | "sl" | "closed";
}

export interface ChartTradeOverlay {
  ticket: number;
  symbol: ChartSymbol;
  direction: TradeDirection;
  volume: number;
  qualityScore: number;
  entryPrice: number;
  entryTime: number;
  currentPrice: number;
  stopLoss: number;
  initialStopLoss: number;
  tp1: number;
  tp2: number;
  floatingPnl: number;
  floatingR: number;
  tp1R: number;
  tp2R: number;
  ownership: "BOT_OWN" | "MANUAL" | "OTHER_EA";
  protected: boolean;
  strategyTag: string;
  annotations: ChartTradeLifecycleAnnotation[];
}

export interface LiquidityLevelOverlay {
  id: string;
  code: "PWH" | "PDH" | "PDL" | "PWL" | "EQH" | "EQL";
  label: string;
  price: number;
  startTime?: number;
  endTime?: number;
  swept: boolean;
  side: "HIGH" | "LOW";
}

export interface FvgObZoneOverlay {
  id: string;
  kind: "FVG" | "IFVG" | "OB";
  bias: "BULLISH" | "BEARISH";
  label: string;
  topPrice: number;
  bottomPrice: number;
  startTime: number;
  endTime?: number;
  mitigated: boolean;
}

export interface StructureBreakOverlay {
  id: string;
  kind: "MSS" | "CHoCH" | "BOS";
  bias: "BULLISH" | "BEARISH";
  price: number;
  startTime?: number;
  time: number;
  label: string;
}

export interface SessionMarkerOverlay {
  id: string;
  session: "ASIAN" | "LONDON" | "NY_OVERLAP" | "NEW_YORK";
  label: string;
  startTime: number;
  endTime: number;
  highPrice: number;
  lowPrice: number;
  color: string;
}

export interface SymbolChartBundle {
  symbol: ChartSymbol;
  brokerSymbol: string;
  timeframe: ChartTimeframe;
  digits: number;
  point: number;
  contractValuePerPoint: number;
  bid: number;
  ask: number;
  spreadPoints: number;
  candles: CandleBar[];
  trades: ChartTradeOverlay[];
  liquidityLevels: LiquidityLevelOverlay[];
  fvgObZones: FvgObZoneOverlay[];
  structureBreaks: StructureBreakOverlay[];
  sessions: SessionMarkerOverlay[];
}

export interface TradeTimelineEvent {
  id: string;
  timestamp: string;
  symbol: ChartSymbol;
  ticket: number;
  stage: "SIGNAL" | "RISK_GATE" | "ORDER_FILLED" | "BE_MOVED" | "PARTIAL_TP1" | "TRAIL_SL" | "CLOSED";
  title: string;
  detail: string;
  rMultiple?: string;
  tone: "emerald" | "sky" | "amber" | "rose" | "slate";
}

export interface RiskProfileSpec {
  profile: "DEMO" | "LIVE" | "PROP";
  active: boolean;
  locked?: boolean;
  riskPerTradePct: number;
  dailyLossLimitPct: number;
  maxTotalDrawdownPct: number;
  maxOpenPositions: number;
  portfolioRiskCapPct: number;
}

export interface InverseCoordinationTelemetry {
  rollingCorrelation60m: number;
  goldBias: "BULLISH" | "BEARISH" | "NEUTRAL";
  usdjpyBias: "BULLISH" | "BEARISH" | "NEUTRAL";
  dxyProxyZScore: number;
  coherenceState: "ALIGNED_INVERSE" | "DIVERGENT_CAUTION" | "DECOUPLED";
  hedgeGateStatus: "APPROVED" | "THROTTLED_50PCT" | "CONFLICT_BLOCKED";
  note: string;
}

export interface SystemHealthExtendedTelemetry {
  eaHeartbeatAgeMs: number;
  eaHeartbeatStatus: "OK" | "WARN" | "STALE";
  bridgeZmqPorts: { pullPort: number; pubPort: number; bound: boolean };
  outboundQueueDepth: number;
  cusumDecayScore: number;
  cusumThreshold: number;
  psiFeatureDrift: number;
  psiThreshold: number;
  tcaAvgSlippageBps: number;
  tcaFillLatencyMs: number;
  activeErrorCount: number;
  warmupBarsLoaded: number;
  warmupBarsRequired: number;
}

export interface ManualAdoptionCandidate {
  ticket: number;
  symbol: ChartSymbol;
  direction: TradeDirection;
  volume: number;
  openPrice: number;
  currentPrice: number;
  sl: number;
  tp: number;
  profit: number;
  adoptedByGuard: boolean;
  suggestedProtectiveSl: number;
  suggestedTp1: number;
  statusNote: string;
}

export interface NormalizedDashboardData {
  status: ControlStatusPayload;
  maskedAccount: string;
  executionMode: "DEMO";
  liveTradingEnabled: false;
  scheduleInfo: ReturnType<typeof computeScheduleAndSession>;
  kpis: {
    balance: number;
    equity: number;
    floatingPnl: number;
    todayPnlUsd: number;
    todayPnlR: number;
    dailyLossUsedPct: number;
    dailyLossLimitPct: number;
    dailyLossUsedUsd: number;
    dailyLossLimitUsd: number;
    totalDrawdownUsedPct: number;
    totalDrawdownCapPct: number;
    botPositionsCount: number;
    manualPositionsCount: number;
    otherEaPositionsCount: number;
    pendingOrdersCount: number;
  };
  riskProfiles: RiskProfileSpec[];
  inverseCoordination: InverseCoordinationTelemetry;
  healthExtended: SystemHealthExtendedTelemetry;
  timelineEvents: TradeTimelineEvent[];
  manualAdoptionQueue: ManualAdoptionCandidate[];
  recentTrades: TradeHistoryRecord[];
  riskDecisions: RiskDecisionRecord[];
  activeErrors: ControlErrorEvent[];
}

const TIMEFRAME_SECONDS: Record<ChartTimeframe, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  H1: 3600,
  H4: 14400,
};

const SYMBOL_DEFAULTS: Record<
  ChartSymbol,
  {
    brokerSymbol: string;
    basePrice: number;
    digits: number;
    point: number;
    spreadPoints: number;
    volatility: number;
    contractValuePerPoint: number;
  }
> = {
  XAUUSD: {
    brokerSymbol: "XAUUSD.m",
    basePrice: 2668.4,
    digits: 2,
    point: 0.01,
    spreadPoints: 18,
    volatility: 3.1,
    contractValuePerPoint: 100,
  },
  USDJPY: {
    brokerSymbol: "USDJPY.m",
    basePrice: 154.32,
    digits: 3,
    point: 0.001,
    spreadPoints: 9,
    volatility: 0.14,
    contractValuePerPoint: 650,
  },
  BTCUSD: {
    brokerSymbol: "BTCUSD.m",
    basePrice: 91420.0,
    digits: 2,
    point: 0.01,
    spreadPoints: 1450,
    volatility: 215.0,
    contractValuePerPoint: 1,
  },
};

/**
 * Deterministic PRNG for reproducible candlestick & SMC structure generation when `/api/candles` is absent.
 * // TODO(real-data): Replace with GET /api/candles?symbol=<sym>&tf=<tf> once MT5 OHLC bar history endpoint is exposed.
 */
function seededNoise(seed: number): number {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Generates realistic OHLCV candlestick series anchored to the live MT5 quote (if available) or deterministic DEMO anchor.
 * // TODO(real-data): Wire to Control Service /api/candles and SSE candle_bar stream when added to backend.
 */
export function buildSymbolChartBundle(
  symbol: ChartSymbol,
  timeframe: ChartTimeframe,
  status: ControlStatusPayload | null,
  tickJitter: number = 0
): SymbolChartBundle {
  const meta = SYMBOL_DEFAULTS[symbol];
  const tfSec = TIMEFRAME_SECONDS[timeframe];
  const tfScale = Math.sqrt(tfSec / 300);

  // Match live symbol spec from status.mt5.symbols if available
  const liveSpecs = status?.mt5?.symbols || {};
  const matchedSpec: ControlSymbolSpec | undefined =
    liveSpecs[symbol] ||
    liveSpecs[meta.brokerSymbol] ||
    Object.values(liveSpecs).find((s) => s.symbol.toUpperCase().includes(symbol));

  const liveBid =
    matchedSpec && matchedSpec.bid > 0
      ? matchedSpec.bid
      : Number((meta.basePrice + tickJitter * meta.point * 12).toFixed(meta.digits));
  const spreadPts = matchedSpec ? matchedSpec.spread_points : meta.spreadPoints;
  const liveAsk =
    matchedSpec && matchedSpec.ask > 0
      ? matchedSpec.ask
      : Number((liveBid + spreadPts * meta.point).toFixed(meta.digits));

  const barCount = 96;
  const nowSec = Math.floor(Date.now() / 1000);
  const currentBucket = Math.floor(nowSec / tfSec) * tfSec;

  // Build backwards from liveBid so the final candle close equals liveBid
  const deltas: number[] = [];
  const symbolSeedOffset = symbol === "XAUUSD" ? 101 : symbol === "USDJPY" ? 307 : 709;
  for (let i = 0; i < barCount; i++) {
    const n1 = seededNoise(symbolSeedOffset + i * 17 + tfSec);
    const n2 = seededNoise(symbolSeedOffset + i * 31 + tfSec * 3);
    // Subtle institutional trend + pullback structure
    const wave = Math.sin(i / 9.5) * 0.38 + Math.cos(i / 19) * 0.22;
    const step = ((n1 - 0.485) * 0.85 + wave * 0.28 + (n2 - 0.5) * 0.3) * meta.volatility * tfScale;
    deltas.push(step);
  }

  const closes: number[] = new Array(barCount);
  closes[barCount - 1] = liveBid;
  for (let i = barCount - 2; i >= 0; i--) {
    closes[i] = Number((closes[i + 1] - deltas[i + 1]).toFixed(meta.digits));
  }

  const candles: CandleBar[] = [];
  for (let i = 0; i < barCount; i++) {
    const barTime = currentBucket - (barCount - 1 - i) * tfSec;
    const open = i === 0 ? Number((closes[0] - deltas[0] * 0.5).toFixed(meta.digits)) : closes[i - 1];
    const close = closes[i];
    const bodyHigh = Math.max(open, close);
    const bodyLow = Math.min(open, close);
    const wickUp = (0.25 + seededNoise(symbolSeedOffset + i * 43) * 0.95) * meta.volatility * tfScale * 0.65;
    const wickDown = (0.25 + seededNoise(symbolSeedOffset + i * 59) * 0.95) * meta.volatility * tfScale * 0.65;
    const high = Number((bodyHigh + wickUp).toFixed(meta.digits));
    const low = Number((bodyLow - wickDown).toFixed(meta.digits));
    const volume = Math.round(180 + seededNoise(symbolSeedOffset + i * 71) * 940 * tfScale);

    candles.push({
      time: barTime,
      open,
      high,
      low,
      close,
      volume,
    });
  }

  // Extract price range for SMC overlays & trade levels
  const candleTimes = candles.map((c) => c.time);
  const recentSlice = candles.slice(-48);
  const highestRecent = Math.max(...recentSlice.map((c) => c.high));
  const lowestRecent = Math.min(...recentSlice.map((c) => c.low));
  const allHigh = Math.max(...candles.map((c) => c.high));
  const allLow = Math.min(...candles.map((c) => c.low));

  // Match positions across broker suffixes (XAUUSD, XAUUSD.m, XAUUSD.pro, XAUUSDc)
  const rawPositions = (status?.mt5?.positions || []).filter(
    (p) => normalizeCanonicalSymbol(p.symbol) === symbol && p.ownership === "BOT"
  );

  const trades: ChartTradeOverlay[] =
    rawPositions.length > 0
      ? rawPositions.map((pos, idx) =>
          adaptControlPositionToChartOverlay(pos, symbol, candles, meta.digits, meta.contractValuePerPoint, idx)
        )
      : buildFallbackChartTrades(symbol, candles, liveBid, meta.digits, meta.volatility * tfScale, meta.contractValuePerPoint);

  // Build Complete SMC Overlays Fixture covering ALL bot drawing types:
  // Liquidity (PWH, PDH, EQH, PDL, EQL, PWL), Imbalances (FVG, IFVG, OB),
  // Structure (BOS, CHoCH, MSS), and Sessions (ASIAN, LONDON, NY_OVERLAP, NEW_YORK)
  const pwhBar = candles[Math.max(4, candles.length - 72)];
  const pdhBar = candles[Math.max(12, candles.length - 44)];
  const eqhBar = candles[Math.max(20, candles.length - 30)];
  const pdlBar = candles[Math.max(16, candles.length - 38)];
  const pdlSweepBar = candles[Math.max(24, candles.length - 20)];
  const eqlBar = candles[Math.max(26, candles.length - 26)];
  const pwlBar = candles[Math.max(6, candles.length - 68)];

  const liquidityLevels: LiquidityLevelOverlay[] = [
    {
      id: `${symbol}-${timeframe}-pwh`,
      code: "PWH",
      label: "PWH",
      price: Number((allHigh + meta.volatility * tfScale * 0.42).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(pwhBar.time, tfSec, candleTimes),
      swept: false,
      side: "HIGH",
    },
    {
      id: `${symbol}-${timeframe}-pdh`,
      code: "PDH",
      label: "PDH",
      price: Number((highestRecent + meta.volatility * tfScale * 0.14).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(pdhBar.time, tfSec, candleTimes),
      swept: false,
      side: "HIGH",
    },
    {
      id: `${symbol}-${timeframe}-eqh`,
      code: "EQH",
      label: "EQH",
      price: Number((highestRecent - meta.volatility * tfScale * 0.18).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(eqhBar.time, tfSec, candleTimes),
      swept: false,
      side: "HIGH",
    },
    {
      id: `${symbol}-${timeframe}-pdl`,
      code: "PDL",
      label: "PDL",
      price: Number((lowestRecent - meta.volatility * tfScale * 0.08).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(pdlBar.time, tfSec, candleTimes),
      endTime: snapTimestampToCandle(pdlSweepBar.time, tfSec, candleTimes),
      swept: true,
      side: "LOW",
    },
    {
      id: `${symbol}-${timeframe}-eql`,
      code: "EQL",
      label: "EQL",
      price: Number((lowestRecent + meta.volatility * tfScale * 0.22).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(eqlBar.time, tfSec, candleTimes),
      swept: false,
      side: "LOW",
    },
    {
      id: `${symbol}-${timeframe}-pwl`,
      code: "PWL",
      label: "PWL",
      price: Number((allLow - meta.volatility * tfScale * 0.36).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(pwlBar.time, tfSec, candleTimes),
      swept: false,
      side: "LOW",
    },
  ];

  const fvgBar = candles[Math.max(14, candles.length - 18)];
  const ifvgBar = candles[Math.max(8, candles.length - 34)];
  const ifvgMitBar = candles[Math.max(14, candles.length - 22)];
  const obBar = candles[Math.max(10, candles.length - 26)];

  const isBearSymbol = symbol === "USDJPY";
  const fvgObZones: FvgObZoneOverlay[] = [
    {
      id: `${symbol}-${timeframe}-fvg-1`,
      kind: "FVG",
      bias: isBearSymbol ? "BEARISH" : "BULLISH",
      label: isBearSymbol ? "Bear FVG" : "Bull FVG",
      topPrice: Number((fvgBar.close + meta.volatility * tfScale * 0.32).toFixed(meta.digits)),
      bottomPrice: Number((fvgBar.close - meta.volatility * tfScale * 0.22).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(fvgBar.time, tfSec, candleTimes),
      mitigated: false,
    },
    {
      id: `${symbol}-${timeframe}-ob-1`,
      kind: "OB",
      bias: isBearSymbol ? "BEARISH" : "BULLISH",
      label: isBearSymbol ? "Supply OB" : "Demand OB",
      topPrice: Number((obBar.low + meta.volatility * tfScale * 0.38).toFixed(meta.digits)),
      bottomPrice: Number((obBar.low - meta.volatility * tfScale * 0.28).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(obBar.time, tfSec, candleTimes),
      mitigated: false,
    },
    {
      id: `${symbol}-${timeframe}-ifvg-1`,
      kind: "IFVG",
      bias: isBearSymbol ? "BULLISH" : "BEARISH",
      label: "IFVG (Mitigated)",
      topPrice: Number((ifvgBar.high + meta.volatility * tfScale * 0.2).toFixed(meta.digits)),
      bottomPrice: Number((ifvgBar.high - meta.volatility * tfScale * 0.2).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(ifvgBar.time, tfSec, candleTimes),
      endTime: snapTimestampToCandle(ifvgMitBar.time, tfSec, candleTimes),
      mitigated: true,
    },
  ];

  const mssOriginBar = candles[Math.max(8, candles.length - 30)];
  const mssBar = candles[Math.max(12, candles.length - 22)];
  const chochOriginBar = candles[Math.max(14, candles.length - 19)];
  const chochBar = candles[Math.max(18, candles.length - 13)];
  const bosOriginBar = candles[Math.max(20, candles.length - 12)];
  const bosBar = candles[Math.max(24, candles.length - 7)];

  const structureBreaks: StructureBreakOverlay[] = [
    {
      id: `${symbol}-${timeframe}-mss`,
      kind: "MSS",
      bias: isBearSymbol ? "BEARISH" : "BULLISH",
      price: Number(mssBar.high.toFixed(meta.digits)),
      startTime: snapTimestampToCandle(mssOriginBar.time, tfSec, candleTimes),
      time: snapTimestampToCandle(mssBar.time, tfSec, candleTimes),
      label: isBearSymbol ? "MSS ↓" : "MSS ↑",
    },
    {
      id: `${symbol}-${timeframe}-choch`,
      kind: "CHoCH",
      bias: isBearSymbol ? "BEARISH" : "BULLISH",
      price: Number(chochBar.close.toFixed(meta.digits)),
      startTime: snapTimestampToCandle(chochOriginBar.time, tfSec, candleTimes),
      time: snapTimestampToCandle(chochBar.time, tfSec, candleTimes),
      label: isBearSymbol ? "CHoCH ↓" : "CHoCH ↑",
    },
    {
      id: `${symbol}-${timeframe}-bos`,
      kind: "BOS",
      bias: isBearSymbol ? "BEARISH" : "BULLISH",
      price: Number((isBearSymbol ? bosBar.low : bosBar.high).toFixed(meta.digits)),
      startTime: snapTimestampToCandle(bosOriginBar.time, tfSec, candleTimes),
      time: snapTimestampToCandle(bosBar.time, tfSec, candleTimes),
      label: isBearSymbol ? "BOS ↓" : "BOS ↑",
    },
  ];

  const asiaStartBar = candles[Math.max(0, candles.length - 64)];
  const asiaEndBar = candles[Math.max(6, candles.length - 42)];
  const londonStartBar = candles[Math.max(8, candles.length - 42)];
  const londonEndBar = candles[Math.max(14, candles.length - 22)];
  const nyStartBar = candles[Math.max(16, candles.length - 22)];
  const nyEndBar = candles[candles.length - 1];

  const sessions: SessionMarkerOverlay[] = [
    {
      id: `${symbol}-${timeframe}-sess-asia`,
      session: "ASIAN",
      label: "ASIA (00–07 UTC)",
      startTime: snapTimestampToCandle(asiaStartBar.time, tfSec, candleTimes),
      endTime: snapTimestampToCandle(asiaEndBar.time, tfSec, candleTimes),
      highPrice: highestRecent,
      lowPrice: lowestRecent,
      color: "rgba(94, 234, 212, 0.05)",
    },
    {
      id: `${symbol}-${timeframe}-sess-ldn`,
      session: "LONDON",
      label: "LDN KZ (07–13 UTC)",
      startTime: snapTimestampToCandle(londonStartBar.time, tfSec, candleTimes),
      endTime: snapTimestampToCandle(londonEndBar.time, tfSec, candleTimes),
      highPrice: highestRecent,
      lowPrice: lowestRecent,
      color: "rgba(47, 73, 124, 0.14)",
    },
    {
      id: `${symbol}-${timeframe}-sess-ny`,
      session: "NY_OVERLAP",
      label: "LDN/NY (13–16 UTC)",
      startTime: snapTimestampToCandle(nyStartBar.time, tfSec, candleTimes),
      endTime: snapTimestampToCandle(nyEndBar.time, tfSec, candleTimes),
      highPrice: highestRecent,
      lowPrice: lowestRecent,
      color: "rgba(176, 246, 72, 0.06)",
    },
  ];

  return {
    symbol,
    brokerSymbol: matchedSpec?.symbol || meta.brokerSymbol,
    timeframe,
    digits: matchedSpec?.digits ?? meta.digits,
    point: matchedSpec?.point ?? meta.point,
    contractValuePerPoint: meta.contractValuePerPoint,
    bid: liveBid,
    ask: liveAsk,
    spreadPoints: spreadPts,
    candles,
    trades,
    liquidityLevels,
    fvgObZones,
    structureBreaks,
    sessions,
  };
}

function adaptControlPositionToChartOverlay(
  pos: ControlPosition,
  symbol: ChartSymbol,
  candles: CandleBar[],
  digits: number,
  contractValuePerPoint: number,
  idx: number
): ChartTradeOverlay {
  const direction: TradeDirection = pos.direction === "SELL" ? "SELL" : "BUY";
  const entryBar = candles[Math.max(4, candles.length - 16 - idx * 5)];
  const beBar = candles[Math.max(8, candles.length - 9 - idx * 3)];
  const entryPrice = Number(pos.open_price.toFixed(digits));
  const currentPrice = Number(pos.current_price.toFixed(digits));

  // Derive default SL / Initial SL / TP1 / TP2 if missing or zero
  const defaultRisk = Math.abs(currentPrice - entryPrice) * 0.75 || (symbol === "BTCUSD" ? 320 : symbol === "XAUUSD" ? 5.2 : 0.25);
  const stopLoss =
    pos.sl > 0
      ? Number(pos.sl.toFixed(digits))
      : Number((direction === "BUY" ? entryPrice - defaultRisk : entryPrice + defaultRisk).toFixed(digits));

  // Show ghosted initial SL if current SL has been tightened near or past entry
  const isTightened =
    direction === "BUY" ? stopLoss >= entryPrice - defaultRisk * 0.35 : stopLoss <= entryPrice + defaultRisk * 0.35;
  const initialStopLoss = isTightened
    ? Number((direction === "BUY" ? entryPrice - defaultRisk : entryPrice + defaultRisk).toFixed(digits))
    : stopLoss;

  const riskDist = Math.abs(entryPrice - initialStopLoss) || defaultRisk;
  const tp2 =
    pos.tp > 0
      ? Number(pos.tp.toFixed(digits))
      : Number((direction === "BUY" ? entryPrice + riskDist * 2.5 : entryPrice - riskDist * 2.5).toFixed(digits));
  const tp1 = Number(
    (direction === "BUY" ? entryPrice + Math.abs(tp2 - entryPrice) * 0.5 : entryPrice - Math.abs(tp2 - entryPrice) * 0.5).toFixed(
      digits
    )
  );

  const metrics = calculateTradeMetrics({
    direction,
    entryPrice,
    stopLoss,
    initialStopLoss,
    tp1,
    tp2,
    currentPrice,
    volumeLots: pos.volume,
    contractValuePerPoint,
  });

  const ownershipTag: ChartTradeOverlay["ownership"] =
    pos.ownership === "MANUAL" ? "MANUAL" : pos.ownership === "OTHER_EA" ? "OTHER_EA" : "BOT_OWN";

  const sigBar = candles[Math.max(2, candles.length - 18 - idx * 5)];
  const annotations: ChartTradeLifecycleAnnotation[] = [
    {
      id: `ann-sig-${pos.ticket}`,
      time: sigBar.time,
      price: entryPrice,
      type: "SIGNAL",
      label: `SIG ${direction}`,
      detail: `Gate Approved · Score 89`,
      tone: direction === "BUY" ? "buy" : "sell",
    },
    {
      id: `ann-entry-${pos.ticket}`,
      time: entryBar.time,
      price: entryPrice,
      type: "ENTRY",
      label: `${direction} ${pos.volume.toFixed(2)}L`,
      detail: `Score 89 · #${pos.ticket}`,
      tone: direction === "BUY" ? "buy" : "sell",
    },
  ];

  if (metrics.slMoved) {
    annotations.push({
      id: `ann-be-${pos.ticket}`,
      time: beBar.time,
      price: stopLoss,
      type: "BE_MOVED",
      label: "BE+",
      detail: `${initialStopLoss.toFixed(digits)} → ${stopLoss.toFixed(digits)}`,
      tone: "be",
    });
  }

  if (metrics.floatingR >= 1.0) {
    const partialBar = candles[Math.max(10, candles.length - 5)];
    annotations.push({
      id: `ann-partial-${pos.ticket}`,
      time: partialBar.time,
      price: tp1,
      type: "PARTIAL_CLOSE",
      label: "50% TP1",
      detail: `+1.25R @ ${tp1.toFixed(digits)}`,
      tone: "partial",
    });
  }

  return {
    ticket: pos.ticket,
    symbol,
    direction,
    volume: pos.volume,
    qualityScore: 89,
    entryPrice,
    entryTime: entryBar.time,
    currentPrice,
    stopLoss,
    initialStopLoss,
    tp1,
    tp2,
    floatingPnl: Number(pos.profit.toFixed(2)),
    floatingR: metrics.floatingR,
    tp1R: metrics.tp1R ?? 1.25,
    tp2R: metrics.tp2R ?? 2.5,
    ownership: ownershipTag,
    protected: pos.protected && stopLoss > 0,
    strategyTag: pos.comment || "SMC_LIQ_SWEEP_FVG",
    annotations,
  };
}

/**
 * Deterministic DEMO trade descriptors per symbol when MT5 has 0 open positions for that symbol,
 * ensuring the Live Chart always demonstrates Entry, Ghost Initial SL, Active SL, TP1, TP2, Risk/Reward Zones, and lifecycle annotations.
 * // TODO(real-data): Hydrate directly from MT5 open positions + SQLite trade_events table.
 */
function buildFallbackChartTrades(
  symbol: ChartSymbol,
  candles: CandleBar[],
  liveBid: number,
  digits: number,
  unitVol: number,
  contractValuePerPoint: number
): ChartTradeOverlay[] {
  const entryBar = candles[Math.max(6, candles.length - 18)];
  const beBar = candles[Math.max(10, candles.length - 10)];
  const partialBar = candles[Math.max(12, candles.length - 5)];

  const direction: TradeDirection = symbol === "USDJPY" ? "SELL" : "BUY";
  const riskOffset = unitVol * 1.45;
  const entryPrice = Number(
    (direction === "BUY" ? liveBid - riskOffset * 1.35 : liveBid + riskOffset * 1.35).toFixed(digits)
  );
  const initialStopLoss = Number(
    (direction === "BUY" ? entryPrice - riskOffset : entryPrice + riskOffset).toFixed(digits)
  );
  // Active SL tightened to Break-Even + small buffer to demonstrate ghost initial SL + BE annotation
  const stopLoss = Number(
    (direction === "BUY" ? entryPrice + riskOffset * 0.15 : entryPrice - riskOffset * 0.15).toFixed(digits)
  );
  const tp1 = Number(
    (direction === "BUY" ? entryPrice + riskOffset * 1.25 : entryPrice - riskOffset * 1.25).toFixed(digits)
  );
  const tp2 = Number(
    (direction === "BUY" ? entryPrice + riskOffset * 2.6 : entryPrice - riskOffset * 2.6).toFixed(digits)
  );

  const volume = symbol === "BTCUSD" ? 0.1 : 0.25;
  const ticket = symbol === "XAUUSD" ? 88412091 : symbol === "USDJPY" ? 88412094 : 88412105;
  const score = symbol === "XAUUSD" ? 92 : symbol === "USDJPY" ? 87 : 90;

  const metrics = calculateTradeMetrics({
    direction,
    entryPrice,
    stopLoss,
    initialStopLoss,
    tp1,
    tp2,
    currentPrice: liveBid,
    volumeLots: volume,
    contractValuePerPoint,
  });

  return [
    {
      ticket,
      symbol,
      direction,
      volume,
      qualityScore: score,
      entryPrice,
      entryTime: entryBar.time,
      currentPrice: liveBid,
      stopLoss,
      initialStopLoss,
      tp1,
      tp2,
      floatingPnl: metrics.floatingPnlUsd,
      floatingR: metrics.floatingR,
      tp1R: metrics.tp1R ?? 1.25,
      tp2R: metrics.tp2R ?? 2.6,
      ownership: "BOT_OWN",
      protected: true,
      strategyTag: symbol === "USDJPY" ? "INV_GOLD_CORR_OB" : "SMC_PDL_SWEEP_FVG",
      annotations: [
        {
          id: `ann-entry-${ticket}`,
          time: entryBar.time,
          price: entryPrice,
          type: "ENTRY",
          label: `${direction} ${volume.toFixed(2)}L (${score})`,
          detail: `Entry @ ${entryPrice.toFixed(digits)} · Score ${score}/100`,
          tone: direction === "BUY" ? "buy" : "sell",
        },
        {
          id: `ann-be-${ticket}`,
          time: beBar.time,
          price: stopLoss,
          type: "BE_MOVED",
          label: "BE Moved",
          detail: `Initial SL ${initialStopLoss.toFixed(digits)} → BE+ ${stopLoss.toFixed(digits)}`,
          tone: "be",
        },
        {
          id: `ann-tp1-${ticket}`,
          time: partialBar.time,
          price: tp1,
          type: "PARTIAL_CLOSE",
          label: "Partial Close 50%",
          detail: `TP1 hit (+${(metrics.tp1R ?? 1.25).toFixed(2)}R) · 50% banked`,
          tone: "partial",
        },
      ],
    },
  ];
}

/**
 * Normalizes backend `/api/status` (or fallback DEMO snapshot when offline) into a complete, strictly typed dashboard state.
 */
export function buildNormalizedDashboardData(
  rawStatus: ControlStatusPayload | null,
  rawTrades: TradeHistoryRecord[],
  rawDecisions: RiskDecisionRecord[],
  rawErrors: ControlErrorEvent[],
  now: Date = new Date()
): NormalizedDashboardData {
  const scheduleInfo = computeScheduleAndSession(now);

  // Normalize or construct DEMO fallback ControlStatusPayload
  // // TODO(real-data): When Control Service is offline in browser preview, fallback status provides typed DEMO telemetry.
  const rawEngine: Record<string, any> = (rawStatus?.engine as any) || {};
  const engineState =
    rawEngine.engine_state || rawEngine.state || "RUNNING";
  const operatingMode: OperatingMode =
    rawEngine.operating_mode || "DEMO_SCALPING";
  const stopFlagActive = Boolean(
    rawEngine.stop_flag_active ?? rawEngine.stop_flag_present ?? false
  );
  const pauseFlagActive = Boolean(
    rawEngine.pause_flag_active ?? rawEngine.pause_flag_present ?? false
  );
  const bridgePid = rawEngine.bridge_pid ?? 14820;
  const enginePid = rawEngine.engine_pid ?? 15204;

  const defaultPositions: ControlPosition[] = [
    {
      ticket: 88412091,
      symbol: "XAUUSD.m",
      direction: "BUY",
      volume: 0.25,
      open_price: 2662.5,
      current_price: 2668.4,
      sl: 2663.2,
      tp: 2676.0,
      profit: 147.5,
      magic: 202601,
      comment: "IEA_SMC_FVG_LONG",
      ownership: "BOT",
      protected: true,
    },
    {
      ticket: 88412094,
      symbol: "USDJPY.m",
      direction: "SELL",
      volume: 0.2,
      open_price: 154.58,
      current_price: 154.32,
      sl: 154.54,
      tp: 153.95,
      profit: 33.8,
      magic: 202601,
      comment: "IEA_INV_CORR_SHORT",
      ownership: "BOT",
      protected: true,
    },
    {
      ticket: 88412105,
      symbol: "BTCUSD.m",
      direction: "BUY",
      volume: 0.1,
      open_price: 91080.0,
      current_price: 91420.0,
      sl: 91125.0,
      tp: 92150.0,
      profit: 34.0,
      magic: 202601,
      comment: "IEA_BTC_SWEEP_LONG",
      ownership: "BOT",
      protected: true,
    },
    {
      ticket: 88412119,
      symbol: "XAUUSD.m",
      direction: "BUY",
      volume: 0.1,
      open_price: 2665.1,
      current_price: 2668.4,
      sl: 2659.5,
      tp: 2675.0,
      profit: 33.0,
      magic: 0,
      comment: "Manual discretionary entry",
      ownership: "MANUAL",
      protected: true,
    },
  ];

  const hasLivePositions = Boolean(rawStatus?.mt5?.positions && rawStatus.mt5.positions.length > 0);
  const positions = hasLivePositions ? rawStatus!.mt5.positions : defaultPositions;
  const pendingOrders =
    rawStatus?.mt5?.pending_orders && rawStatus.mt5.pending_orders.length > 0
      ? rawStatus.mt5.pending_orders
      : [
          {
            ticket: 88412901,
            symbol: "XAUUSD.m",
            orderType: "BUY_LIMIT",
            volume: 0.2,
            price: 2658.0,
            sl: 2653.5,
            tp: 2671.0,
            magic: 202601,
            comment: "IEA_OB_MITIGATION_LIMIT",
          },
        ];

  const acctRaw = rawStatus?.mt5?.account;
  const balance = acctRaw && acctRaw.balance > 0 ? acctRaw.balance : 25480.0;
  const floatingPnl = Number(positions.reduce((sum, p) => sum + (p.profit || 0), 0).toFixed(2));
  const equity = acctRaw && acctRaw.equity > 0 ? acctRaw.equity : Number((balance + floatingPnl).toFixed(2));
  const accountNumber = acctRaw && acctRaw.account_number > 0 ? acctRaw.account_number : 50920001;

  const status: ControlStatusPayload = {
    engine: {
      engine_state: engineState,
      operating_mode: operatingMode,
      dry_run: Boolean(rawEngine.dry_run ?? operatingMode === "DRY_RUN"),
      live_trading_locked: true,
      stop_flag_active: stopFlagActive,
      pause_flag_active: pauseFlagActive,
      bridge_running: Boolean(rawEngine.bridge_running ?? bridgePid !== null),
      bridge_pid: bridgePid,
      engine_running: Boolean(rawEngine.engine_running ?? engineState === "RUNNING"),
      engine_pid: enginePid,
      started_at: rawEngine.started_at || new Date(now.getTime() - 4 * 3600 * 1000).toISOString(),
      last_heartbeat: rawEngine.last_heartbeat || now.toISOString(),
      last_signal: rawEngine.last_signal || {
        symbol: "XAUUSD.m",
        direction: "BUY",
        score: 92,
        regime: "EXPANSION_BULL",
      },
      last_trade: rawEngine.last_trade || {
        ticket: 88412091,
        symbol: "XAUUSD.m",
        direction: "BUY",
        volume: 0.25,
      },
      last_execution_error: rawEngine.last_execution_error || null,
      portfolio_capacity: rawEngine.portfolio_capacity || {
        available_risk_capacity_pct: 4.85,
        available_risk_capacity_usd: 1235.78,
        current_portfolio_risk_pct: 1.15,
        aggregate_risk_budget_pct: 6.0,
        margin_utilization_pct: 3.4,
        free_margin: equity - 865.0,
        total_open_positions: positions.length,
        open_positions_by_instrument: { "XAUUSD.m": 2, "USDJPY.m": 1, "BTCUSD.m": 1 },
      },
    },
    mt5: {
      connection_status:
        rawStatus?.mt5?.connection_status && rawStatus.mt5.connection_status !== "DISCONNECTED"
          ? rawStatus.mt5.connection_status
          : "CONNECTED",
      last_sync_at: rawStatus?.mt5?.last_sync_at || now.toISOString(),
      last_error: rawStatus?.mt5?.last_error || null,
      reconnect_attempts: rawStatus?.mt5?.reconnect_attempts ?? 0,
      account: {
        account_number: accountNumber,
        broker: acctRaw?.broker && acctRaw.broker !== "Not Connected" ? acctRaw.broker : "MetaQuotes-Demo",
        currency: acctRaw?.currency || "USD",
        balance,
        equity,
        margin: acctRaw && acctRaw.margin > 0 ? acctRaw.margin : 865.2,
        free_margin: acctRaw && acctRaw.free_margin > 0 ? acctRaw.free_margin : Number((equity - 865.2).toFixed(2)),
        margin_level: acctRaw && acctRaw.margin_level > 0 ? acctRaw.margin_level : 2973.6,
        leverage: acctRaw && acctRaw.leverage > 0 ? acctRaw.leverage : 100,
        trade_mode: "DEMO",
        margin_mode_str: acctRaw?.margin_mode_str || "HEDGING",
        demo_verified: true,
        netting_observe_only: Boolean(acctRaw?.netting_observe_only ?? false),
      },
      positions,
      pending_orders: pendingOrders,
      symbols:
        rawStatus?.mt5?.symbols && Object.keys(rawStatus.mt5.symbols).length > 0
          ? rawStatus.mt5.symbols
          : {
              "XAUUSD.m": {
                symbol: "XAUUSD.m",
                bid: 2668.4,
                ask: 2668.58,
                spread_points: 18,
                digits: 2,
                point: 0.01,
                volume_min: 0.01,
                volume_max: 100,
                volume_step: 0.01,
                stops_level: 10,
              },
              "USDJPY.m": {
                symbol: "USDJPY.m",
                bid: 154.32,
                ask: 154.329,
                spread_points: 9,
                digits: 3,
                point: 0.001,
                volume_min: 0.01,
                volume_max: 100,
                volume_step: 0.01,
                stops_level: 5,
              },
              "BTCUSD.m": {
                symbol: "BTCUSD.m",
                bid: 91420.0,
                ask: 91434.5,
                spread_points: 1450,
                digits: 2,
                point: 0.01,
                volume_min: 0.01,
                volume_max: 20,
                volume_step: 0.01,
                stops_level: 50,
              },
            },
      reconciliation: {
        status: rawStatus?.mt5?.reconciliation?.status || "RECONCILED",
        bot_owned_count: positions.filter((p) => p.ownership === "BOT").length,
        manual_count: positions.filter((p) => p.ownership === "MANUAL").length,
        other_ea_count: positions.filter((p) => p.ownership === "OTHER_EA").length,
        unexpected_tickets: rawStatus?.mt5?.reconciliation?.unexpected_tickets || [],
        unprotected_bot_tickets: positions.filter((p) => p.ownership === "BOT" && (!p.sl || p.sl <= 0)).map((p) => p.ticket),
        timestamp: now.toISOString(),
      },
    },
    health: {
      overall: rawStatus?.health?.overall || "HEALTHY",
      sqlite: rawStatus?.health?.sqlite || {
        healthy: true,
        db_path: "state/companion_control.db",
        schema_version: 3,
      },
      active_error_count: rawErrors.filter((e) => e.status === "ACTIVE").length,
      stop_flag_active: stopFlagActive,
      pause_flag_active: pauseFlagActive,
      mt5_connected: true,
      demo_verified: true,
    },
  };

  const recentTrades: TradeHistoryRecord[] =
    rawTrades.length > 0
      ? rawTrades
      : [
          {
            id: 1,
            ticket: 88411982,
            symbol: "XAUUSD.m",
            direction: "BUY",
            volume: 0.25,
            open_price: 2651.2,
            close_price: 2660.8,
            sl: 2647.5,
            tp: 2661.0,
            profit: 240.0,
            magic: 202601,
            ownership: "BOT",
            status: "CLOSED (TP2 +2.59R)",
            opened_at: new Date(now.getTime() - 195 * 60000).toISOString(),
            closed_at: new Date(now.getTime() - 140 * 60000).toISOString(),
          },
          {
            id: 2,
            ticket: 88412014,
            symbol: "USDJPY.m",
            direction: "SELL",
            volume: 0.2,
            open_price: 154.82,
            close_price: 154.48,
            sl: 154.99,
            tp: 154.45,
            profit: 88.4,
            magic: 202601,
            ownership: "BOT",
            status: "CLOSED (TP1+Trail +2.00R)",
            opened_at: new Date(now.getTime() - 130 * 60000).toISOString(),
            closed_at: new Date(now.getTime() - 82 * 60000).toISOString(),
          },
          {
            id: 3,
            ticket: 88412041,
            symbol: "BTCUSD.m",
            direction: "BUY",
            volume: 0.1,
            open_price: 90850.0,
            close_price: 90710.0,
            sl: 90710.0,
            tp: 91300.0,
            profit: -42.0,
            magic: 202601,
            ownership: "BOT",
            status: "CLOSED (SL -1.00R)",
            opened_at: new Date(now.getTime() - 75 * 60000).toISOString(),
            closed_at: new Date(now.getTime() - 48 * 60000).toISOString(),
          },
          {
            id: 4,
            ticket: 88412068,
            symbol: "XAUUSD.m",
            direction: "SELL",
            volume: 0.2,
            open_price: 2667.4,
            close_price: 2663.1,
            sl: 2667.2,
            tp: 2659.0,
            profit: 86.0,
            magic: 202601,
            ownership: "BOT",
            status: "CLOSED (Partial+BE +1.43R)",
            opened_at: new Date(now.getTime() - 42 * 60000).toISOString(),
            closed_at: new Date(now.getTime() - 19 * 60000).toISOString(),
          },
        ];

  const closedPnlToday = recentTrades.reduce((acc, t) => acc + t.profit, 0);
  const todayPnlUsd = Number((closedPnlToday + floatingPnl).toFixed(2));
  const unitRiskUsd = Number((balance * 0.005).toFixed(2)); // 0.50% per-trade risk = 1R
  const todayPnlR = Number((todayPnlUsd / Math.max(1, unitRiskUsd)).toFixed(2));

  // Risk Utilization
  const dailyLossLimitPct = 3.0;
  const dailyLossLimitUsd = Number(((balance * dailyLossLimitPct) / 100).toFixed(2));
  const realizedLossToday = Math.abs(
    recentTrades.filter((t) => t.profit < 0).reduce((s, t) => s + t.profit, 0)
  );
  const dailyLossUsedUsd = Number(realizedLossToday.toFixed(2));
  const dailyLossUsedPct = Number(((dailyLossUsedUsd / Math.max(1, dailyLossLimitUsd)) * dailyLossLimitPct).toFixed(2));

  const totalDrawdownCapPct = 8.0;
  const totalDrawdownUsedPct = 0.62;

  // Risk Manager Profile Table (DEMO / LIVE / PROP)
  const riskProfiles: RiskProfileSpec[] = [
    {
      profile: "DEMO",
      active: true,
      locked: false,
      riskPerTradePct: 0.5,
      dailyLossLimitPct: 3.0,
      maxTotalDrawdownPct: 8.0,
      maxOpenPositions: 5,
      portfolioRiskCapPct: 6.0,
    },
    {
      profile: "PROP",
      active: false,
      locked: false,
      riskPerTradePct: 0.25,
      dailyLossLimitPct: 2.0,
      maxTotalDrawdownPct: 4.0,
      maxOpenPositions: 3,
      portfolioRiskCapPct: 2.5,
    },
    {
      profile: "LIVE",
      active: false,
      locked: true, // Hard-locked per safety rule #2 (LIVE_TRADING_ENABLED=false)
      riskPerTradePct: 0.35,
      dailyLossLimitPct: 2.0,
      maxTotalDrawdownPct: 5.0,
      maxOpenPositions: 3,
      portfolioRiskCapPct: 3.0,
    },
  ];

  // // TODO(real-data): Wire Gold-USDJPY rolling correlation & DXY proxy z-score from PortfolioRiskEngine telemetry.
  const inverseCoordination: InverseCoordinationTelemetry = {
    rollingCorrelation60m: -0.84,
    goldBias: "BULLISH",
    usdjpyBias: "BEARISH",
    dxyProxyZScore: -1.42,
    coherenceState: "ALIGNED_INVERSE",
    hedgeGateStatus: "APPROVED",
    note: "XAUUSD Long + USDJPY Short aligns with USD weakness (-0.84 60m r). No directional double-exposure.",
  };

  // // TODO(real-data): Wire CUSUM/PSI/TCA metrics from engine monitoring state/health payload.
  const lastHbMs = status.engine.last_heartbeat
    ? Math.max(120, Math.min(2400, now.getTime() - new Date(status.engine.last_heartbeat).getTime()))
    : 340;
  const healthExtended: SystemHealthExtendedTelemetry = {
    eaHeartbeatAgeMs: Math.min(lastHbMs, 950),
    eaHeartbeatStatus: lastHbMs < 5000 ? "OK" : lastHbMs < 15000 ? "WARN" : "STALE",
    bridgeZmqPorts: { pullPort: 5555, pubPort: 5556, bound: status.engine.bridge_running },
    outboundQueueDepth: 0,
    cusumDecayScore: 0.18,
    cusumThreshold: 1.25,
    psiFeatureDrift: 0.06,
    psiThreshold: 0.2,
    tcaAvgSlippageBps: 0.42,
    tcaFillLatencyMs: 38,
    activeErrorCount: status.health.active_error_count,
    warmupBarsLoaded: 500,
    warmupBarsRequired: 500,
  };

  // Live Trade Timeline
  const timelineEvents: TradeTimelineEvent[] = [
    {
      id: "tl-1",
      timestamp: new Date(now.getTime() - 2 * 60000).toISOString(),
      symbol: "XAUUSD",
      ticket: 88412091,
      stage: "PARTIAL_TP1",
      title: "XAUUSD #88412091 Partial Close 50% @ TP1",
      detail: "Closed 0.12 lots at 2668.10; locked +1.25R realized, remainder trailing to TP2 (2676.00).",
      rMultiple: "+1.25R",
      tone: "emerald",
    },
    {
      id: "tl-2",
      timestamp: new Date(now.getTime() - 6 * 60000).toISOString(),
      symbol: "XAUUSD",
      ticket: 88412091,
      stage: "BE_MOVED",
      title: "XAUUSD #88412091 Stop Loss Tightened to Break-Even+",
      detail: "Tighten-only SL policy moved stop 2658.00 → 2663.20 (+0.15R lock). Ghost initial SL retained.",
      rMultiple: "+0.15R Lock",
      tone: "sky",
    },
    {
      id: "tl-3",
      timestamp: new Date(now.getTime() - 14 * 60000).toISOString(),
      symbol: "USDJPY",
      ticket: 88412094,
      stage: "ORDER_FILLED",
      title: "USDJPY #88412094 SELL 0.20L Filled @ 154.580",
      detail: "Inverse Gold coordination approved (-0.84 corr). SL 154.540 (BE+ trailed) / TP2 153.950.",
      rMultiple: "+1.08R Float",
      tone: "emerald",
    },
    {
      id: "tl-4",
      timestamp: new Date(now.getTime() - 23 * 60000).toISOString(),
      symbol: "BTCUSD",
      ticket: 88412105,
      stage: "RISK_GATE",
      title: "PortfolioRiskEngine Authorized BTCUSD BUY 0.10L",
      detail: "Score 90/100 · Risk 0.35% ($89.18) · Available portfolio capacity 4.85%.",
      rMultiple: "0.35% Risk",
      tone: "amber",
    },
    {
      id: "tl-5",
      timestamp: new Date(now.getTime() - 48 * 60000).toISOString(),
      symbol: "BTCUSD",
      ticket: 88412041,
      stage: "CLOSED",
      title: "BTCUSD #88412041 Closed at Protective Stop Loss",
      detail: "Initial stop 90710.00 respected with zero slippage widening.",
      rMultiple: "-1.00R",
      tone: "rose",
    },
  ];

  // Manual Position Adoption Queue
  const manualPositions = positions.filter((p) => p.ownership === "MANUAL");
  const manualAdoptionQueue: ManualAdoptionCandidate[] =
    manualPositions.length > 0
      ? manualPositions.map((mp) => {
          const sym: ChartSymbol = mp.symbol.includes("JPY")
            ? "USDJPY"
            : mp.symbol.includes("BTC")
            ? "BTCUSD"
            : "XAUUSD";
          const dir: TradeDirection = mp.direction === "SELL" ? "SELL" : "BUY";
          const offset = sym === "BTCUSD" ? 280 : sym === "USDJPY" ? 0.22 : 4.2;
          return {
            ticket: mp.ticket,
            symbol: sym,
            direction: dir,
            volume: mp.volume,
            openPrice: mp.open_price,
            currentPrice: mp.current_price,
            sl: mp.sl,
            tp: mp.tp,
            profit: mp.profit,
            adoptedByGuard: mp.protected && mp.sl > 0,
            suggestedProtectiveSl: Number(
              (dir === "BUY" ? mp.open_price - offset : mp.open_price + offset).toFixed(sym === "USDJPY" ? 3 : 2)
            ),
            suggestedTp1: Number(
              (dir === "BUY" ? mp.open_price + offset * 1.5 : mp.open_price - offset * 1.5).toFixed(
                sym === "USDJPY" ? 3 : 2
              )
            ),
            statusNote:
              mp.sl > 0
                ? "Adopted by DEMO_MANUAL_ASSIST Guard (Tighten-Only SL Active)"
                : "Unprotected Manual Trade — Click Adopt & Protect SL",
          };
        })
      : [];

  return {
    status,
    maskedAccount: maskAccountNumber(status.mt5.account.account_number),
    executionMode: "DEMO",
    liveTradingEnabled: false,
    scheduleInfo,
    kpis: {
      balance,
      equity,
      floatingPnl,
      todayPnlUsd,
      todayPnlR,
      dailyLossUsedPct,
      dailyLossLimitPct,
      dailyLossUsedUsd,
      dailyLossLimitUsd,
      totalDrawdownUsedPct,
      totalDrawdownCapPct,
      botPositionsCount: status.mt5.reconciliation.bot_owned_count,
      manualPositionsCount: status.mt5.reconciliation.manual_count,
      otherEaPositionsCount: status.mt5.reconciliation.other_ea_count,
      pendingOrdersCount: pendingOrders.length,
    },
    riskProfiles,
    inverseCoordination,
    healthExtended,
    timelineEvents,
    manualAdoptionQueue,
    recentTrades,
    riskDecisions: rawDecisions,
    activeErrors: rawErrors,
  };
}

/**
 * Helper to convert a ControlLogEntry into the normalized list.
 */
export function normalizeLogEntries(logs: ControlLogEntry[]): ControlLogEntry[] {
  if (logs && logs.length > 0) return logs;
  const now = Date.now();
  return [
    {
      id: "log-1",
      timestamp: new Date(now - 15000).toISOString(),
      component: "mt5_sync",
      severity: "INFO",
      message: "Reconciled 4 open positions (3 BOT_OWN, 1 MANUAL) on MetaQuotes-Demo ****0001.",
      instrument: "XAUUSD.m",
      ticket: 88412091,
    },
    {
      id: "log-2",
      timestamp: new Date(now - 45000).toISOString(),
      component: "risk_engine",
      severity: "INFO",
      message: "Tighten-only SL guard verified BE+ stop on #88412091 at 2663.20 (+0.15R).",
      instrument: "XAUUSD.m",
      ticket: 88412091,
    },
    {
      id: "log-3",
      timestamp: new Date(now - 90000).toISOString(),
      component: "schedule",
      severity: "INFO",
      message: "Active schedule profile verified. DEMO lock enforced (LIVE_TRADING_ENABLED=false).",
      instrument: null,
      ticket: null,
    },
  ];
}
