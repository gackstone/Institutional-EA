import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  PERSISTED_SCHEMA_VERSION,
  readVersionedState,
  resetAllUiPersistedState,
  writeVersionedState,
  type StorageLike,
} from "../persistedState.ts";

class MemoryStorage implements StorageLike {
  map = new Map<string, string>();
  getItem(k: string) {
    return this.map.has(k) ? this.map.get(k)! : null;
  }
  setItem(k: string, v: string) {
    this.map.set(k, v);
  }
  removeItem(k: string) {
    this.map.delete(k);
  }
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const COMPANION_ROOT = path.resolve(__dirname, "../../..");

test("readVersionedState migrates legacy unversioned JSON and plain strings to current schema version", () => {
  const store = new MemoryStorage();
  // Legacy unversioned overlay toggles (using old key `trades`)
  store.setItem(
    "iea_chart_overlay_toggles_v1",
    JSON.stringify({ liquidity: false, fvgOb: true, structure: true, sessions: false, trades: false })
  );

  type Toggles = { liquidity: boolean; fvgOb: boolean; structure: boolean; sessions: boolean; tradeLabels: boolean };
  const defaults: Toggles = { liquidity: true, fvgOb: true, structure: true, sessions: true, tradeLabels: true };
  const validate = (v: unknown): v is Toggles =>
    Boolean(v && typeof v === "object" && typeof (v as any).tradeLabels === "boolean");

  const res = readVersionedState<Toggles>({
    key: "iea_chart_overlay_toggles_v1",
    defaultValue: defaults,
    validate,
    migrate: (legacy: any) =>
      legacy && typeof legacy === "object"
        ? {
            liquidity: Boolean(legacy.liquidity ?? true),
            fvgOb: Boolean(legacy.fvgOb ?? true),
            structure: Boolean(legacy.structure ?? true),
            sessions: Boolean(legacy.sessions ?? true),
            tradeLabels: Boolean(legacy.tradeLabels ?? legacy.trades ?? true),
          }
        : null,
    storage: store,
    logger: () => {},
  });

  assert.equal(res.migrated, true);
  assert.equal(res.reset, false);
  assert.equal(res.value.liquidity, false);
  assert.equal(res.value.tradeLabels, false);

  // Saved value must now carry current schemaVersion
  const saved = JSON.parse(store.getItem("iea_chart_overlay_toggles_v1")!);
  assert.equal(saved.schemaVersion, PERSISTED_SCHEMA_VERSION);
  assert.equal(saved.data.tradeLabels, false);
});

test("readVersionedState recovers cleanly from corrupt JSON without throwing and resets only that key", () => {
  const store = new MemoryStorage();
  store.setItem("iea_chart_overlay_toggles_v1", "{corrupt_json_from_old_build!!!");
  store.setItem("unrelated_key", "keep_me");

  const res = readVersionedState<{ ok: boolean }>({
    key: "iea_chart_overlay_toggles_v1",
    defaultValue: { ok: true },
    validate: (v): v is { ok: boolean } => Boolean(v && typeof v === "object" && typeof (v as any).ok === "boolean"),
    storage: store,
    logger: () => {},
  });

  assert.equal(res.reset, true);
  assert.deepEqual(res.value, { ok: true });
  assert.equal(store.getItem("unrelated_key"), "keep_me");

  // Reset helper clears UI keys only
  writeVersionedState("institutional_ea_theme", "dark", store);
  const cleared = resetAllUiPersistedState(store);
  assert.equal(cleared.length, 2);
  assert.equal(store.getItem("unrelated_key"), "keep_me");
});

test("Preload & IPC contract: every preload invoke channel has a main.cjs handler, and every renderer electronAPI call exists in preload.cjs", () => {
  const preloadSrc = fs.readFileSync(path.join(COMPANION_ROOT, "electron", "preload.cjs"), "utf8");
  const mainSrc = fs.readFileSync(path.join(COMPANION_ROOT, "electron", "main.cjs"), "utf8");

  // 1. Every ipcRenderer.invoke("channel") in preload.cjs must have ipcMain.handle("channel") in main.cjs
  const invokeChannels = [...preloadSrc.matchAll(/ipcRenderer\.invoke\(\s*["']([^"']+)["']/g)].map((m) => m[1]);
  assert.ok(invokeChannels.length > 20, "Expected >20 IPC invoke channels in preload.cjs");

  const missingHandlers = invokeChannels.filter(
    (ch) => !new RegExp(`ipcMain\\.handle\\(\\s*["']${ch}["']`).test(mainSrc)
  );
  assert.deepEqual(missingHandlers, [], `Missing ipcMain.handle for channels: ${missingHandlers.join(", ")}`);

  // 2. Every exposed method on window.electronAPI
  const exposedMethods = new Set(
    [...preloadSrc.matchAll(/^\s+([a-zA-Z0-9_]+)\s*:\s*\(/gm)].map((m) => m[1])
  );

  // Check ipc.ts and App.tsx calls to window.electronAPI.<method>
  const rendererFiles = [
    path.join(COMPANION_ROOT, "src", "services", "ipc.ts"),
    path.join(COMPANION_ROOT, "src", "App.tsx"),
    path.join(COMPANION_ROOT, "src", "components", "ErrorBoundary.tsx"),
  ];
  const missingMethods: string[] = [];
  for (const file of rendererFiles) {
    const content = fs.readFileSync(file, "utf8");
    for (const m of content.matchAll(/electronAPI\??\.([a-zA-Z0-9_]+)/g)) {
      const method = m[1];
      if (!exposedMethods.has(method)) {
        missingMethods.push(`${path.basename(file)}:${method}`);
      }
    }
  }
  assert.deepEqual(missingMethods, [], `Renderer calls missing preload methods: ${missingMethods.join(", ")}`);
});

test("Fallback recovery screen exists and includes Reload, Reset settings, and Open logs actions", () => {
  const fallbackHtml = fs.readFileSync(path.join(COMPANION_ROOT, "electron", "fallback.html"), "utf8");
  assert.match(fallbackHtml, /btn-reload/);
  assert.match(fallbackHtml, /btn-reset/);
  assert.match(fallbackHtml, /btn-logs/);
  assert.match(fallbackHtml, /watchdog-fallback-screen/);
});
