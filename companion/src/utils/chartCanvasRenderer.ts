import type { EngineDrawingItem } from "./chartDrawingsSchema";

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
  highlightedId: string | null
): void {
  ctx.clearRect(0, 0, plotWidth, plotHeight);
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
  const sorted = [...projected].sort(
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

      // Allowed permanent text inside FVG/OB box ONLY
      if (h >= 12 && w >= 24) {
        const boxText = item.subtype === "IFVG" ? "IFVG" : item.type === "OB" ? "OB" : "FVG";
        ctx.font = "700 10px 'Plus Jakarta Sans', system-ui, sans-serif";
        ctx.fillStyle = isBear ? "#B91C1C" : CANVAS_THEME.fvgText;
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(boxText, p.x1 + w / 2, p.y1 + h / 2);
      }
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
