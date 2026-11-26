import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../../../../");

test("Supabase migration 20261126000003 enforces read_only scope constraint and RLS on all 3 tables", () => {
  const sqlPath = path.join(
    REPO_ROOT,
    "supabase/migrations/20261126000003_mobile_cloud_pairing_sync.sql"
  );
  const sql = fs.readFileSync(sqlPath, "utf-8");

  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.mobile_pairing_sessions/);
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.mobile_paired_devices/);
  assert.match(sql, /CREATE TABLE IF NOT EXISTS public\.companion_telemetry_snapshots/);
  assert.match(sql, /CHECK\s*\(\s*scope\s*=\s*'read_only'\s*\)/i);
  assert.match(sql, /ALTER TABLE public\.mobile_pairing_sessions ENABLE ROW LEVEL SECURITY/);
  assert.match(sql, /ALTER TABLE public\.mobile_paired_devices ENABLE ROW LEVEL SECURITY/);
  assert.match(sql, /ALTER TABLE public\.companion_telemetry_snapshots ENABLE ROW LEVEL SECURITY/);
});

test("Edge Function mobile-sync enforces HTTP 403 READ_ONLY_VIOLATION for any non-GET from mobile token", () => {
  const syncFnPath = path.join(REPO_ROOT, "supabase/functions/mobile-sync/index.ts");
  const src = fs.readFileSync(syncFnPath, "utf-8");

  assert.match(src, /bearer\.startsWith\("iea_ro_"\)/);
  assert.match(src, /if\s*\(req\.method\s*!==\s*"GET"\)/);
  assert.match(src, /READ_ONLY_VIOLATION/);
  assert.match(src, /403/);
  assert.match(src, /DEVICE_REVOKED/);
  assert.match(src, /TOKEN_EXPIRED/);
  assert.match(src, /ignoredStale:\s*true/);
});

test("Edge Function mobile-pairing enforces expiry, rate limiting, one-time consumption, and approval", () => {
  const pairFnPath = path.join(REPO_ROOT, "supabase/functions/mobile-pairing/index.ts");
  const src = fs.readFileSync(pairFnPath, "utf-8");

  assert.match(src, /MAX_PAIRING_ATTEMPTS\s*=\s*5/);
  assert.match(src, /PAIRING_EXPIRED/);
  assert.match(src, /RATE_LIMITED/);
  assert.match(src, /awaiting_approval/);
  assert.match(src, /issued_token_once:\s*null/);
  assert.match(src, /scope:\s*"read_only"/);
  assert.match(src, /action === "revoke"/);
});

test("Production cloudAuthManager defaults to HTTPS production portal, never localhost", () => {
  const authMgrPath = path.join(REPO_ROOT, "companion/electron/cloudAuthManager.cjs");
  const src = fs.readFileSync(authMgrPath, "utf-8");

  assert.doesNotMatch(src, /"http:\/\/localhost:5173"/);
  assert.match(src, /"https:\/\/arcadefx\.live"/);
  assert.match(src, /mobilePairingAction/);
  assert.match(src, /pushMobileSnapshot/);
});

test("Windows SettingsScreen exposes plain-English sections, PAIR NEW ANDROID DEVICE, and Logout", () => {
  const settingsPath = path.join(
    REPO_ROOT,
    "companion/src/components/screens/MonitoringSettingsScreens.tsx"
  );
  const src = fs.readFileSync(settingsPath, "utf-8");

  assert.match(src, /PAIR NEW ANDROID DEVICE/);
  assert.match(src, /data-testid="settings-section-application"/);
  assert.match(src, /data-testid="settings-section-bot"/);
  assert.match(src, /data-testid="settings-section-mt5"/);
  assert.match(src, /data-testid="settings-logout-btn"/);
  assert.match(src, /Credentials never exposed/);
});

test("Android SecurityScreen supports Cloud QR & 6-digit pairing without requiring Host IP or Port", () => {
  const secPath = path.join(REPO_ROOT, "apps/mobile/src/screens/SecurityScreen.tsx");
  const src = fs.readFileSync(secPath, "utf-8");

  assert.match(src, /parseAnyPairingQrPayload/);
  assert.match(src, /claimCloudPairing/);
  assert.match(src, /pollCloudPairingApproval/);
  assert.match(src, /Advanced: Local Wi-Fi Fallback/);
  assert.match(src, /Waiting for approval/);
});

test("Build-time public Supabase config generator blocks service_role keys and DesktopPublicEntry deduplicates errors", () => {
  const genPath = path.join(REPO_ROOT, "scripts/generate_companion_public_config.mjs");
  const genSrc = fs.readFileSync(genPath, "utf-8");
  assert.match(genSrc, /sb_secret_/);
  assert.match(genSrc, /service_role/);
  assert.match(genSrc, /--require/);

  const entryPath = path.join(REPO_ROOT, "companion/src/components/DesktopPublicEntry.tsx");
  const entrySrc = fs.readFileSync(entryPath, "utf-8");
  assert.match(entrySrc, /\/not configured\/i\.test\(formError\)/);

  const authPath = path.join(REPO_ROOT, "companion/electron/cloudAuthManager.cjs");
  const authSrc = fs.readFileSync(authPath, "utf-8");
  assert.match(authSrc, /publicConfig\.generated\.cjs/);
  assert.match(authSrc, /loadUserConfigJson/);
});

test("supabase/config.toml configures mobile-pairing and mobile-sync and MobileSyncModal maps 404/401/429 cleanly", () => {
  const toml = fs.readFileSync(path.join(REPO_ROOT, "supabase/config.toml"), "utf-8");
  assert.match(toml, /\[functions\.mobile-pairing\]\s+verify_jwt\s*=\s*false/);
  assert.match(toml, /\[functions\.mobile-sync\]\s+verify_jwt\s*=\s*false/);

  const modal = fs.readFileSync(
    path.join(REPO_ROOT, "companion/src/components/MobileSyncModal.tsx"),
    "utf-8"
  );
  assert.match(modal, /formatFriendlyCloudPairingError/);
  assert.match(modal, /Use Local Wi-Fi Fallback/);
});

test("Migration 20261126000004 backfills missing profiles with lowest-privilege user role and SECURITY DEFINER trigger", () => {
  const sql = fs.readFileSync(
    path.join(REPO_ROOT, "supabase/migrations/20261126000004_profile_backfill_and_trigger.sql"),
    "utf-8"
  );
  assert.match(sql, /INSERT INTO public\.profiles/);
  assert.match(sql, /'user' AS role/);
  assert.match(sql, /ON CONFLICT \(id\) DO NOTHING/);
  assert.match(sql, /SECURITY DEFINER/);
  assert.match(sql, /SET search_path = public/);
  assert.match(sql, /ALTER TABLE public\.profiles ENABLE ROW LEVEL SECURITY/);
  assert.doesNotMatch(sql, /'admin'/i);

  const authTs = fs.readFileSync(
    path.join(REPO_ROOT, "supabase/functions/_shared/auth.ts"),
    "utf-8"
  );
  assert.match(authTs, /ignoreDuplicates:\s*true/);
  assert.match(authTs, /role:\s*"user"/);
});
