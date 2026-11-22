import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  IChartApi,
  ISeriesApi,
  LineStyle,
  UTCTimestamp,
} from "lightweight-charts";
import {
  Activity,
  Camera,
  Clock,
  Eye,
  Layers,
  Maximize2,
  Minimize2,
  Radio,
  ShieldCheck,
  TrendingUp,
} from "lucide-react";
import {
  ChartSymbol,
  ChartTimeframe,
  DataFeedStatus,
  SymbolChartBundle,
} from "../services/dashboardDataAdapter";
import { getSymbolChipSpec } from "../styles/designTokens";
import { CHART_TV_LIGHT_THEME } from "../styles/chartTheme";
import { UI_COPY } from "../constants/uiCopy";

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
  onCaptureScreenshot?: (ticket: number, symbol: string, stage: string, dataUrl: string) => void;
}

interface ProjectedFvgObBox {
  id: string;
  topY: number;
  heightPx: number;
  leftX: number;
  widthPx: number;
  text: "FVG" | "OB";
  mitigated: boolean;
  labelLeftX: number;
  showText: boolean;
}

interface ProjectedPositionTemplate {
  id: string;
  direction: "BUY" | "SELL";
  leftX: number;
  mainWidthPx: number;
  extWidthPx: number;
  fullWidthPx: number;
  profitTopY: number | null;
  profitHeightPx: number;
  lossTopY: number | null;
  lossHeightPx: number;
  entryY: number;
  tpOuterY: number | null;
  tp1InnerY: number | null;
  slY: number | null;
  pathStartX: number;
  pathStartY: number;
  pathEndX: number;
  pathEndY: number;
  labelText: "LONG POSITION" | "SHORT POSITION";
  labelX: number;
  labelY: number;
  opacityScale: number;
  isPending: boolean;
}

interface ProjectedMutedLine {
  id: string;
  y: number;
  startX: number;
  endX: number;
  color: string;
  dashed: boolean;
}

interface ProjectedStructureDot {
  id: string;
  x: number;
  y: number;
}

interface ProjectedSessionBand {
  id: string;
  leftX: number;
  widthPx: number;
}

const SYMBOLS: ChartSymbol[] = ["XAUUSD", "USDJPY", "BTCUSD"];
const TIMEFRAMES: ChartTimeframe[] = ["M1", "M5", "M15", "H1", "H4"];
const OVERLAY_STORAGE_KEY = "iea_chart_overlay_toggles_v1";

function loadSavedOverlayToggles(): OverlayTogglesState {
  try {
    const raw = localStorage.getItem(OVERLAY_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        liquidity: Boolean(parsed.liquidity ?? true),
        fvgOb: Boolean(parsed.fvgOb ?? true),
        structure: Boolean(parsed.structure ?? true),
        sessions: Boolean(parsed.sessions ?? true),
        tradeLabels: Boolean(parsed.tradeLabels ?? true),
      };
    }
  } catch {
    // ignore storage errors
  }
  return {
    liquidity: true,
    fvgOb: true,
    structure: true,
    sessions: true,
    tradeLabels: true,
  };
}

export const LiveTradingChart: React.FC<LiveTradingChartProps> = ({
  bundle,
  selectedSymbol,
  selectedTimeframe,
  feedStatus,
  onSelectSymbol,
  onSelectTimeframe,
  onCaptureScreenshot,
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const [overlays, setOverlays] = useState<OverlayTogglesState>(loadSavedOverlayToggles);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  const [fvgObBoxes, setFvgObBoxes] = useState<ProjectedFvgObBox[]>([]);
  const [positionTemplates, setPositionTemplates] = useState<ProjectedPositionTemplate[]>([]);
  const [mutedLines, setMutedLines] = useState<ProjectedMutedLine[]>([]);
  const [structureDots, setStructureDots] = useState<ProjectedStructureDot[]>([]);
  const [sessionBands, setSessionBands] = useState<ProjectedSessionBand[]>([]);

  const toggleOverlay = (key: keyof OverlayTogglesState) => {
    setOverlays((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      try {
        localStorage.setItem(OVERLAY_STORAGE_KEY, JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const primaryTrade = bundle.trades[0] || null;
  const activeSymbolChip = getSymbolChipSpec(selectedSymbol);

  // Close fullscreen on Escape key
  useEffect(() => {
    if (!isFullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsFullscreen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isFullscreen]);

  // Compute pixel coordinates for TradingView-light zones, position templates, and text-free muted layers
  const recomputeOverlayGeometry = useCallback(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;

    const rect = container.getBoundingClientRect();
    const width = Math.max(320, Math.floor(rect.width));
    const height = Math.max(260, Math.floor(rect.height));
    const plotBottom = Math.max(180, height - 28);
    const plotRight = Math.max(200, width - 72);

    const priceToY = (price: number): number | null => {
      if (!Number.isFinite(price) || price <= 0) return null;
      try {
        const y = series.priceToCoordinate(price);
        if (y === null || !Number.isFinite(y)) return null;
        return Number(y);
      } catch {
        return null;
      }
    };

    const timeToX = (timeSec?: number): number | null => {
      if (!timeSec) return null;
      try {
        const x = chart.timeScale().timeToCoordinate(timeSec as UTCTimestamp);
        if (x === null || !Number.isFinite(x)) return null;
        return Number(x);
      } catch {
        return null;
      }
    };

    // Estimate pixel width per bar for min-3-bar extension
    let barSpacingPx = 9;
    if (bundle.candles.length >= 2) {
      const xA = timeToX(bundle.candles[bundle.candles.length - 2].time);
      const xB = timeToX(bundle.candles[bundle.candles.length - 1].time);
      if (xA !== null && xB !== null && Math.abs(xB - xA) >= 2) {
        barSpacingPx = Math.abs(xB - xA);
      }
    }

    const lastCandle = bundle.candles[bundle.candles.length - 1];
    const latestCandleX = lastCandle ? timeToX(lastCandle.time) ?? plotRight - 24 : plotRight - 24;

    const nextSessions: ProjectedSessionBand[] = [];
    const nextFvgObs: ProjectedFvgObBox[] = [];
    const nextPositions: ProjectedPositionTemplate[] = [];
    const nextMutedLines: ProjectedMutedLine[] = [];
    const nextDots: ProjectedStructureDot[] = [];

    // 1. Sessions (text-free, ultra-faint vertical bands)
    if (overlays.sessions) {
      for (const sess of bundle.sessions.slice(-3)) {
        const x1 = timeToX(sess.startTime);
        const x2 = timeToX(sess.endTime) ?? plotRight;
        if (x1 === null) continue;
        const left = Math.max(0, Math.min(x1, x2));
        const right = Math.min(plotRight, Math.max(x1, x2));
        if (right - left > 12) {
          nextSessions.push({ id: sess.id, leftX: left, widthPx: right - left });
        }
      }
    }

    // 2. FVG & OB Boxes (light-green translucent fill, "FVG" / "OB" dark text inside near right end)
    if (overlays.fvgOb) {
      for (const z of bundle.fvgObZones.slice(-6)) {
        const yTop = priceToY(z.topPrice);
        const yBot = priceToY(z.bottomPrice);
        const rawStartX = timeToX(z.startTime);
        if (yTop === null || yBot === null || rawStartX === null) continue;
        const rawEndX = z.endTime ? timeToX(z.endTime) ?? plotRight : plotRight;
        const left = Math.max(0, Math.min(rawStartX, rawEndX));
        const right = Math.min(plotRight, Math.max(rawStartX, rawEndX));
        if (right <= 0 || left >= plotRight) continue;

        const top = Math.max(2, Math.min(yTop, yBot));
        const bot = Math.min(plotBottom - 2, Math.max(yTop, yBot));
        const hPx = bot - top;
        const wPx = right - left;
        if (wPx < 4 || hPx < 4) continue;

        const boxText: "FVG" | "OB" = z.kind === "OB" ? "OB" : "FVG";
        const showText = hPx >= 14 && wPx >= 34;
        // Anchor label inside the visible portion near the right end
        const visibleRight = Math.min(right, plotRight - 6);
        const labelLeftX = Math.max(left + 6, visibleRight - (boxText === "FVG" ? 30 : 24));

        nextFvgObs.push({
          id: z.id,
          topY: top,
          heightPx: hPx,
          leftX: left,
          widthPx: wPx,
          text: boxText,
          mitigated: z.mitigated,
          labelLeftX,
          showText,
        });
      }
    }

    // 3. Liquidity Levels (text-free muted dashed horizontal lines)
    if (overlays.liquidity) {
      for (const liq of bundle.liquidityLevels.slice(0, 6)) {
        const y = priceToY(liq.price);
        if (y === null || y < 4 || y > plotBottom - 4) continue;
        const startX = Math.max(0, timeToX(liq.startTime) ?? 0);
        const endX =
          liq.swept && liq.endTime
            ? Math.min(plotRight, timeToX(liq.endTime) ?? plotRight)
            : plotRight;
        if (endX - startX > 8) {
          nextMutedLines.push({
            id: `liq-${liq.id}`,
            y,
            startX,
            endX,
            color: CHART_TV_LIGHT_THEME.layers.liquidityLine,
            dashed: true,
          });
        }
      }
    }

    // 4. Structure Breaks (text-free thin lines + tiny pivot dots)
    if (overlays.structure) {
      for (const st of bundle.structureBreaks.slice(-4)) {
        const y = priceToY(st.price);
        const xBreak = timeToX(st.time);
        if (y === null || xBreak === null || y < 6 || y > plotBottom - 6) continue;
        const xStart = timeToX(st.startTime) ?? Math.max(0, xBreak - barSpacingPx * 6);
        nextMutedLines.push({
          id: `struct-${st.id}`,
          y,
          startX: Math.max(0, Math.min(xStart, xBreak)),
          endX: Math.min(plotRight, Math.max(xStart, xBreak)),
          color: CHART_TV_LIGHT_THEME.layers.structureLine,
          dashed: st.kind !== "BOS",
        });
        if (xBreak >= 0 && xBreak <= plotRight) {
          nextDots.push({ id: `dot-${st.id}`, x: xBreak, y });
        }
      }
    }

    // 5. Trades Layer: TradingView-Style LONG POSITION / SHORT POSITION Template
    if (overlays.tradeLabels) {
      bundle.trades.slice(0, 4).forEach((trade, idx) => {
        const outerTp = trade.tp2 > 0 ? trade.tp2 : trade.tp1;
        // Pending signals without SL/TP data show nothing on the chart
        if (trade.isPendingSignal && trade.stopLoss <= 0 && outerTp <= 0) return;

        const entryY = priceToY(trade.entryPrice);
        if (entryY === null) return;

        const rawEntryX = timeToX(trade.entryTime);
        if (rawEntryX === null) return;

        const rawEndX =
          trade.isClosed && trade.exitTime
            ? timeToX(trade.exitTime) ?? latestCandleX
            : latestCandleX;

        // If closed trade scrolled completely out of view, skip
        if (rawEndX < 0 || rawEntryX > plotRight) return;

        const leftX = Math.max(0, Math.min(rawEntryX, rawEndX));
        const mainRightX = Math.min(plotRight, Math.max(leftX + barSpacingPx * 2, rawEndX));
        const mainWidthPx = Math.max(12, mainRightX - leftX);

        // Short light-shaded right extension (~15% of trade width, min 3 bars, never beyond right margin)
        const desiredExt = Math.max(barSpacingPx * 3, mainWidthPx * 0.15);
        const fullRightX = Math.min(plotRight - 2, mainRightX + desiredExt);
        const extWidthPx = Math.max(0, fullRightX - mainRightX);
        const fullWidthPx = mainWidthPx + extWidthPx;

        const isBuy = trade.direction === "BUY";
        const tpOuterY = outerTp > 0 ? priceToY(outerTp) : null;
        const hasBothTps = trade.tp1 > 0 && trade.tp2 > 0 && Math.abs(trade.tp2 - trade.tp1) > 1e-6;
        const tp1InnerY = hasBothTps ? priceToY(trade.tp1) : null;
        const slY = trade.stopLoss > 0 ? priceToY(trade.stopLoss) : null;

        let profitTopY: number | null = null;
        let profitHeightPx = 0;
        if (tpOuterY !== null) {
          const validProfit = isBuy ? outerTp > trade.entryPrice : outerTp < trade.entryPrice;
          if (validProfit) {
            const top = Math.max(2, Math.min(entryY, tpOuterY));
            const bot = Math.min(plotBottom - 2, Math.max(entryY, tpOuterY));
            if (bot - top >= 2) {
              profitTopY = top;
              profitHeightPx = bot - top;
            }
          }
        }

        let lossTopY: number | null = null;
        let lossHeightPx = 0;
        if (slY !== null) {
          const validLoss = isBuy ? trade.stopLoss < trade.entryPrice : trade.stopLoss > trade.entryPrice;
          if (validLoss) {
            const top = Math.max(2, Math.min(entryY, slY));
            const bot = Math.min(plotBottom - 2, Math.max(entryY, slY));
            if (bot - top >= 2) {
              lossTopY = top;
              lossHeightPx = bot - top;
            }
          }
        }

        // Dashed path line from (entryTime, entryPrice) to (exitTime/latest, exitPrice/currentPrice)
        const endPrice = trade.isClosed && trade.exitPrice ? trade.exitPrice : trade.currentPrice;
        const pathEndY = priceToY(endPrice) ?? entryY;

        // Place ONLY "LONG POSITION" (below box on SL side) or "SHORT POSITION" (above box on SL side)
        const boxBottomY = Math.max(
          entryY,
          lossTopY !== null ? lossTopY + lossHeightPx : entryY,
          profitTopY !== null ? profitTopY + profitHeightPx : entryY
        );
        const boxTopY = Math.min(
          entryY,
          lossTopY !== null ? lossTopY : entryY,
          profitTopY !== null ? profitTopY : entryY
        );

        const labelY = isBuy
          ? Math.min(plotBottom - 16, boxBottomY + 6)
          : Math.max(4, boxTopY - 18);

        const opacityScale = trade.isPendingSignal
          ? CHART_TV_LIGHT_THEME.position.pendingOpacityScale
          : idx === 0 && !trade.isClosed
          ? 1.0
          : CHART_TV_LIGHT_THEME.position.secondaryOpacityScale;

        nextPositions.push({
          id: `pos-tpl-${trade.ticket}-${idx}`,
          direction: trade.direction,
          leftX,
          mainWidthPx,
          extWidthPx,
          fullWidthPx,
          profitTopY,
          profitHeightPx,
          lossTopY,
          lossHeightPx,
          entryY,
          tpOuterY,
          tp1InnerY,
          slY,
          pathStartX: leftX,
          pathStartY: entryY,
          pathEndX: mainRightX,
          pathEndY,
          labelText: isBuy ? "LONG POSITION" : "SHORT POSITION",
          labelX: leftX,
          labelY,
          opacityScale,
          isPending: Boolean(trade.isPendingSignal),
        });
      });
    }

    setSessionBands(nextSessions);
    setFvgObBoxes(nextFvgObs);
    setPositionTemplates(nextPositions);
    setMutedLines(nextMutedLines);
    setStructureDots(nextDots);
  }, [bundle, overlays]);

  // Initialize lightweight-charts instance (TradingView Light style, transparent canvas over #FFFFFF)
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialRect = container.getBoundingClientRect();
    const chart = createChart(container, {
      width: Math.max(320, Math.floor(initialRect.width || 760)),
      height: Math.max(260, Math.floor(initialRect.height || 440)),
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: CHART_TV_LIGHT_THEME.axisText,
        fontFamily: CHART_TV_LIGHT_THEME.typography.axisFontFamily,
        fontSize: 11,
      },
      grid: {
        vertLines: { color: CHART_TV_LIGHT_THEME.gridLine },
        horzLines: { color: CHART_TV_LIGHT_THEME.gridLine },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: CHART_TV_LIGHT_THEME.crosshairLine,
          style: LineStyle.Dashed,
          width: 1,
          labelBackgroundColor: CHART_TV_LIGHT_THEME.crosshairLabelBg,
        },
        horzLine: {
          color: CHART_TV_LIGHT_THEME.crosshairLine,
          style: LineStyle.Dashed,
          width: 1,
          labelBackgroundColor: CHART_TV_LIGHT_THEME.crosshairLabelBg,
        },
      },
      rightPriceScale: {
        borderColor: CHART_TV_LIGHT_THEME.axisBorder,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: CHART_TV_LIGHT_THEME.axisBorder,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 10,
        barSpacing: 9,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: CHART_TV_LIGHT_THEME.candles.bull,
      downColor: CHART_TV_LIGHT_THEME.candles.bear,
      borderVisible: false,
      wickUpColor: CHART_TV_LIGHT_THEME.candles.bull,
      wickDownColor: CHART_TV_LIGHT_THEME.candles.bear,
      priceFormat: {
        type: "price",
        precision: bundle.digits,
        minMove: bundle.point,
      },
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;

    const handleVisibleChange = () => recomputeOverlayGeometry();
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

  // Re-trigger resize when toggling fullscreen
  useEffect(() => {
    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (container && chartRef.current) {
        const rect = container.getBoundingClientRect();
        if (rect.width > 100 && rect.height > 100) {
          chartRef.current.applyOptions({
            width: Math.floor(rect.width),
            height: Math.floor(rect.height),
          });
          chartRef.current.timeScale().fitContent();
          recomputeOverlayGeometry();
        }
      }
    }, 60);
    return () => clearTimeout(timer);
  }, [isFullscreen, recomputeOverlayGeometry]);

  // Update candle series data & auto-scale range when bundle changes
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

    series.setData(
      bundle.candles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );

    series.applyOptions({
      autoscaleInfoProvider: (original: () => { priceRange: { minValue: number; maxValue: number } } | null) => {
        const res = original();
        if (!res || !res.priceRange) return res;
        let minVal = res.priceRange.minValue;
        let maxVal = res.priceRange.maxValue;
        for (const t of bundle.trades) {
          for (const p of [t.entryPrice, t.stopLoss, t.tp1, t.tp2]) {
            if (p > 0) {
              minVal = Math.min(minVal, p);
              maxVal = Math.max(maxVal, p);
            }
          }
        }
        const pad = (maxVal - minVal) * 0.08;
        return {
          priceRange: {
            minValue: minVal - pad,
            maxValue: maxVal + pad,
          },
        };
      },
    });

    requestAnimationFrame(() => recomputeOverlayGeometry());
  }, [bundle, recomputeOverlayGeometry]);

  // Auto-save chart PNG screenshot via lightweight-charts takeScreenshot() when a real trade opens
  const capturedTicketsRef = useRef<Set<string>>(new Set());
  const triggerChartScreenshot = useCallback(
    (ticket: number, symbol: string, stage: string) => {
      if (!chartRef.current || !onCaptureScreenshot) return;
      try {
        const canvas = chartRef.current.takeScreenshot();
        onCaptureScreenshot(ticket, symbol, stage, canvas.toDataURL("image/png"));
      } catch {
        // ignore screenshot errors
      }
    },
    [onCaptureScreenshot]
  );

  useEffect(() => {
    if (!primaryTrade || bundle.candles.length === 0 || !onCaptureScreenshot) return;
    const key = `${primaryTrade.ticket}:OPEN`;
    if (!capturedTicketsRef.current.has(key)) {
      capturedTicketsRef.current.add(key);
      const t = setTimeout(() => {
        triggerChartScreenshot(primaryTrade.ticket, bundle.brokerSymbol, "OPEN");
      }, 400);
      return () => clearTimeout(t);
    }
  }, [primaryTrade, bundle.candles.length, bundle.brokerSymbol, onCaptureScreenshot, triggerChartScreenshot]);

  return (
    <section
      aria-label="Live Institutional Execution Chart"
      data-fullscreen={isFullscreen ? "true" : "false"}
      style={
        isFullscreen
          ? { top: "calc(var(--iea-titlebar-h, 0px) + 12px)" }
          : undefined
      }
      className={
        isFullscreen
          ? "fixed left-3 right-3 bottom-3 z-50 flex flex-col iea-chart-glass-shell overflow-hidden shadow-2xl"
          : "flex flex-col h-full min-h-[470px] iea-chart-glass-shell overflow-hidden"
      }
    >
      {/* Adaptive Dark Glass Header above White TradingView Plot */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 bg-[#0D1B36]/92 border-b border-[rgba(186,214,255,0.14)] shrink-0">
        {/* Left: Symbol Switcher + Timeframes + Live Quote & Provenance */}
        <div className="flex flex-wrap items-center gap-2">
          <div
            className="inline-flex items-center bg-[#091426]/80 border border-[rgba(186,214,255,0.15)] rounded-full p-0.5 gap-0.5"
            role="group"
            aria-label="Select Chart Symbol"
          >
            {SYMBOLS.map((sym) => {
              const active = sym === selectedSymbol;
              const chip = getSymbolChipSpec(sym);
              return (
                <button
                  key={sym}
                  type="button"
                  onClick={() => onSelectSymbol(sym)}
                  aria-pressed={active}
                  title={`${sym} (${chip.tagLabel})`}
                  className={`px-2.5 py-1 rounded-full text-xs font-mono font-bold transition-all duration-150 inline-flex items-center space-x-1.5 ${
                    active
                      ? "bg-[#B0F648] text-[#081321] shadow-[0_0_14px_rgba(176,246,72,0.38)]"
                      : "text-[#B6C5E0] hover:text-[#F4F7FF] hover:bg-white/5"
                  }`}
                >
                  <span
                    className={`w-4 h-4 rounded-full text-[9px] font-extrabold inline-flex items-center justify-center ${
                      active ? "bg-[#081321] text-[#B0F648]" : chip.chipBg
                    }`}
                  >
                    {chip.shortCode}
                  </span>
                  <span>{sym}</span>
                </button>
              );
            })}
          </div>

          <div
            className="inline-flex items-center bg-[#091426]/80 border border-[rgba(186,214,255,0.15)] rounded-full p-0.5 gap-0.5"
            role="group"
            aria-label="Select Chart Timeframe"
          >
            {TIMEFRAMES.map((tf) => {
              const active = tf === selectedTimeframe;
              return (
                <button
                  key={tf}
                  type="button"
                  onClick={() => onSelectTimeframe(tf)}
                  aria-pressed={active}
                  title={`Timeframe ${tf}`}
                  className={`px-2 py-1 rounded-full text-[11px] font-mono font-semibold transition-all duration-150 ${
                    active
                      ? "bg-[#223D6A] text-[#B0F648] border border-[#B0F648]/45"
                      : "text-[#8496B8] hover:text-[#F4F7FF]"
                  }`}
                >
                  {tf}
                </button>
              );
            })}
          </div>

          <div
            className="hidden xl:flex items-center space-x-1.5 px-2.5 py-1 iea-pill-control font-mono text-xs"
            title={`Source: ${bundle.source} · Broker ${bundle.brokerSymbol} · ${bundle.freshnessReason}`}
          >
            <span
              className={`w-4 h-4 rounded-full text-[9px] font-bold inline-flex items-center justify-center ${activeSymbolChip.chipBg}`}
            >
              {activeSymbolChip.shortCode}
            </span>
            <span className="text-[#B0F648] font-bold">
              {bundle.bid !== null ? bundle.bid.toFixed(bundle.digits) : "—"}
            </span>
            <span className="text-[#8496B8]">/</span>
            <span className="text-[#FF5A6E] font-bold">
              {bundle.ask !== null ? bundle.ask.toFixed(bundle.digits) : "—"}
            </span>
            <span className="text-[10px] text-[#C2F076] bg-[#B0F648]/12 px-1.5 py-0.2 rounded-full">
              Spr {bundle.spreadPoints !== null ? bundle.spreadPoints : "—"}
            </span>
            <span
              className={`text-[10px] px-1.5 py-0.2 rounded-full font-bold ${
                bundle.marketClosed
                  ? "bg-[#FBBF24]/20 text-[#FBBF24]"
                  : bundle.stale
                  ? "bg-[#FF5A6E]/20 text-[#FF7A8A]"
                  : bundle.source === "MT5"
                  ? "bg-[#5EEAD4]/15 text-[#5EEAD4]"
                  : "bg-white/10 text-[#8496B8]"
              }`}
            >
              {bundle.marketClosed
                ? "CLOSED"
                : bundle.stale
                ? "STALE"
                : bundle.source === "MT5"
                ? `MT5${bundle.tickTimeUtc ? ` · ${bundle.tickTimeUtc.slice(11, 19)}` : ""}`
                : "WAITING"}
            </span>
          </div>
        </div>

        {/* Right: Independent Layer Toggles + Screenshot + Fullscreen */}
        <div className="flex flex-wrap items-center gap-1">
          <button
            type="button"
            onClick={() => toggleOverlay("liquidity")}
            aria-pressed={overlays.liquidity}
            title={UI_COPY.chart.layers.liquidity.tooltip}
            className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all duration-150 inline-flex items-center space-x-1 ${
              overlays.liquidity
                ? "bg-[#B0F648]/16 border-[#B0F648]/50 text-[#C2F076]"
                : "bg-[#0E1E3B]/70 border-[rgba(186,214,255,0.14)] text-[#8496B8] hover:text-[#F4F7FF]"
            }`}
          >
            <Layers className="w-3 h-3" />
            <span>{UI_COPY.chart.layers.liquidity.label}</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("fvgOb")}
            aria-pressed={overlays.fvgOb}
            title={UI_COPY.chart.layers.fvgOb.tooltip}
            className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all duration-150 inline-flex items-center space-x-1 ${
              overlays.fvgOb
                ? "bg-[#5EEAD4]/16 border-[#5EEAD4]/50 text-[#5EEAD4]"
                : "bg-[#0E1E3B]/70 border-[rgba(186,214,255,0.14)] text-[#8496B8] hover:text-[#F4F7FF]"
            }`}
          >
            <Activity className="w-3 h-3" />
            <span>{UI_COPY.chart.layers.fvgOb.label}</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("structure")}
            aria-pressed={overlays.structure}
            title={UI_COPY.chart.layers.structure.tooltip}
            className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all duration-150 inline-flex items-center space-x-1 ${
              overlays.structure
                ? "bg-[#C077FA]/18 border-[#C077FA]/55 text-[#E5C7FF]"
                : "bg-[#0E1E3B]/70 border-[rgba(186,214,255,0.14)] text-[#8496B8] hover:text-[#F4F7FF]"
            }`}
          >
            <TrendingUp className="w-3 h-3" />
            <span>{UI_COPY.chart.layers.structure.label}</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("sessions")}
            aria-pressed={overlays.sessions}
            title={UI_COPY.chart.layers.sessions.tooltip}
            className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all duration-150 inline-flex items-center space-x-1 ${
              overlays.sessions
                ? "bg-[#4F8CFF]/20 border-[#7196CB]/60 text-[#D4E4FF]"
                : "bg-[#0E1E3B]/70 border-[rgba(186,214,255,0.14)] text-[#8496B8] hover:text-[#F4F7FF]"
            }`}
          >
            <Clock className="w-3 h-3" />
            <span>{UI_COPY.chart.layers.sessions.label}</span>
          </button>

          <button
            type="button"
            onClick={() => toggleOverlay("tradeLabels")}
            aria-pressed={overlays.tradeLabels}
            title={UI_COPY.chart.layers.tradeLabels.tooltip}
            className={`px-2.5 py-1 rounded-full text-[11px] font-semibold border transition-all duration-150 inline-flex items-center space-x-1 ${
              overlays.tradeLabels
                ? "bg-[#B0F648]/20 border-[#B0F648]/60 text-[#B0F648]"
                : "bg-[#0E1E3B]/70 border-[rgba(186,214,255,0.14)] text-[#8496B8] hover:text-[#F4F7FF]"
            }`}
          >
            <Eye className="w-3 h-3" />
            <span>{UI_COPY.chart.layers.tradeLabels.label}</span>
          </button>

          {primaryTrade && onCaptureScreenshot && (
            <button
              type="button"
              onClick={() => triggerChartScreenshot(primaryTrade.ticket, bundle.brokerSymbol, "MANUAL")}
              title={`Save PNG chart screenshot for trade #${primaryTrade.ticket}`}
              className="p-1.5 rounded-full border bg-[#0E1E3B]/80 hover:bg-[#19305C] border-[rgba(186,214,255,0.18)] text-[#5EEAD4] transition"
            >
              <Camera className="w-3.5 h-3.5" />
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsFullscreen((p) => !p)}
            aria-label={isFullscreen ? "Exit fullscreen chart" : "Fullscreen chart"}
            title={isFullscreen ? "Exit Fullscreen (Esc)" : "Fullscreen Chart"}
            data-testid="chart-fullscreen-toggle"
            className={`p-1.5 rounded-full border transition ${
              isFullscreen
                ? "bg-[#B0F648] text-[#081321] border-[#B0F648]"
                : "bg-[#0E1E3B]/80 hover:bg-[#19305C] border-[rgba(186,214,255,0.18)] text-[#F4F7FF]"
            }`}
          >
            {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Sub-Header Active Trade Info Strip (App UI outside the plot) */}
      {primaryTrade && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-1.5 bg-[#0B172F]/92 border-b border-[rgba(186,214,255,0.12)] text-xs font-mono shrink-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`px-2 py-0.5 rounded-full font-bold text-[10px] ${
                primaryTrade.direction === "BUY"
                  ? "bg-[#B0F648]/20 text-[#B0F648] border border-[#B0F648]/45"
                  : "bg-[#FF5A6E]/20 text-[#FF5A6E] border border-[#FF5A6E]/45"
              }`}
            >
              {primaryTrade.direction} {primaryTrade.volume.toFixed(2)}L
            </span>
            <span className="text-[#F4F7FF] font-bold">#{primaryTrade.ticket}</span>
            <span className="text-[#8496B8]">
              In <strong className="text-[#F4F7FF]">{primaryTrade.entryPrice.toFixed(bundle.digits)}</strong>
            </span>
            <span className="text-[#FF7A8A]">
              SL <strong>{primaryTrade.stopLoss > 0 ? primaryTrade.stopLoss.toFixed(bundle.digits) : "—"}</strong>
            </span>
            {primaryTrade.tp1 > 0 && (
              <span className="text-[#C2F076]">
                TP1 <strong>{primaryTrade.tp1.toFixed(bundle.digits)}</strong>
              </span>
            )}
            {primaryTrade.tp2 > 0 && (
              <span className="text-[#B0F648]">
                TP2 <strong>{primaryTrade.tp2.toFixed(bundle.digits)}</strong>
              </span>
            )}
          </div>

          <div className="flex items-center space-x-2">
            <span
              className={`px-2.5 py-0.5 rounded-full font-bold ${
                primaryTrade.floatingPnl >= 0
                  ? "bg-[#B0F648]/20 text-[#B0F648] border border-[#B0F648]/45"
                  : "bg-[#FF5A6E]/20 text-[#FF5A6E] border border-[#FF5A6E]/45"
              }`}
            >
              {primaryTrade.floatingPnl >= 0 ? "+" : ""}${primaryTrade.floatingPnl.toFixed(2)} (
              {primaryTrade.floatingR >= 0 ? "+" : ""}
              {primaryTrade.floatingR.toFixed(2)}R)
            </span>
            <span className="inline-flex items-center space-x-1 text-[10px] font-sans text-[#C2F076] bg-[#B0F648]/12 border border-[#B0F648]/30 px-2 py-0.5 rounded-full">
              <ShieldCheck className="w-3 h-3" />
              <span>Tighten-SL</span>
            </span>
            <span className="inline-flex items-center space-x-1 text-[10px] font-sans text-[#B6C5E0] bg-[#091426]/80 px-2 py-0.5 rounded-full border border-[rgba(186,214,255,0.14)]">
              <Radio className="w-3 h-3 text-[#B0F648] animate-pulse" />
              <span>{feedStatus}</span>
            </span>
          </div>
        </div>
      )}

      {/* White TradingView Plot Surface — z-5 zones -> z-10 candles -> z-20 lines -> z-30 ONLY position & FVG/OB text */}
      <div
        className="relative flex-1 min-h-0 w-full"
        style={{ backgroundColor: CHART_TV_LIGHT_THEME.background }}
      >
        {bundle.candles.length === 0 && (
          <div className="absolute inset-0 z-30 flex flex-col items-center justify-center bg-white/90 text-center px-4">
            <div className="text-sm font-semibold text-[#1F2937]">
              {bundle.marketClosed ? "Market Closed" : "Waiting for MT5 Candles"}
            </div>
            <div className="text-xs font-mono text-[#6B7280] mt-1">
              {bundle.brokerSymbol} ({bundle.timeframe}) · {bundle.freshnessReason}
            </div>
          </div>
        )}

        {/* BACKDROP LAYER (z-5): Behind candlesticks so candles stay 100% crisp & un-tinted */}
        <div
          className="absolute inset-0 z-[5] pointer-events-none overflow-hidden select-none"
          style={{ right: "72px", bottom: "28px" }}
        >
          {/* Text-free Session Bands */}
          {sessionBands.map((sb) => (
            <div
              key={sb.id}
              style={{
                left: `${sb.leftX}px`,
                width: `${sb.widthPx}px`,
                backgroundColor: CHART_TV_LIGHT_THEME.layers.sessionBand,
              }}
              className="absolute top-0 bottom-0"
            />
          ))}

          {/* FVG & OB Light-Green Translucent Rectangles (no heavy border) */}
          {fvgObBoxes.map((box) => (
            <div
              key={box.id}
              data-testid={`tv-box-${box.text.toLowerCase()}`}
              style={{
                top: `${box.topY}px`,
                height: `${box.heightPx}px`,
                left: `${box.leftX}px`,
                width: `${box.widthPx}px`,
                backgroundColor: box.mitigated
                  ? CHART_TV_LIGHT_THEME.fvgOb.mitigatedFill
                  : CHART_TV_LIGHT_THEME.fvgOb.fill,
              }}
              className="absolute"
            />
          ))}

          {/* LONG / SHORT Position Zones (2-shade Profit Zone + Light Red Loss Zone) */}
          {positionTemplates.map((pt) => (
            <React.Fragment key={pt.id}>
              {/* Profit Zone: Stronger main duration fill + Lighter right extension */}
              {pt.profitTopY !== null && pt.profitHeightPx > 0 && (
                <>
                  <div
                    data-testid={`tv-pos-profit-main-${pt.direction.toLowerCase()}`}
                    style={{
                      top: `${pt.profitTopY}px`,
                      height: `${pt.profitHeightPx}px`,
                      left: `${pt.leftX}px`,
                      width: `${pt.mainWidthPx}px`,
                      backgroundColor: CHART_TV_LIGHT_THEME.position.profitFillPrimary,
                      opacity: pt.opacityScale,
                    }}
                    className="absolute"
                  />
                  {pt.extWidthPx > 0 && (
                    <div
                      data-testid={`tv-pos-profit-ext-${pt.direction.toLowerCase()}`}
                      style={{
                        top: `${pt.profitTopY}px`,
                        height: `${pt.profitHeightPx}px`,
                        left: `${pt.leftX + pt.mainWidthPx}px`,
                        width: `${pt.extWidthPx}px`,
                        backgroundColor: CHART_TV_LIGHT_THEME.position.profitFillExtension,
                        opacity: pt.opacityScale,
                      }}
                      className="absolute"
                    />
                  )}
                </>
              )}

              {/* Loss Zone: Single light red/pink fill across full width */}
              {pt.lossTopY !== null && pt.lossHeightPx > 0 && (
                <div
                  data-testid={`tv-pos-loss-${pt.direction.toLowerCase()}`}
                  style={{
                    top: `${pt.lossTopY}px`,
                    height: `${pt.lossHeightPx}px`,
                    left: `${pt.leftX}px`,
                    width: `${pt.fullWidthPx}px`,
                    backgroundColor: CHART_TV_LIGHT_THEME.position.lossFill,
                    opacity: pt.opacityScale,
                  }}
                  className="absolute"
                />
              )}
            </React.Fragment>
          ))}
        </div>

        {/* Lightweight Charts Canvas Mount (z-10, transparent bg so candles render ON TOP of zones) */}
        <div ref={containerRef} className="absolute inset-0 z-10 w-full h-full" />

        {/* FOREGROUND LINES & ALLOWED LABELS (z-20 / z-30) */}
        <div
          className="absolute inset-0 z-20 pointer-events-none overflow-hidden select-none"
          style={{ right: "72px", bottom: "28px" }}
        >
          <svg className="absolute inset-0 w-full h-full overflow-visible">
            {/* Muted Text-Free Liquidity & Structure Lines */}
            {mutedLines.map((ln) => (
              <line
                key={ln.id}
                x1={ln.startX}
                y1={ln.y}
                x2={ln.endX}
                y2={ln.y}
                stroke={ln.color}
                strokeWidth={1}
                strokeDasharray={ln.dashed ? "4 4" : undefined}
              />
            ))}

            {/* Small Text-Free Structure Pivot Dots */}
            {structureDots.map((dot) => (
              <circle
                key={dot.id}
                cx={dot.x}
                cy={dot.y}
                r={3}
                fill={CHART_TV_LIGHT_THEME.layers.structureDot}
              />
            ))}

            {/* Position Template Crisp 1px Edges, Entry Line & Dashed Path Line */}
            {positionTemplates.map((pt) => {
              const edgeDash = pt.isPending ? "4 4" : undefined;
              const rightX = pt.leftX + pt.fullWidthPx;
              return (
                <g key={`lines-${pt.id}`} opacity={pt.opacityScale}>
                  {/* Thin Gray Entry Line across full zone */}
                  <line
                    x1={pt.leftX}
                    y1={pt.entryY}
                    x2={rightX}
                    y2={pt.entryY}
                    stroke={CHART_TV_LIGHT_THEME.position.entryLine}
                    strokeWidth={1}
                    strokeDasharray={edgeDash}
                  />

                  {/* Subtle 1px Outer TP Edge */}
                  {pt.tpOuterY !== null && (
                    <line
                      x1={pt.leftX}
                      y1={pt.tpOuterY}
                      x2={rightX}
                      y2={pt.tpOuterY}
                      stroke={CHART_TV_LIGHT_THEME.position.tpEdge}
                      strokeWidth={1}
                      strokeDasharray={edgeDash}
                    />
                  )}

                  {/* Thin Dashed Inner TP1 Line (when TP1 & TP2 both exist, no text) */}
                  {pt.tp1InnerY !== null && (
                    <line
                      x1={pt.leftX}
                      y1={pt.tp1InnerY}
                      x2={rightX}
                      y2={pt.tp1InnerY}
                      stroke={CHART_TV_LIGHT_THEME.position.tp1InnerDashed}
                      strokeWidth={1}
                      strokeDasharray="4 4"
                    />
                  )}

                  {/* Subtle 1px Outer SL Edge */}
                  {pt.slY !== null && (
                    <line
                      x1={pt.leftX}
                      y1={pt.slY}
                      x2={rightX}
                      y2={pt.slY}
                      stroke={CHART_TV_LIGHT_THEME.position.slEdge}
                      strokeWidth={1}
                      strokeDasharray={edgeDash}
                    />
                  )}

                  {/* Thin Gray Dashed Path Line from Entry to Exit/Current */}
                  <line
                    x1={pt.pathStartX}
                    y1={pt.pathStartY}
                    x2={pt.pathEndX}
                    y2={pt.pathEndY}
                    stroke={CHART_TV_LIGHT_THEME.position.pathDashedLine}
                    strokeWidth={1}
                    strokeDasharray="4 4"
                  />
                </g>
              );
            })}
          </svg>

          {/* FVG & OB Text INSIDE Boxes ("FVG" / "OB" only, dark regular weight, vertically centered near right end) */}
          {fvgObBoxes
            .filter((box) => box.showText)
            .map((box) => (
              <span
                key={`txt-${box.id}`}
                data-testid={`tv-box-label-${box.text.toLowerCase()}`}
                style={{
                  position: "absolute",
                  left: `${box.labelLeftX}px`,
                  top: `${box.topY + box.heightPx / 2}px`,
                  transform: "translateY(-50%)",
                  color: CHART_TV_LIGHT_THEME.typography.labelColor,
                  fontFamily: CHART_TV_LIGHT_THEME.typography.fontFamily,
                  fontSize: CHART_TV_LIGHT_THEME.typography.boxLabelSize,
                  fontWeight: 500,
                  lineHeight: 1,
                }}
              >
                {box.text}
              </span>
            ))}

          {/* Position Template Labels ("LONG POSITION" below SL side / "SHORT POSITION" above SL side) */}
          {positionTemplates.map((pt) => (
            <span
              key={`lbl-${pt.id}`}
              data-testid={`tv-pos-label-${pt.direction.toLowerCase()}`}
              style={{
                position: "absolute",
                left: `${pt.labelX}px`,
                top: `${pt.labelY}px`,
                color: CHART_TV_LIGHT_THEME.typography.labelColor,
                fontFamily: CHART_TV_LIGHT_THEME.typography.fontFamily,
                fontSize: CHART_TV_LIGHT_THEME.typography.positionLabelSize,
                fontWeight: 700,
                letterSpacing: "0.02em",
                lineHeight: 1,
                opacity: pt.opacityScale,
              }}
            >
              {pt.labelText}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
};
