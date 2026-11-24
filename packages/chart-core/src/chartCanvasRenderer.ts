import type { EngineDrawingItem } from "./chartDrawingsSchema";
import type { SmcComputationResult } from "./luxalgoSmcEngine";
import type {
  LabelSizeOption,
  LineStyleOption,
  SmcChartSettings,
} from "./smcChartSettings";

const SMC_RENDER_PALETTE = {
  colored: {
    green: "#089981",
    red: "#F23645",
    blue: "#2157f3",
    gray: "#878b94",
  },
  monochrome: {
    bull: "#b2b5be",
    bear: "#5d606b",
    neutral: "#878b94",
    internalBullOb: "rgba(178, 181, 190, 0.20)",
    internalBearOb: "rgba(93, 96, 107, 0.20)",
    swingBullOb: "rgba(178, 181, 190, 0.20)",
    swingBearOb: "rgba(93, 96, 107, 0.20)",
    swingBullObBorder: "rgba(178, 181, 190, 0.85)",
    swingBearObBorder: "rgba(93, 96, 107, 0.85)",
    bullFvg: "rgba(178, 181, 190, 0.28)",
    bearFvg: "rgba(93, 96, 107, 0.28)",
    premiumZone: "rgba(93, 96, 107, 0.20)",
    equilibriumZone: "rgba(135, 139, 148, 0.20)",
    discountZone: "rgba(178, 181, 190, 0.20)",
  },
  labelSizesPx: {
    Tiny: 9.5,
    Small: 11,
    Normal: 12.5,
  },
} as const;

// ============================================================================
// Shared centered zone label (FVG / OB / IFVG) — used by BOTH the engine
// drawings renderer and the LuxAlgo SMC renderer (dashboard + fullscreen).
// ============================================================================
export type ZoneLabelCode = "FVG" | "OB" | "IFVG";
export type ChartThemeMode = "light" | "dark";

export const ZONE_LABEL_FULL_NAMES: Record<ZoneLabelCode, string> = {
  FVG: "Fair Value Gap",
  OB: "Order Block",
  IFVG: "Inverse Fair Value Gap",
};

/** "FVG - Fair Value Gap" style legend text. */
export function formatZoneLegend(code: ZoneLabelCode): string {
  return `${code} - ${ZONE_LABEL_FULL_NAMES[code]}`;
}

export const ZONE_LABEL_FONT_PX = 10;
const ZONE_LABEL_PAD_X = 4;
const ZONE_LABEL_PAD_Y = 2;

export const ZONE_LABEL_THEME: Record<ChartThemeMode, { text: string; halo: string }> = {
  light: { text: "rgba(15, 23, 42, 0.86)", halo: "rgba(255, 255, 255, 0.70)" },
  dark: { text: "rgba(243, 244, 246, 0.94)", halo: "rgba(10, 10, 12, 0.65)" },
};

/**
 * Pure placement math: clips the zone rectangle to the visible plot area and returns
 * the label center, or null when the visible part is too small to fit the text.
 */
export function computeZoneLabelPlacement(
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  plotWidth: number,
  plotHeight: number,
  textWidth: number,
  fontPx: number = ZONE_LABEL_FONT_PX
): { x: number; y: number } | null {
  if (![x1, y1, x2, y2, plotWidth, plotHeight, textWidth].every(Number.isFinite)) return null;
  const left = Math.max(0, Math.min(x1, x2));
  const right = Math.min(plotWidth, Math.max(x1, x2));
  const top = Math.max(0, Math.min(y1, y2));
  const bottom = Math.min(plotHeight, Math.max(y1, y2));
  const w = right - left;
  const h = bottom - top;
  if (w < textWidth + ZONE_LABEL_PAD_X * 2 || h < fontPx + ZONE_LABEL_PAD_Y * 2) return null;
  return { x: left + w / 2, y: top + h / 2 };
}

/**
 * Draws a small bold label centered inside the visible portion of a zone rectangle.
 * Non-interactive (canvas is pointer-events-none). Returns true if drawn.
 */
export function drawCenteredZoneLabel(
  ctx: CanvasRenderingContext2D,
  label: ZoneLabelCode,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  plotWidth: number,
  plotHeight: number,
  theme: ChartThemeMode = "light"
): boolean {
  ctx.save();
  ctx.font = `700 ${ZONE_LABEL_FONT_PX}px 'Plus Jakarta Sans', system-ui, sans-serif`;
  const textWidth = ctx.measureText(label).width;
  const pos = computeZoneLabelPlacement(x1, y1, x2, y2, plotWidth, plotHeight, textWidth);
  if (!pos) {
    ctx.restore();
    return false;
  }
  const colors = ZONE_LABEL_THEME[theme] ?? ZONE_LABEL_THEME.light;
  ctx.beginPath();
  ctx.rect(0, 0, plotWidth, plotHeight);
  ctx.clip();
  ctx.globalAlpha = 1;
  ctx.setLineDash([]);
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.lineJoin = "round";
  ctx.lineWidth = 3;
  ctx.strokeStyle = colors.halo;
  ctx.strokeText(label, pos.x, pos.y);
  ctx.fillStyle = colors.text;
  ctx.fillText(label, pos.x, pos.y);
  ctx.restore();
  return true;
}

function deriveBorderColorLocal(fillColor: string, borderAlpha = 0.85): string {
  const c = fillColor.trim();
  const m = c.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
  if (m) {
    return `rgba(${m[1]}, ${m[2]}, ${m[3]}, ${borderAlpha.toFixed(2)})`;
  }
  if (/^#[0-9a-f]{6}$/i.test(c)) {
    const r = parseInt(c.slice(1, 3), 16);
    const g = parseInt(c.slice(3, 5), 16);
    const b = parseInt(c.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${borderAlpha.toFixed(2)})`;
  }
  return fillColor;
}

const CANVAS_THEME = {
  fvgFill: "rgba(110, 198, 114, 0.30)",
  fvgBorder: "rgba(10, 153, 125, 0.48)",
  fvgText: "#166534",
  profitFillPrimary: "rgba(10, 153, 125, 0.34)",
  lossFill: "rgba(238, 55, 73, 0.15)",
  sessionFillFallback: "rgba(59, 130, 246, 0.055)",
  sessionBorderFallback: "rgba(148, 163, 184, 0.25)",
} as const;

export interface CandlePoint {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
}

export interface OverlayVisibility {
  liquidity: boolean;
  fvgOb: boolean;
  structure: boolean;
  sessions: boolean;
  trades: boolean;
}

export interface CoordinateProjector {
  timeToX: (timeSec: number) => number | null;
  priceToY: (price: number) => number | null;
  plotWidth: number;
  plotHeight: number;
  candles: CandlePoint[];
}

export interface ProjectedDrawing {
  item: EngineDrawingItem;
  kind: "LINE" | "RECT" | "BAND" | "TRADE";
  x1: number;
  x2: number;
  y1: number;
  y2: number;
  // Extra coordinates for specific types
  sweepX?: number | null;
  entryY?: number;
  slY?: number | null;
  initialSlY?: number | null;
  tpY?: number | null;
  tp1Y?: number | null;
  exitY?: number | null;
  isLong?: boolean;
}

/**
 * Anchors any Unix timestamp to an X coordinate on the time scale,
 * gracefully handling HTF origin timestamps earlier than the first visible bar,
 * weekend gaps, and missing intermediate candles.
 */
export function resolveTimeCoordinate(
  timeSec: number,
  projector: CoordinateProjector,
  clampLeftIfBeforeStart = true
): number | null {
  const direct = projector.timeToX(timeSec);
  if (direct !== null && Number.isFinite(direct)) return direct;

  const candles = projector.candles;
  if (!candles.length) return null;

  const firstTime = candles[0].time;
  const lastTime = candles[candles.length - 1].time;

  if (timeSec <= firstTime) {
    if (!clampLeftIfBeforeStart) return null;
    const firstX = projector.timeToX(firstTime);
    return firstX !== null && Number.isFinite(firstX) ? Math.max(0, firstX) : 0;
  }

  if (timeSec >= lastTime) {
    const lastX = projector.timeToX(lastTime);
    return lastX !== null && Number.isFinite(lastX) ? lastX : projector.plotWidth;
  }

  // Binary search for nearest candle (handles weekend gaps / missing bars)
  let lo = 0;
  let hi = candles.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (candles[mid].time < timeSec) lo = mid + 1;
    else hi = mid;
  }
  const snapped = candles[lo].time;
  const snappedX = projector.timeToX(snapped);
  if (snappedX !== null && Number.isFinite(snappedX)) return snappedX;
  return null;
}

export function projectEngineDrawings(
  items: EngineDrawingItem[],
  visibility: OverlayVisibility,
  projector: CoordinateProjector
): ProjectedDrawing[] {
  const out: ProjectedDrawing[] = [];
  const { plotWidth, plotHeight } = projector;
  if (plotWidth <= 0 || plotHeight <= 0) return out;

  for (const item of items) {
    if (item.type === "LIQ" && !visibility.liquidity) continue;
    if ((item.type === "FVG" || item.type === "OB") && !visibility.fvgOb) continue;
    if (item.type === "STRUCT" && !visibility.structure) continue;
    if (item.type === "SESS" && !visibility.sessions) continue;
    if (item.type === "TRADE" && !visibility.trades) continue;

    const pl = item.price_levels;

    if (item.type === "SESS") {
      const x1 = resolveTimeCoordinate(item.start_time, projector, true);
      const x2 =
        item.end_time !== null
          ? resolveTimeCoordinate(item.end_time, projector, false)
          : plotWidth;
      if (x1 === null || x2 === null) continue;
      const left = Math.max(0, Math.min(x1, x2));
      const right = Math.min(plotWidth, Math.max(x1, x2));
      if (right <= 0 || left >= plotWidth || right - left < 2) continue;
      out.push({
        item,
        kind: "BAND",
        x1: left,
        x2: right,
        y1: 0,
        y2: plotHeight,
      });
      continue;
    }

    if (item.type === "LIQ") {
      if (typeof pl.price !== "number") continue;
      const y = projector.priceToY(pl.price);
      if (y === null || !Number.isFinite(y) || y < -20 || y > plotHeight + 20) continue;
      const x1Raw = resolveTimeCoordinate(item.start_time, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth, x1Raw));
      const x2Raw =
        item.end_time !== null
          ? resolveTimeCoordinate(item.end_time, projector, false)
          : plotWidth;
      const x2 = x2Raw !== null ? Math.max(x1 + 4, Math.min(plotWidth, x2Raw)) : plotWidth;
      const sweepX =
        item.status === "SWEPT" && pl.sweep_time
          ? resolveTimeCoordinate(pl.sweep_time, projector, false)
          : null;
      out.push({
        item,
        kind: "LINE",
        x1,
        x2,
        y1: y,
        y2: y,
        sweepX,
      });
      continue;
    }

    if (item.type === "STRUCT") {
      if (typeof pl.price !== "number") continue;
      const y = projector.priceToY(pl.price);
      if (y === null || !Number.isFinite(y) || y < -20 || y > plotHeight + 20) continue;
      const x1Raw = resolveTimeCoordinate(item.start_time, projector, true);
      const x2Raw =
        item.end_time !== null
          ? resolveTimeCoordinate(item.end_time, projector, false)
          : plotWidth;
      if (x1Raw === null || x2Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth, Math.min(x1Raw, x2Raw)));
      const x2 = Math.max(x1 + 6, Math.min(plotWidth, Math.max(x1Raw, x2Raw)));
      out.push({
        item,
        kind: "LINE",
        x1,
        x2,
        y1: y,
        y2: y,
      });
      continue;
    }

    if (item.type === "FVG" || item.type === "OB") {
      if (typeof pl.top !== "number" || typeof pl.bottom !== "number") continue;
      const yTop = projector.priceToY(pl.top);
      const yBot = projector.priceToY(pl.bottom);
      if (yTop === null || yBot === null || !Number.isFinite(yTop) || !Number.isFinite(yBot)) continue;
      const x1Raw = resolveTimeCoordinate(item.start_time, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth, x1Raw));
      const x2Raw =
        item.end_time !== null
          ? resolveTimeCoordinate(item.end_time, projector, false)
          : plotWidth;
      const x2 = x2Raw !== null ? Math.max(x1 + 12, Math.min(plotWidth, x2Raw)) : plotWidth;
      out.push({
        item,
        kind: "RECT",
        x1,
        x2,
        y1: Math.min(yTop, yBot),
        y2: Math.max(yTop, yBot),
      });
      continue;
    }

    if (item.type === "TRADE") {
      if (typeof pl.entry !== "number") continue;
      const entryY = projector.priceToY(pl.entry);
      if (entryY === null || !Number.isFinite(entryY)) continue;
      const slY = typeof pl.sl === "number" && pl.sl > 0 ? projector.priceToY(pl.sl) : null;
      const initSlY =
        typeof pl.initial_sl === "number" && pl.initial_sl > 0
          ? projector.priceToY(pl.initial_sl)
          : slY;
      const tpY = typeof pl.tp === "number" && pl.tp > 0 ? projector.priceToY(pl.tp) : null;
      const tp1Y = typeof pl.tp1 === "number" && pl.tp1 > 0 ? projector.priceToY(pl.tp1) : null;
      const exitY = typeof pl.exit === "number" && pl.exit > 0 ? projector.priceToY(pl.exit) : null;

      const x1Raw = resolveTimeCoordinate(item.start_time, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth - 24, x1Raw));
      let x2: number;
      if (item.status === "CLOSED" && item.end_time !== null) {
        const endRaw = resolveTimeCoordinate(item.end_time, projector, false);
        x2 = endRaw !== null ? Math.max(x1 + 28, Math.min(plotWidth, endRaw)) : Math.min(plotWidth, x1 + 90);
      } else {
        x2 = Math.min(plotWidth, Math.max(x1 + 72, plotWidth - 8));
      }

      const ys = [entryY, slY, initSlY, tpY, exitY].filter(
        (v): v is number => v !== null && Number.isFinite(v)
      );
      const y1 = Math.min(...ys);
      const y2 = Math.max(...ys);

      out.push({
        item,
        kind: "TRADE",
        x1,
        x2,
        y1,
        y2,
        entryY,
        slY,
        initialSlY: initSlY,
        tpY,
        tp1Y,
        exitY,
        isLong: item.direction === "BULLISH",
      });
    }
  }

  return out;
}

/**
 * Hit-tests cursor coordinates (x, y) against projected drawings.
 * Priority: TRADE > STRUCT > LIQ > FVG/OB > SESS so small items aren't masked by session bands.
 */
export function hitTestProjectedDrawings(
  x: number,
  y: number,
  projected: ProjectedDrawing[]
): ProjectedDrawing | null {
  const priority: Record<string, number> = {
    TRADE: 5,
    STRUCT: 4,
    LIQ: 3,
    OB: 2,
    FVG: 2,
    SESS: 1,
  };

  let best: ProjectedDrawing | null = null;
  let bestPrio = -1;
  const lineTol = 7;

  for (const p of projected) {
    let hit = false;
    if (p.kind === "LINE") {
      if (x >= p.x1 - 4 && x <= p.x2 + 4 && Math.abs(y - p.y1) <= lineTol) {
        hit = true;
      }
    } else if (p.kind === "RECT" || p.kind === "BAND" || p.kind === "TRADE") {
      const pad = p.kind === "TRADE" ? 4 : 0;
      if (x >= p.x1 - pad && x <= p.x2 + pad && y >= p.y1 - pad && y <= p.y2 + pad) {
        hit = true;
      }
    }

    if (hit) {
      const prio = priority[p.item.type] ?? 0;
      if (prio >= bestPrio) {
        best = p;
        bestPrio = prio;
      }
    }
  }
  return best;
}

const SESSION_FILL: Record<string, string> = {
  ASIA: "rgba(59, 130, 246, 0.055)",
  LONDON: "rgba(16, 185, 129, 0.06)",
  OVERLAP: "rgba(245, 158, 11, 0.075)",
  NY: "rgba(139, 92, 246, 0.055)",
};

const SESSION_BORDER: Record<string, string> = {
  ASIA: "rgba(59, 130, 246, 0.18)",
  LONDON: "rgba(16, 185, 129, 0.22)",
  OVERLAP: "rgba(245, 158, 11, 0.28)",
  NY: "rgba(139, 92, 246, 0.20)",
};

/**
 * Renders all projected drawings onto a crisp high-DPI 2D canvas.
 * Enforces the strict text rule: NO permanent text on the plot except
 * "LONG POSITION" / "SHORT POSITION" and "FVG" / "IFVG" / "OB" inside boxes.
 */
export function drawProjectedOverlaysToCanvas(
  ctx: CanvasRenderingContext2D,
  projected: ProjectedDrawing[],
  plotWidth: number,
  plotHeight: number,
  highlightedId: string | null,
  options?: { clear?: boolean; onlyTypes?: Set<string>; theme?: ChartThemeMode }
): void {
  const labelTheme: ChartThemeMode = options?.theme ?? "light";
  if (options?.clear !== false) {
    ctx.clearRect(0, 0, plotWidth, plotHeight);
  }
  ctx.save();

  // Layer order: SESS -> FVG/OB -> TRADE -> LIQ -> STRUCT
  const order: Record<string, number> = {
    SESS: 0,
    FVG: 1,
    OB: 2,
    TRADE: 3,
    LIQ: 4,
    STRUCT: 5,
  };
  const filtered = options?.onlyTypes
    ? projected.filter((p) => options.onlyTypes!.has(p.item.type))
    : projected;
  const sorted = [...filtered].sort(
    (a, b) => (order[a.item.type] ?? 9) - (order[b.item.type] ?? 9)
  );

  for (const p of sorted) {
    const isHi = highlightedId !== null && p.item.id === highlightedId;
    const { item } = p;

    // 1. SESS: faint vertical session/killzone band (no permanent text)
    if (item.type === "SESS") {
      ctx.save();
      ctx.fillStyle = isHi
        ? "rgba(245, 158, 11, 0.14)"
        : SESSION_FILL[item.subtype] || CANVAS_THEME.sessionFillFallback;
      ctx.fillRect(p.x1, 0, p.x2 - p.x1, plotHeight);
      ctx.strokeStyle = isHi
        ? "rgba(245, 158, 11, 0.55)"
        : SESSION_BORDER[item.subtype] || CANVAS_THEME.sessionBorderFallback;
      ctx.lineWidth = isHi ? 1.5 : 1;
      ctx.beginPath();
      ctx.moveTo(Math.round(p.x1) + 0.5, 0);
      ctx.lineTo(Math.round(p.x1) + 0.5, plotHeight);
      ctx.moveTo(Math.round(p.x2) + 0.5, 0);
      ctx.lineTo(Math.round(p.x2) + 0.5, plotHeight);
      ctx.stroke();
      ctx.restore();
      continue;
    }

    // 2. FVG / OB: filled rectangle with ONLY "FVG"/"IFVG"/"OB" inside
    if (item.type === "FVG" || item.type === "OB") {
      const mitigated = item.status === "MITIGATED" || item.status === "INVALIDATED";
      const isBear = item.direction === "BEARISH";
      const h = Math.max(4, p.y2 - p.y1);
      const w = Math.max(8, p.x2 - p.x1);
      ctx.save();
      ctx.globalAlpha = mitigated ? 0.42 : 1;
      ctx.fillStyle =
        item.type === "OB"
          ? isBear
            ? "rgba(238, 55, 73, 0.14)"
            : "rgba(10, 153, 125, 0.16)"
          : isBear
          ? "rgba(238, 55, 73, 0.11)"
          : CANVAS_THEME.fvgFill;
      ctx.fillRect(p.x1, p.y1, w, h);

      ctx.strokeStyle = isHi
        ? isBear
          ? "#EE3749"
          : "#0A997D"
        : isBear
        ? "rgba(238, 55, 73, 0.45)"
        : CANVAS_THEME.fvgBorder;
      ctx.lineWidth = isHi ? 1.8 : 1;
      if (mitigated) ctx.setLineDash([4, 3]);
      ctx.strokeRect(
        Math.round(p.x1) + 0.5,
        Math.round(p.y1) + 0.5,
        Math.max(1, Math.round(w) - 1),
        Math.max(1, Math.round(h) - 1)
      );
      ctx.setLineDash([]);

      // Allowed permanent text inside FVG/OB box ONLY (shared centered, clipped label)
      const boxText: ZoneLabelCode =
        item.subtype === "IFVG" ? "IFVG" : item.type === "OB" ? "OB" : "FVG";
      drawCenteredZoneLabel(ctx, boxText, p.x1, p.y1, p.x1 + w, p.y1 + h, plotWidth, plotHeight, labelTheme);
      ctx.restore();
      continue;
    }

    // 3. LIQ: thin horizontal line from origin to right edge (or sweep), sweep marker dot
    if (item.type === "LIQ") {
      const swept = item.status === "SWEPT";
      const y = Math.round(p.y1) + 0.5;
      ctx.save();
      ctx.strokeStyle = isHi
        ? "#2563EB"
        : swept
        ? "rgba(148, 163, 184, 0.72)"
        : item.subtype.startsWith("PW") || item.subtype.startsWith("PD")
        ? "rgba(71, 85, 105, 0.72)"
        : "rgba(100, 116, 139, 0.6)";
      ctx.lineWidth = isHi ? 2 : 1;
      if (item.subtype === "EQH" || item.subtype === "EQL" || swept) {
        ctx.setLineDash([4, 3]);
      }
      ctx.beginPath();
      ctx.moveTo(p.x1, y);
      ctx.lineTo(p.x2, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Origin anchor dot
      ctx.fillStyle = isHi ? "#2563EB" : "rgba(100, 116, 139, 0.85)";
      ctx.beginPath();
      ctx.arc(p.x1, y, isHi ? 3 : 2, 0, Math.PI * 2);
      ctx.fill();

      // Sweep marker (small hollow ring + cross) at the sweep candle
      if (swept && p.sweepX !== null && p.sweepX !== undefined) {
        const sx = Math.max(0, Math.min(plotWidth, p.sweepX));
        ctx.strokeStyle = "#F59E0B";
        ctx.fillStyle = "#FEF3C7";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(sx, y, 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
      }
      ctx.restore();
      continue;
    }

    // 4. STRUCT: BOS / MSS / CHoCH thin line from swing to break candle + direction triangle
    if (item.type === "STRUCT") {
      const isBull = item.direction === "BULLISH";
      const y = Math.round(p.y1) + 0.5;
      const stroke = isHi
        ? isBull
          ? "#0A997D"
          : "#EE3749"
        : isBull
        ? "rgba(10, 153, 125, 0.72)"
        : "rgba(238, 55, 73, 0.72)";
      ctx.save();
      ctx.strokeStyle = stroke;
      ctx.lineWidth = isHi ? 2 : 1.15;
      if (item.subtype === "CHOCH") {
        ctx.setLineDash([5, 3]);
      }
      ctx.beginPath();
      ctx.moveTo(p.x1, y);
      ctx.lineTo(p.x2, y);
      ctx.stroke();
      ctx.setLineDash([]);

      // Small direction arrow marker at break candle (no permanent text)
      ctx.fillStyle = stroke;
      ctx.beginPath();
      if (isBull) {
        ctx.moveTo(p.x2, y - 5);
        ctx.lineTo(p.x2 - 4, y + 2);
        ctx.lineTo(p.x2 + 4, y + 2);
      } else {
        ctx.moveTo(p.x2, y + 5);
        ctx.lineTo(p.x2 - 4, y - 2);
        ctx.lineTo(p.x2 + 4, y - 2);
      }
      ctx.closePath();
      ctx.fill();
      ctx.restore();
      continue;
    }

    // 5. TRADE: Long/Short position template (profit zone, loss zone, entry, moved SL, dashed path, allowed label)
    if (item.type === "TRADE" && p.entryY !== undefined) {
      const isPending = item.status === "PENDING";
      const isClosed = item.status === "CLOSED";
      const w = Math.max(24, p.x2 - p.x1);
      ctx.save();
      ctx.globalAlpha = isPending ? 0.55 : isClosed ? 0.72 : 1.0;

      // Profit zone (entry -> tp)
      if (p.tpY !== null && p.tpY !== undefined) {
        const top = Math.min(p.entryY, p.tpY);
        const h = Math.max(2, Math.abs(p.tpY - p.entryY));
        ctx.fillStyle = CANVAS_THEME.profitFillPrimary;
        ctx.fillRect(p.x1, top, w, h);
        // Optional TP1 inner dashed line
        if (p.tp1Y !== null && p.tp1Y !== undefined) {
          const y1r = Math.round(p.tp1Y) + 0.5;
          ctx.strokeStyle = "rgba(10, 153, 125, 0.55)";
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(p.x1, y1r);
          ctx.lineTo(p.x2, y1r);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        // TP outer border
        ctx.strokeStyle = isHi ? "#0A997D" : "rgba(10, 153, 125, 0.75)";
        ctx.lineWidth = isHi ? 1.8 : 1;
        ctx.beginPath();
        ctx.moveTo(p.x1, Math.round(p.tpY) + 0.5);
        ctx.lineTo(p.x2, Math.round(p.tpY) + 0.5);
        ctx.stroke();
      }

      // Loss zone (entry -> initialSl or current sl)
      const lossBoundY = p.initialSlY ?? p.slY;
      if (lossBoundY !== null && lossBoundY !== undefined) {
        const top = Math.min(p.entryY, lossBoundY);
        const h = Math.max(2, Math.abs(lossBoundY - p.entryY));
        ctx.fillStyle = CANVAS_THEME.lossFill;
        ctx.fillRect(p.x1, top, w, h);
      }

      // Current SL line (highlighted if moved from initial SL)
      if (p.slY !== null && p.slY !== undefined) {
        const slMoved =
          p.initialSlY !== null &&
          p.initialSlY !== undefined &&
          Math.abs(p.initialSlY - p.slY) > 1.5;
        ctx.strokeStyle = slMoved ? "#0EA5E9" : "#EE3749";
        ctx.lineWidth = slMoved || isHi ? 1.8 : 1.2;
        if (slMoved) ctx.setLineDash([5, 3]);
        ctx.beginPath();
        ctx.moveTo(p.x1, Math.round(p.slY) + 0.5);
        ctx.lineTo(p.x2, Math.round(p.slY) + 0.5);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Entry line
      const ey = Math.round(p.entryY) + 0.5;
      ctx.strokeStyle = isHi ? "#111827" : "#475569";
      ctx.lineWidth = isHi ? 1.8 : 1.25;
      ctx.beginPath();
      ctx.moveTo(p.x1, ey);
      ctx.lineTo(p.x2, ey);
      ctx.stroke();

      // Dashed path line from entry to exit (closed) or to TP (open/pending)
      const pathTargetY = isClosed && p.exitY !== null && p.exitY !== undefined ? p.exitY : p.tpY;
      if (pathTargetY !== null && pathTargetY !== undefined) {
        ctx.strokeStyle = "rgba(15, 23, 42, 0.48)";
        ctx.lineWidth = 1;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(p.x1, p.entryY);
        ctx.lineTo(p.x2, pathTargetY);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Highlight outer outline when hovered/pinned
      if (isHi) {
        ctx.strokeStyle = "#2563EB";
        ctx.lineWidth = 1.6;
        ctx.strokeRect(p.x1, p.y1, w, Math.max(4, p.y2 - p.y1));
      }

      // Allowed permanent label: ONLY "LONG POSITION" or "SHORT POSITION"
      const label = p.isLong ? "LONG POSITION" : "SHORT POSITION";
      const labelY = p.isLong ? Math.max(12, p.y1 - 8) : Math.min(plotHeight - 10, p.y2 + 10);
      ctx.font = "700 9.5px 'Plus Jakarta Sans', system-ui, sans-serif";
      ctx.fillStyle = p.isLong ? "#0A997D" : "#EE3749";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(label, p.x1 + 3, labelY);

      ctx.restore();
    }
  }

  ctx.restore();
}

function getLineDashPattern(style: LineStyleOption): number[] {
  if (style === "dashed") return [5, 3];
  if (style === "dotted") return [2, 2.5];
  return [];
}

function getLabelFont(size: LabelSizeOption, weight: 500 | 600 | 700 = 600): string {
  const px = SMC_RENDER_PALETTE.labelSizesPx[size] ?? 10;
  return `${weight} ${px}px 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif`;
}

export interface MtfLevelInput {
  code: "PDH" | "PDL" | "PWH" | "PWL" | "PMH" | "PML";
  period: "D" | "W" | "M";
  price: number;
  startTime: number;
}

/**
 * Renders LuxAlgo Smart Money Concepts overlays onto the 2D canvas.
 * Matches LuxAlgo "Smart Money Concepts" Pine v5 visual styling (CC BY-NC-SA 4.0 © LuxAlgo).
 */
export function drawLuxAlgoSmcOverlaysToCanvas(
  ctx: CanvasRenderingContext2D,
  smc: SmcComputationResult,
  mtfLevels: MtfLevelInput[],
  settings: SmcChartSettings,
  projector: CoordinateProjector,
  digits = 2,
  theme: ChartThemeMode = "light"
): void {
  const { plotWidth, plotHeight, candles } = projector;
  if (plotWidth <= 0 || plotHeight <= 0 || candles.length === 0) return;

  const isMono = settings.style === "Monochrome";
  const mono = SMC_RENDER_PALETTE.monochrome;
  const colored = SMC_RENDER_PALETTE.colored;

  const allowIrlErl = (tag: "IRL" | "ERL") => (tag === "IRL" ? settings.showIRL : settings.showERL);

  // Estimate bar pixel spacing for FVG right extension
  let barSpacingPx = 8;
  if (candles.length >= 2) {
    const xLast = projector.timeToX(candles[candles.length - 1].time);
    const xPrev = projector.timeToX(candles[candles.length - 2].time);
    if (xLast !== null && xPrev !== null && Number.isFinite(xLast - xPrev) && xLast > xPrev) {
      barSpacingPx = Math.max(2, Math.min(40, xLast - xPrev));
    }
  }
  const lastCandleXRaw = resolveTimeCoordinate(candles[candles.length - 1].time, projector, true);
  const lastCandleX = lastCandleXRaw !== null ? Math.min(plotWidth, lastCandleXRaw) : plotWidth;

  ctx.save();

  // ------------------------------------------------------------------
  // 1. Premium / Equilibrium / Discount Zones
  // ------------------------------------------------------------------
  if (settings.showPremiumDiscount && smc.premiumDiscountZones.length > 0) {
    for (const z of smc.premiumDiscountZones) {
      if (!allowIrlErl(z.irlErl)) continue;
      const yTop = projector.priceToY(z.top);
      const yBot = projector.priceToY(z.bottom);
      if (yTop === null || yBot === null || !Number.isFinite(yTop) || !Number.isFinite(yBot)) continue;
      const x1Raw = resolveTimeCoordinate(z.startTime, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth - 10, x1Raw));
      const x2 = plotWidth;
      const top = Math.min(yTop, yBot);
      const h = Math.max(2, Math.abs(yBot - yTop));

      let fill: string;
      let textColor: string;
      if (z.kind === "PREMIUM") {
        fill = isMono ? mono.premiumZone : settings.premiumColor;
        textColor = isMono ? mono.bear : colored.red;
      } else if (z.kind === "DISCOUNT") {
        fill = isMono ? mono.discountZone : settings.discountColor;
        textColor = isMono ? mono.bull : colored.green;
      } else {
        fill = isMono ? mono.equilibriumZone : settings.equilibriumColor;
        textColor = isMono ? mono.neutral : colored.gray;
      }

      ctx.save();
      ctx.fillStyle = fill;
      ctx.fillRect(x1, top, x2 - x1, h);

      ctx.font = getLabelFont("Small", 600);
      ctx.fillStyle = textColor;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      const labelX = x1 + (x2 - x1) * 0.5;
      const labelY =
        z.kind === "PREMIUM"
          ? top + Math.min(12, h / 2)
          : z.kind === "DISCOUNT"
          ? top + h - Math.min(12, h / 2)
          : top + h / 2;
      ctx.fillText(z.label, labelX, labelY);
      ctx.restore();
    }
  }

  // ------------------------------------------------------------------
  // 2. Order Blocks (Internal: no border; Swing: crisp border; extend right)
  // ------------------------------------------------------------------
  const drawObList = (obs: typeof smc.internalOrderBlocks, isSwing: boolean) => {
    for (const ob of obs) {
      if (!allowIrlErl(ob.irlErl)) continue;
      const yTop = projector.priceToY(ob.top);
      const yBot = projector.priceToY(ob.bottom);
      if (yTop === null || yBot === null || !Number.isFinite(yTop) || !Number.isFinite(yBot)) continue;
      const x1Raw = resolveTimeCoordinate(ob.startTime, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth - 4, x1Raw));
      const x2 = plotWidth;
      const top = Math.min(yTop, yBot);
      const h = Math.max(2, Math.abs(yBot - yTop));
      const isBull = ob.direction === "BULLISH";

      const fill = isMono
        ? isSwing
          ? isBull
            ? mono.swingBullOb
            : mono.swingBearOb
          : isBull
          ? mono.internalBullOb
          : mono.internalBearOb
        : isSwing
        ? isBull
          ? settings.swingBullOBColor
          : settings.swingBearOBColor
        : isBull
        ? settings.internalBullOBColor
        : settings.internalBearOBColor;

      ctx.save();
      ctx.fillStyle = fill;
      ctx.fillRect(x1, top, x2 - x1, h);

      // Swing OB has border; Internal OB has NO border (exact Pine spec)
      if (isSwing) {
        ctx.strokeStyle = isMono
          ? isBull
            ? mono.swingBullObBorder
            : mono.swingBearObBorder
          : deriveBorderColorLocal(fill, 0.85);
        ctx.lineWidth = 1;
        ctx.strokeRect(
          Math.round(x1) + 0.5,
          Math.round(top) + 0.5,
          Math.max(1, Math.round(x2 - x1) - 1),
          Math.max(1, Math.round(h) - 1)
        );
      }
      drawCenteredZoneLabel(ctx, "OB", x1, top, x2, top + h, plotWidth, plotHeight, theme);
      ctx.restore();
    }
  };

  if (settings.showSwingOB) drawObList(smc.swingOrderBlocks, true);
  if (settings.showInternalOB) drawObList(smc.internalOrderBlocks, false);

  // ------------------------------------------------------------------
  // 3. Fair Value Gaps (2 stacked half-boxes, extended by fvgExtend bars)
  // ------------------------------------------------------------------
  if (settings.showFvg && allowIrlErl("IRL")) {
    for (const fvg of smc.fairValueGaps) {
      const yTop = projector.priceToY(fvg.top);
      const yMid = projector.priceToY(fvg.midpoint);
      const yBot = projector.priceToY(fvg.bottom);
      if (
        yTop === null ||
        yMid === null ||
        yBot === null ||
        !Number.isFinite(yTop) ||
        !Number.isFinite(yMid) ||
        !Number.isFinite(yBot)
      ) {
        continue;
      }
      const x1Raw = resolveTimeCoordinate(fvg.startTime, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth - 2, x1Raw));
      const x2 = Math.min(plotWidth, Math.max(x1 + 8, lastCandleX + fvg.extendBars * barSpacingPx));
      const w = Math.max(2, x2 - x1);
      const isBull = fvg.direction === "BULLISH";
      const fill = isMono
        ? isBull
          ? mono.bullFvg
          : mono.bearFvg
        : isBull
        ? settings.fvgBullColor
        : settings.fvgBearColor;

      const topY = Math.min(yTop, yBot);
      const midY = Math.max(topY, Math.min(Math.max(yTop, yBot), yMid));
      const botY = Math.max(yTop, yBot);

      ctx.save();
      ctx.fillStyle = fill;
      // Upper half box
      ctx.fillRect(x1, topY, w, Math.max(1, midY - topY));
      // Lower half box
      ctx.fillRect(x1, midY, w, Math.max(1, botY - midY));

      // Subtle midpoint seam between stacked boxes
      ctx.strokeStyle = deriveBorderColorLocal(fill, 0.35);
      ctx.lineWidth = 0.75;
      ctx.beginPath();
      ctx.moveTo(x1, Math.round(midY) + 0.5);
      ctx.lineTo(x2, Math.round(midY) + 0.5);
      ctx.stroke();
      drawCenteredZoneLabel(ctx, "FVG", x1, topY, x1 + w, botY, plotWidth, plotHeight, theme);
      ctx.restore();
    }
  }

  // ------------------------------------------------------------------
  // 4. MTF Highs & Lows (Daily PDH/PDL, Weekly PWH/PWL, Monthly PMH/PML)
  // ------------------------------------------------------------------
  if (allowIrlErl("ERL") && mtfLevels.length > 0) {
    for (const lvl of mtfLevels) {
      const enabled =
        (lvl.period === "D" && settings.showDailyHL) ||
        (lvl.period === "W" && settings.showWeeklyHL) ||
        (lvl.period === "M" && settings.showMonthlyHL);
      if (!enabled) continue;

      const y = projector.priceToY(lvl.price);
      if (y === null || !Number.isFinite(y) || y < -16 || y > plotHeight + 16) continue;
      const x1Raw = resolveTimeCoordinate(lvl.startTime, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth - 20, x1Raw));
      const yr = Math.round(y) + 0.5;

      const style =
        lvl.period === "D"
          ? settings.dailyStyle
          : lvl.period === "W"
          ? settings.weeklyStyle
          : settings.monthlyStyle;
      const rawColor =
        lvl.period === "D"
          ? settings.dailyColor
          : lvl.period === "W"
          ? settings.weeklyColor
          : settings.monthlyColor;
      const color = isMono ? mono.neutral : rawColor;

      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.setLineDash(getLineDashPattern(style));
      ctx.beginPath();
      ctx.moveTo(x1, yr);
      ctx.lineTo(plotWidth, yr);
      ctx.stroke();
      ctx.setLineDash([]);

      ctx.font = getLabelFont("Tiny", 600);
      ctx.fillStyle = color;
      ctx.textAlign = "right";
      ctx.textBaseline = "bottom";
      ctx.fillText(lvl.code, plotWidth - 6, yr - 2);
      ctx.restore();
    }
  }

  // ------------------------------------------------------------------
  // 5. Strong / Weak High & Low (right-extended line + label + right-edge tag)
  // ------------------------------------------------------------------
  if (settings.showStrongWeakHL && allowIrlErl("ERL")) {
    for (const sw of smc.strongWeakLevels) {
      const y = projector.priceToY(sw.price);
      if (y === null || !Number.isFinite(y) || y < -16 || y > plotHeight + 16) continue;
      const x1Raw = resolveTimeCoordinate(sw.startTime, projector, true);
      if (x1Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth - 20, x1Raw));
      const yr = Math.round(y) + 0.5;
      const isHigh = sw.kind === "HIGH";
      const color = isMono
        ? isHigh
          ? mono.bear
          : mono.bull
        : isHigh
        ? settings.swingBearishColor
        : settings.swingBullishColor;

      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      if (!sw.isStrong) ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x1, yr);
      ctx.lineTo(plotWidth, yr);
      ctx.stroke();
      ctx.setLineDash([]);

      // Tiny label at right end of line
      ctx.font = getLabelFont("Tiny", 600);
      ctx.fillStyle = color;
      ctx.textAlign = "right";
      ctx.textBaseline = isHigh ? "bottom" : "top";
      ctx.fillText(sw.label, plotWidth - 46, isHigh ? yr - 3 : yr + 3);

      // Compact right-axis High / Low tag badge (like Image 1)
      const tagText = isHigh ? `High ${sw.price.toFixed(digits)}` : `Low ${sw.price.toFixed(digits)}`;
      ctx.font = "600 9px 'JetBrains Mono', monospace";
      const tagW = Math.min(86, ctx.measureText(tagText).width + 8);
      const tagH = 14;
      const tagX = plotWidth - tagW - 2;
      const tagY = Math.max(2, Math.min(plotHeight - tagH - 2, yr - tagH / 2));
      ctx.fillStyle = color;
      ctx.fillRect(tagX, tagY, tagW, tagH);
      ctx.fillStyle = "#FFFFFF";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(tagText, tagX + tagW / 2, tagY + tagH / 2 + 0.5);
      ctx.restore();
    }
  }

  // ------------------------------------------------------------------
  // 6. EQH / EQL (dotted line between two pivots + centered label)
  // ------------------------------------------------------------------
  if (settings.showEqhEql && allowIrlErl("ERL")) {
    for (const eq of smc.equalHighsLows) {
      const y1 = projector.priceToY(eq.startPrice);
      const y2 = projector.priceToY(eq.endPrice);
      const x1 = resolveTimeCoordinate(eq.startTime, projector, false);
      const x2 = resolveTimeCoordinate(eq.endTime, projector, false);
      if (
        y1 === null ||
        y2 === null ||
        x1 === null ||
        x2 === null ||
        !Number.isFinite(y1) ||
        !Number.isFinite(y2)
      ) {
        continue;
      }
      if (Math.max(x1, x2) < 0 || Math.min(x1, x2) > plotWidth) continue;

      const isHigh = eq.tag === "EQH";
      const color = isMono
        ? isHigh
          ? mono.bear
          : mono.bull
        : isHigh
        ? settings.swingBearishColor
        : settings.swingBullishColor;

      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 2.5]);
      ctx.beginPath();
      ctx.moveTo(x1, Math.round(y1) + 0.5);
      ctx.lineTo(x2, Math.round(y2) + 0.5);
      ctx.stroke();
      ctx.setLineDash([]);

      const midX = (x1 + x2) / 2;
      const midY = (y1 + y2) / 2;
      ctx.font = getLabelFont(settings.eqhLabelSize, 600);
      ctx.fillStyle = color;
      ctx.textAlign = "center";
      ctx.textBaseline = isHigh ? "bottom" : "top";
      ctx.fillText(eq.tag, midX, isHigh ? midY - 3 : midY + 3);
      ctx.restore();
    }
  }

  // ------------------------------------------------------------------
  // 7. Market Structure (Internal: dashed; Swing: solid; centered BOS/CHoCH)
  // ------------------------------------------------------------------
  const drawStructureList = (
    list: typeof smc.internalStructures,
    isSwing: boolean
  ) => {
    const bullFilter = isSwing ? settings.swingBullishFilter : settings.internalBullishFilter;
    const bearFilter = isSwing ? settings.swingBearishFilter : settings.internalBearishFilter;
    const labelSize = isSwing ? settings.swingLabelSize : settings.internalLabelSize;

    for (const ev of list) {
      if (!allowIrlErl(ev.irlErl)) continue;
      const isBull = ev.direction === "BULLISH";
      const activeFilter = isBull ? bullFilter : bearFilter;
      if (activeFilter !== "All" && ev.tag !== activeFilter) continue;

      const y = projector.priceToY(ev.price);
      if (y === null || !Number.isFinite(y) || y < -16 || y > plotHeight + 16) continue;
      const x1Raw = resolveTimeCoordinate(ev.startTime, projector, true);
      const x2Raw = resolveTimeCoordinate(ev.endTime, projector, false);
      if (x1Raw === null || x2Raw === null) continue;
      const x1 = Math.max(0, Math.min(plotWidth, Math.min(x1Raw, x2Raw)));
      const x2 = Math.max(x1 + 4, Math.min(plotWidth, Math.max(x1Raw, x2Raw)));
      if (x2 <= 0 || x1 >= plotWidth) continue;

      const color = isMono
        ? isBull
          ? mono.bull
          : mono.bear
        : isBull
        ? isSwing
          ? settings.swingBullishColor
          : settings.internalBullishColor
        : isSwing
        ? settings.swingBearishColor
        : settings.internalBearishColor;

      const yr = Math.round(y) + 0.5;
      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = isSwing ? 1.25 : 1;
      if (!isSwing) ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x1, yr);
      ctx.lineTo(x2, yr);
      ctx.stroke();
      ctx.setLineDash([]);

      // Centered BOS / CHoCH text, NO background, colored same as line
      ctx.font = getLabelFont(labelSize, isSwing ? 700 : 600);
      ctx.fillStyle = color;
      ctx.textAlign = "center";
      ctx.textBaseline = isBull ? "bottom" : "top";
      ctx.fillText(ev.tag, (x1 + x2) / 2, isBull ? yr - 3 : yr + 3);
      ctx.restore();
    }
  };

  if (settings.showInternalStructure) drawStructureList(smc.internalStructures, false);
  if (settings.showSwingStructure) drawStructureList(smc.swingStructures, true);

  // ------------------------------------------------------------------
  // 8. Swing Points (HH / HL / LH / LL)
  // ------------------------------------------------------------------
  if (settings.showSwingPoints && allowIrlErl("ERL")) {
    ctx.save();
    ctx.font = getLabelFont(settings.swingLabelSize, 700);
    ctx.textAlign = "center";
    for (const sp of smc.swingPoints) {
      const x = resolveTimeCoordinate(sp.time, projector, false);
      const y = projector.priceToY(sp.price);
      if (x === null || y === null || !Number.isFinite(y) || x < 0 || x > plotWidth) continue;
      const isHigh = sp.tag === "HH" || sp.tag === "LH";
      ctx.fillStyle = isMono
        ? isHigh
          ? mono.bear
          : mono.bull
        : isHigh
        ? settings.swingBearishColor
        : settings.swingBullishColor;
      ctx.textBaseline = isHigh ? "bottom" : "top";
      ctx.fillText(sp.tag, x, isHigh ? y - 6 : y + 6);
    }
    ctx.restore();
  }

  ctx.restore();
}
