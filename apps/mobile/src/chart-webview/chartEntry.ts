import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import {
  BULL_COLOR,
  BEAR_COLOR,
  DEFAULT_SMC_CHART_SETTINGS,
  drawPremiumDiscountZones,
  drawProjectedOverlaysToCanvas,
  getChartThemeTokens,
  projectEngineDrawings,
  validateEngineDrawingsFeed,
  type CandlePoint,
  type EngineDrawingsFeed,
  type OverlayVisibility,
} from "@institutional-ea/chart-core";

declare global {
  interface Window {
    ReactNativeWebView?: {
      postMessage: (msg: string) => void;
    };
  }
}

interface IncomingChartMessage {
  action:
    | "SET_DATA"
    | "UPDATE_CANDLE"
    | "UPDATE_DRAWINGS"
    | "UPDATE_LAYERS"
    | "UPDATE_THEME"
    | "RESET_VIEW"
    | "FOCUS_TIME";
  payload?: any;
}

function postToNative(type: string, payload?: unknown): void {
  try {
    if (window.ReactNativeWebView?.postMessage) {
      window.ReactNativeWebView.postMessage(JSON.stringify({ type, payload }));
    }
  } catch {
    // Ignore bridge post failures
  }
}

function bootChart(): void {
  const container = document.getElementById("chart-container");
  const canvas = document.getElementById("overlay-canvas") as HTMLCanvasElement | null;
  if (!container || !canvas) return;

  let theme: "dark" | "light" = "dark";
  let symbol = "";
  let timeframe = "M5";
  let digits = 2;
  let candles: CandlePoint[] = [];
  let drawingsFeed: EngineDrawingsFeed | null = null;
  let layers: OverlayVisibility = {
    liquidity: true,
    fvgOb: true,
    structure: true,
    sessions: true,
    trades: true,
  };
  let rafId: number | null = null;
  let lastHistoryRequestTime = 0;
  let lastTapTime = 0;
  let lastCrosshairPost = 0;

  const initialTokens = getChartThemeTokens(theme);

  const chart: IChartApi = createChart(container, {
    width: container.clientWidth || window.innerWidth,
    height: container.clientHeight || window.innerHeight,
    layout: {
      background: { type: ColorType.Solid, color: initialTokens.background },
      textColor: initialTokens.axisText,
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
      autoScale: true,
      scaleMargins: { top: 0.1, bottom: 0.1 },
    },
    timeScale: {
      borderColor: initialTokens.axisBorder,
      timeVisible: true,
      secondsVisible: false,
      rightOffset: 8,
      barSpacing: 7,
      minBarSpacing: 2,
    },
    handleScroll: {
      mouseWheel: true,
      pressedMouseMove: true,
      horzTouchDrag: true,
      vertTouchDrag: true,
    },
    handleScale: {
      axisPressedMouseMove: true,
      mouseWheel: true,
      pinch: true,
    },
  });

  const series: ISeriesApi<"Candlestick"> = chart.addSeries(CandlestickSeries, {
    upColor: BULL_COLOR,
    downColor: BEAR_COLOR,
    borderVisible: false,
    wickUpColor: BULL_COLOR,
    wickDownColor: BEAR_COLOR,
    priceLineVisible: true,
    lastValueVisible: true,
  });

  function scheduleRedraw(): void {
    if (rafId !== null) return;
    rafId = requestAnimationFrame(() => {
      rafId = null;
      redrawOverlay();
    });
  }

  function redrawOverlay(): void {
    if (!container || !canvas) return;
    const plotW = container.clientWidth;
    const plotH = container.clientHeight;
    if (plotW <= 0 || plotH <= 0) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const targetW = Math.round(plotW * dpr);
    const targetH = Math.round(plotH * dpr);
    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
      canvas.style.width = `${plotW}px`;
      canvas.style.height = `${plotH}px`;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, plotW, plotH);

    if (drawingsFeed && candles.length > 0 && symbol) {
      const validated = validateEngineDrawingsFeed(drawingsFeed, symbol, timeframe);
      const projector = {
        timeToX: (t: number) => chart.timeScale().timeToCoordinate(t as UTCTimestamp),
        priceToY: (p: number) => series.priceToCoordinate(p),
        plotWidth: plotW,
        plotHeight: plotH,
        candles,
      };

      const pndZones = (drawingsFeed as any)?.smc?.premium_discount_zones ?? [];
      if (pndZones.length > 0) {
        drawPremiumDiscountZones(ctx, pndZones, DEFAULT_SMC_CHART_SETTINGS, projector, theme);
      }

      const projected = projectEngineDrawings(validated.items, layers, projector);
      drawProjectedOverlaysToCanvas(ctx, projected, plotW, plotH, null, {
        clear: false,
        theme,
        smcSettings: DEFAULT_SMC_CHART_SETTINGS,
        digits,
      });
    }

    ctx.restore();
  }

  function applyTheme(nextTheme: "dark" | "light"): void {
    theme = nextTheme;
    const tokens = getChartThemeTokens(theme);
    document.body.style.background = tokens.background;
    chart.applyOptions({
      layout: {
        background: { type: ColorType.Solid, color: tokens.background },
        textColor: tokens.axisText,
      },
      grid: {
        vertLines: { color: tokens.gridLine },
        horzLines: { color: tokens.gridLine },
      },
      rightPriceScale: { borderColor: tokens.axisBorder },
      timeScale: { borderColor: tokens.axisBorder },
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
    });
    scheduleRedraw();
  }

  chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
    scheduleRedraw();
    if (range && range.from < 8 && candles.length > 0) {
      const now = Date.now();
      if (now - lastHistoryRequestTime > 2000) {
        lastHistoryRequestTime = now;
        postToNative("LOAD_MORE_HISTORY", { beforeTime: candles[0].time });
      }
    }
  });

  chart.subscribeCrosshairMove((param) => {
    const now = Date.now();
    if (now - lastCrosshairPost < 50) return;
    lastCrosshairPost = now;
    if (!param || !param.time) {
      postToNative("CROSSHAIR", null);
      return;
    }
    const bar = param.seriesData.get(series) as any;
    if (bar && typeof bar.close === "number") {
      postToNative("CROSSHAIR", {
        time: Number(param.time),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      });
    }
  });

  // Double-tap to reset view & price auto-fit
  container.addEventListener(
    "touchend",
    () => {
      const now = Date.now();
      if (now - lastTapTime < 280) {
        chart.timeScale().fitContent();
        chart.priceScale("right").applyOptions({ autoScale: true });
        scheduleRedraw();
      }
      lastTapTime = now;
    },
    { passive: true }
  );

  // ResizeObserver for portrait/landscape & fullscreen transitions
  const resize = () => {
    const w = container.clientWidth || window.innerWidth;
    const h = container.clientHeight || window.innerHeight;
    if (w > 0 && h > 0) {
      chart.resize(w, h);
      scheduleRedraw();
    }
  };
  if (typeof ResizeObserver !== "undefined") {
    new ResizeObserver(resize).observe(container);
  }
  window.addEventListener("resize", resize);

  function handleMessage(raw: unknown): void {
    try {
      const msg: IncomingChartMessage =
        typeof raw === "string" ? JSON.parse(raw) : (raw as IncomingChartMessage);
      if (!msg || !msg.action) return;

      switch (msg.action) {
        case "SET_DATA": {
          const p = msg.payload || {};
          if (typeof p.symbol === "string") symbol = p.symbol;
          if (typeof p.timeframe === "string") timeframe = p.timeframe;
          if (typeof p.digits === "number" && Number.isFinite(p.digits)) {
            digits = p.digits;
            const minMove = typeof p.point === "number" && p.point > 0 ? p.point : Math.pow(10, -digits);
            series.applyOptions({
              priceFormat: { type: "price", precision: digits, minMove },
            });
          }
          if (p.theme === "light" || p.theme === "dark") {
            applyTheme(p.theme);
          }
          if (p.layers) {
            layers = { ...layers, ...p.layers };
          }
          if (Array.isArray(p.candles)) {
            const clean = p.candles
              .filter(
                (c: any) =>
                  typeof c?.time === "number" &&
                  typeof c?.open === "number" &&
                  typeof c?.high === "number" &&
                  typeof c?.low === "number" &&
                  typeof c?.close === "number"
              )
              .sort((a: any, b: any) => a.time - b.time);
            // Deduplicate identical timestamps
            const deduped: CandlePoint[] = [];
            for (const c of clean) {
              if (deduped.length > 0 && deduped[deduped.length - 1].time === c.time) {
                deduped[deduped.length - 1] = c;
              } else {
                deduped.push(c);
              }
            }
            candles = deduped;
            series.setData(
              deduped.map((c) => ({
                time: c.time as UTCTimestamp,
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close,
              }))
            );
            if (!p.preserveRange) {
              chart.timeScale().fitContent();
            }
          }
          if (p.drawings !== undefined) {
            drawingsFeed = p.drawings;
          }
          if (typeof p.focusTime === "number" && p.focusTime > 0 && candles.length > 0) {
            const idx = candles.findIndex((c) => c.time >= p.focusTime);
            const center = idx >= 0 ? idx : candles.length - 1;
            chart.timeScale().setVisibleLogicalRange({
              from: Math.max(0, center - 35),
              to: Math.min(candles.length + 5, center + 25),
            });
          }
          scheduleRedraw();
          break;
        }

        case "UPDATE_CANDLE": {
          const c = msg.payload;
          if (c && typeof c.time === "number" && typeof c.close === "number") {
            const bar: CandlePoint = {
              time: c.time,
              open: c.open,
              high: c.high,
              low: c.low,
              close: c.close,
            };
            if (candles.length > 0 && candles[candles.length - 1].time === bar.time) {
              candles[candles.length - 1] = bar;
            } else if (candles.length === 0 || bar.time > candles[candles.length - 1].time) {
              candles.push(bar);
            }
            series.update({
              time: bar.time as UTCTimestamp,
              open: bar.open,
              high: bar.high,
              low: bar.low,
              close: bar.close,
            });
            scheduleRedraw();
          }
          break;
        }

        case "UPDATE_DRAWINGS": {
          drawingsFeed = msg.payload ?? null;
          scheduleRedraw();
          break;
        }

        case "UPDATE_LAYERS": {
          if (msg.payload) {
            layers = { ...layers, ...msg.payload };
            scheduleRedraw();
          }
          break;
        }

        case "UPDATE_THEME": {
          if (msg.payload === "light" || msg.payload === "dark") {
            applyTheme(msg.payload);
          }
          break;
        }

        case "RESET_VIEW": {
          chart.timeScale().fitContent();
          chart.priceScale("right").applyOptions({ autoScale: true });
          scheduleRedraw();
          break;
        }

        case "FOCUS_TIME": {
          const ts = Number(msg.payload);
          if (Number.isFinite(ts) && ts > 0 && candles.length > 0) {
            const idx = candles.findIndex((c) => c.time >= ts);
            const center = idx >= 0 ? idx : candles.length - 1;
            chart.timeScale().setVisibleLogicalRange({
              from: Math.max(0, center - 35),
              to: Math.min(candles.length + 5, center + 25),
            });
            scheduleRedraw();
          }
          break;
        }
      }
    } catch {
      // Malformed bridge message ignored safely
    }
  }

  // Listen on BOTH document (Android WebView) and window (iOS WebView)
  document.addEventListener("message", (ev: any) => handleMessage(ev?.data));
  window.addEventListener("message", (ev: any) => handleMessage(ev?.data));

  postToNative("CHART_READY", { width: container.clientWidth, height: container.clientHeight });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", bootChart);
} else {
  bootChart();
}
