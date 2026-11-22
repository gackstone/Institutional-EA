import React from "react";
import {
  Wallet,
  TrendingUp,
  DollarSign,
  PieChart,
  Layers,
  Zap,
  ArrowUpRight,
  ArrowDownRight
} from "lucide-react";
import { AccountMetrics } from "../types";

interface MetricsGridProps {
  account: AccountMetrics;
}

export const MetricsGrid: React.FC<MetricsGridProps> = ({ account }) => {
  const isDailyPnlPos = account.dailyPnl > 0.0001;
  const isDailyPnlNeg = account.dailyPnl < -0.0001;

  const isFloatingPos = account.profit > 0.0001;
  const isFloatingNeg = account.profit < -0.0001;

  const currencySymbol = account.currency === "EUR" ? "€" : account.currency === "GBP" ? "£" : "$";

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2.5 sm:gap-3 p-3 sm:px-4 sm:py-3 bg-institutional-ea-bg border-b border-institutional-ea-border transition-colors duration-150 z-10">
      {/* 1. Balance */}
      <div className="institutional-ea-card p-3 sm:p-3.5 flex flex-col justify-between shadow-xs hover:border-institutional-ea-borderStrong transition-all">
        <div className="flex items-center justify-between text-institutional-ea-textSecondary text-[11px] font-sans font-semibold uppercase tracking-wider">
          <span>Balance</span>
          <div className="w-6 h-6 rounded-md bg-institutional-ea-secondary border border-institutional-ea-border flex items-center justify-center text-institutional-ea-textMuted">
            <Wallet className="w-3.5 h-3.5" />
          </div>
        </div>
        <div className="mt-2.5">
          <div className="text-lg sm:text-xl font-bold font-mono tracking-tight text-institutional-ea-text">
            {currencySymbol}
            {account.balance.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
          <div className="text-[10px] text-institutional-ea-textMuted font-sans mt-0.5 truncate">
            {account.currency || "USD"} Base Account
          </div>
        </div>
      </div>

      {/* 2. Equity */}
      <div className="institutional-ea-card p-3 sm:p-3.5 flex flex-col justify-between shadow-xs hover:border-institutional-ea-borderStrong transition-all">
        <div className="flex items-center justify-between text-institutional-ea-textSecondary text-[11px] font-sans font-semibold uppercase tracking-wider">
          <span>Equity</span>
          <div className="w-6 h-6 rounded-md bg-institutional-ea-primary/10 border border-institutional-ea-primary/20 flex items-center justify-center text-institutional-ea-primary">
            <TrendingUp className="w-3.5 h-3.5" />
          </div>
        </div>
        <div className="mt-2.5">
          <div className="text-lg sm:text-xl font-bold font-mono tracking-tight text-institutional-ea-text">
            {currencySymbol}
            {account.equity.toLocaleString(undefined, {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2,
            })}
          </div>
          <div className="text-[10px] text-institutional-ea-textMuted font-sans mt-0.5 truncate">
            Mark-to-Market Valuation
          </div>
        </div>
      </div>

      {/* 3. Daily P&L */}
      <div className="institutional-ea-card p-3 sm:p-3.5 flex flex-col justify-between shadow-xs hover:border-institutional-ea-borderStrong transition-all">
        <div className="flex items-center justify-between text-institutional-ea-textSecondary text-[11px] font-sans font-semibold uppercase tracking-wider">
          <span>Daily P&amp;L</span>
          <div
            className={`w-6 h-6 rounded-md flex items-center justify-center border ${
              isDailyPnlPos
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-500"
                : isDailyPnlNeg
                ? "bg-rose-500/10 border-rose-500/20 text-rose-500"
                : "bg-institutional-ea-secondary border-institutional-ea-border text-institutional-ea-textMuted"
            }`}
          >
            {isDailyPnlPos ? (
              <ArrowUpRight className="w-3.5 h-3.5" />
            ) : isDailyPnlNeg ? (
              <ArrowDownRight className="w-3.5 h-3.5" />
            ) : (
              <DollarSign className="w-3.5 h-3.5" />
            )}
          </div>
        </div>
        <div className="mt-2.5">
          <div
            className={`text-lg sm:text-xl font-bold font-mono tracking-tight ${
              isDailyPnlPos
                ? "text-emerald-600 dark:text-emerald-400"
                : isDailyPnlNeg
                ? "text-rose-600 dark:text-rose-400"
                : "text-institutional-ea-text"
            }`}
          >
            {isDailyPnlPos ? "+" : isDailyPnlNeg ? "-" : ""}
            {currencySymbol}
            {Math.abs(account.dailyPnl).toFixed(2)}
          </div>
          <div className="text-[10px] text-institutional-ea-textMuted font-sans mt-0.5 truncate">
            Realized + Floating Today
          </div>
        </div>
      </div>

      {/* 4. Floating P&L */}
      <div className="institutional-ea-card p-3 sm:p-3.5 flex flex-col justify-between shadow-xs hover:border-institutional-ea-borderStrong transition-all">
        <div className="flex items-center justify-between text-institutional-ea-textSecondary text-[11px] font-sans font-semibold uppercase tracking-wider">
          <span>Floating P&amp;L</span>
          <div
            className={`w-6 h-6 rounded-md flex items-center justify-center border ${
              isFloatingPos
                ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-500"
                : isFloatingNeg
                ? "bg-rose-500/10 border-rose-500/20 text-rose-500"
                : "bg-institutional-ea-secondary border-institutional-ea-border text-institutional-ea-textMuted"
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
          </div>
        </div>
        <div className="mt-2.5">
          <div
            className={`text-lg sm:text-xl font-bold font-mono tracking-tight ${
              isFloatingPos
                ? "text-emerald-600 dark:text-emerald-400"
                : isFloatingNeg
                ? "text-rose-600 dark:text-rose-400"
                : "text-institutional-ea-text"
            }`}
          >
            {isFloatingPos ? "+" : isFloatingNeg ? "-" : ""}
            {currencySymbol}
            {Math.abs(account.profit).toFixed(2)}
          </div>
          <div className="text-[10px] text-institutional-ea-textMuted font-sans mt-0.5 truncate">
            Net Open Position Profit
          </div>
        </div>
      </div>

      {/* 5. Margin Level */}
      <div className="institutional-ea-card p-3 sm:p-3.5 flex flex-col justify-between shadow-xs hover:border-institutional-ea-borderStrong transition-all">
        <div className="flex items-center justify-between text-institutional-ea-textSecondary text-[11px] font-sans font-semibold uppercase tracking-wider">
          <span>Margin Level</span>
          <div className="w-6 h-6 rounded-md bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-500">
            <PieChart className="w-3.5 h-3.5" />
          </div>
        </div>
        <div className="mt-2.5">
          <div className="text-lg sm:text-xl font-bold font-mono tracking-tight text-institutional-ea-text">
            {account.marginLevel > 0 ? `${account.marginLevel.toFixed(1)}%` : "Safe (0%)"}
          </div>
          <div className="text-[10px] text-institutional-ea-textMuted font-sans mt-0.5 truncate">
            Free: {currencySymbol}{account.freeMargin.toFixed(0)}
          </div>
        </div>
      </div>

      {/* 6. Active Trades */}
      <div className="institutional-ea-card p-3 sm:p-3.5 flex flex-col justify-between shadow-xs hover:border-institutional-ea-borderStrong transition-all">
        <div className="flex items-center justify-between text-institutional-ea-textSecondary text-[11px] font-sans font-semibold uppercase tracking-wider">
          <span>Active Trades</span>
          <div className="w-6 h-6 rounded-md bg-institutional-ea-primary/10 border border-institutional-ea-primary/20 flex items-center justify-center text-institutional-ea-primary">
            <Layers className="w-3.5 h-3.5" />
          </div>
        </div>
        <div className="mt-2.5">
          <div className="text-lg sm:text-xl font-bold font-mono tracking-tight text-institutional-ea-text">
            {account.positionsCount}
          </div>
          <div className="text-[10px] text-institutional-ea-textMuted font-sans mt-0.5 truncate">
            Leverage: 1:{account.leverage || 100}
          </div>
        </div>
      </div>
    </div>
  );
};
