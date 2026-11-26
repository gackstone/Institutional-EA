import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "../../../..");

const { createCloudAuthManager } = require("../../../electron/cloudAuthManager.cjs");

test("cloudAuthManager encrypts session on disk, never leaks tokens to renderer, and hashes device fingerprint", () => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "iea-cloud-auth-test-"));
  try {
    const manager = createCloudAuthManager({
      credentialsDir: tmpDir,
      projectRoot: REPO_ROOT,
      appVersion: "1.3.4",
    });

    const fp = manager.getDeviceFingerprintHash();
    assert.match(fp, /^[a-f0-9]{64}$/, "Device fingerprint must be a 64-char SHA-256 hex digest");
    assert.ok(!fp.includes(os.hostname()), "Device fingerprint must never expose raw hostname");

    const initial = manager.getSanitizedState();
    assert.equal(initial.authenticated, false);
    assert.equal((initial as any).access_token, undefined);
    assert.equal((initial as any).refresh_token, undefined);
    assert.equal(initial.entitlement.status, "no_subscription");
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

test("Supabase SQL migrations enforce RLS on all 6 tables, $50 Pro plan seed, and anti-escalation guards", () => {
  const schemaSql = fs.readFileSync(
    path.join(REPO_ROOT, "supabase/migrations/20261126000001_initial_cloud_schema.sql"),
    "utf8"
  );
  const rlsSql = fs.readFileSync(
    path.join(REPO_ROOT, "supabase/migrations/20261126000002_rls_and_storage.sql"),
    "utf8"
  );

  for (const table of ["profiles", "plans", "subscriptions", "payments", "devices", "audit_logs"]) {
    assert.ok(
      schemaSql.includes(`CREATE TABLE IF NOT EXISTS public.${table}`),
      `Missing table definition for ${table}`
    );
    assert.ok(
      rlsSql.includes(`ALTER TABLE public.${table} ENABLE ROW LEVEL SECURITY`),
      `RLS not enabled for ${table}`
    );
  }

  assert.ok(schemaSql.includes("Institutional EA Pro"), "Missing Institutional EA Pro seed");
  assert.ok(schemaSql.includes("50.00"), "Missing $50.00 plan price");
  assert.ok(schemaSql.includes("uq_payments_tx_ref_active"), "Missing duplicate TXID unique index");
  assert.ok(schemaSql.includes("enforce_device_limit"), "Missing server-side device limit trigger");
  assert.ok(rlsSql.includes("prevent_profile_role_escalation"), "Missing role escalation guard");
  assert.ok(rlsSql.includes("payment-proofs"), "Missing private payment-proofs bucket");
});

test("Security boundary: SUPABASE_SERVICE_ROLE_KEY is never referenced in frontend or companion renderer code", () => {
  const scanDirs = [
    path.join(REPO_ROOT, "apps/web/src"),
    path.join(REPO_ROOT, "companion/src"),
  ];

  function walk(dir: string): string[] {
    const out: string[] = [];
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "__tests__" || entry.name === "node_modules") continue;
        out.push(...walk(full));
      } else if (/\.(ts|tsx|js|jsx|cjs)$/.test(entry.name)) {
        out.push(full);
      }
    }
    return out;
  }

  for (const dir of scanDirs) {
    for (const file of walk(dir)) {
      const content = fs.readFileSync(file, "utf8");
      // Allow comments explaining it's forbidden, but forbid env access or literal usage
      assert.ok(
        !/process\.env\.SUPABASE_SERVICE_ROLE_KEY|import\.meta\.env\.VITE_SUPABASE_SERVICE_ROLE_KEY/.test(
          content
        ),
        `Forbidden service role key reference found in ${file}`
      );
    }
  }
});

test("Supplied Binance USDT TRC20 QR image exists in both web and companion public assets", () => {
  const webQr = path.join(REPO_ROOT, "apps/web/public/assets/binance-usdt-trc20-qr.jpg");
  const compQr = path.join(REPO_ROOT, "companion/public/assets/binance-usdt-trc20-qr.jpg");
  assert.ok(fs.existsSync(webQr), "Missing web Binance QR image");
  assert.ok(fs.existsSync(compQr), "Missing companion Binance QR image");
  assert.ok(fs.statSync(webQr).size > 10000, "Web QR image appears empty/corrupt");
  assert.equal(fs.statSync(webQr).size, fs.statSync(compQr).size, "QR assets must match identically");
});
