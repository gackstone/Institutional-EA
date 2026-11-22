import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  IChartApi,
  ISeriesApi,
  UTCTimestamp,
} from "lightweight-charts";
import {
  Camera,
  FastForward,
  Pause,
  Play,
  SkipBack,
  SkipForward,
  X,
} from "lucide-react";
import { controlClient } from "../services/ipc";
import { TradeReplayPayload } from "../types";
import { DESIGN_TOKENS } from "../styles/designTokens";

interface TradeReplayModalProps {
  ticket: number | null;
  onClose: () => void;
}

const SPEEDS = [1, 2, 4, 8] as const;

export const TradeReplayModal: React.FC<TradeReplayModalProps> = ({ ticket, onClose }) => {
  const [tf, setTf] = useState<"M1" | "M5" | "M15" | "H1">("M5");
  const [payload, setPayload] = useState<TradeReplayPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [barIndex, setBarIndex] = useState<number>(0);
  const [playing, setPlaying] = useState<boolean>(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(2);
  const [screenshotBaseUrl, setScreenshotBaseUrl] = useState<string>("http://127.0.0.1:8765");
  const [authToken, setAuthToken] = useState<string>("");

  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (window.electronAPI?.getControlConnectionInfo) {
      window.electronAPI.getControlConnectionInfo().then((info) => {
        setScreenshotBaseUrl(info.baseUrl || "http://127.0.0.1:8765");
        setAuthToken(info.token || "");
      }).catch(() => {});
    }
  }, []);

  useEffect(() => {
    if (ticket === null) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setPlaying(false);
    controlClient
      .getTradeReplay(ticket, tf)
      .then((res) => {
        if (cancelled) return;
        setPayload(res);
        setBarIndex(res.candles.length > 0 ? Math.min(20, res.candles.length - 1) : 0);
      })
      .catch((err) => {
        if (!cancelled) setError(err?.message || "Unable to load trade replay from MT5/bot.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticket, tf]);

  // Playback timer
  useEffect(() => {
    if (!playing || !payload || payload.candles.length === 0) return;
    const intervalMs = Math.max(120, Math.round(900 / speed));
    const timer = setInterval(() => {
      setBarIndex((prev) => {
        if (prev >= payload.candles.length - 1) {
          setPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [playing, speed, payload]);

  // Initialize replay chart
  useEffect(() => {
    const el = containerRef.current;
    if (!el || ticket === null) return;

    const chart = createChart(el, {
      width: Math.max(320, el.clientWidth || 720),
      height: 360,
      layout: {
        background: { type: ColorType.Solid, color: DESIGN_TOKENS.colors.chart.background },
        textColor: DESIGN_TOKENS.colors.chart.axisText,
        fontFamily: "'JetBrains Mono Variable', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: DESIGN_TOKENS.colors.chart.gridLine },
        horzLines: { color: DESIGN_TOKENS.colors.chart.gridLine },
      },
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: DESIGN_TOKENS.colors.chart.upCandle,
      downColor: DESIGN_TOKENS.colors.chart.downCandle,
      borderUpColor: DESIGN_TOKENS.colors.chart.upCandle,
      borderDownColor: DESIGN_TOKENS.colors.chart.downCandle,
      wickUpColor: DESIGN_TOKENS.colors.chart.upWick,
      wickDownColor: DESIGN_TOKENS.colors.chart.downWick,
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        if (e.contentRect.width > 100) {
          chart.applyOptions({ width: Math.floor(e.contentRect.width) });
        }
      }
    });
    ro.observe(el);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [ticket]);

  // Update visible candles up to barIndex
  const visibleCandles = useMemo(() => {
    if (!payload || payload.candles.length === 0) return [];
    return payload.candles.slice(0, barIndex + 1);
  }, [payload, barIndex]);

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    series.setData(
      visibleCandles.map((c) => ({
        time: c.time as UTCTimestamp,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      }))
    );
  }, [visibleCandles]);

  if (ticket === null) return null;

  const trade = payload?.trade;
  const currentBar = visibleCandles[visibleCandles.length - 1];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Trade Replay #${ticket}`}
      className="fixed inset-0 z-50 bg-[#0E0D0B]/85 backdrop-blur-md flex items-center justify-center p-4"
    >
      <div className="iea-card w-full max-w-5xl max-h-[92vh] overflow-y-auto p-5 space-y-4 shadow-2xl">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[rgba(255,255,253,0.08)] pb-3">
          <div>
            <h2 className="text-base font-semibold text-[#F5F5F2]">
              Trade Replay · #{ticket} {trade ? `(${trade.symbol} ${trade.direction} ${trade.volume}L)` : ""}
            </h2>
            <p className="text-[11px] font-mono text-[#8A8986] mt-0.5">
              Source: MT5 Historical Candles + Bot Execution Events
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <div className="inline-flex bg-[#0E0D0B]/80 border border-[rgba(255,255,253,0.10)] rounded-full p-0.5">
              {(["M1", "M5", "M15", "H1"] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  onClick={() => setTf(t)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-mono font-bold ${
                    tf === t ? "bg-[#F5F5F2] text-[#121110]" : "text-[#B4B3B0] hover:text-white"
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close trade replay"
              className="p-1.5 rounded-full bg-white/5 hover:bg-white/15 text-[#F5F5F2]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Trade Summary Strip */}
        {trade && (
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs font-mono">
            <div className="iea-inset p-2.5">
              <div className="text-[10px] font-sans text-[#8A8986]">Entry</div>
              <div className="text-[#F5F5F2] font-bold">{trade.open_price}</div>
            </div>
            <div className="iea-inset p-2.5">
              <div className="text-[10px] font-sans text-[#8A8986]">Exit</div>
              <div className="text-[#F5F5F2] font-bold">{trade.close_price || "—"}</div>
            </div>
            <div className="iea-inset p-2.5">
              <div className="text-[10px] font-sans text-[#8A8986]">SL</div>
              <div className="text-[#F5989E] font-bold">{trade.sl || "—"}</div>
            </div>
            <div className="iea-inset p-2.5">
              <div className="text-[10px] font-sans text-[#8A8986]">TP</div>
              <div className="text-[#6EE7B7] font-bold">{trade.tp || "—"}</div>
            </div>
            <div className="iea-inset p-2.5">
              <div className="text-[10px] font-sans text-[#8A8986]">Realized P&amp;L</div>
              <div className={trade.profit >= 0 ? "text-[#6EE7B7] font-bold" : "text-[#F07178] font-bold"}>
                {trade.profit >= 0 ? "+" : ""}${trade.profit.toFixed(2)}
              </div>
            </div>
          </div>
        )}

        {/* Replay Chart Canvas */}
        <div className="relative rounded-2xl overflow-hidden border border-[rgba(255,255,253,0.08)] bg-[#161513] min-h-[360px]">
          <div ref={containerRef} className="w-full h-[360px]" />
          {loading && (
            <div className="absolute inset-0 bg-[#161513]/85 flex items-center justify-center text-xs text-[#B4B3B0]">
              Loading real MT5 historical candles for trade #{ticket}...
            </div>
          )}
          {!loading && error && (
            <div className="absolute inset-0 bg-[#161513]/90 flex items-center justify-center text-xs text-[#F5989E] px-4 text-center">
              {error}
            </div>
          )}
          {!loading && !error && payload && payload.candles.length === 0 && (
            <div className="absolute inset-0 bg-[#161513]/90 flex items-center justify-center text-xs text-[#8A8986] px-4 text-center">
              Waiting for MT5 historical candles for this trade window ({tf}). Ensure MT5 terminal is connected.
            </div>
          )}
        </div>

        {/* Playback Controls */}
        {payload && payload.candles.length > 0 && (
          <div className="iea-inset p-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setBarIndex((i) => Math.max(0, i - 1))}
                className="iea-pill-control p-2 text-[#F5F5F2]"
                title="Step back 1 bar"
              >
                <SkipBack className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setPlaying((p) => !p)}
                className="px-4 py-1.5 rounded-full bg-[#36B37E] hover:bg-[#3FC48B] text-[#121110] text-xs font-extrabold inline-flex items-center space-x-1.5"
              >
                {playing ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                <span>{playing ? "Pause" : "Play"}</span>
              </button>
              <button
                type="button"
                onClick={() => setBarIndex((i) => Math.min(payload.candles.length - 1, i + 1))}
                className="iea-pill-control p-2 text-[#F5F5F2]"
                title="Step forward 1 bar"
              >
                <SkipForward className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() =>
                  setSpeed((s) => SPEEDS[(SPEEDS.indexOf(s) + 1) % SPEEDS.length])
                }
                className="iea-pill-control px-3 py-1.5 text-xs font-mono text-[#5EC2C6] inline-flex items-center space-x-1"
                title="Playback speed"
              >
                <FastForward className="w-3 h-3" />
                <span>{speed}x</span>
              </button>
            </div>

            <div className="flex-1 min-w-[180px] flex items-center space-x-3">
              <input
                type="range"
                min={0}
                max={payload.candles.length - 1}
                value={barIndex}
                onChange={(e) => setBarIndex(Number(e.target.value))}
                className="w-full accent-[#6EE7B7]"
                aria-label="Replay timeline scrubber"
              />
              <span className="text-[11px] font-mono text-[#B4B3B0] shrink-0">
                {barIndex + 1}/{payload.candles.length}
                {currentBar ? ` · ${new Date(currentBar.time * 1000).toISOString().slice(11, 16)} UTC` : ""}
              </span>
            </div>
          </div>
        )}

        {/* Execution Events & Saved Trade Screenshots */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="iea-inset p-3.5 space-y-2">
            <h3 className="font-semibold text-[#F5F5F2]">Real Trade Events ({payload?.events.length ?? 0})</h3>
            {!payload || payload.events.length === 0 ? (
              <div className="text-[#8A8986] py-2">No execution lifecycle events recorded for this ticket.</div>
            ) : (
              <div className="space-y-1.5 max-h-40 overflow-y-auto font-mono text-[11px]">
                {payload.events.map((ev) => (
                  <div key={ev.id} className="flex items-center justify-between bg-[#0E0D0B]/65 px-2.5 py-1.5 rounded-lg">
                    <span className="text-[#6EE7B7] font-bold">{ev.event_type}</span>
                    <span className="text-[#8A8986]">{new Date(ev.created_at).toLocaleTimeString()}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="iea-inset p-3.5 space-y-2">
            <h3 className="font-semibold text-[#F5F5F2] flex items-center space-x-1.5">
              <Camera className="w-3.5 h-3.5 text-[#5EC2C6]" />
              <span>Trade Chart Screenshots ({payload?.screenshots.length ?? 0})</span>
            </h3>
            {!payload || payload.screenshots.length === 0 ? (
              <div className="text-[#8A8986] py-2">No chart screenshots saved for this trade yet.</div>
            ) : (
              <div className="grid grid-cols-2 gap-2 max-h-44 overflow-y-auto">
                {payload.screenshots.map((sh) => {
                  const srcUrl = `${screenshotBaseUrl}/api/trades/screenshots/file?name=${encodeURIComponent(
                    sh.filename
                  )}${authToken ? `&token=${encodeURIComponent(authToken)}` : ""}`;
                  return (
                    <a
                      key={sh.id}
                      href={srcUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="block rounded-xl overflow-hidden border border-[rgba(255,255,253,0.10)] bg-[#0E0D0B]"
                    >
                      <img src={srcUrl} alt={`${sh.symbol} ${sh.stage}`} className="w-full h-24 object-cover" />
                      <div className="px-2 py-1 text-[10px] font-mono text-[#B4B3B0] flex justify-between">
                        <span className="text-[#6EE7B7] font-bold">{sh.stage}</span>
                        <span>{new Date(sh.created_at).toLocaleTimeString()}</span>
                      </div>
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
