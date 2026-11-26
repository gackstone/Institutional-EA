import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const CORE_TRADING_SCREENS_PATH = path.resolve(
  __dirname,
  "../../components/screens/CoreTradingScreens.tsx"
);

test("Regression Guard: Removed Watchlist must never reappear in Dashboard source", () => {
  const content = fs.readFileSync(CORE_TRADING_SCREENS_PATH, "utf-8");

  // Removed watchlist symbols, filters, card labels
  const forbiddenPatterns = [
    /<Watchlist/i,
    /WATCHLIST_INSTRUMENTS/,
    /filteredWatchlist/,
    /My watchlist/i,
    /data-testid="watchlist-card"/i,
  ];

  for (const pattern of forbiddenPatterns) {
    assert.equal(
      pattern.test(content),
      false,
      `Regression detected: forbidden pattern ${pattern} found in CoreTradingScreens.tsx`
    );
  }
});

test("Regression Guard: Old KPI labels (Profit Factor, Max Drawdown, Net Realized) must never reappear", () => {
  const content = fs.readFileSync(CORE_TRADING_SCREENS_PATH, "utf-8");

  // Old labels that were replaced in KPI row
  const forbiddenKpiLabels = [
    />PROFIT FACTOR</,
    />MAX DRAWDOWN</,
    />NET REALIZED</,
    /data-testid="kpi-card-profit-factor"/,
    /data-testid="kpi-card-max-drawdown"/,
    /data-testid="kpi-card-net-realized"/,
  ];

  for (const pattern of forbiddenKpiLabels) {
    assert.equal(
      pattern.test(content),
      false,
      `Regression detected: deprecated KPI label ${pattern} found in CoreTradingScreens.tsx`
    );
  }

  // Required new KPI cards must exist
  assert.match(content, /data-testid="kpi-card-account"/);
  assert.match(content, /account-kpi-toggle-/);
  assert.match(content, /data-testid="kpi-card-today-pnl"/);
  assert.match(content, /data-testid="kpi-card-total-profits"/);
  assert.match(content, /data-testid="kpi-card-win-rate"/);
});

test("Regression Guard: Deprecated PNL Trend chart header block must remain removed", () => {
  const content = fs.readFileSync(CORE_TRADING_SCREENS_PATH, "utf-8");

  // Deprecated header elements
  const forbiddenHeaderElements = [
    /Real-time equity curve, institutional order flow/,
    /<h2[^>]*>PNL Trend<\/h2>/,
    /<span[^>]*>LIVE<\/span>/,
  ];

  for (const pattern of forbiddenHeaderElements) {
    assert.equal(
      pattern.test(content),
      false,
      `Regression detected: deprecated chart header element ${pattern} found in CoreTradingScreens.tsx`
    );
  }

  // Removed chart header P&L/Equity toggle, Balance/Sync bar, and time-period filters must stay removed
  const forbiddenChartHeaderControls = [
    /aria-label="Toggle P&L or Equity display"/,
    /aria-label="Select trend range"/,
    /TREND_RANGES/,
    /handleRangeSelect/,
  ];

  for (const pattern of forbiddenChartHeaderControls) {
    assert.equal(
      pattern.test(content),
      false,
      `Regression detected: removed chart header control ${pattern} found in CoreTradingScreens.tsx`
    );
  }
});
