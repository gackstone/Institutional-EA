import React from "react";
import { ShieldCheck, TrendingUp } from "lucide-react";

interface PhoneMockupProps {
  compact?: boolean;
}

export const PhoneMockup: React.FC<PhoneMockupProps> = ({ compact = false }) => {
  return (
    <div
      className={`relative mx-auto rounded-[2.6rem] border-[7px] border-slate-900 bg-[#0D0E11] text-white shadow-2xl dark:border-slate-700 ${
        compact ? "w-[260px] p-3.5" : "w-[295px] sm:w-[320px] p-4"
      }`}
    >
      {/* Dynamic Island / Notch */}
      <div className="mx-auto mb-3 h-5 w-24 rounded-full bg-slate-950" />

      {/* Header */}
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <img
            src="/logo.png"
            alt="Institutional EA"
            className="h-7 w-7 shrink-0 rounded-lg bg-black object-contain p-0.5 ring-1 ring-white/15"
          />
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-emerald-400">
              Institutional EA
            </p>
            <p className="text-sm font-bold text-white">XAUUSD · M15</p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/15 px-2.5 py-1 text-[10px] font-semibold text-emerald-400">
          <ShieldCheck className="h-3 w-3" /> READ-ONLY
        </span>
      </div>

      {/* KPI Strip */}
      <div className="mb-3 grid grid-cols-2 gap-2">
        <div className="rounded-xl border border-white/10 bg-white/5 p-2.5">
          <p className="text-[10px] text-slate-400">Equity</p>
          <p className="font-mono text-sm font-semibold text-white">$10,582.40</p>
          <p className="text-[10px] text-emerald-400">+1.26% today</p>
        </div>
        <div className="rounded-xl border border-white/10 bg-white/5 p-2.5">
          <p className="text-[10px] text-slate-400">Today P/L</p>
          <p className="font-mono text-sm font-semibold text-emerald-400">+$132.15</p>
          <p className="text-[10px] text-slate-400">4 trades · 75% WR</p>
        </div>
      </div>

      {/* TradingView-style SMC Chart Preview */}
      <div className="relative mb-3 overflow-hidden rounded-xl border border-white/10 bg-white p-3 text-slate-900">
        <div className="mb-2 flex items-center justify-between text-[10px] font-mono">
          <span className="font-semibold text-slate-700">2656.80</span>
          <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-semibold text-emerald-700">
            LONDON
          </span>
        </div>

        <svg viewBox="0 0 240 110" className="h-28 w-full" aria-label="Live Smart Money Concepts chart preview">
          {/* FVG Zone */}
          <rect x="35" y="64" width="160" height="18" fill="rgba(0, 255, 104, 0.22)" stroke="#089981" strokeWidth="0.8" />
          <text x="115" y="76" textAnchor="middle" fontSize="8" fontWeight="700" fill="#065f46">
            FVG
          </text>

          {/* OB Zone */}
          <rect x="110" y="12" width="110" height="16" fill="rgba(242, 54, 69, 0.18)" stroke="#F23645" strokeWidth="0.8" />
          <text x="165" y="23" textAnchor="middle" fontSize="8" fontWeight="700" fill="#991b1b">
            OB
          </text>

          {/* BOS dashed line */}
          <line x1="20" y1="42" x2="185" y2="42" stroke="#089981" strokeWidth="1" strokeDasharray="3 2" />
          <text x="102" y="38" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="#089981">
            BOS
          </text>

          {/* Candlesticks */}
          {[
            { x: 24, o: 84, c: 76, h: 72, l: 88, bull: true },
            { x: 42, o: 76, c: 66, h: 62, l: 78, bull: true },
            { x: 60, o: 66, c: 72, h: 64, l: 76, bull: false },
            { x: 78, o: 72, c: 58, h: 54, l: 74, bull: true },
            { x: 96, o: 58, c: 48, h: 44, l: 60, bull: true },
            { x: 114, o: 48, c: 52, h: 46, l: 56, bull: false },
            { x: 132, o: 52, c: 38, h: 34, l: 54, bull: true },
            { x: 150, o: 38, c: 32, h: 28, l: 42, bull: true },
            { x: 168, o: 32, c: 36, h: 30, l: 40, bull: false },
            { x: 186, o: 36, c: 26, h: 22, l: 38, bull: true },
          ].map((b) => (
            <g key={b.x}>
              <line x1={b.x} y1={b.h} x2={b.x} y2={b.l} stroke={b.bull ? "#089981" : "#F23645"} strokeWidth="1.2" />
              <rect
                x={b.x - 4}
                y={Math.min(b.o, b.c)}
                width="8"
                height={Math.max(3, Math.abs(b.o - b.c))}
                rx="1"
                fill={b.bull ? "#089981" : "#F23645"}
              />
            </g>
          ))}
        </svg>

        <div className="mt-1 flex items-center justify-between text-[9px] text-slate-500">
          <span>LONG POSITION · SL 2645.00</span>
          <span className="font-semibold text-emerald-600">TP 2670.00</span>
        </div>
      </div>

      {/* Active Trade Row */}
      <div className="flex items-center justify-between rounded-xl border border-white/10 bg-white/5 px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400">
            <TrendingUp className="h-4 w-4" />
          </span>
          <div>
            <p className="text-xs font-semibold text-white">BUY 0.10 XAUUSD</p>
            <p className="text-[10px] text-slate-400">Entry 2652.50 · #104921</p>
          </div>
        </div>
        <span className="font-mono text-xs font-bold text-emerald-400">+$43.00</span>
      </div>
    </div>
  );
};
