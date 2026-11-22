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
  Minimize2,
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
import { DESIGN_TOKENS, getSymbolChipSpec } from "../styles/designTokens";
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
}

interface ProjectedZoneBox {
  id: string;
  topY: number;
  heightPx: number;
  leftX: number;
  widthPx: number;
  kind: "FVG_BULL" | "FVG_BEAR" | "IFVG" | "OB_BULL" | "OB_BEAR";
  label: string;
  tooltip: string;
  mitigated?: boolean;
}

interface ProjectedTradePositionBox {
  id: string;
  topY: number;
  heightPx: number;
  leftX: number;
  widthPx: number;
  kind: "PROFIT" | "LOSS";
  opacity: number;
  dashed?: boolean;
}

interface ProjectedSignalArrow {
  id: string;
  x: number;
  y: number;
  direction: "BUY" | "SELL";
}

interface ProjectedLineLevel {
  id: string;
  y: number;
  price: number;
  style: "solid" | "dashed" | "dotted";
  color: string;
  startX: number;
  endX: number;
  width: number;
  opacity?: number;
}

interface ProjectedAnnotationPin {
  id: string;
  x: number;
  y: number;
  label: string;
  detail: string;
  tone: "mss" | "choch" | "bos";
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
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const [overlays, setOverlays] = useState<OverlayTogglesState>(loadSavedOverlayToggles);
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  const [chartDims, setChartDims] = useState<{ width: number; height: number }>({
    width: 760,
    height: 440,
  });
  const [resolvedLabels, setResolvedLabels] = useState<ResolvedPriceLabelItem[]>([]);
  const [zoneBoxes, setZoneBoxes] = useState<ProjectedZoneBox[]>([]);
  const [tradePositionBoxes, setTradePositionBoxes] = useState<ProjectedTradePositionBox[]>([]);
  const [signalArrows, setSignalArrows] = useState<ProjectedSignalArrow[]>([]);
  const [levelLines, setLevelLines] = useState<ProjectedLineLevel[]>([]);
  const [annotationPins, setAnnotationPins] = useState<ProjectedAnnotationPin[]>([]);
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
      if (e.key === "Escape") {
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isFullscreen]);

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

    const nextZones: ProjectedZoneBox[] = [];
    const nextTradeBoxes: ProjectedTradePositionBox[] = [];
    const nextSignalArrows: ProjectedSignalArrow[] = [];
    const nextLines: ProjectedLineLevel[] = [];
    const rawLabels: RawPriceLabelItem[] = [];
    const nextPins: ProjectedAnnotationPin[] = [];
    const nextSessions: ProjectedSessionBand[] = [];

    // 1. Sessions shading bands (capped to 3 most recent)
    if (overlays.sessions) {
      for (const sess of bundle.sessions.slice(-3)) {
        const x1 = timeToX(sess.startTime) ?? 18;
        const x2 = timeToX(sess.endTime) ?? plotRight - 6;
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

    // 2. FVG / IFVG / Order Block boxes (capped to 4 most recent)
    if (overlays.fvgOb) {
      for (const z of bundle.fvgObZones.slice(-4)) {
        const yTop = priceToY(z.topPrice);
        const yBot = priceToY(z.bottomPrice);
        if (yTop !== null && yBot !== null) {
          const top = Math.max(6, Math.min(yTop, yBot));
          const bot = Math.min(plotBottom - 4, Math.max(yTop, yBot));
          const startX = Math.max(12, Math.min(plotRight - 70, timeToX(z.startTime) ?? 48));
          const endX = z.endTime
            ? Math.max(startX + 36, Math.min(plotRight, timeToX(z.endTime) ?? plotRight))
            : plotRight;
          nextZones.push({
            id: z.id,
            topY: top,
            heightPx: Math.max(12, bot - top),
            leftX: startX,
            widthPx: Math.max(36, endX - startX),
            kind:
              z.kind === "IFVG"
                ? "IFVG"
                : z.kind === "FVG"
                ? z.bias === "BULLISH"
                  ? "FVG_BULL"
                  : "FVG_BEAR"
                : z.bias === "BULLISH"
                ? "OB_BULL"
                : "OB_BEAR",
            label: z.label,
            tooltip: `${z.kind} (${z.bias}) · ${z.bottomPrice.toFixed(bundle.digits)}–${z.topPrice.toFixed(
              bundle.digits
            )} · ${z.mitigated ? "Mitigated" : "Active"}`,
            mitigated: z.mitigated,
          });
        }
      }
    }

    // 3. Liquidity Levels (PWH / PDH / EQH / PDL / EQL / PWL — capped to 6)
    if (overlays.liquidity) {
      for (const liq of bundle.liquidityLevels.slice(0, 6)) {
        const y = priceToY(liq.price);
        if (y !== null && y >= 6 && y <= plotBottom) {
          const startX = Math.max(14, Math.min(plotRight - 90, timeToX(liq.startTime) ?? 20));
          const endX =
            liq.swept && liq.endTime
              ? Math.max(startX + 45, Math.min(plotRight, timeToX(liq.endTime) ?? plotRight))
              : plotRight;
          nextLines.push({
            id: liq.id,
            y,
            price: liq.price,
            style: liq.swept ? "dotted" : "dashed",
            color:
              liq.code === "EQH" || liq.code === "EQL"
                ? "rgba(192, 119, 250, 0.72)"
                : liq.side === "HIGH"
                ? "rgba(194, 240, 118, 0.60)"
                : "rgba(94, 234, 212, 0.60)",
            startX,
            endX,
            width: 1.2,
          });
          rawLabels.push({
            id: liq.id,
            price: liq.price,
            idealY: y,
            priority: 60,
            label: `${liq.code} ${liq.price.toFixed(bundle.digits)}`,
            sublabel: liq.swept ? "SWEPT" : undefined,
            tone: "liquidity",
          });
        }
      }
    }

    // 4. Structure Breaks (MSS / CHoCH / BOS — with horizontal break ray from swing pivot to break bar)
    if (overlays.structure) {
      for (const st of bundle.structureBreaks.slice(-4)) {
        const y = priceToY(st.price);
        const xBreak = timeToX(st.time) ?? Math.floor(plotRight * 0.62);
        const xStart = timeToX(st.startTime) ?? Math.max(20, xBreak - 85);
        if (y !== null && y >= 14 && y <= plotBottom - 10) {
          nextLines.push({
            id: `struct-line-${st.id}`,
            y,
            price: st.price,
            style: st.kind === "BOS" ? "solid" : "dotted",
            color: st.bias === "BULLISH" ? "rgba(176, 246, 72, 0.70)" : "rgba(192, 119, 250, 0.75)",
            startX: Math.max(16, Math.min(xStart, xBreak - 24)),
            endX: Math.min(plotRight - 20, Math.max(xStart + 24, xBreak)),
            width: 1.4,
          });
          nextPins.push({
            id: st.id,
            x: Math.max(36, Math.min(plotRight - 135, xBreak - 18)),
            y,
            label: st.label,
            detail: `${st.price.toFixed(bundle.digits)}`,
            tone: st.kind === "MSS" ? "mss" : st.kind === "BOS" ? "bos" : "choch",
          });
        }
      }
    }

    // 5. Trades Layer: Clean TradingView-Style Long/Short Position Drawing ONLY (ZERO text, pills, or tags)
    if (overlays.tradeLabels) {
      const lastCandle = bundle.candles[bundle.candles.length - 1];
      const latestCandleX = lastCandle ? timeToX(lastCandle.time) ?? plotRight : plotRight;
      const clampedEndX = Math.max(48, Math.min(plotRight, latestCandleX + 10));

      bundle.trades.slice(0, 3).forEach((trade, idx) => {
        const zones = calculateTradeZones({
          direction: trade.direction,
          entryPrice: trade.entryPrice,
          stopLoss: trade.stopLoss,
          initialStopLoss: trade.initialStopLoss,
          tp1: trade.tp1,
          tp2: trade.tp2,
        });

        const entryStartX = Math.max(
          16,
          Math.min(clampedEndX - 28, timeToX(trade.entryTime) ?? Math.floor(clampedEndX * 0.5))
        );
        const boxWidth = Math.max(28, clampedEndX - entryStartX);

        // Cap opacity so multiple trades on the same symbol stay crisp and readable
        const isPrimary = idx === 0;
        const profitFillOpacity = isPrimary ? 0.16 : 0.08;
        const lossFillOpacity = isPrimary ? 0.15 : 0.08;
        const lineOpacity = isPrimary ? 1.0 : 0.65;

        const isBuy = trade.direction === "BUY";
        const outerTp = trade.tp2 > 0 ? trade.tp2 : trade.tp1;
        const hasBothTps = trade.tp1 > 0 && trade.tp2 > 0 && Math.abs(trade.tp2 - trade.tp1) > 1e-6;

        // Profit Zone (Green/Lime): ABOVE entry for LONG, BELOW entry for SHORT
        if (outerTp > 0) {
          const yEntry = priceToY(trade.entryPrice);
          const yTp = priceToY(outerTp);
          if (yEntry !== null && yTp !== null) {
            const validProfitDir = isBuy ? outerTp > trade.entryPrice : outerTp < trade.entryPrice;
            if (validProfitDir) {
              const top = Math.max(4, Math.min(yEntry, yTp));
              const bot = Math.min(plotBottom, Math.max(yEntry, yTp));
              if (bot - top >= 2) {
                nextTradeBoxes.push({
                  id: `pos-profit-${trade.ticket}`,
                  topY: top,
                  heightPx: bot - top,
                  leftX: entryStartX,
                  widthPx: boxWidth,
                  kind: "PROFIT",
                  opacity: profitFillOpacity,
                });
              }
            }
          }
        }

        // Loss Zone (Red): BELOW entry for LONG, ABOVE entry for SHORT (uses CURRENT stop loss)
        if (trade.stopLoss > 0) {
          const yEntry = priceToY(trade.entryPrice);
          const ySl = priceToY(trade.stopLoss);
          if (yEntry !== null && ySl !== null) {
            const validLossDir = isBuy ? trade.stopLoss < trade.entryPrice : trade.stopLoss > trade.entryPrice;
            if (validLossDir) {
              const top = Math.max(4, Math.min(yEntry, ySl));
              const bot = Math.min(plotBottom, Math.max(yEntry, ySl));
              if (bot - top >= 2) {
                nextTradeBoxes.push({
                  id: `pos-loss-${trade.ticket}`,
                  topY: top,
                  heightPx: bot - top,
                  leftX: entryStartX,
                  widthPx: boxWidth,
                  kind: "LOSS",
                  opacity: lossFillOpacity,
                });
              }
            }
          }
        }

        // Entry Line (clean solid neutral white across the position zone)
        const entryY = priceToY(trade.entryPrice);
        if (entryY !== null && entryY >= 4 && entryY <= plotBottom) {
          nextLines.push({
            id: `line-entry-${trade.ticket}`,
            y: entryY,
            price: trade.entryPrice,
            style: "solid",
            color: "#F4F7FF",
            startX: entryStartX,
            endX: clampedEndX,
            width: 1.5,
            opacity: lineOpacity,
          });
        }

        // Current Stop Loss Edge (clean solid red)
        if (trade.stopLoss > 0) {
          const slY = priceToY(trade.stopLoss);
          if (slY !== null && slY >= 4 && slY <= plotBottom) {
            nextLines.push({
              id: `line-sl-${trade.ticket}`,
              y: slY,
              price: trade.stopLoss,
              style: "solid",
              color: "#FF5A6E",
              startX: entryStartX,
              endX: clampedEndX,
              width: 1.5,
              opacity: lineOpacity,
            });
          }
        }

        // Faint dashed Original/Ghost SL line when stop has moved (tighten-only / BE+ / trail), NO text
        if (zones.ghostInitialSlPrice !== null) {
          const ghostY = priceToY(zones.ghostInitialSlPrice);
          if (ghostY !== null && ghostY >= 4 && ghostY <= plotBottom) {
            nextLines.push({
              id: `line-ghost-sl-${trade.ticket}`,
              y: ghostY,
              price: zones.ghostInitialSlPrice,
              style: "dashed",
              color: "rgba(255, 90, 110, 0.36)",
              startX: entryStartX,
              endX: clampedEndX,
              width: 1,
              opacity: lineOpacity,
            });
          }
        }

        // Outer TP Edge (clean solid green/lime)
        if (outerTp > 0) {
          const tpOuterY = priceToY(outerTp);
          if (tpOuterY !== null && tpOuterY >= 4 && tpOuterY <= plotBottom) {
            nextLines.push({
              id: `line-tp-outer-${trade.ticket}`,
              y: tpOuterY,
              price: outerTp,
              style: "solid",
              color: "#B0F648",
              startX: entryStartX,
              endX: clampedEndX,
              width: 1.5,
              opacity: lineOpacity,
            });
          }
        }

        // Inner TP1 Line (thin dashed green inside the profit zone when both TP1 & TP2 exist), NO text
        if (hasBothTps) {
          const tp1Y = priceToY(trade.tp1);
          if (tp1Y !== null && tp1Y >= 4 && tp1Y <= plotBottom) {
            nextLines.push({
              id: `line-tp1-${trade.ticket}`,
              y: tp1Y,
              price: trade.tp1,
              style: "dashed",
              color: "rgba(194, 240, 118, 0.72)",
              startX: entryStartX,
              endX: clampedEndX,
              width: 1,
              opacity: lineOpacity,
            });
          }
        }

        // Icon-only signal arrow if no SL/TP levels exist on a pending signal
        if (trade.stopLoss <= 0 && outerTp <= 0 && entryY !== null) {
          nextSignalArrows.push({
            id: `sig-arrow-${trade.ticket}`,
            x: entryStartX,
            y: entryY,
            direction: trade.direction,
          });
        }
      });
    }

    // Run priority-aware collision-free vertical label placement solver (Liquidity labels only)
    const nonOverlapping = resolveLabelCollisions(rawLabels, {
      minY: 8,
      maxY: plotBottom - 6,
      minGapPx: 23,
      defaultHeightPx: 20,
      maxLabels: 8,
    });

    // De-collide structure annotation pins vertically if two share similar X and Y
    const sortedPins = [...nextPins].sort((a, b) => a.y - b.y);
    for (let i = 1; i < sortedPins.length; i++) {
      if (
        Math.abs(sortedPins[i].x - sortedPins[i - 1].x) < 110 &&
        sortedPins[i].y - sortedPins[i - 1].y < 23
      ) {
        sortedPins[i] = {
          ...sortedPins[i],
          y: Math.min(plotBottom - 14, sortedPins[i - 1].y + 24),
        };
      }
    }

    setChartDims({ width, height });
    setZoneBoxes(nextZones);
    setTradePositionBoxes(nextTradeBoxes);
    setSignalArrows(nextSignalArrows);
    setLevelLines(nextLines);
    setResolvedLabels(nonOverlapping);
    setAnnotationPins(sortedPins);
    setSessionBands(nextSessions);
  }, [bundle, overlays]);

  // Initialize lightweight-charts instance and ResizeObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const initialRect = container.getBoundingClientRect();
    const chart = createChart(container, {
      width: Math.max(320, Math.floor(initialRect.width || 760)),
      height: Math.max(260, Math.floor(initialRect.height || 440)),
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: DESIGN_TOKENS.colors.chart.axisText,
        fontFamily: "'JetBrains Mono Variable', 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: DESIGN_TOKENS.colors.chart.gridLine },
        horzLines: { color: DESIGN_TOKENS.colors.chart.gridLine },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: DESIGN_TOKENS.colors.chart.crosshair,
          labelBackgroundColor: DESIGN_TOKENS.colors.chart.crosshairLabelBg,
        },
        horzLine: {
          color: DESIGN_TOKENS.colors.chart.crosshair,
          labelBackgroundColor: DESIGN_TOKENS.colors.chart.crosshairLabelBg,
        },
      },
      rightPriceScale: {
        borderColor: DESIGN_TOKENS.colors.chart.axisBorder,
        scaleMargins: {
          top: 0.08,
          bottom: 0.08,
        },
      },
      timeScale: {
        borderColor: DESIGN_TOKENS.colors.chart.axisBorder,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        barSpacing: 9,
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: DESIGN_TOKENS.colors.chart.upCandle,
      downColor: DESIGN_TOKENS.colors.chart.downCandle,
      borderUpColor: DESIGN_TOKENS.colors.chart.upCandle,
      borderDownColor: DESIGN_TOKENS.colors.chart.downCandle,
      wickUpColor: DESIGN_TOKENS.colors.chart.upWick,
      wickDownColor: DESIGN_TOKENS.colors.chart.downWick,
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

    // Ensure auto-scale price range spans Entry, SL, Ghost Initial SL, TP1, TP2
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

  const handleToggleFullscreen = () => {
    setIsFullscreen((prev) => !prev);
  };

  const labelToneClasses: Partial<Record<ResolvedPriceLabelItem["tone"], string>> = useMemo(
    () => ({
      liquidity: "bg-[#14274A]/92 border-[#C2F076]/55 text-[#C2F076]",
      structure: "bg-[#241B4B]/92 border-[#C077FA]/65 text-[#E5C7FF]",
    }),
    []
  );

  const pinToneClasses: Record<ProjectedAnnotationPin["tone"], string> = useMemo(
    () => ({
      mss: "bg-[#221D4E]/95 border-[#C077FA] text-[#E5C7FF]",
      choch: "bg-[#2A1D54]/95 border-[#C9ACDA] text-[#F0DEFF]",
      bos: "bg-[#16343A]/95 border-[#5EEAD4] text-[#C8FFF4]",
    }),
    []
  );

  return (
    <section
      aria-label="Live Institutional Execution Chart"
      data-fullscreen={isFullscreen ? "true" : "false"}
      className={
        isFullscreen
          ? "fixed inset-3 z-50 flex flex-col iea-chart-glass-shell overflow-hidden shadow-2xl"
          : "flex flex-col h-full min-h-[470px] iea-chart-glass-shell overflow-hidden"
      }
    >
      {/* Chart Toolbar Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2 bg-[#0D1B36]/85 border-b border-[rgba(186,214,255,0.13)] shrink-0">
        {/* Left: Symbol Switcher with Circular Coin Chips + Timeframes + Live Quote */}
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

          {/* Timeframe Selector (Segmented Pill Tabs) */}
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

          {/* Live Bid/Ask + Spread Pill */}
          <div
            className="hidden xl:flex items-center space-x-1.5 px-2.5 py-1 iea-pill-control font-mono text-xs"
            title={`Broker symbol ${bundle.brokerSymbol} · Spread ${bundle.spreadPoints} points`}
          >
            <span
              className={`w-4 h-4 rounded-full text-[9px] font-bold inline-flex items-center justify-center ${activeSymbolChip.chipBg}`}
            >
              {activeSymbolChip.shortCode}
            </span>
            <span className="text-[#B0F648] font-bold">{bundle.bid.toFixed(bundle.digits)}</span>
            <span className="text-[#8496B8]">/</span>
            <span className="text-[#FF5A6E] font-bold">{bundle.ask.toFixed(bundle.digits)}</span>
            <span className="text-[10px] text-[#C2F076] bg-[#B0F648]/12 px-1.5 py-0.2 rounded-full">
              Spr {bundle.spreadPoints}
            </span>
          </div>
        </div>

        {/* Right: Short-Form Toggleable Overlays + Fullscreen Toggle */}
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

          <button
            type="button"
            onClick={handleToggleFullscreen}
            aria-label={isFullscreen ? "Exit fullscreen chart" : "Fit chart content to view"}
            title={isFullscreen ? "Exit Fullscreen (Esc)" : "Fullscreen Chart"}
            data-testid="chart-fullscreen-toggle"
            className={`p-1.5 rounded-full border transition ${
              isFullscreen
                ? "bg-[#B0F648] text-[#081321] border-[#B0F648]"
                : "bg-[#0E1E3B]/80 hover:bg-[#19305C] border-[rgba(186,214,255,0.18)] text-[#F4F7FF]"
            }`}
          >
            {isFullscreen ? (
              <Minimize2 className="w-3.5 h-3.5" />
            ) : (
              <Maximize2 className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Sub-Header Active Trade Strip + Compact Drawing Legend */}
      {primaryTrade && (
        <div className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-1.5 bg-[#0B172F]/90 border-b border-[rgba(186,214,255,0.11)] text-xs font-mono shrink-0">
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
            <span
              title="Owner & Setup Quality Score"
              className="px-2 py-0.5 rounded-full bg-[#223D6A]/70 text-[#5EEAD4] border border-[#5EEAD4]/30 text-[10px] font-sans font-medium"
            >
              {primaryTrade.ownership} · S{primaryTrade.qualityScore}
            </span>
            <span className="text-[#8496B8]" title="Entry Price">
              In <strong className="text-[#F4F7FF]">{primaryTrade.entryPrice.toFixed(bundle.digits)}</strong>
            </span>
            <span className="text-[#FF7A8A]" title="Active Stop Loss (Initial SL in brackets)">
              SL <strong>{primaryTrade.stopLoss.toFixed(bundle.digits)}</strong>
              {Math.abs(primaryTrade.initialStopLoss - primaryTrade.stopLoss) > 1e-6 && (
                <span className="text-[#8496B8] ml-1">
                  ({primaryTrade.initialStopLoss.toFixed(bundle.digits)})
                </span>
              )}
            </span>
            <span className="text-[#C2F076]" title="Partial Take Profit 1 (50%)">
              TP1 <strong>{primaryTrade.tp1.toFixed(bundle.digits)}</strong> (+{primaryTrade.tp1R.toFixed(2)}R)
            </span>
            <span className="text-[#B0F648]" title="Final Take Profit 2 Target">
              TP2 <strong>{primaryTrade.tp2.toFixed(bundle.digits)}</strong> (+{primaryTrade.tp2R.toFixed(2)}R)
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span
              title="Floating P&L and R-Multiple"
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
            <span
              title="Rule R9.3: Stop Loss can only be tightened, never widened or removed"
              className="inline-flex items-center space-x-1 text-[10px] font-sans text-[#C2F076] bg-[#B0F648]/12 border border-[#B0F648]/30 px-2 py-0.5 rounded-full"
            >
              <ShieldCheck className="w-3 h-3" />
              <span>Tighten-SL</span>
            </span>
            <span
              title="Real-time telemetry feed status"
              className="inline-flex items-center space-x-1 text-[10px] font-sans text-[#B6C5E0] bg-[#091426]/80 px-2 py-0.5 rounded-full border border-[rgba(186,214,255,0.14)]"
            >
              <Radio className="w-3 h-3 text-[#B0F648] animate-pulse" />
              <span>{feedStatus}</span>
            </span>
          </div>
        </div>
      )}

      {/* Main Chart Viewport — true z-order: zones (z-5) -> candles (z-10) -> lines (z-20) -> non-trade labels (z-30) */}
      <div
        className="relative flex-1 min-h-0 w-full"
        style={{ backgroundColor: DESIGN_TOKENS.colors.chart.background }}
      >
        {/* BACKDROP OVERLAY LAYER (z-5): Behind candlesticks so candles stay 100% crisp */}
        <div
          className="absolute inset-0 z-[5] pointer-events-none overflow-hidden select-none"
          style={{ right: "72px", bottom: "26px" }}
        >
          {/* Session Background Bands */}
          {sessionBands.map((sb) => (
            <div
              key={sb.id}
              style={{
                left: `${sb.leftX}px`,
                width: `${sb.widthPx}px`,
                backgroundColor: sb.color,
              }}
              className="absolute top-0 bottom-0 border-x border-[rgba(186,214,255,0.12)]"
            />
          ))}

          {/* FVG / IFVG / OB Shaded Boxes */}
          {zoneBoxes.map((zb) => {
            const boxStyleByKind: Record<ProjectedZoneBox["kind"], string> = {
              FVG_BULL: "bg-[#5EEAD4]/[0.10] border border-[#5EEAD4]/40 rounded-r-md",
              FVG_BEAR: "bg-[#FBBF24]/[0.10] border border-[#FBBF24]/40 rounded-r-md",
              IFVG: "bg-[#C077FA]/[0.06] border border-dashed border-[#C077FA]/35 rounded-md opacity-75",
              OB_BULL: "bg-[#B0F648]/[0.09] border border-[#C2F076]/40 rounded-r-md",
              OB_BEAR: "bg-[#C077FA]/[0.10] border border-[#C077FA]/45 rounded-r-md",
            };
            return (
              <div
                key={zb.id}
                style={{
                  top: `${zb.topY}px`,
                  height: `${zb.heightPx}px`,
                  left: `${zb.leftX}px`,
                  width: `${zb.widthPx}px`,
                }}
                className={`absolute ${boxStyleByKind[zb.kind]}`}
              />
            );
          })}

          {/* Trades Layer: Clean Long/Short Position Profit & Loss Zones (NO text, NO pills, NO tooltips) */}
          {tradePositionBoxes.map((tb) => (
            <div
              key={tb.id}
              data-testid={`trade-position-zone-${tb.kind.toLowerCase()}`}
              style={{
                top: `${tb.topY}px`,
                height: `${tb.heightPx}px`,
                left: `${tb.leftX}px`,
                width: `${tb.widthPx}px`,
                backgroundColor:
                  tb.kind === "PROFIT"
                    ? `rgba(176, 246, 72, ${tb.opacity})`
                    : `rgba(255, 90, 110, ${tb.opacity})`,
              }}
              className={`absolute ${tb.dashed ? "border border-dashed border-white/20" : ""}`}
            />
          ))}
        </div>

        {/* Lightweight Charts Canvas Mount (z-10, transparent bg so candles sit cleanly ON TOP of zones) */}
        <div ref={containerRef} className="absolute inset-0 z-10 w-full h-full" />

        {/* FOREGROUND OVERLAY LAYER (z-20 / z-30): Lines above zones + labels ONLY for non-trade layers */}
        <div
          className="absolute inset-0 z-20 pointer-events-none overflow-hidden select-none"
          style={{ right: "72px", bottom: "26px" }}
        >
          {/* Session Header Labels (Sessions layer only) */}
          {sessionBands.map((sb) => (
            <div
              key={`lbl-${sb.id}`}
              style={{ left: `${sb.leftX}px`, width: `${sb.widthPx}px` }}
              className="absolute top-0"
            >
              <span className="inline-block m-1.5 px-2 py-0.5 rounded-full bg-[#0A152B]/85 text-[9px] font-mono text-[#B6C5E0] border border-[rgba(186,214,255,0.16)]">
                {sb.label}
              </span>
            </div>
          ))}

          {/* FVG / IFVG / OB Labels (FVG/OB layer only) */}
          {zoneBoxes.map((zb) => (
            <div
              key={`lbl-${zb.id}`}
              title={zb.tooltip}
              style={{ top: `${zb.topY}px`, left: `${zb.leftX}px` }}
              className="absolute pointer-events-auto"
            >
              <span className="inline-block ml-1.5 mt-0.5 px-1.5 py-0.2 text-[9px] font-mono font-semibold text-[#F4F7FF] bg-[#0A152B]/85 rounded-full border border-[rgba(186,214,255,0.14)]">
                {zb.label}
              </span>
            </div>
          ))}

          {/* Horizontal Level Lines (Trades Entry/SL/TP/GhostSL + Liquidity + Structure Rays) & Signal Arrows */}
          <svg className="absolute inset-0 z-20 w-full h-full overflow-visible">
            {levelLines.map((ln) => (
              <line
                key={ln.id}
                x1={ln.startX}
                y1={ln.y}
                x2={ln.endX}
                y2={ln.y}
                stroke={ln.color}
                strokeWidth={ln.width}
                strokeOpacity={ln.opacity ?? 1}
                strokeDasharray={
                  ln.style === "dashed" ? "6 4" : ln.style === "dotted" ? "2 3" : undefined
                }
              />
            ))}

            {/* Icon-only arrow markers for signals without SL/TP levels (zero text) */}
            {signalArrows.map((arr) =>
              arr.direction === "BUY" ? (
                <polygon
                  key={arr.id}
                  points={`${arr.x},${arr.y - 6} ${arr.x - 5},${arr.y + 4} ${arr.x + 5},${arr.y + 4}`}
                  fill="#B0F648"
                />
              ) : (
                <polygon
                  key={arr.id}
                  points={`${arr.x},${arr.y + 6} ${arr.x - 5},${arr.y - 4} ${arr.x + 5},${arr.y - 4}`}
                  fill="#FF5A6E"
                />
              )
            )}

            {/* Leader lines connecting true price Y to collision-resolved liquidity badge Y when displaced */}
            {resolvedLabels
              .filter((lbl) => lbl.displaced)
              .map((lbl) => (
                <path
                  key={`leader-${lbl.id}`}
                  d={`M ${Math.max(120, chartDims.width - 280)} ${lbl.idealY} L ${Math.max(
                    135,
                    chartDims.width - 262
                  )} ${lbl.resolvedY}`}
                  stroke="rgba(182, 197, 224, 0.55)"
                  strokeWidth={1}
                  strokeDasharray="2 2"
                  fill="none"
                />
              ))}
          </svg>

          {/* Structure Break Annotations (MSS / CHoCH / BOS only — zero trade pins) */}
          {annotationPins.map((pin) => (
            <div
              key={pin.id}
              title={`${pin.label} · ${pin.detail}`}
              style={{
                left: `${pin.x}px`,
                top: `${Math.max(8, pin.y - 11)}px`,
              }}
              className={`absolute z-30 pointer-events-auto px-2 py-0.5 rounded-lg border text-[10px] font-mono leading-tight shadow-sm whitespace-nowrap ${
                pinToneClasses[pin.tone]
              }`}
            >
              <div className="font-bold flex items-center space-x-1">
                <Target className="w-2.5 h-2.5 shrink-0" />
                <span>{pin.label}</span>
                <span className="text-[9px] opacity-80">{pin.detail}</span>
              </div>
            </div>
          ))}

          {/* Collision-Aware Right-Aligned Level Labels (Liquidity layer only — zero trade labels) */}
          {resolvedLabels.map((lbl) => (
            <div
              key={lbl.id}
              data-testid={`chart-level-label-${lbl.tone}`}
              title={`${lbl.label}${lbl.sublabel ? ` (${lbl.sublabel})` : ""}`}
              style={{
                top: `${lbl.resolvedY - 10}px`,
                right: "6px",
              }}
              className={`absolute z-30 pointer-events-auto px-2 py-0.5 rounded-full border text-[10px] font-mono leading-none flex items-center space-x-1 whitespace-nowrap ${
                labelToneClasses[lbl.tone] || ""
              }`}
            >
              <span className="font-bold">{lbl.label}</span>
              {lbl.sublabel && (
                <span className="text-[9px] px-1.5 py-0.2 rounded-full bg-black/35 text-[#F4F7FF]">
                  {lbl.sublabel}
                </span>
              )}
            </div>
          ))}

          {/* Compact Bottom-Left Drawing Layer Legend */}
          <div className="absolute left-2.5 bottom-2 z-30 flex flex-wrap items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#091426]/85 border border-[rgba(186,214,255,0.14)] text-[9px] font-mono text-[#B6C5E0]">
            <span className="inline-flex items-center space-x-1">
              <span className="w-2 h-2 rounded-full bg-[#B0F648]" />
              <span>TP/Bull</span>
            </span>
            <span className="inline-flex items-center space-x-1">
              <span className="w-2 h-2 rounded-full bg-[#FF5A6E]" />
              <span>SL/Risk</span>
            </span>
            <span className="inline-flex items-center space-x-1">
              <span className="w-2 h-2 rounded-full bg-[#5EEAD4]" />
              <span>FVG</span>
            </span>
            <span className="inline-flex items-center space-x-1">
              <span className="w-2 h-2 rounded-full bg-[#C077FA]" />
              <span>MSS/EQH</span>
            </span>
          </div>
        </div>
      </div>
    </section>
  );
};
