import {
  ControlLogEntry,
  ControlStatusPayload,
  ControlSymbolSpec,
  OperatingMode,
  TradeHistoryRecord,
} from "../types";
import {
  calculateTradeMetrics,
  maskAccountNumber,
  normalizeCanonicalSymbol,
  snapTimestampToCandle,
  TradeDirection,
} from "../utils/tradeChartMath";

export type ChartSymbol = "XAUUSD" | "USDJPY" | "BTCUSD";
export type ChartTimeframe = "M1" | "M5" | "M15" | "H1" | "H4";
export type DataFeedStatus = "LIVE_SSE" | "POLLING" | "STALE" | "DISCONNECTED" | "LOADING";

export interface CandleBar {
  time: number; // Unix timestamp in seconds (UTC)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
  bid: number | null;
  ask: number | null;
  spreadPoints: number | null;
  candles: CandleBar[];
  trades: ChartTradeOverlay[];
  liquidityLevels: LiquidityLevelOverlay[];
  fvgObZones: FvgObZoneOverlay[];
  structureBreaks: StructureBreakOverlay[];
  sessions: SessionMarkerOverlay[];
  source: "MT5" | "NONE";
  tickTimeUtc: string | null;
  tickAgeSec: number | null;
  stale: boolean;
  marketClosed: boolean;
  freshnessReason: string;
}

export interface DataProvenance {
  source: "MT5" | "BOT" | "NONE";
  updatedAt: string | null;
  stale: boolean;
  connected: boolean;
}

export interface NormalizedDashboardData {
  status: ControlStatusPayload;
  connected: boolean;
  provenance: DataProvenance;
  maskedAccount: string;
  executionMode: "DEMO";
  liveTradingEnabled: false;
  kpis: {
    balance: number | null;
    equity: number | null;
    floatingPnl: number | null;
    todayPnlUsd: number | null;
    todayPnlR: number | null;
    dailyLossUsedPct: number;
    dailyLossLimitPct: number;
    dailyLossUsedUsd: number;
    dailyLossLimitUsd: number;
    totalDrawdownUsedPct: number;
    totalDrawdownCapPct: number;
    botPositionsCount: number;
    pendingOrdersCount: number;
  };
  recentTrades: TradeHistoryRecord[];
}

// Config-driven contract metadata ONLY (no prices, spreads, or market data)
const SYMBOL_CONFIG_SPECS: Record<
  ChartSymbol,
  {
    brokerSymbol: string;
    digits: number;
    point: number;
    contractValuePerPoint: number;
  }
> = {
  XAUUSD: {
    brokerSymbol: "XAUUSD.m",
    digits: 2,
    point: 0.01,
    contractValuePerPoint: 100,
  },
  USDJPY: {
    brokerSymbol: "USDJPY.m",
    digits: 3,
    point: 0.001,
    contractValuePerPoint: 650,
  },
  BTCUSD: {
    brokerSymbol: "BTCUSD.m",
    digits: 2,
    point: 0.01,
    contractValuePerPoint: 1,
  },
};

const TIMEFRAME_SECONDS: Record<ChartTimeframe, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  H1: 3600,
  H4: 14400,
};

// Risk policy limits from config/risk_config.json (config constants only, never market data)
const CONFIG_DAILY_LOSS_LIMIT_PCT = 3.0;
const CONFIG_TOTAL_DRAWDOWN_CAP_PCT = 8.0;
const CONFIG_RISK_UNIT_PCT = 0.005;
const STALE_SYNC_THRESHOLD_MS = 15_000;

/**
 * Builds a chart bundle strictly from real MT5 OHLC candles and real MT5 positions.
 * Never generates synthetic candles, fake prices, or fake SMC drawings.
 */
export function buildSymbolChartBundle(
  symbol: ChartSymbol,
  timeframe: ChartTimeframe,
  status: ControlStatusPayload | null,
  realCandles: CandleBar[] = [],
  liveQuoteOverride: ControlSymbolSpec | null = null
): SymbolChartBundle {
  const cfg = SYMBOL_CONFIG_SPECS[symbol];
  const liveSpecs = status?.mt5?.symbols || {};
  const matchedSpec: ControlSymbolSpec | undefined =
    liveQuoteOverride ||
    liveSpecs[cfg.brokerSymbol] ||
    liveSpecs[symbol] ||
    Object.values(liveSpecs).find((s) => normalizeCanonicalSymbol(s.symbol) === symbol);

  const digits = matchedSpec?.digits ?? cfg.digits;
  const point = matchedSpec?.point ?? cfg.point;
  const bid = matchedSpec && matchedSpec.bid > 0 ? matchedSpec.bid : null;
  const ask = matchedSpec && matchedSpec.ask > 0 ? matchedSpec.ask : null;
  const spreadPoints =
    matchedSpec && bid !== null && ask !== null
      ? matchedSpec.spread_points
      : null;

  const latestBarTime =
    realCandles.length > 0 ? realCandles[realCandles.length - 1].time : Math.floor(Date.now() / 1000);

  // Project ONLY real open MT5 positions for this symbol onto the chart
  const realPositions = (status?.mt5?.positions || []).filter(
    (p) => normalizeCanonicalSymbol(p.symbol) === symbol
  );

  const trades: ChartTradeOverlay[] = realPositions.map((p) => {
    const dir: TradeDirection = p.direction === "SELL" ? "SELL" : "BUY";
    const currentP = bid ?? p.current_price;
    const metrics = calculateTradeMetrics({
      direction: dir,
      entryPrice: p.open_price,
      stopLoss: p.sl,
      currentPrice: currentP,
      volumeLots: p.volume,
      contractValuePerPoint: cfg.contractValuePerPoint,
    });
    const snappedEntryTime = snapTimestampToCandle(latestBarTime, TIMEFRAME_SECONDS[timeframe]);
    return {
      ticket: p.ticket,
      symbol,
      direction: dir,
      volume: p.volume,
      qualityScore: 0,
      entryPrice: p.open_price,
      entryTime: snappedEntryTime,
      currentPrice: currentP,
      stopLoss: p.sl,
      initialStopLoss: p.sl,
      tp1: 0,
      tp2: p.tp,
      floatingPnl: p.profit,
      floatingR: metrics.floatingR,
      tp1R: 0,
      tp2R:
        p.tp > 0 && metrics.riskDistance > 0
          ? Number((Math.abs(p.tp - p.open_price) / metrics.riskDistance).toFixed(2))
          : 0,
      ownership:
        p.ownership === "BOT"
          ? "BOT_OWN"
          : p.ownership === "MANUAL"
          ? "MANUAL"
          : "OTHER_EA",
      protected: p.protected,
      strategyTag: p.comment || "MT5",
    };
  });

  return {
    symbol,
    brokerSymbol: matchedSpec?.symbol || cfg.brokerSymbol,
    timeframe,
    digits,
    point,
    contractValuePerPoint: cfg.contractValuePerPoint,
    bid,
    ask,
    spreadPoints,
    candles: realCandles,
    trades,
    liquidityLevels: [],
    fvgObZones: [],
    structureBreaks: [],
    sessions: [],
    source: matchedSpec || realCandles.length > 0 ? "MT5" : "NONE",
    tickTimeUtc: matchedSpec?.tick_time_utc ?? null,
    tickAgeSec: matchedSpec?.tick_age_sec ?? null,
    stale: Boolean(matchedSpec?.stale ?? false),
    marketClosed: Boolean(matchedSpec?.market_closed ?? false),
    freshnessReason:
      matchedSpec?.freshness_reason ||
      (realCandles.length > 0 ? "LIVE" : "Waiting for MT5"),
  };
}

/**
 * Normalizes real backend `/api/status` and real closed trades without inventing any fallback data.
 * When disconnected or waiting for MT5, numeric fields remain null and arrays remain empty.
 */
export function buildNormalizedDashboardData(
  rawStatus: ControlStatusPayload | null,
  rawTrades: TradeHistoryRecord[],
  now: Date = new Date()
): NormalizedDashboardData {
  const mt5Connected =
    rawStatus !== null && rawStatus.mt5.connection_status === "CONNECTED";

  const lastSyncAt = rawStatus?.mt5?.last_sync_at || null;
  const isStale =
    !mt5Connected ||
    !lastSyncAt ||
    now.getTime() - new Date(lastSyncAt).getTime() > STALE_SYNC_THRESHOLD_MS;

  const emptyStatus: ControlStatusPayload = {
    engine: {
      engine_state: rawStatus?.engine?.engine_state || "STOPPED",
      operating_mode: (rawStatus?.engine?.operating_mode || "DEMO_SCALPING") as OperatingMode,
      dry_run: Boolean(rawStatus?.engine?.dry_run ?? false),
      live_trading_locked: true,
      stop_flag_active: Boolean(rawStatus?.engine?.stop_flag_active ?? false),
      pause_flag_active: Boolean(rawStatus?.engine?.pause_flag_active ?? false),
      bridge_running: Boolean(rawStatus?.engine?.bridge_running ?? false),
      bridge_pid: rawStatus?.engine?.bridge_pid ?? null,
      engine_running: Boolean(rawStatus?.engine?.engine_running ?? false),
      engine_pid: rawStatus?.engine?.engine_pid ?? null,
      started_at: rawStatus?.engine?.started_at ?? null,
      last_heartbeat: rawStatus?.engine?.last_heartbeat ?? null,
      last_signal: rawStatus?.engine?.last_signal ?? null,
      last_trade: rawStatus?.engine?.last_trade ?? null,
      last_execution_error: rawStatus?.engine?.last_execution_error ?? null,
      portfolio_capacity: rawStatus?.engine?.portfolio_capacity,
    },
    mt5: {
      connection_status: rawStatus?.mt5?.connection_status || "DISCONNECTED",
      last_sync_at: lastSyncAt,
      last_error: rawStatus?.mt5?.last_error ?? null,
      reconnect_attempts: rawStatus?.mt5?.reconnect_attempts ?? 0,
      account: rawStatus?.mt5?.account || {
        account_number: 0,
        broker: "Not Connected",
        currency: "USD",
        balance: 0,
        equity: 0,
        margin: 0,
        free_margin: 0,
        margin_level: 0,
        leverage: 0,
        trade_mode: "DEMO",
        margin_mode_str: "HEDGING",
        demo_verified: false,
        netting_observe_only: false,
      },
      positions: rawStatus?.mt5?.positions || [],
      pending_orders: rawStatus?.mt5?.pending_orders || [],
      symbols: rawStatus?.mt5?.symbols || {},
      reconciliation: rawStatus?.mt5?.reconciliation || {
        status: "NOT_SYNCED",
        bot_owned_count: 0,
        manual_count: 0,
        other_ea_count: 0,
        unexpected_tickets: [],
        unprotected_bot_tickets: [],
        timestamp: null,
      },
    },
    health: rawStatus?.health || {
      overall: "WAITING",
      sqlite: { healthy: false, db_path: "" },
      active_error_count: 0,
      stop_flag_active: false,
      pause_flag_active: false,
      mt5_connected: false,
      demo_verified: false,
    },
  };

  const positions = emptyStatus.mt5.positions;
  const pendingOrders = emptyStatus.mt5.pending_orders;

  const hasAccount = mt5Connected && emptyStatus.mt5.account.account_number > 0;
  const balance = hasAccount ? Number(emptyStatus.mt5.account.balance.toFixed(2)) : null;
  const equity = hasAccount ? Number(emptyStatus.mt5.account.equity.toFixed(2)) : null;
  const floatingPnl =
    balance !== null && equity !== null ? Number((equity - balance).toFixed(2)) : null;

  const todayUtcDate = now.toISOString().slice(0, 10);
  const closedToday = rawTrades.filter(
    (t) => t.closed_at && t.closed_at.slice(0, 10) === todayUtcDate
  );
  const closedPnlToday = closedToday.reduce((acc, t) => acc + t.profit, 0);
  const todayPnlUsd =
    floatingPnl !== null ? Number((closedPnlToday + floatingPnl).toFixed(2)) : null;
  const unitRiskUsd = balance !== null ? Math.max(0.01, balance * CONFIG_RISK_UNIT_PCT) : null;
  const todayPnlR =
    todayPnlUsd !== null && unitRiskUsd !== null
      ? Number((todayPnlUsd / unitRiskUsd).toFixed(2))
      : null;

  const dailyLossLimitUsd =
    balance !== null ? Number(((balance * CONFIG_DAILY_LOSS_LIMIT_PCT) / 100).toFixed(2)) : 0;
  const realizedLossToday = Math.abs(
    closedToday.filter((t) => t.profit < 0).reduce((s, t) => s + t.profit, 0)
  );
  const dailyLossUsedUsd = Number(realizedLossToday.toFixed(2));
  const dailyLossUsedPct =
    dailyLossLimitUsd > 0
      ? Number(((dailyLossUsedUsd / dailyLossLimitUsd) * CONFIG_DAILY_LOSS_LIMIT_PCT).toFixed(2))
      : 0;

  const totalDrawdownUsedPct =
    balance !== null && equity !== null && balance > 0 && equity < balance
      ? Number((((balance - equity) / balance) * 100).toFixed(2))
      : 0;

  return {
    status: emptyStatus,
    connected: mt5Connected,
    provenance: {
      source: mt5Connected ? "MT5" : "NONE",
      updatedAt: lastSyncAt,
      stale: isStale,
      connected: mt5Connected,
    },
    maskedAccount:
      emptyStatus.mt5.account.account_number > 0
        ? maskAccountNumber(emptyStatus.mt5.account.account_number)
        : "Not Connected",
    executionMode: "DEMO",
    liveTradingEnabled: false,
    kpis: {
      balance,
      equity,
      floatingPnl,
      todayPnlUsd,
      todayPnlR,
      dailyLossUsedPct,
      dailyLossLimitPct: CONFIG_DAILY_LOSS_LIMIT_PCT,
      dailyLossUsedUsd,
      dailyLossLimitUsd,
      totalDrawdownUsedPct,
      totalDrawdownCapPct: CONFIG_TOTAL_DRAWDOWN_CAP_PCT,
      botPositionsCount: positions.filter((p) => p.ownership === "BOT").length,
      pendingOrdersCount: pendingOrders.length,
    },
    recentTrades: rawTrades,
  };
}

/**
 * Returns real runtime logs directly without fabricating fallback entries.
 */
export function normalizeLogEntries(logs: ControlLogEntry[]): ControlLogEntry[] {
  return logs || [];
}
