/**
 * Pure formatting utilities for currency, prices, P/L, durations, and timestamps.
 * Never hardcodes '$' — always respects the currency code from the companion payload.
 */

const CURRENCY_SYMBOLS: Record<string, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  JPY: "¥",
  CHF: "CHF ",
  AUD: "A$",
  CAD: "C$",
  USDT: "$",
  USC: "¢",
};

export function getCurrencyPrefix(currency?: string | null): string {
  const code = (currency || "USD").trim().toUpperCase();
  return CURRENCY_SYMBOLS[code] ?? `${code} `;
}

export function formatCurrency(value: number | null | undefined, currency?: string | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const prefix = getCurrencyPrefix(currency);
  const abs = Math.abs(value);
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return value < 0 ? `-${prefix}${formatted}` : `${prefix}${formatted}`;
}

export function formatSignedPnl(value: number | null | undefined, currency?: string | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const prefix = getCurrencyPrefix(currency);
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const abs = Math.abs(value);
  const formatted = abs.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${sign}${prefix}${formatted}`;
}

export function formatPrice(value: number | null | undefined, digits = 2): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const safeDigits = Math.max(0, Math.min(8, Math.round(digits)));
  return value.toFixed(safeDigits);
}

export function formatPercent(value: number | null | undefined, decimals = 1): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${value.toFixed(decimals)}%`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return "—";
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ${m % 60}m`;
  const d = Math.floor(h / 24);
  return `${d}d ${h % 24}h`;
}

export function formatClockTime(isoOrMs: string | number | null | undefined): string {
  if (isoOrMs === null || isoOrMs === undefined) return "—";
  const d = typeof isoOrMs === "number" ? new Date(isoOrMs) : new Date(isoOrMs);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export function formatShortDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const mon = d.toLocaleString("en-US", { month: "short" });
  const day = d.getDate();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${mon} ${day}, ${hh}:${mm}`;
}

export function computeSlTpDistance(
  currentPrice: number,
  targetPrice: number | null | undefined,
  digits = 2
): string {
  if (
    !Number.isFinite(currentPrice) ||
    typeof targetPrice !== "number" ||
    !Number.isFinite(targetPrice) ||
    targetPrice <= 0
  ) {
    return "—";
  }
  const diff = Math.abs(targetPrice - currentPrice);
  return diff.toFixed(Math.max(0, Math.min(6, digits)));
}
