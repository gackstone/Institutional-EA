#!/usr/bin/env node
/**
 * CI / Lint Guard: Fails if hardcoded sample telemetry values, fake positions,
 * or mock/fixture/faker imports appear anywhere in apps/mobile/src production code.
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const srcRoot = path.resolve(__dirname, "../src");

const FORBIDDEN_PATTERNS = [
  { name: "Hardcoded balance 10450.25", regex: /\b10450(?:\.25)?\b/ },
  { name: "Hardcoded equity 10582.40", regex: /\b10582(?:\.40?)?\b/ },
  { name: "Hardcoded todayPnl 132.15", regex: /\b132\.15\b/ },
  { name: "Hardcoded totalProfit 2450.80", regex: /\b2450\.80?\b/ },
  { name: "Hardcoded winRate 72.4", regex: /\b72\.4\b/ },
  { name: "Hardcoded ticket 104921", regex: /\b104921\b/ },
  { name: "Hardcoded XAUUSD price 2652.5", regex: /\b2652\.50?\b/ },
  { name: "Hardcoded XAUUSD price 2656.8", regex: /\b2656\.80?\b/ },
  { name: "Hardcoded XAUUSD SL 2645.0", regex: /\b2645\.00?\b/ },
  { name: "Hardcoded XAUUSD TP 2670.0", regex: /\b2670\.00?\b/ },
  { name: "Hardcoded sample comment", regex: /Inst-EA Swing FVG/i },
  { name: "Hardcoded '58 deals'", regex: /58\s+deals/i },
  { name: "Hardcoded '4 trades today'", regex: /4\s+trades\s+today/i },
  { name: "Hardcoded fake security string", regex: /Hardware Enclave Active/i },
  { name: "Mock/Faker/Fixture import", regex: /from\s+["'][^"']*(?:faker|__mocks__|fixtures?|sampleData|mockData)[^"']*["']/i },
];

function walk(dir, files = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "__tests__" || entry.name === "generated") continue;
      walk(full, files);
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

const files = walk(srcRoot);
const violations = [];

for (const file of files) {
  const content = fs.readFileSync(file, "utf8");
  const lines = content.split(/\r?\n/);
  lines.forEach((line, idx) => {
    for (const rule of FORBIDDEN_PATTERNS) {
      if (rule.regex.test(line)) {
        violations.push({
          file: path.relative(srcRoot, file),
          line: idx + 1,
          rule: rule.name,
          snippet: line.trim(),
        });
      }
    }
  });
}

if (violations.length > 0) {
  console.error(`[no-hardcoded-guard] FAILED with ${violations.length} violation(s):`);
  for (const v of violations) {
    console.error(`  - ${v.file}:${v.line} [${v.rule}] -> ${v.snippet}`);
  }
  process.exit(1);
}

console.log(`[no-hardcoded-guard] PASS (${files.length} production files checked, 0 hardcoded/mock violations)`);
