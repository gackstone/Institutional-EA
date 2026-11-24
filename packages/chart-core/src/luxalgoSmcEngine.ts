/**
 * LuxAlgo Smart Money Concepts (SMC) — TypeScript Port for Instant Chart Rendering.
 *
 * Attribution & License:
 *   Ported from LuxAlgo "Smart Money Concepts [LuxAlgo]" (Pine Script v5),
 *   licensed under CC BY-NC-SA 4.0 © LuxAlgo.
 *   Pure, deterministic, read-only visualization calculation. Mirrors companion/service/market/luxalgo_smc.py.
 */

import type { CandlePoint } from "./chartCanvasRenderer";
import type { FvgTimeframeOption, SmcChartSettings } from "./smcChartSettings";

export const SMC_BULLISH_LEG = 1;
export const SMC_BEARISH_LEG = 0;

export const SMC_BULLISH = 1;
export const SMC_BEARISH = -1;
export const SMC_NEUTRAL = 0;

export const MAX_STORED_ORDER_BLOCKS = 100;
export const MAX_SMC_OBJECTS = 500;

export type IrlErlTag = "IRL" | "ERL";

export interface SmcStructureEvent {
  id: string;
  tag: "BOS" | "CHoCH";
  tier: "INTERNAL" | "SWING";
  direction: "BULLISH" | "BEARISH";
  price: number;
  startTime: number;
  endTime: number;
  startIndex: number;
  endIndex: number;
  irlErl: IrlErlTag;
}

export interface SmcSwingPoint {
  id: string;
  tag: "HH" | "HL" | "LH" | "LL";
  price: number;
  time: number;
  barIndex: number;
  direction: "BULLISH" | "BEARISH";
  irlErl: IrlErlTag;
}

export interface SmcOrderBlock {
  id: string;
  top: number;
  bottom: number;
  midpoint: number;
  startTime: number;
  barIndex: number;
  direction: "BULLISH" | "BEARISH";
  tier: "INTERNAL" | "SWING";
  irlErl: IrlErlTag;
}

export interface SmcEqhEql {
  id: string;
  tag: "EQH" | "EQL";
  startTime: number;
  endTime: number;
  startPrice: number;
  endPrice: number;
  price: number;
  direction: "BULLISH" | "BEARISH";
  irlErl: IrlErlTag;
}

export interface SmcFairValueGap {
  id: string;
  top: number;
  bottom: number;
  midpoint: number;
  startTime: number;
  barIndex: number;
  direction: "BULLISH" | "BEARISH";
  extendBars: number;
  irlErl: IrlErlTag;
}

export interface SmcStrongWeakLevel {
  id: string;
  kind: "HIGH" | "LOW";
  label: "Strong High" | "Weak High" | "Strong Low" | "Weak Low";
  isStrong: boolean;
  price: number;
  startTime: number;
  direction: "BULLISH" | "BEARISH";
  irlErl: IrlErlTag;
}

export interface SmcZone {
  id: string;
  kind: "PREMIUM" | "EQUILIBRIUM" | "DISCOUNT";
  label: "Premium" | "Equilibrium" | "Discount";
  top: number;
  bottom: number;
  startTime: number;
  irlErl: IrlErlTag;
}

export interface SmcComputationResult {
  internalStructures: SmcStructureEvent[];
  swingStructures: SmcStructureEvent[];
  swingPoints: SmcSwingPoint[];
  internalOrderBlocks: SmcOrderBlock[];
  swingOrderBlocks: SmcOrderBlock[];
  equalHighsLows: SmcEqhEql[];
  fairValueGaps: SmcFairValueGap[];
  strongWeakLevels: SmcStrongWeakLevel[];
  premiumDiscountZones: SmcZone[];
  candleTrends: number[];
  swingTrend: number;
  internalTrend: number;
}

interface PivotState {
  currentLevel: number | null;
  lastLevel: number | null;
  crossed: boolean;
  barTime: number;
  barIndex: number;
}

interface InternalOb {
  barHigh: number;
  barLow: number;
  barTime: number;
  barIndex: number;
  bias: number;
  tier: "INTERNAL" | "SWING";
}

interface InternalFvg {
  top: number;
  bottom: number;
  bias: number;
  barTime: number;
  barIndex: number;
}

function createPivot(): PivotState {
  return { currentLevel: null, lastLevel: null, crossed: false, barTime: 0, barIndex: 0 };
}

function computeAtrRma(candles: CandlePoint[], period = 200): number[] {
  const n = candles.length;
  if (n === 0) return [];
  const atr = new Array<number>(n);
  const alpha = 1 / period;
  let running = Math.max(0, candles[0].high - candles[0].low);
  atr[0] = running;
  for (let i = 1; i < n; i++) {
    const prevClose = candles[i - 1].close;
    const tr = Math.max(
      candles[i].high - candles[i].low,
      Math.abs(candles[i].high - prevClose),
      Math.abs(candles[i].low - prevClose)
    );
    if (i < period) {
      running = (running * i + tr) / (i + 1);
    } else {
      running = alpha * tr + (1 - alpha) * running;
    }
    atr[i] = running;
  }
  return atr;
}

function computeCumMeanRange(candles: CandlePoint[]): number[] {
  const n = candles.length;
  if (n === 0) return [];
  const out = new Array<number>(n);
  let cum = 0;
  for (let i = 0; i < n; i++) {
    const tr =
      i === 0
        ? Math.max(0, candles[0].high - candles[0].low)
        : Math.max(
            candles[i].high - candles[i].low,
            Math.abs(candles[i].high - candles[i - 1].close),
            Math.abs(candles[i].low - candles[i - 1].close)
          );
    cum += tr;
    out[i] = cum / (i + 1);
  }
  return out;
}

function detectLegSeries(candles: CandlePoint[], size: number): Uint8Array {
  const n = candles.length;
  const legs = new Uint8Array(n); // initialized to 0 (SMC_BEARISH_LEG)
  if (size < 1 || n <= size) return legs;

  let curLeg = SMC_BEARISH_LEG;
  for (let i = size; i < n; i++) {
    const pivotH = candles[i - size].high;
    const pivotL = candles[i - size].low;
    let maxH = -Infinity;
    let minL = Infinity;
    for (let k = i - size + 1; k <= i; k++) {
      if (candles[k].high > maxH) maxH = candles[k].high;
      if (candles[k].low < minL) minL = candles[k].low;
    }
    if (pivotH > maxH) {
      curLeg = SMC_BEARISH_LEG;
    } else if (pivotL < minL) {
      curLeg = SMC_BULLISH_LEG;
    }
    legs[i] = curLeg;
  }
  return legs;
}

const TF_SECONDS: Record<string, number> = {
  M1: 60,
  M5: 300,
  M15: 900,
  M30: 1800,
  H1: 3600,
  H4: 14400,
  D1: 86400,
};

function resampleCandlesForFvg(
  candles: CandlePoint[],
  chartTf: string,
  fvgTf: FvgTimeframeOption
): CandlePoint[] {
  if (fvgTf === "Chart") return candles;
  const targetSec = TF_SECONDS[fvgTf] ?? 0;
  const chartSec = TF_SECONDS[chartTf.toUpperCase()] ?? 0;
  if (targetSec <= 0 || targetSec <= chartSec) return candles;

  const buckets: CandlePoint[] = [];
  let curBucketStart = -1;
  let cur: CandlePoint | null = null;

  for (let i = 0; i < candles.length; i++) {
    const c = candles[i];
    const bStart = Math.floor(c.time / targetSec) * targetSec;
    if (bStart !== curBucketStart || !cur) {
      if (cur) buckets.push(cur);
      curBucketStart = bStart;
      cur = {
        time: bStart,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume ?? 0,
      };
    } else {
      if (c.high > cur.high) cur.high = c.high;
      if (c.low < cur.low) cur.low = c.low;
      cur.close = c.close;
      cur.volume = (cur.volume ?? 0) + (c.volume ?? 0);
    }
  }
  if (cur) buckets.push(cur);
  return buckets;
}

export function computeLuxAlgoSmc(
  candles: CandlePoint[],
  settings: SmcChartSettings,
  chartTf = "M5"
): SmcComputationResult {
  const empty: SmcComputationResult = {
    internalStructures: [],
    swingStructures: [],
    swingPoints: [],
    internalOrderBlocks: [],
    swingOrderBlocks: [],
    equalHighsLows: [],
    fairValueGaps: [],
    strongWeakLevels: [],
    premiumDiscountZones: [],
    candleTrends: [],
    swingTrend: SMC_NEUTRAL,
    internalTrend: SMC_NEUTRAL,
  };

  const n = candles.length;
  if (n < 3) return empty;

  const atr200 = computeAtrRma(candles, 200);
  const cumMean = computeCumMeanRange(candles);
  const volMeasure = settings.obFilter === "Atr" ? atr200 : cumMean;

  const parsedHighs = new Float64Array(n);
  const parsedLows = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const rng = c.high - c.low;
    const isHighVol = volMeasure[i] > 0 && rng >= 2 * volMeasure[i];
    parsedHighs[i] = isHighVol ? c.low : c.high;
    parsedLows[i] = isHighVol ? c.high : c.low;
  }

  const swingLen = 50;
  const internalLen = 5;
  const swingPtsLen = Math.max(10, Math.round(settings.swingPointsLength || 50));
  const eqhLen = Math.max(1, Math.round(settings.eqhBarsConfirmation || 3));

  const swingLegs = detectLegSeries(candles, swingLen);
  const internalLegs = detectLegSeries(candles, internalLen);
  const eqhLegs = detectLegSeries(candles, eqhLen);
  const swingPtsLegs = swingPtsLen === swingLen ? swingLegs : detectLegSeries(candles, swingPtsLen);

  const swingHigh = createPivot();
  const swingLow = createPivot();
  const internalHigh = createPivot();
  const internalLow = createPivot();
  const eqhPivot = createPivot();
  const eqlPivot = createPivot();
  const spHigh = createPivot();
  const spLow = createPivot();

  let swingTrend = SMC_NEUTRAL;
  let internalTrend = SMC_NEUTRAL;

  let trailingTop: number | null = null;
  let trailingBottom: number | null = null;
  let trailingTopTime = candles[0].time;
  let trailingBottomTime = candles[0].time;

  const internalStructures: SmcStructureEvent[] = [];
  const swingStructures: SmcStructureEvent[] = [];
  const swingPoints: SmcSwingPoint[] = [];
  const equalHighsLows: SmcEqhEql[] = [];
  let internalObs: InternalOb[] = [];
  let swingObs: InternalOb[] = [];
  const candleTrends = new Array<number>(n).fill(SMC_NEUTRAL);

  const storeOb = (pivot: PivotState, breakIdx: number, bias: number, tier: "INTERNAL" | "SWING") => {
    const startI = Math.max(0, pivot.barIndex);
    const endI = Math.max(startI + 1, breakIdx);
    if (startI >= endI || endI > n) return;

    let bestIdx = startI;
    if (bias === SMC_BEARISH) {
      let bestVal = parsedHighs[startI];
      for (let k = startI + 1; k < endI; k++) {
        if (parsedHighs[k] > bestVal) {
          bestVal = parsedHighs[k];
          bestIdx = k;
        }
      }
    } else {
      let bestVal = parsedLows[startI];
      for (let k = startI + 1; k < endI; k++) {
        if (parsedLows[k] < bestVal) {
          bestVal = parsedLows[k];
          bestIdx = k;
        }
      }
    }

    let obTop = Math.max(parsedHighs[bestIdx], parsedLows[bestIdx]);
    let obBot = Math.min(parsedHighs[bestIdx], parsedLows[bestIdx]);
    if (obTop <= obBot) {
      obTop = candles[bestIdx].high;
      obBot = candles[bestIdx].low;
    }
    if (obTop <= obBot) return;

    const ob: InternalOb = {
      barHigh: obTop,
      barLow: obBot,
      barTime: candles[bestIdx].time,
      barIndex: bestIdx,
      bias,
      tier,
    };
    const arr = tier === "INTERNAL" ? internalObs : swingObs;
    arr.unshift(ob);
    if (arr.length > MAX_STORED_ORDER_BLOCKS) arr.pop();
  };

  for (let i = 0; i < n; i++) {
    const c = candles[i];

    // 1. Swing pivots (size = 50)
    if (i > swingLen) {
      const diff = swingLegs[i] - swingLegs[i - 1];
      if (diff === 1) {
        const pIdx = i - swingLen;
        swingLow.lastLevel = swingLow.currentLevel;
        swingLow.currentLevel = candles[pIdx].low;
        swingLow.crossed = false;
        swingLow.barTime = candles[pIdx].time;
        swingLow.barIndex = pIdx;
        trailingBottom = swingLow.currentLevel;
        trailingBottomTime = swingLow.barTime;
      } else if (diff === -1) {
        const pIdx = i - swingLen;
        swingHigh.lastLevel = swingHigh.currentLevel;
        swingHigh.currentLevel = candles[pIdx].high;
        swingHigh.crossed = false;
        swingHigh.barTime = candles[pIdx].time;
        swingHigh.barIndex = pIdx;
        trailingTop = swingHigh.currentLevel;
        trailingTopTime = swingHigh.barTime;
      }
    }

    // Trailing extremes
    if (trailingTop === null || c.high >= trailingTop) {
      trailingTop = c.high;
      trailingTopTime = c.time;
    }
    if (trailingBottom === null || c.low <= trailingBottom) {
      trailingBottom = c.low;
      trailingBottomTime = c.time;
    }

    // 2. Swing point labels (HH/HL/LH/LL)
    if (i > swingPtsLen) {
      const spDiff = swingPtsLegs[i] - swingPtsLegs[i - 1];
      if (spDiff === 1) {
        const pIdx = i - swingPtsLen;
        spLow.lastLevel = spLow.currentLevel;
        spLow.currentLevel = candles[pIdx].low;
        spLow.barTime = candles[pIdx].time;
        spLow.barIndex = pIdx;
        if (spLow.lastLevel !== null) {
          const tag = spLow.currentLevel < spLow.lastLevel ? "LL" : "HL";
          swingPoints.push({
            id: `sp:${tag}:${spLow.barTime}`,
            tag,
            price: spLow.currentLevel,
            time: spLow.barTime,
            barIndex: pIdx,
            direction: "BULLISH",
            irlErl: "ERL",
          });
        }
      } else if (spDiff === -1) {
        const pIdx = i - swingPtsLen;
        spHigh.lastLevel = spHigh.currentLevel;
        spHigh.currentLevel = candles[pIdx].high;
        spHigh.barTime = candles[pIdx].time;
        spHigh.barIndex = pIdx;
        if (spHigh.lastLevel !== null) {
          const tag = spHigh.currentLevel > spHigh.lastLevel ? "HH" : "LH";
          swingPoints.push({
            id: `sp:${tag}:${spHigh.barTime}`,
            tag,
            price: spHigh.currentLevel,
            time: spHigh.barTime,
            barIndex: pIdx,
            direction: "BEARISH",
            irlErl: "ERL",
          });
        }
      }
    }

    // 3. Internal pivots (size = 5)
    if (i > internalLen) {
      const iDiff = internalLegs[i] - internalLegs[i - 1];
      if (iDiff === 1) {
        const pIdx = i - internalLen;
        internalLow.lastLevel = internalLow.currentLevel;
        internalLow.currentLevel = candles[pIdx].low;
        internalLow.crossed = false;
        internalLow.barTime = candles[pIdx].time;
        internalLow.barIndex = pIdx;
      } else if (iDiff === -1) {
        const pIdx = i - internalLen;
        internalHigh.lastLevel = internalHigh.currentLevel;
        internalHigh.currentLevel = candles[pIdx].high;
        internalHigh.crossed = false;
        internalHigh.barTime = candles[pIdx].time;
        internalHigh.barIndex = pIdx;
      }
    }

    // 4. EQH / EQL
    if (i > eqhLen) {
      const eDiff = eqhLegs[i] - eqhLegs[i - 1];
      const thresh = settings.eqhThreshold * atr200[i];
      if (eDiff === -1) {
        const pIdx = i - eqhLen;
        const lvl = candles[pIdx].high;
        if (eqhPivot.currentLevel !== null && Math.abs(lvl - eqhPivot.currentLevel) < thresh) {
          equalHighsLows.push({
            id: `eqh:${eqhPivot.barTime}:${candles[pIdx].time}`,
            tag: "EQH",
            startTime: eqhPivot.barTime,
            endTime: candles[pIdx].time,
            startPrice: eqhPivot.currentLevel,
            endPrice: lvl,
            price: (eqhPivot.currentLevel + lvl) / 2,
            direction: "BEARISH",
            irlErl: "ERL",
          });
        }
        eqhPivot.lastLevel = eqhPivot.currentLevel;
        eqhPivot.currentLevel = lvl;
        eqhPivot.barTime = candles[pIdx].time;
        eqhPivot.barIndex = pIdx;
      } else if (eDiff === 1) {
        const pIdx = i - eqhLen;
        const lvl = candles[pIdx].low;
        if (eqlPivot.currentLevel !== null && Math.abs(lvl - eqlPivot.currentLevel) < thresh) {
          equalHighsLows.push({
            id: `eql:${eqlPivot.barTime}:${candles[pIdx].time}`,
            tag: "EQL",
            startTime: eqlPivot.barTime,
            endTime: candles[pIdx].time,
            startPrice: eqlPivot.currentLevel,
            endPrice: lvl,
            price: (eqlPivot.currentLevel + lvl) / 2,
            direction: "BULLISH",
            irlErl: "ERL",
          });
        }
        eqlPivot.lastLevel = eqlPivot.currentLevel;
        eqlPivot.currentLevel = lvl;
        eqlPivot.barTime = candles[pIdx].time;
        eqlPivot.barIndex = pIdx;
      }
    }

    // 5. Structure breaks
    if (i >= 1) {
      const prevClose = candles[i - 1].close;
      const curClose = c.close;

      let bullishBar = true;
      let bearishBar = true;
      if (settings.internalConfluenceFilter) {
        const upperWick = c.high - Math.max(curClose, c.open);
        const lowerWick = Math.min(curClose, c.open) - c.low;
        bullishBar = upperWick > lowerWick;
        bearishBar = upperWick < lowerWick;
      }

      if (
        internalHigh.currentLevel !== null &&
        !internalHigh.crossed &&
        curClose > internalHigh.currentLevel &&
        prevClose <= internalHigh.currentLevel &&
        internalHigh.currentLevel !== swingHigh.currentLevel &&
        bullishBar
      ) {
        const tag = internalTrend === SMC_BEARISH ? "CHoCH" : "BOS";
        internalHigh.crossed = true;
        internalTrend = SMC_BULLISH;
        internalStructures.push({
          id: `struct:INT:${tag}:${internalHigh.barTime}:${c.time}`,
          tag,
          tier: "INTERNAL",
          direction: "BULLISH",
          price: internalHigh.currentLevel,
          startTime: internalHigh.barTime,
          endTime: c.time,
          startIndex: internalHigh.barIndex,
          endIndex: i,
          irlErl: "IRL",
        });
        storeOb(internalHigh, i, SMC_BULLISH, "INTERNAL");
      }

      if (
        internalLow.currentLevel !== null &&
        !internalLow.crossed &&
        curClose < internalLow.currentLevel &&
        prevClose >= internalLow.currentLevel &&
        internalLow.currentLevel !== swingLow.currentLevel &&
        bearishBar
      ) {
        const tag = internalTrend === SMC_BULLISH ? "CHoCH" : "BOS";
        internalLow.crossed = true;
        internalTrend = SMC_BEARISH;
        internalStructures.push({
          id: `struct:INT:${tag}:${internalLow.barTime}:${c.time}`,
          tag,
          tier: "INTERNAL",
          direction: "BEARISH",
          price: internalLow.currentLevel,
          startTime: internalLow.barTime,
          endTime: c.time,
          startIndex: internalLow.barIndex,
          endIndex: i,
          irlErl: "IRL",
        });
        storeOb(internalLow, i, SMC_BEARISH, "INTERNAL");
      }

      if (
        swingHigh.currentLevel !== null &&
        !swingHigh.crossed &&
        curClose > swingHigh.currentLevel &&
        prevClose <= swingHigh.currentLevel
      ) {
        const tag = swingTrend === SMC_BEARISH ? "CHoCH" : "BOS";
        swingHigh.crossed = true;
        swingTrend = SMC_BULLISH;
        swingStructures.push({
          id: `struct:SWG:${tag}:${swingHigh.barTime}:${c.time}`,
          tag,
          tier: "SWING",
          direction: "BULLISH",
          price: swingHigh.currentLevel,
          startTime: swingHigh.barTime,
          endTime: c.time,
          startIndex: swingHigh.barIndex,
          endIndex: i,
          irlErl: "ERL",
        });
        storeOb(swingHigh, i, SMC_BULLISH, "SWING");
      }

      if (
        swingLow.currentLevel !== null &&
        !swingLow.crossed &&
        curClose < swingLow.currentLevel &&
        prevClose >= swingLow.currentLevel
      ) {
        const tag = swingTrend === SMC_BULLISH ? "CHoCH" : "BOS";
        swingLow.crossed = true;
        swingTrend = SMC_BEARISH;
        swingStructures.push({
          id: `struct:SWG:${tag}:${swingLow.barTime}:${c.time}`,
          tag,
          tier: "SWING",
          direction: "BEARISH",
          price: swingLow.currentLevel,
          startTime: swingLow.barTime,
          endTime: c.time,
          startIndex: swingLow.barIndex,
          endIndex: i,
          irlErl: "ERL",
        });
        storeOb(swingLow, i, SMC_BEARISH, "SWING");
      }
    }

    // 6. Order Block mitigation
    const bearSrc = settings.obMitigation === "Close" ? c.close : c.high;
    const bullSrc = settings.obMitigation === "Close" ? c.close : c.low;
    if (internalObs.length > 0) {
      internalObs = internalObs.filter(
        (ob) =>
          !((ob.bias === SMC_BEARISH && bearSrc > ob.barHigh) || (ob.bias === SMC_BULLISH && bullSrc < ob.barLow))
      );
    }
    if (swingObs.length > 0) {
      swingObs = swingObs.filter(
        (ob) =>
          !((ob.bias === SMC_BEARISH && bearSrc > ob.barHigh) || (ob.bias === SMC_BULLISH && bullSrc < ob.barLow))
      );
    }

    candleTrends[i] = internalTrend !== SMC_NEUTRAL ? internalTrend : swingTrend;
  }

  // 7. Fair Value Gaps (supports Chart or resampled HTF)
  const fvgCandles = resampleCandlesForFvg(candles, chartTf, settings.fvgTimeframe);
  let activeFvgs: InternalFvg[] = [];
  let cumAbsDelta = 0;
  for (let i = 0; i < fvgCandles.length; i++) {
    const c = fvgCandles[i];
    if (activeFvgs.length > 0) {
      activeFvgs = activeFvgs.filter(
        (f) => !((f.bias === SMC_BULLISH && c.low < f.bottom) || (f.bias === SMC_BEARISH && c.high > f.top))
      );
    }
    if (i >= 2) {
      const c1 = fvgCandles[i - 1];
      const c2 = fvgCandles[i - 2];
      const barDeltaPct = c1.open !== 0 ? (c1.close - c1.open) / c1.open : 0;
      cumAbsDelta += Math.abs(barDeltaPct);
      const thresh = settings.fvgAutoThreshold ? (cumAbsDelta / (i + 1)) * 2 : 0;

      if (c.low > c2.high && c1.close > c2.high && barDeltaPct > thresh) {
        activeFvgs.unshift({
          top: c.low,
          bottom: c2.high,
          bias: SMC_BULLISH,
          barTime: c.time,
          barIndex: i,
        });
      } else if (c.high < c2.low && c1.close < c2.low && -barDeltaPct > thresh) {
        activeFvgs.unshift({
          top: c2.low,
          bottom: c.high,
          bias: SMC_BEARISH,
          barTime: c.time,
          barIndex: i,
        });
      }
      if (activeFvgs.length > MAX_SMC_OBJECTS) activeFvgs.pop();
    }
  }

  // Apply Historical vs Present mode & object caps
  const finalInternalStructs =
    settings.mode === "Present"
      ? internalStructures.slice(-1)
      : internalStructures.slice(-MAX_SMC_OBJECTS);
  const finalSwingStructs =
    settings.mode === "Present" ? swingStructures.slice(-1) : swingStructures.slice(-MAX_SMC_OBJECTS);
  const finalEqhEql =
    settings.mode === "Present" ? equalHighsLows.slice(-1) : equalHighsLows.slice(-MAX_SMC_OBJECTS);

  const intObLimit = Math.max(1, Math.min(20, Math.round(settings.internalOBCount || 5)));
  const swObLimit = Math.max(1, Math.min(20, Math.round(settings.swingOBCount || 5)));

  const finalInternalObs: SmcOrderBlock[] = internalObs.slice(0, intObLimit).map((ob) => ({
    id: `ob:INT:${ob.barTime}:${ob.barLow.toFixed(4)}`,
    top: ob.barHigh,
    bottom: ob.barLow,
    midpoint: (ob.barHigh + ob.barLow) / 2,
    startTime: ob.barTime,
    barIndex: ob.barIndex,
    direction: ob.bias === SMC_BULLISH ? "BULLISH" : "BEARISH",
    tier: "INTERNAL",
    irlErl: "IRL",
  }));

  const finalSwingObs: SmcOrderBlock[] = swingObs.slice(0, swObLimit).map((ob) => ({
    id: `ob:SWG:${ob.barTime}:${ob.barLow.toFixed(4)}`,
    top: ob.barHigh,
    bottom: ob.barLow,
    midpoint: (ob.barHigh + ob.barLow) / 2,
    startTime: ob.barTime,
    barIndex: ob.barIndex,
    direction: ob.bias === SMC_BULLISH ? "BULLISH" : "BEARISH",
    tier: "SWING",
    irlErl: "ERL",
  }));

  const finalFvgs: SmcFairValueGap[] = activeFvgs.slice(0, MAX_SMC_OBJECTS).map((f) => ({
    id: `fvg:${f.barTime}:${f.bottom.toFixed(4)}`,
    top: f.top,
    bottom: f.bottom,
    midpoint: (f.top + f.bottom) / 2,
    startTime: f.barTime,
    barIndex: f.barIndex,
    direction: f.bias === SMC_BULLISH ? "BULLISH" : "BEARISH",
    extendBars: Math.max(0, Math.round(settings.fvgExtend || 0)),
    irlErl: "IRL",
  }));

  const strongWeakLevels: SmcStrongWeakLevel[] = [];
  const premiumDiscountZones: SmcZone[] = [];

  if (trailingTop !== null && trailingBottom !== null && trailingTop > trailingBottom) {
    strongWeakLevels.push(
      {
        id: `sw:HIGH:${trailingTopTime}`,
        kind: "HIGH",
        label: swingTrend === SMC_BEARISH ? "Strong High" : "Weak High",
        isStrong: swingTrend === SMC_BEARISH,
        price: trailingTop,
        startTime: trailingTopTime,
        direction: "BEARISH",
        irlErl: "ERL",
      },
      {
        id: `sw:LOW:${trailingBottomTime}`,
        kind: "LOW",
        label: swingTrend === SMC_BULLISH ? "Strong Low" : "Weak Low",
        isStrong: swingTrend === SMC_BULLISH,
        price: trailingBottom,
        startTime: trailingBottomTime,
        direction: "BULLISH",
        irlErl: "ERL",
      }
    );

    const zStart = Math.min(trailingTopTime, trailingBottomTime);
    premiumDiscountZones.push(
      {
        id: `zone:PREMIUM:${zStart}`,
        kind: "PREMIUM",
        label: "Premium",
        top: trailingTop,
        bottom: 0.95 * trailingTop + 0.05 * trailingBottom,
        startTime: zStart,
        irlErl: "ERL",
      },
      {
        id: `zone:EQUILIBRIUM:${zStart}`,
        kind: "EQUILIBRIUM",
        label: "Equilibrium",
        top: 0.525 * trailingTop + 0.475 * trailingBottom,
        bottom: 0.525 * trailingBottom + 0.475 * trailingTop,
        startTime: zStart,
        irlErl: "IRL",
      },
      {
        id: `zone:DISCOUNT:${zStart}`,
        kind: "DISCOUNT",
        label: "Discount",
        top: 0.95 * trailingBottom + 0.05 * trailingTop,
        bottom: trailingBottom,
        startTime: zStart,
        irlErl: "ERL",
      }
    );
  }

  return {
    internalStructures: finalInternalStructs,
    swingStructures: finalSwingStructs,
    swingPoints: swingPoints.slice(-MAX_SMC_OBJECTS),
    internalOrderBlocks: finalInternalObs,
    swingOrderBlocks: finalSwingObs,
    equalHighsLows: finalEqhEql,
    fairValueGaps: finalFvgs,
    strongWeakLevels,
    premiumDiscountZones,
    candleTrends,
    swingTrend,
    internalTrend,
  };
}
