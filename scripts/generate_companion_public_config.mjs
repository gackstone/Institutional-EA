#!/usr/bin/env node
/**
 * Generates build-time public Supabase client configuration for the packaged Windows Companion.
 *
 * Security guarantees:
 * - Reads ONLY public SUPABASE_URL (or VITE_SUPABASE_URL) and public SUPABASE_ANON_KEY (or VITE_SUPABASE_ANON_KEY).
 * - NEVER reads or bundles SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWT_SECRET, DATABASE_URL, or passwords.
 * - Rejects any secret/service_role key format (`sb_secret_*` or JWT with role=service_role).
 * - Fails loudly (exit 1) when `--require` is passed and public config is missing or placeholder.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const OUTPUT_CJS = path.join(REPO_ROOT, "companion", "electron", "publicConfig.generated.cjs");

function loadDotEnv(filePath) {
  const out = {};
  if (!fs.existsSync(filePath)) return out;
  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const idx = line.indexOf("=");
    if (idx <= 0) continue;
    const k = line.slice(0, idx).trim();
    let v = line.slice(idx + 1).trim();
    if ((v.startsWith('"') && v.endsWith('"')) || (v.startsWith("'") && v.endsWith("'"))) {
      v = v.slice(1, -1);
    }
    if (k && !(k in out)) out[k] = v;
  }
  return out;
}

function assertPublicAnonKey(key) {
  if (!key) return;
  if (key.startsWith("sb_secret_")) {
    throw new Error("SECURITY BLOCK: Refusing to bundle a Supabase secret/service_role key (sb_secret_*).");
  }
  const parts = key.split(".");
  if (parts.length === 3) {
    try {
      const payload = JSON.parse(Buffer.from(parts[1], "base64url").toString("utf8"));
      if (String(payload?.role || "").toLowerCase() === "service_role") {
        throw new Error("SECURITY BLOCK: Refusing to bundle a JWT with role=service_role.");
      }
    } catch (err) {
      if (err instanceof Error && err.message.startsWith("SECURITY BLOCK")) throw err;
    }
  }
}

function main() {
  const requireConfigured = process.argv.includes("--require");
  const fileEnv = {
    ...loadDotEnv(path.join(REPO_ROOT, ".env")),
    ...loadDotEnv(path.join(REPO_ROOT, "companion", ".env")),
  };

  const supabaseUrl = (
    process.env.SUPABASE_URL ||
    process.env.VITE_SUPABASE_URL ||
    fileEnv.SUPABASE_URL ||
    fileEnv.VITE_SUPABASE_URL ||
    ""
  )
    .trim()
    .replace(/\/+$/, "");

  const supabaseAnonKey = (
    process.env.SUPABASE_ANON_KEY ||
    process.env.VITE_SUPABASE_ANON_KEY ||
    fileEnv.SUPABASE_ANON_KEY ||
    fileEnv.VITE_SUPABASE_ANON_KEY ||
    ""
  ).trim();

  const webPortalUrl = (
    process.env.INSTITUTIONAL_EA_WEB_URL ||
    process.env.VITE_PUBLIC_SITE_URL ||
    fileEnv.INSTITUTIONAL_EA_WEB_URL ||
    fileEnv.VITE_PUBLIC_SITE_URL ||
    "https://arcadefx.live"
  )
    .trim()
    .replace(/\/+$/, "");

  assertPublicAnonKey(supabaseAnonKey);

  const isConfigured =
    Boolean(supabaseUrl) &&
    Boolean(supabaseAnonKey) &&
    !supabaseUrl.includes("your-project-ref") &&
    !supabaseAnonKey.includes("your-supabase");

  if (requireConfigured && !isConfigured) {
    console.error(
      "\n[BUILD ERROR] Public Supabase config missing!\n" +
        "Set SUPABASE_URL and SUPABASE_ANON_KEY (public anon/publishable key only) in .env or environment variables before building a release.\n"
    );
    process.exit(1);
  }

  const content =
    "// AUTO-GENERATED AT BUILD TIME — PUBLIC CLIENT CONFIG ONLY (NEVER SERVICE_ROLE)\n" +
    `module.exports = ${JSON.stringify(
      {
        supabaseUrl: isConfigured ? supabaseUrl : "",
        supabaseAnonKey: isConfigured ? supabaseAnonKey : "",
        webPortalUrl,
      },
      null,
      2
    )};\n`;

  fs.mkdirSync(path.dirname(OUTPUT_CJS), { recursive: true });
  fs.writeFileSync(OUTPUT_CJS, content, "utf8");

  let hostInfo = "(unconfigured)";
  if (isConfigured) {
    try {
      hostInfo = new URL(supabaseUrl).host;
    } catch {
      hostInfo = "(invalid-url)";
    }
  }
  console.log(`[public-config] Wrote companion/electron/publicConfig.generated.cjs -> host=${hostInfo}`);
}

main();
