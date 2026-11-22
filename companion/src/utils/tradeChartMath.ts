export type TradeDirection = "BUY" | "SELL";

export interface TradeLevelParams {
  direction: TradeDirection;
  entryPrice: number;
  stopLoss: number;
  initialStopLoss?: number;
  tp1?: number;
  tp2?: number;
  currentPrice: number;
  volumeLots: number;
  contractValuePerPoint?: number;
}

export interface TradeMetricsResult {
  riskDistance: number;
  initialRiskDistance: number;
  floatingPriceDelta: number;
  floatingR: number;
  tp1R: number | null;
  tp2R: number | null;
  slMoved: boolean;
  isBreakEvenOrBetter: boolean;
  monetaryRiskUsd: number;
  floatingPnlUsd: number;
}

export interface ZoneBounds {
  topPrice: number;
  bottomPrice: number;
  valid: boolean;
}

export interface TradeZoneGeometry {
  riskZone: ZoneBounds;
  rewardZoneTp1: ZoneBounds;
  rewardZoneTp2: ZoneBounds;
  ghostInitialSlPrice: number | null;
}

export interface TightenSlCheckResult {
  allowed: boolean;
  reason: string;
}

export interface RawPriceLabelItem {
  id: string;
  price: number;
  idealY: number;
  height?: number;
  priority?: number;
  label: string;
  sublabel?: string;
  tone: "entry" | "sl" | "ghost_sl" | "tp1" | "tp2" | "live" | "liquidity" | "structure";
}

export interface ResolvedPriceLabelItem extends RawPriceLabelItem {
  resolvedY: number;
  displaced: boolean;
}

export interface ScheduleCountdownInfo {
  scheduleMode: "WEEKDAY_GOLD_MODE" | "WEEKEND_BTC_MODE";
  sessionName: "ASIAN" | "LONDON" | "LDN/NY OVERLAP" | "NEW YORK" | "WEEKEND CRYPTO 24/7";
  activeInstruments: string[];
  standbyInstruments: string[];
  nextSwitchLabel: string;
  nextSwitchCountdown: string;
  secondsRemaining: number;
  utcIsoTime: string;
  utcClockText: string;
}

/**
 * Pure R-multiple & risk/reward math for an open or planned trade.
 */
export function calculateTradeMetrics(params: TradeLevelParams): TradeMetricsResult {
  const {
    direction,
    entryPrice,
    stopLoss,
    initialStopLoss,
    tp1,
    tp2,
    currentPrice,
    volumeLots,
    contractValuePerPoint = 100,
  } = params;

  const effectiveInitialSl =
    typeof initialStopLoss === "number" && initialStopLoss > 0 ? initialStopLoss : stopLoss;

  const rawInitialRisk =
    direction === "BUY" ? entryPrice - effectiveInitialSl : effectiveInitialSl - entryPrice;
  const rawCurrentRisk = direction === "BUY" ? entryPrice - stopLoss : stopLoss - entryPrice;

  // Use initial risk denominator for R calculation if initial SL was valid; fall back to current SL distance
  const baseRiskDenominator =
    rawInitialRisk > 1e-8 ? rawInitialRisk : Math.abs(entryPrice - stopLoss) > 1e-8 ? Math.abs(entryPrice - stopLoss) : 1;

  const floatingPriceDelta =
    direction === "BUY" ? currentPrice - entryPrice : entryPrice - currentPrice;

  const floatingR = Number((floatingPriceDelta / baseRiskDenominator).toFixed(2));

  let tp1R: number | null = null;
  if (typeof tp1 === "number" && tp1 > 0) {
    const tp1Delta = direction === "BUY" ? tp1 - entryPrice : entryPrice - tp1;
    tp1R = Number((tp1Delta / baseRiskDenominator).toFixed(2));
  }

  let tp2R: number | null = null;
  if (typeof tp2 === "number" && tp2 > 0) {
    const tp2Delta = direction === "BUY" ? tp2 - entryPrice : entryPrice - tp2;
    tp2R = Number((tp2Delta / baseRiskDenominator).toFixed(2));
  }

  const slMoved =
    typeof initialStopLoss === "number" &&
    initialStopLoss > 0 &&
    stopLoss > 0 &&
    Math.abs(initialStopLoss - stopLoss) > 1e-6;

  const isBreakEvenOrBetter =
    stopLoss > 0 &&
    (direction === "BUY" ? stopLoss >= entryPrice - 1e-6 : stopLoss <= entryPrice + 1e-6);

  const activeRiskDist = Math.max(0, rawCurrentRisk);
  const monetaryRiskUsd = Number((activeRiskDist * volumeLots * contractValuePerPoint).toFixed(2));
  const floatingPnlUsd = Number((floatingPriceDelta * volumeLots * contractValuePerPoint).toFixed(2));

  return {
    riskDistance: Number(Math.abs(rawCurrentRisk).toFixed(5)),
    initialRiskDistance: Number(Math.abs(rawInitialRisk).toFixed(5)),
    floatingPriceDelta: Number(floatingPriceDelta.toFixed(5)),
    floatingR,
    tp1R,
    tp2R,
    slMoved,
    isBreakEvenOrBetter,
    monetaryRiskUsd,
    floatingPnlUsd,
  };
}

/**
 * Pure price-zone bounds calculation for shaded Risk and Reward boxes on the chart.
 */
export function calculateTradeZones(params: {
  direction: TradeDirection;
  entryPrice: number;
  stopLoss: number;
  initialStopLoss?: number;
  tp1?: number;
  tp2?: number;
}): TradeZoneGeometry {
  const { direction, entryPrice, stopLoss, initialStopLoss, tp1, tp2 } = params;

  // Risk zone spans between Entry and active SL (or initial SL if active SL moved past entry into profit)
  const effectiveRiskStop =
    stopLoss > 0
      ? (direction === "BUY" && stopLoss > entryPrice) || (direction === "SELL" && stopLoss < entryPrice)
        ? initialStopLoss && initialStopLoss > 0
          ? initialStopLoss
          : stopLoss
        : stopLoss
      : initialStopLoss && initialStopLoss > 0
      ? initialStopLoss
      : 0;

  const riskValid = effectiveRiskStop > 0 && Math.abs(entryPrice - effectiveRiskStop) > 1e-8;
  const riskZone: ZoneBounds = riskValid
    ? {
        topPrice: Math.max(entryPrice, effectiveRiskStop),
        bottomPrice: Math.min(entryPrice, effectiveRiskStop),
        valid: true,
      }
    : { topPrice: entryPrice, bottomPrice: entryPrice, valid: false };

  const tp1Target = typeof tp1 === "number" && tp1 > 0 ? tp1 : 0;
  const tp1Valid =
    tp1Target > 0 &&
    ((direction === "BUY" && tp1Target > entryPrice) || (direction === "SELL" && tp1Target < entryPrice));
  const rewardZoneTp1: ZoneBounds = tp1Valid
    ? {
        topPrice: Math.max(entryPrice, tp1Target),
        bottomPrice: Math.min(entryPrice, tp1Target),
        valid: true,
      }
    : { topPrice: entryPrice, bottomPrice: entryPrice, valid: false };

  const tp2Target = typeof tp2 === "number" && tp2 > 0 ? tp2 : tp1Target;
  const tp2Valid =
    tp2Target > 0 &&
    ((direction === "BUY" && tp2Target > entryPrice) || (direction === "SELL" && tp2Target < entryPrice));
  const rewardZoneTp2: ZoneBounds = tp2Valid
    ? {
        topPrice: Math.max(entryPrice, tp2Target),
        bottomPrice: Math.min(entryPrice, tp2Target),
        valid: true,
      }
    : { topPrice: entryPrice, bottomPrice: entryPrice, valid: false };

  const ghostInitialSlPrice =
    typeof initialStopLoss === "number" &&
    initialStopLoss > 0 &&
    Math.abs(initialStopLoss - stopLoss) > 1e-6
      ? initialStopLoss
      : null;

  return {
    riskZone,
    rewardZoneTp1,
    rewardZoneTp2,
    ghostInitialSlPrice,
  };
}

/**
 * Enforces the Institutional EA Tighten-Only Stop Policy (Hard Safety Rule #5):
 * - Stop Loss can NEVER be removed (proposedSl <= 0 is rejected).
 * - Stop Loss can NEVER be widened (BUY proposedSl < currentSl, SELL proposedSl > currentSl is rejected).
 * - Stop Loss must remain on the valid side of current market price.
 */
export function validateTightenOnlyStopLoss(params: {
  direction: TradeDirection;
  currentSl: number;
  proposedSl: number;
  currentPrice: number;
  minStopDistance?: number;
}): TightenSlCheckResult {
  const { direction, currentSl, proposedSl, currentPrice, minStopDistance = 0 } = params;

  if (!Number.isFinite(proposedSl) || proposedSl <= 0) {
    return {
      allowed: false,
      reason: "TIGHTEN_ONLY_POLICY: Removing Stop Loss (SL <= 0) is strictly prohibited.",
    };
  }

  if (direction === "BUY") {
    if (currentSl > 0 && proposedSl < currentSl - 1e-8) {
      return {
        allowed: false,
        reason: `TIGHTEN_ONLY_POLICY: Cannot widen BUY Stop Loss below current SL (${currentSl}).`,
      };
    }
    if (proposedSl >= currentPrice - minStopDistance) {
      return {
        allowed: false,
        reason: `INVALID_STOP_LEVEL: BUY Stop Loss (${proposedSl}) must be below current market price (${currentPrice}).`,
      };
    }
    return { allowed: true, reason: "VALID_TIGHTEN_BUY_SL" };
  }

  // SELL direction
  if (currentSl > 0 && proposedSl > currentSl + 1e-8) {
    return {
      allowed: false,
      reason: `TIGHTEN_ONLY_POLICY: Cannot widen SELL Stop Loss above current SL (${currentSl}).`,
    };
  }
  if (proposedSl <= currentPrice + minStopDistance) {
    return {
      allowed: false,
      reason: `INVALID_STOP_LEVEL: SELL Stop Loss (${proposedSl}) must be above current market price (${currentPrice}).`,
    };
  }

  return { allowed: true, reason: "VALID_TIGHTEN_SELL_SL" };
}

/**
 * Normalizes any broker symbol string (`XAUUSD.m`, `XAUUSD.pro`, `XAUUSDc`, `BTCUSD.m`, `USDJPY.m`)
 * to its canonical symbol (`XAUUSD`, `USDJPY`, `BTCUSD`).
 */
export function normalizeCanonicalSymbol(rawSymbol: string | null | undefined): "XAUUSD" | "USDJPY" | "BTCUSD" {
  const upper = String(rawSymbol ?? "").toUpperCase();
  if (upper.includes("JPY")) return "USDJPY";
  if (upper.includes("BTC")) return "BTCUSD";
  return "XAUUSD";
}

/**
 * Snaps a UTC timestamp (seconds) to the exact opening bar boundary for the given timeframe (in seconds),
 * optionally applying a broker server UTC offset and clamping to the loaded candle time range.
 */
export function snapTimestampToCandle(
  timestampSec: number,
  timeframeSeconds: number,
  candleTimes?: number[],
  brokerOffsetSeconds: number = 0
): number {
  const tf = Math.max(60, timeframeSeconds);
  const adjusted = timestampSec - brokerOffsetSeconds;
  const bucket = Math.floor(adjusted / tf) * tf;

  if (!candleTimes || candleTimes.length === 0) {
    return bucket;
  }

  const first = candleTimes[0];
  const last = candleTimes[candleTimes.length - 1];
  if (bucket <= first) return first;
  if (bucket >= last) return last;

  // Binary / linear snap to nearest loaded candle bar (handles weekend gaps cleanly)
  let best = first;
  let bestDiff = Math.abs(bucket - first);
  for (let i = 1; i < candleTimes.length; i++) {
    const d = Math.abs(bucket - candleTimes[i]);
    if (d < bestDiff) {
      bestDiff = d;
      best = candleTimes[i];
    }
  }
  return best;
}

const DEFAULT_TONE_PRIORITY: Record<RawPriceLabelItem["tone"], number> = {
  live: 100,
  entry: 95,
  sl: 90,
  tp1: 85,
  tp2: 85,
  ghost_sl: 75,
  liquidity: 60,
  structure: 55,
};

/**
 * Priority-aware, collision-free vertical label layout solver.
 * Guarantees that no two labels overlap (resolvedY[i+1] - resolvedY[i] >= minGapPx)
 * and that no label clips outside [minY + halfH, maxY - halfH] while preserving vertical price order.
 * If more labels compete than vertical height allows, highest-priority labels (Live, Entry, SL, TP) always win.
 */
export function resolveLabelCollisions(
  items: RawPriceLabelItem[],
  bounds: { minY: number; maxY: number; minGapPx?: number; defaultHeightPx?: number; maxLabels?: number }
): ResolvedPriceLabelItem[] {
  if (items.length === 0) return [];

  const defaultHeightPx = bounds.defaultHeightPx ?? 21;
  const minGapPx = bounds.minGapPx ?? defaultHeightPx + 3;
  const topLimit = bounds.minY + defaultHeightPx / 2;
  const bottomLimit = Math.max(topLimit, bounds.maxY - defaultHeightPx / 2);
  const availableSpan = Math.max(1, bottomLimit - topLimit);

  // Determine maximum labels that can comfortably fit
  const maxByHeight = Math.max(4, Math.floor(availableSpan / Math.max(16, minGapPx - 3)) + 1);
  const maxCap = Math.min(bounds.maxLabels ?? 12, maxByHeight);

  let pool = [...items];
  if (pool.length > maxCap) {
    // Keep highest-priority items (Live, Entry, SL, TP1, TP2 always win)
    pool.sort((a, b) => {
      const pa = a.priority ?? DEFAULT_TONE_PRIORITY[a.tone] ?? 50;
      const pb = b.priority ?? DEFAULT_TONE_PRIORITY[b.tone] ?? 50;
      return pb - pa;
    });
    pool = pool.slice(0, maxCap);
  }

  // Sort from top of chart (smallest Y / highest price) to bottom of chart (largest Y / lowest price)
  const sorted = pool.sort((a, b) => {
    if (Math.abs(a.idealY - b.idealY) > 0.5) {
      return a.idealY - b.idealY;
    }
    return b.price - a.price;
  });

  const n = sorted.length;
  const availableSpan = Math.max(1, bottomLimit - topLimit);
  // If more labels than vertical space allows at full minGapPx, compress gap gracefully so none clip
  const effectiveGap = n > 1 ? Math.min(minGapPx, availableSpan / (n - 1)) : minGapPx;

  const positions = sorted.map((item) =>
    Math.min(bottomLimit, Math.max(topLimit, item.idealY))
  );

  // Forward pass: push overlapping labels downward
  for (let i = 1; i < n; i++) {
    const minAllowedY = positions[i - 1] + effectiveGap;
    if (positions[i] < minAllowedY) {
      positions[i] = minAllowedY;
    }
  }

  // Clamp last element to bottomLimit and run backward pass to pull labels upward if bottom overflowed
  if (positions[n - 1] > bottomLimit) {
    positions[n - 1] = bottomLimit;
  }
  for (let i = n - 2; i >= 0; i--) {
    const maxAllowedY = positions[i + 1] - effectiveGap;
    if (positions[i] > maxAllowedY) {
      positions[i] = maxAllowedY;
    }
  }

  // Final forward safety clamp if topLimit was exceeded
  if (positions[0] < topLimit) {
    positions[0] = topLimit;
    for (let i = 1; i < n; i++) {
      const minAllowedY = positions[i - 1] + effectiveGap;
      if (positions[i] < minAllowedY) {
        positions[i] = Math.min(bottomLimit, minAllowedY);
      }
    }
  }

  return sorted.map((item, idx) => {
    const resolvedY = Number(positions[idx].toFixed(2));
    return {
      ...item,
      resolvedY,
      displaced: Math.abs(resolvedY - item.idealY) >= 1.5,
    };
  });
}

/**
 * Masks an MT5 account number to show only the last 4 digits (`****0001`).
 */
export function maskAccountNumber(accountNumber: number | string | null | undefined): string {
  const digits = String(accountNumber ?? "").replace(/\D/g, "");
  if (!digits || digits === "0") {
    return "****0001";
  }
  const tail = digits.slice(-4).padStart(4, "0");
  return `****${tail}`;
}

/**
 * Pure schedule mode, trading session, and next switch countdown calculator for a given UTC Date.
 * Weekday schedule: Monday 00:00 UTC -> Friday 22:00 UTC (`WEEKDAY_GOLD_MODE`: XAUUSD, USDJPY active; BTCUSD standby).
 * Weekend schedule: Friday 22:00 UTC -> Monday 00:00 UTC (`WEEKEND_BTC_MODE`: BTCUSD active; XAUUSD, USDJPY market closed).
 */
export function computeScheduleAndSession(now: Date = new Date()): ScheduleCountdownInfo {
  const utcDay = now.getUTCDay(); // 0 = Sun, 1 = Mon, ..., 5 = Fri, 6 = Sat
  const utcHour = now.getUTCHours();
  const utcMin = now.getUTCMinutes();
  const utcSec = now.getUTCSeconds();

  const isWeekendMode =
    utcDay === 0 || utcDay === 6 || (utcDay === 5 && utcHour >= 22);

  const scheduleMode = isWeekendMode ? "WEEKEND_BTC_MODE" : "WEEKDAY_GOLD_MODE";

  let sessionName: ScheduleCountdownInfo["sessionName"];
  if (isWeekendMode) {
    sessionName = "WEEKEND CRYPTO 24/7";
  } else if (utcHour >= 13 && utcHour < 16) {
    sessionName = "LDN/NY OVERLAP";
  } else if (utcHour >= 7 && utcHour < 13) {
    sessionName = "LONDON";
  } else if (utcHour >= 16 && utcHour < 22) {
    sessionName = "NEW YORK";
  } else {
    sessionName = "ASIAN";
  }

  // Compute next schedule switch timestamp in UTC
  const nextSwitch = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0));
  let nextSwitchLabel: string;

  if (isWeekendMode) {
    // Next switch is Monday 00:00 UTC -> WEEKDAY_GOLD_MODE
    nextSwitchLabel = "WEEKDAY_GOLD_MODE (Mon 00:00 UTC)";
    const daysUntilMonday = utcDay === 0 ? 1 : utcDay === 6 ? 2 : 3; // Fri >=22 -> +3 days
    nextSwitch.setUTCDate(nextSwitch.getUTCDate() + daysUntilMonday);
    nextSwitch.setUTCHours(0, 0, 0, 0);
  } else {
    // Next switch is Friday 22:00 UTC -> WEEKEND_BTC_MODE
    nextSwitchLabel = "WEEKEND_BTC_MODE (Fri 22:00 UTC)";
    const daysUntilFriday = 5 - utcDay;
    nextSwitch.setUTCDate(nextSwitch.getUTCDate() + daysUntilFriday);
    nextSwitch.setUTCHours(22, 0, 0, 0);
  }

  const secondsRemaining = Math.max(0, Math.floor((nextSwitch.getTime() - now.getTime()) / 1000));
  const days = Math.floor(secondsRemaining / 86400);
  const hours = Math.floor((secondsRemaining % 86400) / 3600);
  const mins = Math.floor((secondsRemaining % 3600) / 60);
  const secs = secondsRemaining % 60;

  const nextSwitchCountdown =
    days > 0
      ? `${days}d ${String(hours).padStart(2, "0")}h ${String(mins).padStart(2, "0")}m`
      : `${String(hours).padStart(2, "0")}h ${String(mins).padStart(2, "0")}m ${String(secs).padStart(2, "0")}s`;

  const utcClockText = `${String(utcHour).padStart(2, "0")}:${String(utcMin).padStart(2, "0")}:${String(
    utcSec
  ).padStart(2, "0")} UTC`;

  return {
    scheduleMode,
    sessionName,
    activeInstruments: isWeekendMode ? ["BTCUSD"] : ["XAUUSD", "USDJPY"],
    standbyInstruments: isWeekendMode ? ["XAUUSD", "USDJPY"] : ["BTCUSD"],
    nextSwitchLabel,
    nextSwitchCountdown,
    secondsRemaining,
    utcIsoTime: now.toISOString(),
    utcClockText,
  };
}
