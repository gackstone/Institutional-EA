#!/usr/bin/env node
/**
 * Generates build-time public Supabase config for the Android Read-Only mobile app.
 * Uses ONLY the public SUPABASE_URL and public SUPABASE_ANON_KEY from root .env / env.
 * NEVER bundles service_role keys, database URLs, or secrets.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const OUT_TS = path.join(REPO_ROOT, "apps", "mobile", "src", "generated", "supabasePublicConfig.ts");

function loadDotEnv(filePath) {
  const out = {};
  if (!fs.existsSync(filePath)) return out;
  for (const raw of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
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
    throw new Error("SECURITY BLOCK: Refusing to bundle a Supabase secret/service_role key.");
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
  const fileEnv = loadDotEnv(path.join(REPO_ROOT, ".env"));

  const supabaseUrl = (
    process.env.EXPO_PUBLIC_SUPABASE_URL ||
    process.env.SUPABASE_URL ||
    process.env.VITE_SUPABASE_URL ||
    fileEnv.SUPABASE_URL ||
    fileEnv.VITE_SUPABASE_URL ||
    ""
  )
    .trim()
    .replace(/\/+$/, "");

  const supabaseAnonKey = (
    process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ||
    process.env.SUPABASE_ANON_KEY ||
    process.env.VITE_SUPABASE_ANON_KEY ||
    fileEnv.SUPABASE_ANON_KEY ||
    fileEnv.VITE_SUPABASE_ANON_KEY ||
    ""
  ).trim();

  assertPublicAnonKey(supabaseAnonKey);

  const configured =
    Boolean(supabaseUrl) &&
    Boolean(supabaseAnonKey) &&
    !supabaseUrl.includes("your-project-ref") &&
    !supabaseAnonKey.includes("your-supabase");

  if (requireConfigured && !configured) {
    console.error("[BUILD ERROR] Missing SUPABASE_URL or public SUPABASE_ANON_KEY for mobile build.");
    process.exit(1);
  }

  const content =
    "// AUTO-GENERATED AT BUILD TIME — PUBLIC CLIENT CONFIG ONLY (NEVER SERVICE_ROLE)\n" +
    `export const MOBILE_SUPABASE_PUBLIC_CONFIG = ${JSON.stringify(
      {
        supabaseUrl: configured ? supabaseUrl : "",
        supabaseAnonKey: configured ? supabaseAnonKey : "",
      },
      null,
      2
    )} as const;\n`;

  fs.mkdirSync(path.dirname(OUT_TS), { recursive: true });
  fs.writeFileSync(OUT_TS, content, "utf8");
  const host = configured ? new URL(supabaseUrl).host : "(unconfigured)";
  console.log(`[mobile-public-config] Wrote apps/mobile/src/generated/supabasePublicConfig.ts -> host=${host}`);
}

main();
