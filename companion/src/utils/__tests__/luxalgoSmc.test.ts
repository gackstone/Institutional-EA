import { test } from "node:test";
import assert from "node:assert/strict";
import { computeLuxAlgoSmc, MAX_SMC_OBJECTS } from "../luxalgoSmcEngine.ts";
import {
  applyLayerChipToggle,
  cloneDefaultSmcSettings,
  deriveLayerChipStates,
  formatCssRgba,
  loadSmcChartSettings,
  parseCssColor,
  saveSmcChartSettings,
  SMC_SETTINGS_STORAGE_KEY,
} from "../smcChartSettings.ts";
import type { CandlePoint } from "../chartCanvasRenderer.ts";
import type { StorageLike } from "../persistedState.ts";

function generateCandles(count = 450, stepSec = 3600, base = 154.0): CandlePoint[] {
  const startTs = 1760000000;
  const out: CandlePoint[] = [];
  let price = base;
  for (let i = 0; i < count; i++) {
    const macro = Math.sin(i / 22.0) * 1.4;
    const micro = Math.sin(i / 3.2) * 0.35;
    const trend = (i / count) * 1.2;
    const o = price;
    let c = base + trend + macro + micro;
    if (i % 37 === 15) c = o + 0.95;
    else if (i % 37 === 31) c = o - 0.9;
    let h = Math.max(o, c) + 0.14;
    let l = Math.min(o, c) - 0.14;
    if (i === 60 || i === 72) {
      h = base + 3.2;
      c = Math.max(c, base + 3.05);
    }
    if (i === 110 || i === 122) {
      l = base - 2.4;
      c = Math.min(c, base - 2.25);
    }
    out.push({ time: startTs + i * stepSec, open: o, high: h, low: l, close: c, volume: 100 });
    price = c;
  }
  return out;
}

function makeMemoryStorage(): StorageLike {
  const map = new Map<string, string>();
  return {
    getItem: (k) => map.get(k) ?? null,
    setItem: (k, v) => {
      map.set(k, v);
    },
    removeItem: (k) => {
      map.delete(k);
    },
  };
}

test("computeLuxAlgoSmc produces BOS/CHoCH, OBs, FVGs, Strong/Weak H/L, P/D zones, and IRL/ERL tags", () => {
  const candles = generateCandles(450);
  const settings = cloneDefaultSmcSettings();
  const res = computeLuxAlgoSmc(candles, settings, "H1");

  assert.ok(res.internalStructures.length > 0, "Expected internal structure breaks");
  assert.ok(res.swingStructures.length > 0, "Expected swing structure breaks");
  assert.ok(res.internalStructures.every((s) => s.irlErl === "IRL" && s.tier === "INTERNAL"));
  assert.ok(res.swingStructures.every((s) => s.irlErl === "ERL" && s.tier === "SWING"));

  assert.ok(res.internalOrderBlocks.length <= settings.internalOBCount);
  assert.ok(res.swingOrderBlocks.length <= settings.swingOBCount);
  assert.ok(res.internalOrderBlocks.every((ob) => ob.irlErl === "IRL" && ob.top > ob.bottom));
  assert.ok(res.swingOrderBlocks.every((ob) => ob.irlErl === "ERL" && ob.top > ob.bottom));

  assert.equal(res.strongWeakLevels.length, 2);
  const hi = res.strongWeakLevels.find((l) => l.kind === "HIGH")!;
  const lo = res.strongWeakLevels.find((l) => l.kind === "LOW")!;
  assert.ok(hi.price > lo.price);

  assert.equal(res.premiumDiscountZones.length, 3);
  const prem = res.premiumDiscountZones.find((z) => z.kind === "PREMIUM")!;
  const eq = res.premiumDiscountZones.find((z) => z.kind === "EQUILIBRIUM")!;
  const disc = res.premiumDiscountZones.find((z) => z.kind === "DISCOUNT")!;
  assert.ok(Math.abs(prem.bottom - (0.95 * hi.price + 0.05 * lo.price)) < 1e-6);
  assert.ok(Math.abs(eq.top - (0.525 * hi.price + 0.475 * lo.price)) < 1e-6);
  assert.ok(Math.abs(disc.top - (0.95 * lo.price + 0.05 * hi.price)) < 1e-6);
  assert.equal(eq.irlErl, "IRL");

  assert.equal(res.candleTrends.length, candles.length);
});

test("Present mode caps structures to most recent; 5,000-candle run stays fast and capped", () => {
  const candles = generateCandles(5000, 300);
  const histSettings = cloneDefaultSmcSettings();
  const t0 = performance.now();
  const hist = computeLuxAlgoSmc(candles, histSettings, "M5");
  const elapsedMs = performance.now() - t0;

  assert.ok(elapsedMs < 1000, `5000-candle TS SMC took ${elapsedMs.toFixed(1)}ms`);
  assert.ok(hist.internalStructures.length <= MAX_SMC_OBJECTS);
  assert.ok(hist.swingStructures.length <= MAX_SMC_OBJECTS);
  assert.ok(hist.equalHighsLows.length <= MAX_SMC_OBJECTS);
  assert.ok(hist.fairValueGaps.length <= MAX_SMC_OBJECTS);

  const pres = computeLuxAlgoSmc(candles, { ...histSettings, mode: "Present" }, "M5");
  assert.ok(pres.internalStructures.length <= 1);
  assert.ok(pres.swingStructures.length <= 1);
  assert.ok(pres.equalHighsLows.length <= 1);
});

test("SmcChartSettings persists safely, recovers from corrupt JSON, and syncs with layer chips", () => {
  const storage = makeMemoryStorage();
  const custom = {
    ...cloneDefaultSmcSettings(),
    mode: "Present" as const,
    style: "Monochrome" as const,
    internalOBCount: 12,
    showPremiumDiscount: true,
  };
  assert.equal(saveSmcChartSettings(custom, storage), true);
  const loaded = loadSmcChartSettings(storage);
  assert.equal(loaded.mode, "Present");
  assert.equal(loaded.style, "Monochrome");
  assert.equal(loaded.internalOBCount, 12);
  assert.equal(loaded.showPremiumDiscount, true);

  // Corrupt storage falls back cleanly
  storage.setItem(SMC_SETTINGS_STORAGE_KEY, "{not-valid-json");
  const recovered = loadSmcChartSettings(storage);
  assert.equal(recovered.mode, "Historical");
  assert.equal(recovered.internalOBCount, 5);

  // Bidirectional chip sync
  const toggledStruct = applyLayerChipToggle(recovered, "structure");
  assert.equal(deriveLayerChipStates(toggledStruct).structure, false);
  const toggledBack = applyLayerChipToggle(toggledStruct, "structure");
  assert.equal(deriveLayerChipStates(toggledBack).structure, true);

  // Color alpha helpers
  const parsed = parseCssColor("rgba(49, 121, 245, 0.20)");
  assert.equal(parsed.hex, "#3179f5");
  assert.equal(parsed.alpha, 0.2);
  assert.equal(formatCssRgba("#3179f5", 0.2), "rgba(49, 121, 245, 0.20)");
});
