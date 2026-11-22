import { ScreenId } from "../types";

export interface GlossaryItem {
  short: string;
  full: string;
  category: "Account & Risk" | "Execution & Orders" | "Chart & SMC" | "System";
}

/**
 * Centralized UI Copy, Short Forms, Tooltips, and Glossary.
 * Single Source of Truth for all user-facing strings in the Companion app.
 */
export const UI_COPY = {
  brand: {
    title: "INSTITUTIONAL EA",
    subtitle: "v1.3 · DEMO",
    demoLockChip: "DEMO · LIVE_TRADING_ENABLED=false",
    demoLockShort: "DEMO LOCK",
    demoLockTooltip: "Hard Safety Lock: execution_mode=DEMO and LIVE_TRADING_ENABLED=false",
  },
  nav: {
    groups: {
      Monitor: "MONITOR",
      Control: "CONTROL",
      Diagnose: "DIAGNOSE",
    },
    screens: {
      dashboard: { label: "Dashboard", tooltip: "Main trading terminal & live chart" },
      positions: { label: "Positions & Orders", tooltip: "Open positions & pending orders" },
      history: { label: "Trade History", tooltip: "Closed trade history" },
      analytics: { label: "Analytics", tooltip: "Performance analytics & profit factor" },
      mt5: { label: "MT5 Terminal", tooltip: "MetaTrader 5 terminal scan & EA deploy" },
      operations: { label: "Operations", tooltip: "Allowlisted operations runner" },
      logs: { label: "Event Logs", tooltip: "Structured runtime event logs" },
      health: { label: "System Health", tooltip: "SQLite, MT5 & audit trail health" },
      settings: { label: "Settings", tooltip: "Diagnostics, pairing & short-form glossary" },
    } satisfies Record<ScreenId, { label: string; tooltip: string }>,
  },
  kpis: {
    balEq: { label: "Bal / Eq", tooltip: "Account Balance & Live Equity" },
    todayPnl: { label: "Today P&L", tooltip: "Today realized + floating P&L in USD and R-multiples" },
    dailyLoss: { label: "Daily Loss", tooltip: "Daily realized loss used vs hard daily loss limit" },
    ddCap: { label: "DD vs Cap", tooltip: "Total account drawdown vs maximum drawdown cap" },
    openExp: { label: "Open Exp", tooltip: "Active exposure: open positions & pending orders" },
  },
  chart: {
    layers: {
      liquidity: { label: "Liq", tooltip: "Liquidity Pools (PDH, PDL, PWH, PWL, EQH, EQL)" },
      fvgOb: { label: "FVG/OB", tooltip: "Fair Value Gaps, Inverse FVGs & Order Blocks" },
      structure: { label: "Struct", tooltip: "Market Structure Breaks (MSS, CHoCH, BOS)" },
      sessions: { label: "Sess", tooltip: "Session & Killzone Ranges (Asia, London, NY, Overlap)" },
      tradeLabels: { label: "Trades", tooltip: "Bot Trade Levels (Entry, SL, TP1, TP2, Risk/Reward Zones & Signals)" },
    },
  },
} as const;

export const SHORT_FORM_GLOSSARY: GlossaryItem[] = [
  // Account & Risk
  { short: "Bal", full: "Account Balance (closed trade cash balance)", category: "Account & Risk" },
  { short: "Eq", full: "Account Equity (Balance + Floating P&L)", category: "Account & Risk" },
  { short: "P&L", full: "Profit & Loss (Realized or Floating)", category: "Account & Risk" },
  { short: "DD", full: "Drawdown (Peak-to-valley equity decline)", category: "Account & Risk" },
  { short: "Cap", full: "Hard Maximum Risk / Drawdown Ceiling", category: "Account & Risk" },
  { short: "Exp", full: "Open Portfolio Exposure across instruments", category: "Account & Risk" },
  { short: "Lev", full: "Account Margin Leverage ratio (e.g. 1:100)", category: "Account & Risk" },
  { short: "R / RR", full: "Risk Unit (1R = initial SL risk) / Reward-to-Risk Ratio", category: "Account & Risk" },

  // Execution & Orders
  { short: "Pos", full: "Open Market Position on MT5", category: "Execution & Orders" },
  { short: "Ord", full: "Pending Limit or Stop Order", category: "Execution & Orders" },
  { short: "SL / SL+", full: "Stop Loss / Tighten Stop Loss (Rule R9.3: never widen)", category: "Execution & Orders" },
  { short: "BE+", full: "Break-Even Plus cost buffer lock", category: "Execution & Orders" },
  { short: "TP / TP1 / TP2", full: "Take Profit target (TP1 partial 50%, TP2 final target)", category: "Execution & Orders" },
  { short: "Lot", full: "Standard MT5 contract volume size", category: "Execution & Orders" },
  { short: "Spr", full: "Current Bid-Ask Spread in points", category: "Execution & Orders" },
  { short: "50%", full: "Partial Close 50% of active position volume", category: "Execution & Orders" },

  // Chart & SMC
  { short: "Liq", full: "Liquidity Pools (PDH/PDL/PWH/PWL/EQH/EQL resting stops)", category: "Chart & SMC" },
  { short: "PDH / PDL", full: "Previous Day High / Previous Day Low liquidity level", category: "Chart & SMC" },
  { short: "PWH / PWL", full: "Previous Week High / Previous Week Low liquidity level", category: "Chart & SMC" },
  { short: "EQH / EQL", full: "Equal Highs / Equal Lows liquidity magnet (Rule R4)", category: "Chart & SMC" },
  { short: "FVG / IFVG", full: "Fair Value Gap / Inverse Fair Value Gap imbalance (Rule R6)", category: "Chart & SMC" },
  { short: "OB", full: "Institutional Order Block demand/supply zone (Rule R5)", category: "Chart & SMC" },
  { short: "BOS", full: "Break of Structure body-close trend continuation (Rule R2)", category: "Chart & SMC" },
  { short: "CHoCH", full: "Change of Character early structural shift warning (Rule R3)", category: "Chart & SMC" },
  { short: "MSS", full: "Market Structure Shift with displacement impulse", category: "Chart & SMC" },
  { short: "Sess", full: "Trading Session Killzone (Asian, London, LDN/NY Overlap, NY)", category: "Chart & SMC" },

  // System
  { short: "ZMQ", full: "ZeroMQ/TCP Bridge Sockets (5555 EA / 5556 IPC)", category: "System" },
  { short: "TG", full: "Telegram Notification & Alert Dispatcher", category: "System" },
];
