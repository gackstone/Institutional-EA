import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  IChartApi,
  ISeriesApi,
  LogicalRange,
  UTCTimestamp,
} from "lightweight-charts";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  Bug,
  Camera,
  Clock,
  Eye,
  Layers,
  Maximize2,
  Minimize2,
  Pin,
  Radio,
  RotateCcw,
  Settings,
  ShieldCheck,
  TrendingUp,
  X,
} from "lucide-react";
import {
  ChartSymbol,
  ChartTimeframe,
  DataFeedStatus,
  SymbolChartBundle,
} from "../services/dashboardDataAdapter";
import { getSymbolChipSpec } from "../styles/designTokens";
import { BEAR_COLOR, BULL_COLOR, getChartThemeTokens, LUXALGO_SMC_PALETTE } from "../styles/chartTheme";
import { UI_COPY } from "../constants/uiCopy";
import { useTheme } from "../context/ThemeContext";

const IS_DEV = Boolean((import.meta as any).env?.DEV);
import {
  buildParityDebugReport,
  EngineDrawingItem,
  EngineDrawingsFeed,
  validateEngineDrawingsFeed,
} from "../utils/chartDrawingsSchema";
import {
  drawLuxAlgoSmcOverlaysToCanvas,
  drawProjectedOverlaysToCanvas,
  hitTestProjectedDrawings,
  type MtfLevelInput,
  ProjectedDrawing,
  projectEngineDrawings,
} from "../utils/chartCanvasRenderer";
import { computeLuxAlgoSmc, SMC_BEARISH, SMC_BULLISH } from "../utils/luxalgoSmcEngine";
import {
  applyLayerChipToggle,
  deriveLayerChipStates,
  loadSmcChartSettings,
  saveSmcChartSettings,
  type SmcChartSettings,
} from "../utils/smcChartSettings";
import { SmcSettingsPopover } from "./SmcSettingsPopover";

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
  waitingReason?: string;
  drawingsFeed?: EngineDrawingsFeed | null;
  drawingsError?: string | null;
  onSelectSymbol: (sym: ChartSymbol) => void;
  onSelectTimeframe: (tf: ChartTimeframe) => void;
  onCaptureScreenshot?: (ticket: number, symbol: string, stage: string, dataUrl: string) => void;
}

const SYMBOLS: ChartSymbol[] = ["XAUUSD", "USDJPY", "BTCUSD"];
const TIMEFRAMES: ChartTimeframe[] = ["M1", "M5", "M15", "H1", "H4"];

// Remember visible range per (symbol:timeframe) within the app session
const sessionVisibleRanges = new Map<string, LogicalRange>();

function formatPrice(value: number | undefined | null, digits: number): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value.toFixed(digits);
}

function formatUtcShort(sec: number | null | undefined): string {
  if (!sec || !Number.isFinite(sec)) return "Active";
  const d = new Date(sec * 1000);
  return `${d.toISOString().slice(5, 10)} ${d.toISOString().slice(11, 16)} UTC`;
}

function describeDrawingDetails(item: EngineDrawingItem, digits: number) {
  const pl = item.price_levels;
  const rows: Array<{ label: string; value: string; tone?: "bull" | "bear" | "neutral" }> = [
    { label: "TF / Source", value: `${item.timeframe} · ${item.source}` },
    { label: "Status", value: item.status },
    { label: "Start", value: formatUtcShort(item.start_time) },
    { label: "End", value: formatUtcShort(item.end_time) },
  ];

  if (item.type === "LIQ") {
    rows.unshift({ label: "Level", value: formatPrice(pl.price, digits) });
    if (pl.sweep_time) {
      rows.push({ label: "Swept At", value: formatUtcShort(pl.sweep_time), tone: "bear" });
    }
  } else if (item.type === "STRUCT") {
    rows.unshift({ label: "Break Price", value: formatPrice(pl.price, digits) });
    if (item.meta?.displacement_ratio) {
      rows.push({ label: "Displacement", value: `${Math.round(item.meta.displacement_ratio * 100)}%` });
    }
  } else if (item.type === "FVG" || item.type === "OB") {
    rows.unshift(
      { label: "Top", value: formatPrice(pl.top, digits) },
      { label: "Bottom", value: formatPrice(pl.bottom, digits) }
    );
    if (typeof pl.midpoint === "number") {
      rows.push({ label: "Midpoint", value: formatPrice(pl.midpoint, digits) });
    }
  } else if (item.type === "SESS") {
    if (item.meta?.utc_window) {
      rows.unshift({ label: "Window", value: String(item.meta.utc_window) });
    }
    if (typeof pl.high === "number" && typeof pl.low === "number") {
      rows.push({
        label: "Range",
        value: `${formatPrice(pl.low, digits)} – ${formatPrice(pl.high, digits)}`,
      });
    }
  } else if (item.type === "TRADE") {
    rows.unshift(
      { label: "Entry", value: formatPrice(pl.entry, digits) },
      { label: "SL", value: formatPrice(pl.sl, digits), tone: "bear" },
      { label: "TP", value: formatPrice(pl.tp, digits), tone: "bull" }
    );
    if (typeof pl.initial_sl === "number" && typeof pl.sl === "number" && Math.abs(pl.initial_sl - pl.sl) > 1e-6) {
      rows.push({ label: "Initial SL", value: formatPrice(pl.initial_sl, digits) });
    }
    if (typeof pl.rr === "number" && pl.rr > 0) {
      rows.push({ label: "R:R", value: `1 : ${pl.rr.toFixed(2)}` });
    }
    if (typeof pl.pnl === "number") {
      rows.push({
        label: item.status === "CLOSED" ? "Realized P&L" : "Live P&L",
        value: `${pl.pnl >= 0 ? "+" : ""}$${pl.pnl.toFixed(2)}`,
        tone: pl.pnl >= 0 ? "bull" : "bear",
      });
    }
    if (typeof pl.ticket === "number" && pl.ticket > 0) {
      rows.push({ label: "Ticket", value: `#${pl.ticket} (${pl.ownership || "BOT"})` });
    }
  }

  const title =
    item.type === "TRADE"
      ? `${item.direction === "BULLISH" ? "LONG" : "SHORT"} ${item.subtype}`
      : item.meta?.label
      ? String(item.meta.label)
      : `${item.type} · ${item.subtype}`;

  return { title, rows };
}

export const LiveTradingChart: React.FC<LiveTradingChartProps> = ({
  bundle,
  selectedSymbol,
  selectedTimeframe,
  feedStatus,
  waitingReason,
  drawingsFeed = null,
  drawingsError = null,
  onSelectSymbol,
  onSelectTimeframe,
  onCaptureScreenshot,
}) => {
  const { theme } = useTheme();
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const plotHostRef = useRef<HTMLDivElement | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const overlayCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const projectedRef = useRef<ProjectedDrawing[]>([]);
  const rafIdRef = useRef<number | null>(null);
  const lastRangeKeyRef = useRef<string>("");

  const [committedSettings, setCommittedSettings] = useState<SmcChartSettings>(() =>
    loadSmcChartSettings()
  );
  const [previewSettings, setPreviewSettings] = useState<SmcChartSettings | null>(null);
  const [showSettingsPopover, setShowSettingsPopover] = useState<boolean>(false);
  const activeSettings = previewSettings ?? committedSettings;
  const overlays = useMemo(() => deriveLayerChipStates(activeSettings), [activeSettings]);

  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showJumpLatest, setShowJumpLatest] = useState<boolean>(false);
  const [showDebugOverlay, setShowDebugOverlay] = useState<boolean>(false);

  // Hover & click-to-pin drawing inspection state
  const [hoveredHit, setHoveredHit] = useState<{
    item: EngineDrawingItem;
    x: number;
    y: number;
  } | null>(null);
  const [pinnedHit, setPinnedHit] = useState<{
    item: EngineDrawingItem;
    x: number;
    y: number;
  } | null>(null);

  // OHLC + change readout in toolbar strip (updated on crosshair move, defaults to latest bar)
  const [crosshairOhlc, setCrosshairOhlc] = useState<{
    open: number;
    high: number;
    low: number;
    close: number;
    change: number;
    changePct: number;
    time: number;
  } | null>(null);

  const digits = bundle.digits || (selectedSymbol === "USDJPY" ? 3 : 2);
  const rangeKey = `${selectedSymbol}:${selectedTimeframe}`;

  // Validate engine drawings feed (rejects malformed/wrong-symbol items, applies TF hierarchy)
  const validatedDrawings = useMemo(() => {
    if (!drawingsFeed) {
      return {
        items: [] as EngineDrawingItem[],
        dropped: [] as Array<{ id?: string; reason: string }>,
        counts: { liquidity: 0, fvgOb: 0, structure: 0, sessions: 0, trades: 0 },
        malformedFeed: false,
      };
    }
    const res = validateEngineDrawingsFeed(drawingsFeed, selectedSymbol, selectedTimeframe);
    if (res.dropped.length > 0 && IS_DEV) {
      console.warn("[LiveTradingChart] Dropped malformed/filtered drawings:", res.dropped);
    }
    return res;
  }, [drawingsFeed, selectedSymbol, selectedTimeframe]);

  // Persist committed SMC settings with schema version
  useEffect(() => {
    saveSmcChartSettings(committedSettings);
  }, [committedSettings]);

  // Recompute LuxAlgo SMC ONLY when bar count / closed bar timestamp or detection settings change (never on every tick)
  const smcClosedBarKey = useMemo(() => {
    const len = bundle.candles.length;
    const prevClosedTime = len >= 2 ? bundle.candles[len - 2].time : 0;
    const lastOpenTime = len >= 1 ? bundle.candles[len - 1].time : 0;
    return [
      selectedSymbol,
      selectedTimeframe,
      len,
      prevClosedTime,
      lastOpenTime,
      activeSettings.mode,
      activeSettings.swingPointsLength,
      activeSettings.internalConfluenceFilter ? 1 : 0,
      activeSettings.obFilter,
      activeSettings.obMitigation,
      activeSettings.internalOBCount,
      activeSettings.swingOBCount,
      activeSettings.eqhBarsConfirmation,
      activeSettings.eqhThreshold,
      activeSettings.fvgAutoThreshold ? 1 : 0,
      activeSettings.fvgTimeframe,
      activeSettings.fvgExtend,
    ].join("|");
  }, [
    bundle.candles,
    selectedSymbol,
    selectedTimeframe,
    activeSettings.mode,
    activeSettings.swingPointsLength,
    activeSettings.internalConfluenceFilter,
    activeSettings.obFilter,
    activeSettings.obMitigation,
    activeSettings.internalOBCount,
    activeSettings.swingOBCount,
    activeSettings.eqhBarsConfirmation,
    activeSettings.eqhThreshold,
    activeSettings.fvgAutoThreshold,
    activeSettings.fvgTimeframe,
    activeSettings.fvgExtend,
  ]);

  const smcCandlesRef = useRef(bundle.candles);
  smcCandlesRef.current = bundle.candles;
  const smcSettingsRef = useRef(activeSettings);
  smcSettingsRef.current = activeSettings;

  const smcResult = useMemo(() => {
    return computeLuxAlgoSmc(smcCandlesRef.current, smcSettingsRef.current, selectedTimeframe);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [smcClosedBarKey]);

  // Extract MTF Highs & Lows (PDH/PDL, PWH/PWL, PMH/PML) from backend drawings feed
  const mtfLevels = useMemo<MtfLevelInput[]>(() => {
    const out: MtfLevelInput[] = [];
    for (const item of validatedDrawings.items) {
      if (item.type !== "LIQ" || typeof item.price_levels.price !== "number") continue;
      const st = item.subtype.toUpperCase();
      if (st === "PDH" || st === "PDL") {
        out.push({ code: st, period: "D", price: item.price_levels.price, startTime: item.start_time });
      } else if (st === "PWH" || st === "PWL") {
        out.push({ code: st, period: "W", price: item.price_levels.price, startTime: item.start_time });
      } else if (st === "PMH" || st === "PML") {
        out.push({ code: st, period: "M", price: item.price_levels.price, startTime: item.start_time });
      }
    }
    return out;
  }, [validatedDrawings.items]);

  // Latest bar fallback for OHLC toolbar readout
  const activeOhlc = useMemo(() => {
    if (crosshairOhlc) return crosshairOhlc;
    const last = bundle.candles[bundle.candles.length - 1];
    if (!last) return null;
    const prev = bundle.candles[bundle.candles.length - 2];
    const base = prev ? prev.close : last.open;
    const change = last.close - base;
    const changePct = base > 0 ? (change / base) * 100 : 0;
    return {
      open: last.open,
      high: last.high,
      low: last.low,
      close: last.close,
      change,
      changePct,
      time: last.time,
    };
  }, [crosshairOhlc, bundle.candles]);

  // Schedule single-frame high-DPI canvas redraw (zero DOM churn on ticks/pan)
  const redrawCanvas = useCallback(() => {
    if (rafIdRef.current !== null) return;
    rafIdRef.current = window.requestAnimationFrame(() => {
      rafIdRef.current = null;
      const chart = chartRef.current;
      const series = candleSeriesRef.current;
      const canvas = overlayCanvasRef.current;
      const host = plotHostRef.current;
      if (!chart || !series || !canvas || !host) return;

      const fullW = host.clientWidth;
      const fullH = host.clientHeight;
      if (fullW <= 0 || fullH <= 0) return;

      // Measure actual price/time scale dimensions dynamically
      const priceScaleW = Math.max(52, Math.round(chart.priceScale("right").width() || 68));
      const timeScaleH = Math.max(24, Math.round(chart.timeScale().height() || 28));
      const plotW = Math.max(0, fullW - priceScaleW);
      const plotH = Math.max(0, fullH - timeScaleH);

      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      const backingW = Math.round(plotW * dpr);
      const backingH = Math.round(plotH * dpr);

      if (canvas.width !== backingW || canvas.height !== backingH) {
        canvas.width = backingW;
        canvas.height = backingH;
        canvas.style.width = `${plotW}px`;
        canvas.style.height = `${plotH}px`;
      }

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.save();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, plotW, plotH);

      const projector = {
        timeToX: (t: number) => chart.timeScale().timeToCoordinate(t as UTCTimestamp),
        priceToY: (p: number) => series.priceToCoordinate(p),
        plotWidth: plotW,
        plotHeight: plotH,
        candles: bundle.candles,
      };

      const projected = projectEngineDrawings(
        validatedDrawings.items,
        {
          liquidity: overlays.liquidity,
          fvgOb: overlays.fvgOb,
          structure: overlays.structure,
          sessions: overlays.sessions,
          trades: overlays.tradeLabels,
        },
        projector
      );

      projectedRef.current = projected;
      const activeHighlightId = pinnedHit?.item.id ?? hoveredHit?.item.id ?? null;

      // 1. Session bands (lowest z-order)
      drawProjectedOverlaysToCanvas(ctx, projected, plotW, plotH, activeHighlightId, {
        clear: false,
        onlyTypes: new Set(["SESS"]),
      });

      // 2. LuxAlgo Smart Money Concepts overlays (when enabled for current timeframe)
      if (activeSettings.visibleTimeframes[selectedTimeframe]) {
        drawLuxAlgoSmcOverlaysToCanvas(ctx, smcResult, mtfLevels, activeSettings, projector, digits);
      }

      // 3. Trade position templates on top (LONG POSITION / SHORT POSITION)
      drawProjectedOverlaysToCanvas(ctx, projected, plotW, plotH, activeHighlightId, {
        clear: false,
        onlyTypes: new Set(["TRADE"]),
      });

      ctx.restore();

      // Expose dev parity report on window for quick debugging
      if (IS_DEV) {
        const renderedIds = new Set(projected.map((p) => p.item.id));
        (window as any).__IEA_CHART_PARITY__ = {
          symbol: selectedSymbol,
          timeframe: selectedTimeframe,
          totalEngineItems: validatedDrawings.items.length,
          renderedCount: projected.length,
          counts: validatedDrawings.counts,
          report: buildParityDebugReport(validatedDrawings.items, renderedIds),
        };
      }
    });
  }, [
    validatedDrawings,
    overlays,
    bundle.candles,
    activeSettings,
    smcResult,
    mtfLevels,
    digits,
    hoveredHit?.item.id,
    pinnedHit?.item.id,
    selectedSymbol,
    selectedTimeframe,
  ]);

  // Keep latest redrawCanvas in ref for lightweight-charts subscriptions
  const redrawRef = useRef(redrawCanvas);
  redrawRef.current = redrawCanvas;

  // Initialize lightweight-charts instance once
  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const initialTokens = getChartThemeTokens(theme);
    const chart = createChart(container, {
      width: container.clientWidth || 640,
      height: container.clientHeight || 420,
      layout: {
        background: { type: ColorType.Solid, color: initialTokens.background },
        textColor: initialTokens.axisText,
        fontFamily: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: initialTokens.gridLine },
        horzLines: { color: initialTokens.gridLine },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: initialTokens.crosshairLine,
          labelBackgroundColor: initialTokens.crosshairLabelBg,
        },
        horzLine: {
          color: initialTokens.crosshairLine,
          labelBackgroundColor: initialTokens.crosshairLabelBg,
        },
      },
      rightPriceScale: {
        borderColor: initialTokens.axisBorder,
        scaleMargins: { top: 0.08, bottom: 0.08 },
      },
      timeScale: {
        borderColor: initialTokens.axisBorder,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: 8,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: { time: true, price: true },
        axisDoubleClickReset: { time: true, price: true },
      },
      kineticScroll: {
        touch: !prefersReducedMotion,
        mouse: !prefersReducedMotion,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: BULL_COLOR,
      downColor: BEAR_COLOR,
      borderUpColor: BULL_COLOR,
      borderDownColor: BEAR_COLOR,
      wickUpColor: BULL_COLOR,
      wickDownColor: BEAR_COLOR,
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    const onRangeChange = (range: LogicalRange | null) => {
      if (range && lastRangeKeyRef.current) {
        sessionVisibleRanges.set(lastRangeKeyRef.current, range);
      }
      const scrollPos = chart.timeScale().scrollPosition();
      setShowJumpLatest(scrollPos < -2);
      redrawRef.current();
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);

    const onCrosshairMove = (param: any) => {
      if (!param || !param.time || !param.seriesData) {
        setCrosshairOhlc(null);
        return;
      }
      const bar = param.seriesData.get(candleSeries);
      if (bar && typeof bar.open === "number" && typeof bar.close === "number") {
        const change = bar.close - bar.open;
        const changePct = bar.open > 0 ? (change / bar.open) * 100 : 0;
        setCrosshairOhlc({
          open: bar.open,
          high: bar.high,
          low: bar.low,
          close: bar.close,
          change,
          changePct,
          time: Number(param.time),
        });
      }
    };
    chart.subscribeCrosshairMove(onCrosshairMove);

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          chart.applyOptions({ width: Math.floor(width), height: Math.floor(height) });
          redrawRef.current();
        }
      }
    });
    ro.observe(container);

    return () => {
      ro.disconnect();
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      chart.unsubscribeCrosshairMove(onCrosshairMove);
      if (rafIdRef.current !== null) {
        cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update chart theme colors in-place via applyOptions without reloading data or losing zoom/scroll
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const tokens = getChartThemeTokens(theme);
    chart.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: tokens.background },
        textColor: tokens.axisText,
      },
      grid: {
        vertLines: { color: tokens.gridLine },
        horzLines: { color: tokens.gridLine },
      },
      crosshair: {
        vertLine: {
          color: tokens.crosshairLine,
          labelBackgroundColor: tokens.crosshairLabelBg,
        },
        horzLine: {
          color: tokens.crosshairLine,
          labelBackgroundColor: tokens.crosshairLabelBg,
        },
      },
      rightPriceScale: {
        borderColor: tokens.axisBorder,
      },
      timeScale: {
        borderColor: tokens.axisBorder,
      },
    });
    redrawRef.current();
  }, [theme]);

  // Update candlestick data & precision when bundle changes
  useEffect(() => {
    const series = candleSeriesRef.current;
    const chart = chartRef.current;
    if (!series || !chart) return;

    const minMove = Number((1 / Math.pow(10, digits)).toFixed(digits));
    series.applyOptions({
      priceFormat: { type: "price", precision: digits, minMove },
    });

    const isMono = activeSettings.style === "Monochrome";
    const trendBullColor = isMono
      ? LUXALGO_SMC_PALETTE.monochrome.bull
      : activeSettings.internalBullishColor;
    const trendBearColor = isMono
      ? LUXALGO_SMC_PALETTE.monochrome.bear
      : activeSettings.internalBearishColor;

    const data = bundle.candles.map((c, idx) => {
      const base = {
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      };
      if (!activeSettings.colorCandles) return base;
      const tr = smcResult.candleTrends[idx] ?? 0;
      if (tr === SMC_BULLISH) {
        return {
          ...base,
          color: trendBullColor,
          borderColor: trendBullColor,
          wickColor: trendBullColor,
        };
      }
      if (tr === SMC_BEARISH) {
        return {
          ...base,
          color: trendBearColor,
          borderColor: trendBearColor,
          wickColor: trendBearColor,
        };
      }
      return base;
    });
    series.setData(data);

    // Restore remembered visible range per (symbol, timeframe) or fit on first view
    if (lastRangeKeyRef.current !== rangeKey) {
      lastRangeKeyRef.current = rangeKey;
      setPinnedHit(null);
      setHoveredHit(null);
      const saved = sessionVisibleRanges.get(rangeKey);
      if (saved && data.length > 0) {
        try {
          chart.timeScale().setVisibleLogicalRange(saved);
        } catch {
          chart.timeScale().fitContent();
        }
      } else if (data.length > 0) {
        chart.timeScale().fitContent();
      }
    }

    redrawCanvas();
  }, [
    bundle.candles,
    digits,
    rangeKey,
    redrawCanvas,
    activeSettings.colorCandles,
    activeSettings.style,
    activeSettings.internalBullishColor,
    activeSettings.internalBearishColor,
    smcResult.candleTrends,
  ]);

  // Trigger canvas redraw whenever drawings, toggles, or highlight change
  useEffect(() => {
    redrawCanvas();
  }, [redrawCanvas]);

  // Clear pinned/hovered card if its item disappears
  useEffect(() => {
    if (pinnedHit && !validatedDrawings.items.some((d) => d.id === pinnedHit.item.id)) {
      setPinnedHit(null);
    }
  }, [validatedDrawings.items, pinnedHit]);

  // Fullscreen & Escape handling
  useEffect(() => {
    const onFsChange = () => {
      setIsFullscreen(document.fullscreenElement === wrapperRef.current);
      setTimeout(() => redrawRef.current(), 60);
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const handleToggleFullscreen = useCallback(async () => {
    const el = wrapperRef.current;
    if (!el) return;
    try {
      if (document.fullscreenElement === el) {
        await document.exitFullscreen();
      } else if (el.requestFullscreen) {
        await el.requestFullscreen();
      } else {
        setIsFullscreen((v) => !v);
      }
    } catch {
      setIsFullscreen((v) => !v);
    }
  }, []);

  const handleResetView = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.priceScale("right").applyOptions({ autoScale: true });
    chart.timeScale().fitContent();
    sessionVisibleRanges.delete(rangeKey);
    setShowJumpLatest(false);
    redrawCanvas();
  }, [rangeKey, redrawCanvas]);

  const handleJumpToLatest = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;
    chart.timeScale().scrollToRealTime();
    setShowJumpLatest(false);
    redrawCanvas();
  }, [redrawCanvas]);

  // Keyboard shortcuts when chart container is focused
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      const chart = chartRef.current;
      if (!chart) return;

      if (e.key === "Escape") {
        if (pinnedHit) {
          setPinnedHit(null);
          e.stopPropagation();
          return;
        }
        if (isFullscreen && document.fullscreenElement) {
          document.exitFullscreen().catch(() => {});
        }
        return;
      }

      if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "d" && IS_DEV) {
        e.preventDefault();
        setShowDebugOverlay((v) => !v);
        return;
      }

      const range = chart.timeScale().getVisibleLogicalRange();
      if (!range) return;
      const span = range.to - range.from;

      if (e.key === "+" || e.key === "=") {
        e.preventDefault();
        const delta = span * 0.12;
        chart.timeScale().setVisibleLogicalRange({
          from: range.from + delta,
          to: range.to - delta,
        });
      } else if (e.key === "-") {
        e.preventDefault();
        const delta = span * 0.14;
        chart.timeScale().setVisibleLogicalRange({
          from: range.from - delta,
          to: range.to + delta,
        });
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const shift = Math.max(2, span * 0.1);
        chart.timeScale().setVisibleLogicalRange({
          from: range.from - shift,
          to: range.to - shift,
        });
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        const shift = Math.max(2, span * 0.1);
        chart.timeScale().setVisibleLogicalRange({
          from: range.from + shift,
          to: range.to + shift,
        });
      } else if (e.key === "0" || e.key.toLowerCase() === "r") {
        e.preventDefault();
        handleResetView();
      } else if (e.key.toLowerCase() === "f") {
        e.preventDefault();
        handleToggleFullscreen();
      }
    },
    [pinnedHit, isFullscreen, handleResetView, handleToggleFullscreen]
  );

  // Pointer hover & click-to-pin on plot (never blocks panning/zooming)
  const handlePlotMouseMove = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const host = plotHostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const hit = hitTestProjectedDrawings(x, y, projectedRef.current);
    if (hit) {
      setHoveredHit((prev) =>
        prev && prev.item.id === hit.item.id && Math.abs(prev.x - x) < 4 && Math.abs(prev.y - y) < 4
          ? prev
          : { item: hit.item, x, y }
      );
    } else {
      setHoveredHit((prev) => (prev ? null : prev));
    }
  }, []);

  const handlePlotMouseLeave = useCallback(() => {
    setHoveredHit(null);
  }, []);

  const handlePlotClick = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    const host = plotHostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const hit = hitTestProjectedDrawings(x, y, projectedRef.current);
    if (hit) {
      setPinnedHit({ item: hit.item, x, y });
    } else {
      setPinnedHit(null);
    }
  }, []);

  // Composite screenshot (candles canvas + drawings canvas)
  const handleManualScreenshot = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || !onCaptureScreenshot) return;
    try {
      const baseCanvas = chart.takeScreenshot();
      const overlay = overlayCanvasRef.current;
      const out = document.createElement("canvas");
      out.width = baseCanvas.width;
      out.height = baseCanvas.height;
      const ctx = out.getContext("2d");
      if (ctx) {
        ctx.drawImage(baseCanvas, 0, 0);
        if (overlay && overlay.width > 0 && overlay.height > 0) {
          ctx.drawImage(overlay, 0, 0);
        }
        onCaptureScreenshot(0, selectedSymbol, "MANUAL", out.toDataURL("image/png"));
      }
    } catch {
      // ignore screenshot errors
    }
  }, [onCaptureScreenshot, selectedSymbol]);

  const toggleLayer = (key: keyof OverlayTogglesState) => {
    setCommittedSettings((prev) => applyLayerChipToggle(prev, key));
    if (previewSettings) {
      setPreviewSettings((prev) => (prev ? applyLayerChipToggle(prev, key) : null));
    }
  };

  const handleOpenSettings = useCallback(() => {
    setShowSettingsPopover((open) => {
      if (open) {
        setPreviewSettings(null);
        return false;
      }
      return true;
    });
  }, []);

  const handleConfirmSettings = useCallback((next: SmcChartSettings) => {
    setCommittedSettings(next);
    setPreviewSettings(null);
    setShowSettingsPopover(false);
  }, []);

  const handleCancelSettings = useCallback(() => {
    setPreviewSettings(null);
    setShowSettingsPopover(false);
  }, []);

  const activeCard = pinnedHit || hoveredHit;
  const activeCardDetails = activeCard
    ? describeDrawingDetails(activeCard.item, digits)
    : null;

  // Clamp tooltip/pinned card cleanly inside plot bounds
  const cardStyle = useMemo(() => {
    if (!activeCard || !plotHostRef.current) return undefined;
    const hostW = plotHostRef.current.clientWidth || 720;
    const hostH = plotHostRef.current.clientHeight || 420;
    const cardW = 236;
    const cardH = 190;
    const left = Math.min(Math.max(10, activeCard.x + 14), Math.max(10, hostW - cardW - 76));
    const top = Math.min(Math.max(10, activeCard.y - 12), Math.max(10, hostH - cardH - 36));
    return { left: `${left}px`, top: `${top}px` };
  }, [activeCard]);

  const smcCounts = useMemo(() => {
    const liqCount =
      mtfLevels.length + smcResult.equalHighsLows.length + smcResult.strongWeakLevels.length;
    const fvgObCount =
      (activeSettings.showInternalOB ? smcResult.internalOrderBlocks.length : 0) +
      (activeSettings.showSwingOB ? smcResult.swingOrderBlocks.length : 0) +
      (activeSettings.showFvg ? smcResult.fairValueGaps.length : 0);
    const structCount =
      (activeSettings.showInternalStructure ? smcResult.internalStructures.length : 0) +
      (activeSettings.showSwingStructure ? smcResult.swingStructures.length : 0);
    return {
      liquidity: liqCount,
      fvgOb: fvgObCount,
      structure: structCount,
    };
  }, [mtfLevels.length, smcResult, activeSettings]);

  const layerToggleSpecs: Array<{
    key: keyof OverlayTogglesState;
    label: string;
    count: number;
    tooltip: string;
    icon: React.ComponentType<{ className?: string }>;
  }> = [
    {
      key: "liquidity",
      label: UI_COPY.chart.layers.liquidity.label,
      count: smcCounts.liquidity,
      tooltip: "Liquidity levels (PDH/PDL, PWH/PWL, PMH/PML, EQH/EQL & Strong/Weak H/L)",
      icon: Activity,
    },
    {
      key: "fvgOb",
      label: UI_COPY.chart.layers.fvgOb.label,
      count: smcCounts.fvgOb,
      tooltip: "Fair Value Gaps (FVG) & Internal/Swing Order Blocks (OB)",
      icon: Layers,
    },
    {
      key: "structure",
      label: UI_COPY.chart.layers.structure.label,
      count: smcCounts.structure,
      tooltip: "Internal & Swing Market Structure Breaks (BOS / CHoCH)",
      icon: TrendingUp,
    },
    {
      key: "sessions",
      label: UI_COPY.chart.layers.sessions.label,
      count: validatedDrawings.counts.sessions,
      tooltip: "Engine Trading Sessions & Killzones (UTC configured in sessions.json)",
      icon: Clock,
    },
    {
      key: "tradeLabels",
      label: UI_COPY.chart.layers.tradeLabels.label,
      count: validatedDrawings.counts.trades,
      tooltip: "Open MT5 Positions, Pending Signals & Closed Trade History",
      icon: ShieldCheck,
    },
  ];

  const debugReport = useMemo(() => {
    if (!showDebugOverlay) return [];
    const renderedIds = new Set(projectedRef.current.map((p) => p.item.id));
    return buildParityDebugReport(validatedDrawings.items, renderedIds);
  }, [showDebugOverlay, validatedDrawings.items]);

  return (
    <div
      ref={wrapperRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      aria-label={`Live Trading Chart for ${selectedSymbol} ${selectedTimeframe}`}
      className={`iea-glass-card flex flex-col overflow-hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent ${
        isFullscreen ? "fixed inset-0 z-50 rounded-none h-screen w-screen" : "h-full min-h-[460px]"
      }`}
    >
      {/* Top Toolbar: Symbols, Timeframes, Layer Toggles with Count Badges, Actions */}
      <div className="px-3.5 py-2 border-b border-iea-borderSubtle bg-[var(--iea-chart-toolbar-bg)] flex flex-wrap items-center justify-between gap-2 shrink-0">
        {/* Left: Symbol Tabs + Timeframes */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex items-center rounded-full bg-iea-inset border border-iea-borderDefault p-0.5">
            {SYMBOLS.map((sym) => {
              const active = sym === selectedSymbol;
              getSymbolChipSpec(sym);
              return (
                <button
                  key={sym}
                  type="button"
                  onClick={() => onSelectSymbol(sym)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent ${
                    active
                      ? "bg-iea-accent text-white shadow-sm"
                      : "text-iea-textSecondary hover:text-iea-textPrimary"
                  }`}
                >
                  <span>{sym}</span>
                </button>
              );
            })}
          </div>

          <div className="inline-flex items-center rounded-full bg-iea-inset border border-iea-borderDefault p-0.5">
            {TIMEFRAMES.map((tf) => {
              const active = tf === selectedTimeframe;
              return (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onSelectTimeframe(tf)}
                  className={`px-2 py-1 rounded-full text-[11px] font-mono font-bold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent ${
                    active
                      ? "bg-iea-accentSoft text-iea-accent border border-iea-accentBorder"
                      : "text-iea-textSecondary hover:text-iea-textPrimary"
                  }`}
                >
                  {tf}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Layer Toggles with Engine Count Badges + Chart Controls */}
        <div className="flex flex-wrap items-center gap-1.5">
          {layerToggleSpecs.map(({ key, label, count, tooltip, icon: Icon }) => {
            const on = overlays[key];
            return (
              <button
                key={key}
                type="button"
                data-testid={`layer-toggle-${key}`}
                aria-pressed={on}
                title={`${tooltip} (${count} on ${selectedSymbol} ${selectedTimeframe})`}
                onClick={() => toggleLayer(key)}
                className={`px-2.5 py-1 rounded-full text-[11px] font-semibold inline-flex items-center space-x-1.5 border transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent ${
                  on
                    ? "bg-iea-accentSoft border-iea-accentBorder text-iea-textPrimary"
                    : "bg-iea-inset border-iea-borderSubtle text-iea-textMuted hover:text-iea-textSecondary"
                }`}
              >
                <Icon className={`w-3 h-3 ${on ? "text-iea-accent" : "text-iea-textMuted"}`} />
                <span>{label}</span>
                <span
                  data-testid={`layer-count-${key}`}
                  className={`px-1.5 py-0 rounded-full text-[10px] font-mono font-bold tabular-nums ${
                    on
                      ? count > 0
                        ? "bg-iea-accent text-white"
                        : "bg-iea-elevated text-iea-textSecondary"
                      : "bg-iea-elevated text-iea-textMuted"
                  }`}
                >
                  {count}
                </span>
              </button>
            );
          })}

          <div className="flex items-center space-x-1 pl-1 border-l border-iea-borderDefault">
            <button
              type="button"
              data-testid="btn-smc-settings"
              aria-expanded={showSettingsPopover}
              onClick={handleOpenSettings}
              title="Smart Money Concepts Settings"
              aria-label="Smart Money Concepts Settings"
              className={`p-1.5 rounded-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent ${
                showSettingsPopover
                  ? "bg-iea-accentSoft text-iea-accent"
                  : "text-iea-textSecondary hover:text-iea-textPrimary hover:bg-iea-elevated"
              }`}
            >
              <Settings className="w-3.5 h-3.5" />
            </button>

            <button
              type="button"
              onClick={handleResetView}
              title="Reset zoom & auto-fit view (double-click plot or press 0)"
              aria-label="Reset chart view"
              className="p-1.5 rounded-lg text-iea-textSecondary hover:text-iea-textPrimary hover:bg-iea-elevated transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>

            {onCaptureScreenshot && (
              <button
                type="button"
                onClick={handleManualScreenshot}
                title="Save chart snapshot PNG (includes overlays)"
                aria-label="Save chart screenshot"
                className="p-1.5 rounded-lg text-iea-textSecondary hover:text-iea-textPrimary hover:bg-iea-elevated transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent"
              >
                <Camera className="w-3.5 h-3.5" />
              </button>
            )}

            {IS_DEV && (
              <button
                type="button"
                onClick={() => setShowDebugOverlay((v) => !v)}
                title="Toggle dev drawings parity report (Ctrl+Shift+D)"
                aria-label="Toggle drawings parity debug overlay"
                className={`p-1.5 rounded-lg transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent ${
                  showDebugOverlay
                    ? "bg-iea-accentSoft text-iea-accent"
                    : "text-iea-textMuted hover:text-iea-textPrimary hover:bg-iea-elevated"
                }`}
              >
                <Bug className="w-3.5 h-3.5" />
              </button>
            )}

            <button
              type="button"
              onClick={handleToggleFullscreen}
              title={isFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen chart (F)"}
              aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              className="p-1.5 rounded-lg text-iea-textSecondary hover:text-iea-textPrimary hover:bg-iea-elevated transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent"
            >
              {isFullscreen ? (
                <Minimize2 className="w-3.5 h-3.5" />
              ) : (
                <Maximize2 className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Secondary OHLC + Live Quote Strip ABOVE the plot (never permanent text on plot) */}
      <div
        data-testid="chart-ohlc-strip"
        className="px-3.5 py-1.5 border-b border-iea-borderSubtle bg-iea-inset flex flex-wrap items-center justify-between gap-2 text-[11px] font-mono shrink-0"
      >
        <div className="flex flex-wrap items-center gap-3 tabular-nums">
          <span className="font-bold text-iea-textPrimary">
            {bundle.brokerSymbol || selectedSymbol} · {selectedTimeframe}
          </span>
          {activeOhlc ? (
            <>
              <span className="text-iea-textMuted">
                O <span className="text-iea-textPrimary">{activeOhlc.open.toFixed(digits)}</span>
              </span>
              <span className="text-iea-textMuted">
                H <span className="text-iea-profit">{activeOhlc.high.toFixed(digits)}</span>
              </span>
              <span className="text-iea-textMuted">
                L <span className="text-iea-danger">{activeOhlc.low.toFixed(digits)}</span>
              </span>
              <span className="text-iea-textMuted">
                C <span className="text-iea-textPrimary font-semibold">{activeOhlc.close.toFixed(digits)}</span>
              </span>
              <span
                className={
                  activeOhlc.change >= 0 ? "text-iea-profit font-semibold" : "text-iea-danger font-semibold"
                }
              >
                {activeOhlc.change >= 0 ? "+" : ""}
                {activeOhlc.change.toFixed(digits)} ({activeOhlc.changePct >= 0 ? "+" : ""}
                {activeOhlc.changePct.toFixed(2)}%)
              </span>
            </>
          ) : (
            <span className="text-iea-textMuted">Waiting for OHLC bars…</span>
          )}
        </div>

        <div className="flex items-center gap-2.5 text-[11px]">
          {(drawingsError || validatedDrawings.malformedFeed) && (
            <span
              data-testid="drawings-feed-warning"
              title={drawingsError || "Malformed drawings payload received"}
              className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-iea-warningSoft border border-iea-warningBorder text-iea-warning text-[10px]"
            >
              <AlertCircle className="w-3 h-3 shrink-0" />
              <span>Drawings sync issue</span>
            </span>
          )}

          {bundle.bid !== null && bundle.ask !== null && bundle.bid > 0 && (
            <span className="text-iea-textSecondary tabular-nums">
              Bid <strong className="text-iea-textPrimary">{bundle.bid.toFixed(digits)}</strong> · Ask{" "}
              <strong className="text-iea-textPrimary">{bundle.ask.toFixed(digits)}</strong> · Spr{" "}
              <strong className="text-iea-accent">{bundle.spreadPoints}</strong>
            </span>
          )}

          <span className="inline-flex items-center space-x-1 text-iea-accent">
            <Radio className="w-3 h-3 text-iea-profit" />
            <span>{feedStatus}</span>
          </span>
        </div>
      </div>

      {/* Main Plot Area: lightweight-charts canvas + High-DPI Engine Drawings Canvas */}
      <div
        ref={plotHostRef}
        onMouseMove={handlePlotMouseMove}
        onMouseLeave={handlePlotMouseLeave}
        onClick={handlePlotClick}
        onDoubleClick={handleResetView}
        className="relative flex-1 min-h-0 w-full bg-[var(--iea-chart-bg)] select-none overflow-hidden"
      >
        {/* Lightweight Charts Host */}
        <div ref={chartContainerRef} className="absolute inset-0 z-10" />

        {/* Single High-DPI Canvas for All Engine Drawings (pointer-events-none so panning/zooming never blocks) */}
        <canvas
          ref={overlayCanvasRef}
          data-testid="engine-drawings-canvas"
          aria-hidden="true"
          className="absolute top-0 left-0 z-20 pointer-events-none"
        />

        {/* SMC Indicator Settings Popover (Inputs | Style | Visibility) */}
        <SmcSettingsPopover
          open={showSettingsPopover}
          settings={committedSettings}
          onLiveChange={setPreviewSettings}
          onConfirm={handleConfirmSettings}
          onCancel={handleCancelSettings}
        />

        {/* Waiting / Empty Candles Overlay */}
        {bundle.candles.length === 0 && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-[var(--iea-chart-bg)]/85 backdrop-blur-sm">
            <div className="px-4 py-3 rounded-2xl bg-iea-card border border-iea-borderDefault text-iea-textPrimary text-xs font-medium shadow-lg flex items-center space-x-2">
              <Eye className="w-4 h-4 text-iea-accent" />
              <span>{waitingReason || "Waiting for MT5 Candles..."}</span>
            </div>
          </div>
        )}

        {/* Jump to Latest Button (appears when scrolled away from newest candle) */}
        {showJumpLatest && bundle.candles.length > 0 && (
          <button
            type="button"
            data-testid="btn-jump-to-latest"
            onClick={(e) => {
              e.stopPropagation();
              handleJumpToLatest();
            }}
            title="Jump to latest candle"
            className="absolute right-20 bottom-10 z-30 px-3 py-1.5 rounded-full bg-iea-card hover:bg-iea-elevated text-iea-textPrimary border border-iea-accentBorder shadow-lg text-xs font-semibold inline-flex items-center space-x-1.5 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent"
          >
            <span>Jump to latest</span>
            <ArrowRight className="w-3.5 h-3.5 text-iea-accent" />
          </button>
        )}

        {/* Hover Tooltip / Pinned Details Card (clamped inside plot, hover card never blocks pan) */}
        {activeCard && activeCardDetails && cardStyle && (
          <div
            data-testid={pinnedHit ? "pinned-drawing-card" : "hover-drawing-tooltip"}
            style={cardStyle}
            onClick={(e) => e.stopPropagation()}
            className={`absolute z-30 w-[236px] rounded-xl bg-[var(--iea-tooltip-bg)] text-[var(--iea-tooltip-text)] border shadow-2xl p-2.5 text-[11px] backdrop-blur-md ${
              pinnedHit
                ? "border-iea-accentBorder pointer-events-auto"
                : "border-[var(--iea-tooltip-border)] pointer-events-none"
            }`}
          >
            <div className="flex items-center justify-between gap-2 pb-1.5 mb-1.5 border-b border-iea-borderSubtle">
              <div className="flex items-center space-x-1.5 min-w-0">
                {pinnedHit && <Pin className="w-3 h-3 text-iea-accent shrink-0" />}
                <span className="font-bold truncate">{activeCardDetails.title}</span>
              </div>
              {pinnedHit ? (
                <button
                  type="button"
                  onClick={() => setPinnedHit(null)}
                  aria-label="Close pinned drawing details"
                  className="p-0.5 rounded hover:bg-iea-elevated text-iea-textSecondary hover:text-iea-textPrimary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-iea-accent"
                >
                  <X className="w-3 h-3" />
                </button>
              ) : (
                <span className="text-[9px] text-iea-textMuted font-mono shrink-0">Click to pin</span>
              )}
            </div>
            <div className="space-y-1 font-mono text-[10.5px]">
              {activeCardDetails.rows.map((r) => (
                <div key={r.label} className="flex items-center justify-between gap-2">
                  <span className="text-iea-textMuted">{r.label}</span>
                  <span
                    className={`font-semibold text-right truncate ${
                      r.tone === "bull"
                        ? "text-iea-profit"
                        : r.tone === "bear"
                        ? "text-iea-danger"
                        : "text-iea-textPrimary"
                    }`}
                  >
                    {r.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Dev-Only Parity Debug Overlay */}
        {IS_DEV && showDebugOverlay && (
          <div
            data-testid="parity-debug-overlay"
            onClick={(e) => e.stopPropagation()}
            className="absolute left-3 top-3 z-40 w-80 max-h-[75%] overflow-y-auto rounded-xl bg-iea-card border border-iea-accentBorder text-iea-textPrimary p-3 text-[10px] font-mono shadow-2xl space-y-2"
          >
            <div className="flex items-center justify-between border-b border-iea-borderSubtle pb-1">
              <span className="font-bold text-iea-accent">
                Engine Parity ({selectedSymbol} {selectedTimeframe})
              </span>
              <button
                type="button"
                onClick={() => setShowDebugOverlay(false)}
                className="text-iea-textSecondary hover:text-iea-textPrimary"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
            <div className="text-iea-textSecondary">
              Engine: {validatedDrawings.items.length} · Rendered: {projectedRef.current.length} ·
              Dropped: {validatedDrawings.dropped.length}
            </div>
            <div className="space-y-1">
              {debugReport.map((entry) => (
                <div
                  key={entry.id}
                  className="flex items-center justify-between gap-2 py-0.5 border-b border-iea-borderSubtle"
                >
                  <span className="truncate">
                    [{entry.type}/{entry.subtype}] {entry.timeframe}
                  </span>
                  <span className={entry.rendered ? "text-iea-profit" : "text-iea-warning"}>
                    {entry.rendered ? "DRAWN" : "SKIP"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
