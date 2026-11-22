import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from "lightweight-charts";
import {
  Activity,
  Clock,
  Eye,
  Layers,
  Maximize2,
  Radio,
  ShieldCheck,
  Target,
  TrendingUp,
} from "lucide-react";
import {
  ChartSymbol,
  ChartTimeframe,
  DataFeedStatus,
  SymbolChartBundle,
} from "../services/dashboardDataAdapter";
import {
  calculateTradeZones,
  RawPriceLabelItem,
  ResolvedPriceLabelItem,
  resolveLabelCollisions,
} from "../utils/tradeChartMath";

export interface OverlayTogglesState {
  liquidity: boolean;
  fvgOb: boolean;
  structure: boolean;
  sessions: boolean;
  tradeLabels: boolean;
}

interface LiveTradingChartProps {
  bundle: SymbolChartBundle;
  selectedSymbol: ChartSymbol;
  selectedTimeframe: ChartTimeframe;
  feedStatus: DataFeedStatus;
  onSelectSymbol: (sym: ChartSymbol) => void;
  onSelectTimeframe: (tf: ChartTimeframe) => void;
}

interface ProjectedZoneBox {
  id: string;
  topY: number;
  heightPx: number;
  leftX: number;
  kind: "RISK" | "REWARD_TP1" | "REWARD_TP2" | "FVG_BULL" | "FVG_BEAR" | "OB_BULL" | "OB_BEAR";
  label: string;
}

interface ProjectedLineLevel {
  id: string;
  y: number;
  price: number;
  style: "solid" | "dashed" | "dotted";
  color: string;
  startX: number;
}

interface ProjectedAnnotationPin {
  id: string;
  x: number;
  y: number;
  label: string;
  detail: string;
  tone: "buy" | "sell" | "be" | "partial" | "tp" | "sl" | "closed" | "mss" | "choch";
}

interface ProjectedSessionBand {
  id: string;
  leftX: number;
  widthPx: number;
  label: string;
  color: string;
}

const SYMBOLS: ChartSymbol[] = ["XAUUSD", "USDJPY", "BTCUSD"];
const TIMEFRAMES: ChartTimeframe[] = ["M1", "M5", "M15", "H1", "H4"];

export const LiveTradingChart: React.FC<LiveTradingChartProps> = ({
  bundle,
  selectedSymbol,
  selectedTimeframe,
  feedStatus,
  onSelectSymbol,
  onSelectTimeframe,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const [overlays, setOverlays] = useState<OverlayTogglesState>({
    liquidity: true,
    fvgOb: true,
    structure: true,
    sessions: true,
    tradeLabels: true,
  });

  const [chartDims, setChartDims] = useState<{ width: number; height: number }>({
    width: 760,
    height: 440,
  });
  const [resolvedLabels, setResolvedLabels] = useState<ResolvedPriceLabelItem[]>([]);
  const [zoneBoxes, setZoneBoxes] = useState<ProjectedZoneBox[]>([]);
  const [levelLines, setLevelLines] = useState<ProjectedLineLevel[]>([]);
  const [annotationPins, setAnnotationPins] = useState<ProjectedAnnotationPin[]>([]);
  const [sessionBands, setSessionBands] = useState<ProjectedSessionBand[]>([]);

  const toggleOverlay = (key: keyof OverlayTogglesState) => {
    setOverlays((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const primaryTrade = bundle.trades[0] || null;

  // Compute pixel coordinates for zones, lines, annotations, and collision-free labels
  const recomputeOverlayGeometry = useCallback(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;

    const rect = container.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width));
    const height = Math.max(260, Math.floor(rect.height));
    const plotBottom = Math.max(180, height - 30); // Leave bottom time-axis clear
    const plotRight = Math.max(200, width - 74); // Leave right price-axis scale clear

    const priceToY = (price: number): number | null => {
      try {
        const y = series.priceToCoordinate(price);
        if (y === null || !Number.isFinite(y)) return null;
        return Number(y);
      } catch {
        return null;
      }
    };

    const timeToX = (timeSec: number): number | null => {
      try {
        const x = chart.timeScale().timeToCoordinate(timeSec as UTCTimestamp);
        if (x === null || !Number.isFinite(x)) return null;
        return Number(x);
      } catch {
        return null;
      }
    };

    const nextZones: ProjectedZoneBox[] = [];
    const nextLines: ProjectedLineLevel[] = [];
    const rawLabels: RawPriceLabelItem[] = [];
    const nextPins: ProjectedAnnotationPin[] = [];
    const nextSessions: ProjectedSessionBand[] = [];

    // 1. Sessions shading bands
    if (overlays.sessions) {
      for (const sess of bundle.sessions) {
        const x1 = timeToX(sess.startTime) ?? 20;
        const x2 = timeToX(sess.endTime) ?? plotRight - 10;
        const left = Math.max(0, Math.min(x1, x2));
        const right = Math.min(plotRight, Math.max(x1, x2));
        if (right - left > 24) {
          nextSessions.push({
            id: sess.id,
            leftX: left,
            widthPx: right - left,
            label: sess.label,
            color: sess.color,
          });
        }
      }
    }

    // 2. FVG / Order Block boxes
    if (overlays.fvgOb) {
      for (const z of bundle.fvgObZones) {
        const yTop = priceToY(z.topPrice);
        const yBot = priceToY(z.bottomPrice);
        if (yTop !== null && yBot !== null) {
          const top = Math.max(6, Math.min(yTop, yBot));
          const bot = Math.min(plotBottom - 4, Math.max(yTop, yBot));
          const startX = Math.max(12, Math.min(plotRight - 80, timeToX(z.startTime) ?? 48));
          nextZones.push({
            id: z.id,
            topY: top,
            heightPx: Math.max(12, bot - top),
            leftX: startX,
            kind:
              z.kind === "FVG"
                ? z.bias === "BULLISH"
                  ? "FVG_BULL"
                  : "FVG_BEAR"
                : z.bias === "BULLISH"
                ? "OB_BULL"
                : "OB_BEAR",
            label: `${z.kind} · ${z.label}`,
          });
        }
      }
    }

    // 3. Liquidity Levels (PWH / PDH / PDL / PWL)
    if (overlays.liquidity) {
      for (const liq of bundle.liquidityLevels) {
        const y = priceToY(liq.price);
        if (y !== null && y >= 6 && y <= plotBottom) {
          nextLines.push({
            id: liq.id,
            y,
            price: liq.price,
            style: liq.swept ? "dotted" : "dashed",
            color: liq.side === "HIGH" ? "rgba(251, 191, 36, 0.55)" : "rgba(56, 189, 248, 0.55)",
            startX: 16,
          });
          rawLabels.push({
            id: liq.id,
            price: liq.price,
            idealY: y,
            label: `${liq.code} ${liq.price.toFixed(bundle.digits)}`,
            sublabel: liq.swept ? "SWEPT" : "POOL",
            tone: "liquidity",
          });
        }
      }
    }

    // 4. Structure Breaks (MSS / CHoCH)
    if (overlays.structure) {
      for (const st of bundle.structureBreaks) {
        const y = priceToY(st.price);
        const x = timeToX(st.time) ?? Math.floor(plotRight * 0.55);
        if (y !== null && y >= 14 && y <= plotBottom - 10) {
          nextPins.push({
            id: st.id,
            x: Math.max(40, Math.min(plotRight - 140, x)),
            y,
            label: st.label,
            detail: `@ ${st.price.toFixed(bundle.digits)}`,
            tone: st.kind === "MSS" ? "mss" : "choch",
          });
        }
      }
    }

    // 5. Bot Trade Overlays: Entry, SL, Ghost Initial SL, TP1, TP2, Shaded Risk/Reward Zones, Event Annotations
    for (const trade of bundle.trades) {
      const zones = calculateTradeZones({
        direction: trade.direction,
        entryPrice: trade.entryPrice,
        stopLoss: trade.stopLoss,
        initialStopLoss: trade.initialStopLoss,
        tp1: trade.tp1,
        tp2: trade.tp2,
      });

      const entryStartX = Math.max(20, Math.min(plotRight - 120, timeToX(trade.entryTime) ?? Math.floor(plotRight * 0.42)));

      if (overlays.tradeLabels) {
        // Risk Zone Shading
        if (zones.riskZone.valid) {
          const y1 = priceToY(zones.riskZone.topPrice);
          const y2 = priceToY(zones.riskZone.bottomPrice);
          if (y1 !== null && y2 !== null) {
            const top = Math.max(4, Math.min(y1, y2));
            const bot = Math.min(plotBottom, Math.max(y1, y2));
            nextZones.push({
              id: `zone-risk-${trade.ticket}`,
              topY: top,
              heightPx: Math.max(8, bot - top),
              leftX: entryStartX,
              kind: "RISK",
              label: `RISK ZONE (1.0R)`,
            });
          }
        }

        // Reward Zone TP2 Shading
        if (zones.rewardZoneTp2.valid) {
          const y1 = priceToY(zones.rewardZoneTp2.topPrice);
          const y2 = priceToY(zones.rewardZoneTp2.bottomPrice);
          if (y1 !== null && y2 !== null) {
            const top = Math.max(4, Math.min(y1, y2));
            const bot = Math.min(plotBottom, Math.max(y1, y2));
            nextZones.push({
              id: `zone-reward2-${trade.ticket}`,
              topY: top,
              heightPx: Math.max(10, bot - top),
              leftX: entryStartX,
              kind: "REWARD_TP2",
              label: `REWARD ZONE (+${trade.tp2R.toFixed(2)}R)`,
            });
          }
        }

        // Entry Line & Badge
        const entryY = priceToY(trade.entryPrice);
        if (entryY !== null) {
          nextLines.push({
            id: `line-entry-${trade.ticket}`,
            y: entryY,
            price: trade.entryPrice,
            style: "solid",
            color: trade.direction === "BUY" ? "#38bdf8" : "#f43f5e",
            startX: entryStartX,
          });
          rawLabels.push({
            id: `lbl-entry-${trade.ticket}`,
            price: trade.entryPrice,
            idealY: entryY,
            label: `${trade.direction} ${trade.volume.toFixed(2)}L · ${trade.entryPrice.toFixed(bundle.digits)}`,
            sublabel: `Score ${trade.qualityScore} · #${trade.ticket}`,
            tone: "entry",
          });
        }

        // Active Stop Loss Line & Badge (Red)
        const slY = priceToY(trade.stopLoss);
        if (slY !== null && trade.stopLoss > 0) {
          nextLines.push({
            id: `line-sl-${trade.ticket}`,
            y: slY,
            price: trade.stopLoss,
            style: "solid",
            color: "#ef4444",
            startX: entryStartX,
          });
          const isBeOrPositive =
            trade.direction === "BUY"
              ? trade.stopLoss >= trade.entryPrice
              : trade.stopLoss <= trade.entryPrice;
          rawLabels.push({
            id: `lbl-sl-${trade.ticket}`,
            price: trade.stopLoss,
            idealY: slY,
            label: `SL ${trade.stopLoss.toFixed(bundle.digits)}`,
            sublabel: isBeOrPositive ? "BE+ LOCKED" : "-1.00R STOP",
            tone: "sl",
          });
        }

        // Ghosted Initial Stop Loss when moved
        if (zones.ghostInitialSlPrice !== null) {
          const ghostY = priceToY(zones.ghostInitialSlPrice);
          if (ghostY !== null) {
            nextLines.push({
              id: `line-ghost-sl-${trade.ticket}`,
              y: ghostY,
              price: zones.ghostInitialSlPrice,
              style: "dashed",
              color: "rgba(248, 113, 113, 0.45)",
              startX: entryStartX,
            });
            rawLabels.push({
              id: `lbl-ghost-sl-${trade.ticket}`,
              price: zones.ghostInitialSlPrice,
              idealY: ghostY,
              label: `INIT SL ${zones.ghostInitialSlPrice.toFixed(bundle.digits)}`,
              sublabel: "GHOST (MOVED)",
              tone: "ghost_sl",
            });
          }
        }

        // TP1 Line & Badge (Green)
        if (trade.tp1 > 0) {
          const tp1Y = priceToY(trade.tp1);
          if (tp1Y !== null) {
            nextLines.push({
              id: `line-tp1-${trade.ticket}`,
              y: tp1Y,
              price: trade.tp1,
              style: "dashed",
              color: "#10b981",
              startX: entryStartX,
            });
            rawLabels.push({
              id: `lbl-tp1-${trade.ticket}`,
              price: trade.tp1,
              idealY: tp1Y,
              label: `TP1 ${trade.tp1.toFixed(bundle.digits)}`,
              sublabel: `+${trade.tp1R.toFixed(2)}R (50%)`,
              tone: "tp1",
            });
          }
        }

        // TP2 Line & Badge (Green)
        if (trade.tp2 > 0) {
          const tp2Y = priceToY(trade.tp2);
          if (tp2Y !== null) {
            nextLines.push({
              id: `line-tp2-${trade.ticket}`,
              y: tp2Y,
              price: trade.tp2,
              style: "solid",
              color: "#059669",
              startX: entryStartX,
            });
            rawLabels.push({
              id: `lbl-tp2-${trade.ticket}`,
              price: trade.tp2,
              idealY: tp2Y,
              label: `TP2 ${trade.tp2.toFixed(bundle.digits)}`,
              sublabel: `+${trade.tp2R.toFixed(2)}R TARGET`,
              tone: "tp2",
            });
          }
        }

        // Event Annotations (Entry marker, Break-Even moved, Partial close, SL/TP hit)
        trade.annotations.forEach((ann, idx) => {
          const ay = priceToY(ann.price);
          const ax = timeToX(ann.time) ?? entryStartX + idx * 55;
          if (ay !== null && ay >= 10 && ay <= plotBottom - 10) {
            nextPins.push({
              id: ann.id,
              x: Math.max(24, Math.min(plotRight - 165, ax)),
              y: ay,
              label: ann.label,
              detail: ann.detail,
              tone: ann.tone,
            });
          }
        });
      }
    }

    // 6. Live Price Tag with Floating R
    const liveY = priceToY(bundle.bid);
    if (liveY !== null) {
      const floatR = primaryTrade ? primaryTrade.floatingR : 0;
      const floatPnl = primaryTrade ? primaryTrade.floatingPnl : 0;
      const rPrefix = floatR >= 0 ? "+" : "";
      const pnlPrefix = floatPnl >= 0 ? "+" : "";
      rawLabels.push({
        id: `lbl-live-${bundle.symbol}`,
        price: bundle.bid,
        idealY: liveY,
        label: `LIVE ${bundle.bid.toFixed(bundle.digits)}`,
        sublabel: primaryTrade
          ? `${rPrefix}${floatR.toFixed(2)}R (${pnlPrefix}$${floatPnl.toFixed(2)})`
          : `Spread ${bundle.spreadPoints} pts`,
        tone: "live",
      });
    }

    // Run collision-aware vertical label placement solver so labels never overlap or clip
    const nonOverlapping = resolveLabelCollisions(rawLabels, {
      minY: 8,
      maxY: plotBottom - 6,
      minGapPx: 24,
      defaultHeightPx: 21,
    });

    // Also de-collide annotation pins vertically if two share similar X and Y
    const sortedPins = [...nextPins].sort((a, b) => a.y - b.y);
    for (let i = 1; i < sortedPins.length; i++) {
      if (
        Math.abs(sortedPins[i].x - sortedPins[i - 1].x) < 115 &&
        sortedPins[i].y - sortedPins[i - 1].y < 24
      ) {
        sortedPins[i] = {
          ...sortedPins[i],
          y: Math.min(plotBottom - 14, sortedPins[i - 1].y + 25),
        };
      }
    }

    setChartDims({ width, height });
    setZoneBoxes(nextZones);
    setLevelLines(nextLines);
    setResolvedLabels(nonOverlapping);
    setAnnotationPins(sortedPins);
    setSessionBands(nextSessions);
  }, [bundle, overlays, primaryTrade]);

  // Initialize lightweight-charts instance and ResizeObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialRect = container.getBoundingClientRect();
    const chart = createChart(container, {
      width: Math.max(320, Math.floor(initialRect.width || 760)),
      height: Math.max(260, Math.floor(initialRect.height || 440)),
      layout: {
        background: { type: ColorType.Solid, color: "#070a0e" },
        textColor: "#94a3b8",
        fontFamily: "'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(30, 41, 59, 0.45)" },
        horzLines: { color: "rgba(30, 41, 59, 0.45)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(56, 189, 248, 0.45)",
          labelBackgroundColor: "#0f172a",
        },
        horzLine: {
          color: "rgba(56, 189, 248, 0.45)",
          labelBackgroundColor: "#0f172a",
        },
      },
      rightPriceScale: {
        borderColor: "#1e293b",
        scaleMargins: {
          top: 0.08,
          bottom: 0.08,
        },
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: 9,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",
      downColor: "#ef4444",
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
      priceFormat: {
        type: "price",
        precision: bundle.digits,
        minMove: bundle.point,
      },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;

    const handleVisibleChange = () => {
      recomputeOverlayGeometry();
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(handleVisibleChange);

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 100 && height > 100 && chartRef.current) {
          chartRef.current.applyOptions({
            width: Math.floor(width),
            height: Math.floor(height),
          });
          recomputeOverlayGeometry();
        }
      }
    });

    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handleVisibleChange);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // Update candle series data & price precision when symbol/timeframe/bundle updates
  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    series.applyOptions({
      priceFormat: {
        type: "price",
        precision: bundle.digits,
        minMove: bundle.point,
      },
    });

    const formatted = bundle.candles.map((c) => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    series.setData(formatted);

    // Ensure auto-scale price range spans Entry, SL, Ghost Initial SL, TP1, TP2, and Liquidity levels
    series.applyOptions({
      autoscaleInfoProvider: (original: () => { priceRange: { minValue: number; maxValue: number } } | null) => {
        const res = original();
        if (!res || !res.priceRange) return res;
        let minVal = res.priceRange.minValue;
        let maxVal = res.priceRange.maxValue;
        for (const t of bundle.trades) {
          for (const p of [t.entryPrice, t.stopLoss, t.initialStopLoss, t.tp1, t.tp2]) {
            if (p > 0) {
              minVal = Math.min(minVal, p);
              maxVal = Math.max(maxVal, p);
            }
          }
        }
        const pad = (maxVal - minVal) * 0.06;
        return {
          priceRange: {
            minValue: minVal - pad,
            maxValue: maxVal + pad,
          },
        };
      },
    });

    requestAnimationFrame(() => {
      recomputeOverlayGeometry();
    });
  }, [bundle, recomputeOverlayGeometry]);

  const handleFitView = () => {
    if (chartRef.current) {
      chartRef.current.timeScale().fitContent();
      requestAnimationFrame(() => recomputeOverlayGeometry());
    }
  };

  const labelToneClasses: Record<ResolvedPriceLabelItem["tone"], string> = useMemo(
    () => ({
      entry: "bg-sky-950/95 border-sky-400 text-sky-100 shadow-sm",
      sl: "bg-rose-950/95 border-rose-500 text-rose-100 shadow-sm",
      ghost_sl: "bg-slate-900/90 border-rose-500/50 border-dashed text-rose-300/90",
      tp1: "bg-emerald-950/95 border-emerald-400 text-emerald-100 shadow-sm",
      tp2: "bg-emerald-900/95 border-emerald-300 text-emerald-50 shadow-sm",
      live: "bg-amber-950/95 border-amber-400 text-amber-100 shadow-md",
      liquidity: "bg-slate-900/90 border-amber-500/50 text-amber-200",
      structure: "bg-slate-900/90 border-purple-400/60 text-purple-200",
    }),
    []
  );

  const pinToneClasses: Record<ProjectedAnnotationPin["tone"], string> = useMemo(
    () => ({
      buy: "bg-emerald-950/95 border-emerald-400 text-emerald-200",
      sell: "bg-rose-950/95 border-rose-400 text-rose-200",
      be: "bg-sky-950/95 border-sky-400 text-sky-200",
      partial: "bg-emerald-900/95 border-emerald-300 text-emerald-100",
      tp: "bg-emerald-900/95 border-emerald-300 text-emerald-100",
      sl: "bg-rose-950/95 border-rose-400 text-rose-200",
      closed: "bg-slate-900/95 border-slate-500 text-slate-200",
      mss: "bg-indigo-950/95 border-indigo-400 text-indigo-200",
      choch: "bg-purple-950/95 border-purple-400 text-purple-200",
    }),
    []
  );

  return (
    <section
      aria-label="Live Institutional Execution Chart"
      className="flex flex-col h-full min-h-[460px] bg-[#070a0e] border border-slate-800/90 rounded-xl overflow-hidden"
    >
      {/* Chart Toolbar Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-slate-950/90 border-b border-slate-800/90 shrink-0">
        {/* Left: Symbol Switcher + Live Quote + Timeframes */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5" role="group" aria-label="Select Chart Symbol">
            {SYMBOLS.map((sym) => {
              const active = sym === selectedSymbol;
              return (
                <button
                  key={sym}
                  type="button"
                  onClick={() => onSelectSymbol(sym)}
                  aria-pressed={active}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono font-bold transition ${
                    active
                      ? "bg-sky-600 text-white shadow-xs"
                      : "text-slate-300 hover:text-white hover:bg-slate-800/70"
                  }`}
                >
                  {sym}
                </button>
              );
            })}
          </div>

          {/* Timeframe Selector */}
          <div className="inline-flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5" role="group" aria-label="Select Chart Timeframe">
            {TIMEFRAMES.map((tf) => {
              const active = tf === selectedTimeframe;
              return (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onSelectTimeframe(tf)}
                  aria-pressed={active}
                  className={`px-2 py-1 rounded-md text-[11px] font-mono font-semibold transition ${
                    active
                      ? "bg-slate-700 text-sky-300 border border-sky-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {tf}
                </button>
              );
            })}
          </div>

          {/* Live Bid/Ask + Spread Ticker */}
          <div className="hidden xl:flex items-center space-x-2 px-2.5 py-1 bg-slate-900/90 border border-slate-800 rounded-lg font-mono text-xs">
            <span className="text-slate-400">{bundle.brokerSymbol}</span>
            <span className="text-emerald-400 font-bold">{bundle.bid.toFixed(bundle.digits)}</span>
            <span className="text-slate-600">/</span>
            <span className="text-rose-400 font-bold">{bundle.ask.toFixed(bundle.digits)}</span>
            <span className="text-[11px] text-amber-300 bg-amber-500/10 px-1.5 py-0.5 rounded">
              {bundle.spreadPoints} pts
            </span>
          </div>
        </div>

        {/* Right: Toggleable Overlays + Feed Indicator */}
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => toggleOverlay("liquidity")}
            aria-pressed={overlays.liquidity}
            className={`px-2 py-1 rounded text-[11px] font-medium border transition inline-flex items-center space-x-1 ${
              overlays.liquidity
                ? "bg-amber-950/70 border-amber-500/60 text-amber-200"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>Liquidity (PDL/PWH)</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("fvgOb")}
            aria-pressed={overlays.fvgOb}
            className={`px-2 py-1 rounded text-[11px] font-medium border transition inline-flex items-center space-x-1 ${
              overlays.fvgOb
                ? "bg-sky-950/70 border-sky-500/60 text-sky-200"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <Activity className="w-3 h-3" />
            <span>FVG/OB</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("structure")}
            aria-pressed={overlays.structure}
            className={`px-2 py-1 rounded text-[11px] font-medium border transition inline-flex items-center space-x-1 ${
              overlays.structure
                ? "bg-purple-950/70 border-purple-500/60 text-purple-200"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <TrendingUp className="w-3 h-3" />
            <span>Structure (MSS/CHoCH)</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("sessions")}
            aria-pressed={overlays.sessions}
            className={`px-2 py-1 rounded text-[11px] font-medium border transition inline-flex items-center space-x-1 ${
              overlays.sessions
                ? "bg-teal-950/70 border-teal-500/60 text-teal-200"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <Clock className="w-3 h-3" />
            <span>Sessions</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("tradeLabels")}
            aria-pressed={overlays.tradeLabels}
            className={`px-2 py-1 rounded text-[11px] font-medium border transition inline-flex items-center space-x-1 ${
              overlays.tradeLabels
                ? "bg-emerald-950/80 border-emerald-500/60 text-emerald-200"
                : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <Eye className="w-3 h-3" />
            <span>Trade Labels</span>
          </button>

          <button
            type="button"
            onClick={handleFitView}
            aria-label="Fit chart content to view"
            title="Fit chart content"
            className="p-1.5 rounded bg-slate-900 hover:bg-slate-800 border border-slate-800 text-slate-300"
          >
            <Maximize2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Sub-Header Active Trade Strip */}
      {primaryTrade && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-1.5 bg-slate-900/90 border-b border-slate-800/80 text-xs font-mono shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`px-1.5 py-0.5 rounded font-bold text-[10px] ${
                primaryTrade.direction === "BUY"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
              }`}
            >
              {primaryTrade.direction} {primaryTrade.volume.toFixed(2)}L
            </span>
            <span className="text-slate-200 font-bold">#{primaryTrade.ticket}</span>
            <span className="px-1.5 py-0.5 rounded bg-sky-500/15 text-sky-300 text-[10px] font-sans font-semibold">
              {primaryTrade.ownership} · Score {primaryTrade.qualityScore}/100
            </span>
            <span className="text-slate-400">
              Entry <strong className="text-slate-100">{primaryTrade.entryPrice.toFixed(bundle.digits)}</strong>
            </span>
            <span className="text-rose-300">
              SL <strong>{primaryTrade.stopLoss.toFixed(bundle.digits)}</strong>
              {Math.abs(primaryTrade.initialStopLoss - primaryTrade.stopLoss) > 1e-6 && (
                <span className="text-slate-400 ml-1">
                  (Init {primaryTrade.initialStopLoss.toFixed(bundle.digits)})
                </span>
              )}
            </span>
            <span className="text-emerald-300">
              TP1 <strong>{primaryTrade.tp1.toFixed(bundle.digits)}</strong> (+{primaryTrade.tp1R.toFixed(2)}R)
            </span>
            <span className="text-emerald-400">
              TP2 <strong>{primaryTrade.tp2.toFixed(bundle.digits)}</strong> (+{primaryTrade.tp2R.toFixed(2)}R)
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span
              className={`px-2 py-0.5 rounded font-bold ${
                primaryTrade.floatingPnl >= 0
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                  : "bg-rose-500/20 text-rose-300 border border-rose-500/40"
              }`}
            >
              {primaryTrade.floatingPnl >= 0 ? "+" : ""}${primaryTrade.floatingPnl.toFixed(2)} (
              {primaryTrade.floatingR >= 0 ? "+" : ""}
              {primaryTrade.floatingR.toFixed(2)}R)
            </span>
            <span className="inline-flex items-center space-x-1 text-[10px] font-sans text-emerald-300 bg-emerald-950/70 border border-emerald-500/30 px-2 py-0.5 rounded">
              <ShieldCheck className="w-3 h-3" />
              <span>Tighten-Only SL</span>
            </span>
            <span className="inline-flex items-center space-x-1 text-[10px] font-sans text-slate-300 bg-slate-950 px-2 py-0.5 rounded border border-slate-800">
              <Radio className="w-3 h-3 text-emerald-400 animate-pulse" />
              <span>{feedStatus}</span>
            </span>
          </div>
        </div>
      )}

      {/* Main Chart Viewport — fills 100% remaining height with zero empty space below */}
      <div className="relative flex-1 min-h-0 w-full">
        {/* Lightweight Charts Canvas Mount */}
        <div ref={containerRef} className="absolute inset-0 z-0 w-full h-full" />

        {/* Pointer-events-none Synchronized Institutional Overlay Layer (z-10 above lightweight-charts canvas z-index: 1/2) */}
        <div
          className="absolute inset-0 z-10 pointer-events-none overflow-hidden select-none"
          style={{ right: "72px", bottom: "26px" }}
        >
          {/* 1. Session Background Bands */}
          {sessionBands.map((sb) => (
            <div
              key={sb.id}
              style={{
                left: `${sb.leftX}px`,
                width: `${sb.widthPx}px`,
                backgroundColor: sb.color,
              }}
              className="absolute top-0 bottom-0 border-x border-slate-700/30"
            >
              <span className="inline-block m-1.5 px-1.5 py-0.5 rounded bg-slate-950/80 text-[9px] font-mono text-slate-300 border border-slate-800">
                {sb.label}
              </span>
            </div>
          ))}

          {/* 2. Shaded Risk & Reward Zones + FVG/OB Boxes */}
          {zoneBoxes.map((zb) => {
            const boxStyleByKind: Record<ProjectedZoneBox["kind"], string> = {
              RISK: "bg-rose-500/12 border-y border-rose-500/35",
              REWARD_TP1: "bg-emerald-500/12 border-y border-emerald-500/35",
              REWARD_TP2: "bg-emerald-500/10 border-y border-emerald-400/30",
              FVG_BULL: "bg-sky-500/14 border border-sky-400/40",
              FVG_BEAR: "bg-amber-500/14 border border-amber-400/40",
              OB_BULL: "bg-teal-500/14 border border-teal-400/40",
              OB_BEAR: "bg-purple-500/14 border border-purple-400/40",
            };
            return (
              <div
                key={zb.id}
                style={{
                  top: `${zb.topY}px`,
                  height: `${zb.heightPx}px`,
                  left: `${zb.leftX}px`,
                  right: "0px",
                }}
                className={`absolute ${boxStyleByKind[zb.kind]}`}
              >
                <span className="inline-block ml-1.5 mt-0.5 px-1.5 py-0.2 text-[9px] font-mono font-semibold text-slate-200 bg-slate-950/75 rounded">
                  {zb.label}
                </span>
              </div>
            );
          })}

          {/* 3. Horizontal Level Lines + Connector Ticks to De-Collided Labels */}
          <svg className="absolute inset-0 w-full h-full overflow-visible">
            {levelLines.map((ln) => (
              <line
                key={ln.id}
                x1={ln.startX}
                y1={ln.y}
                x2={chartDims.width}
                y2={ln.y}
                stroke={ln.color}
                strokeWidth={ln.style === "solid" ? 1.5 : 1.15}
                strokeDasharray={
                  ln.style === "dashed" ? "6 4" : ln.style === "dotted" ? "2 3" : undefined
                }
              />
            ))}

            {/* Leader lines connecting true price Y to collision-resolved badge Y when displaced */}
            {resolvedLabels
              .filter((lbl) => lbl.displaced)
              .map((lbl) => (
                <path
                  key={`leader-${lbl.id}`}
                  d={`M ${Math.max(120, chartDims.width - 310)} ${lbl.idealY} L ${Math.max(
                    135,
                    chartDims.width - 292
                  )} ${lbl.resolvedY}`}
                  stroke="rgba(148, 163, 184, 0.55)"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                  fill="none"
                />
              ))}
          </svg>

          {/* 4. Event Annotations (Entry marker, Break-Even moved, Partial close, MSS/CHoCH) */}
          {annotationPins.map((pin) => (
            <div
              key={pin.id}
              style={{
                left: `${pin.x}px`,
                top: `${Math.max(8, pin.y - 11)}px`,
              }}
              className={`absolute px-1.5 py-0.5 rounded border text-[10px] font-mono leading-tight shadow-sm whitespace-nowrap ${
                pinToneClasses[pin.tone]
              }`}
            >
              <div className="font-bold flex items-center space-x-1">
                <Target className="w-2.5 h-2.5 shrink-0" />
                <span>{pin.label}</span>
              </div>
              <div className="text-[9px] opacity-85">{pin.detail}</div>
            </div>
          ))}

          {/* 5. Collision-Aware Right-Aligned Level Labels (Guaranteed Non-Overlapping) */}
          {resolvedLabels.map((lbl) => (
            <div
              key={lbl.id}
              data-testid={`chart-level-label-${lbl.tone}`}
              style={{
                top: `${lbl.resolvedY - 10}px`,
                right: "6px",
              }}
              className={`absolute px-2 py-0.5 rounded border text-[10px] font-mono leading-none flex items-center space-x-1.5 whitespace-nowrap ${
                labelToneClasses[lbl.tone]
              }`}
            >
              <span className="font-bold">{lbl.label}</span>
              {lbl.sublabel && (
                <span className="text-[9px] px-1 py-0.5 rounded bg-black/35 text-slate-200">
                  {lbl.sublabel}
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};
