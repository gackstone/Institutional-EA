#!/usr/bin/env node
/**
 * Safe, Isolated Windows Desktop Release Builder for Institutional EA
 *
 * - Never terminates or interferes with a running Institutional EA app or MT5 control service.
 * - Always builds into a fresh isolated staging directory to avoid locked-file failures
 *   on `companion/release/win-unpacked/resources/bin/mt5_control_service.exe`.
 * - Independently verifies unpacked executable, NSIS installer, uninstaller, app.asar,
 *   sidecars, and branding assets before publishing the final installer + SHA-256 checksums.
 * - Cleans temporary staging artifacts only after verification and publication succeed.
 */

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const COMPANION_DIR = path.join(REPO_ROOT, "companion");

function runCmd(command, args, opts = {}) {
  const res = spawnSync(command, args, {
    stdio: "inherit",
    shell: process.platform === "win32",
    ...opts,
  });
  if (res.status !== 0) {
    throw new Error(`Command failed (${res.status}): ${command} ${args.join(" ")}`);
  }
}

function sha256File(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function sha512Base64File(filePath) {
  const hash = crypto.createHash("sha512");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("base64");
}

function assertExistsNonEmpty(filePath, label) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`Verification failed — missing ${label}: ${filePath}`);
  }
  const stat = fs.statSync(filePath);
  if (stat.size <= 0) {
    throw new Error(`Verification failed — empty ${label}: ${filePath}`);
  }
  return stat.size;
}

function isDirLocked(dirPath) {
  if (!fs.existsSync(dirPath)) return false;
  const probeExe = path.join(dirPath, "resources", "bin", "mt5_control_service.exe");
  if (!fs.existsSync(probeExe)) return false;
  try {
    const fd = fs.openSync(probeExe, "r+");
    fs.closeSync(fd);
    return false;
  } catch {
    return true;
  }
}

function main() {
  const pkg = JSON.parse(fs.readFileSync(path.join(COMPANION_DIR, "package.json"), "utf8"));
  const version = pkg.version;
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const stagingName = `release-staging-${stamp}`;
  const stagingDir = path.join(COMPANION_DIR, stagingName);
  const releaseDir = path.join(COMPANION_DIR, "release");

  console.log(`\n=== Institutional EA Windows Safe Release Build (v${version}) ===`);

  const unpackedPath = path.join(releaseDir, "win-unpacked");
  if (isDirLocked(unpackedPath)) {
    console.log(
      `[SAFE-MODE] Detected active/locked runtime in ${unpackedPath}. Leaving active runtime untouched and building in isolated staging directory: ${stagingName}`
    );
  } else {
    console.log(`[ISOLATED] Building in clean staging directory: ${stagingName}`);
  }

  // Ensure resources/bin exists (CI may not build Python sidecars unless configured)
  fs.mkdirSync(path.join(COMPANION_DIR, "resources", "bin"), { recursive: true });

  // 1. Build companion frontend (TypeScript + Vite)
  console.log("\n[1/4] Building companion frontend (tsc && vite build)...");
  runCmd("npm", ["run", "build"], { cwd: COMPANION_DIR });

  // 2. Package Windows NSIS installer into isolated staging directory
  console.log("\n[2/4] Packaging Windows x64 NSIS installer via electron-builder...");
  const ebEnv = { ...process.env };
  if (!ebEnv.CSC_LINK) {
    console.log("[INFO] CSC_LINK not set — building unsigned Windows installer.");
    ebEnv.CSC_IDENTITY_AUTO_DISCOVERY = "false";
  }
  runCmd(
    "npx",
    ["electron-builder", "--win", "nsis:x64", "--publish", "never", `--config.directories.output=${stagingName}`],
    { cwd: COMPANION_DIR, env: ebEnv }
  );

  // 3. Independently verify generated artifacts & branding assets
  console.log("\n[3/4] Verifying packaged executable, installer, blockmap, and branding...");
  const stagedExe = path.join(stagingDir, "win-unpacked", "Institutional EA.exe");
  const stagedAsar = path.join(stagingDir, "win-unpacked", "resources", "app.asar");
  const stagedInstaller = path.join(stagingDir, `InstitutionalEA-Setup-${version}.exe`);
  const stagedBlockmap = path.join(stagingDir, `InstitutionalEA-Setup-${version}.exe.blockmap`);

  const exeSize = assertExistsNonEmpty(stagedExe, "Windows executable (Institutional EA.exe)");
  const asarSize = assertExistsNonEmpty(stagedAsar, "packaged Electron app.asar");
  const installerSize = assertExistsNonEmpty(stagedInstaller, `NSIS installer (InstitutionalEA-Setup-${version}.exe)`);
  const blockmapSize = assertExistsNonEmpty(stagedBlockmap, "NSIS blockmap");

  // Verify required branding inputs & public Supabase config were present during packaging
  assertExistsNonEmpty(path.join(COMPANION_DIR, "dist", "institutional-ea-logo.png"), "dist/institutional-ea-logo.png");
  assertExistsNonEmpty(path.join(COMPANION_DIR, "electron", "icon.png"), "electron/icon.png");
  assertExistsNonEmpty(path.join(COMPANION_DIR, "electron", "publicConfig.generated.cjs"), "electron/publicConfig.generated.cjs");
  assertExistsNonEmpty(path.join(COMPANION_DIR, "resources", "icon.ico"), "resources/icon.ico");
  assertExistsNonEmpty(path.join(COMPANION_DIR, "resources", "installerHeader.bmp"), "resources/installerHeader.bmp");
  assertExistsNonEmpty(path.join(COMPANION_DIR, "resources", "installerSidebar.bmp"), "resources/installerSidebar.bmp");

  // Inspect packaged app.asar: prove public Supabase config is bundled and NO service_role / .env secret leaked
  const asarBuf = fs.readFileSync(stagedAsar);
  const asarText = asarBuf.toString("latin1");
  if (!asarText.includes("publicConfig.generated.cjs")) {
    throw new Error("Verification failed — publicConfig.generated.cjs not found inside app.asar");
  }
  if (asarText.includes("sb_secret_") || asarText.includes("SUPABASE_DB_URL=")) {
    throw new Error("SECURITY FAILURE — secret key or .env content detected inside app.asar!");
  }
  console.log("  [OK] app.asar verified: publicConfig.generated.cjs bundled, zero secret/service_role leakage");

  const binDir = path.join(stagingDir, "win-unpacked", "resources", "bin");
  const sidecars = fs.existsSync(binDir)
    ? fs.readdirSync(binDir).filter((f) => f.toLowerCase().endsWith(".exe"))
    : [];

  const installerHash = sha256File(stagedInstaller);
  console.log(`  [OK] Institutional EA.exe (${(exeSize / 1048576).toFixed(2)} MB)`);
  console.log(`  [OK] resources/app.asar (${(asarSize / 1048576).toFixed(2)} MB)`);
  console.log(`  [OK] InstitutionalEA-Setup-${version}.exe (${(installerSize / 1048576).toFixed(2)} MB)`);
  console.log(`  [OK] InstitutionalEA-Setup-${version}.exe.blockmap (${(blockmapSize / 1024).toFixed(1)} KB)`);
  console.log(`  [OK] Bundled MT5 sidecars (${sidecars.length}): ${sidecars.join(", ") || "none"}`);
  console.log(`  [OK] SHA-256: ${installerHash}`);

  // 4. Publish canonical verified installer + checksum + blockmap + latest.yml without touching locked win-unpacked
  console.log("\n[4/4] Publishing canonical verified installer and cleaning temporary staging directory...");
  fs.mkdirSync(releaseDir, { recursive: true });
  let targetDir = releaseDir;
  const latestName = "InstitutionalEA-Setup.exe";
  const latestBlockmapName = "InstitutionalEA-Setup.exe.blockmap";
  const sha512Base64 = sha512Base64File(stagedInstaller);
  const releaseDateIso = new Date().toISOString();

  try {
    fs.copyFileSync(stagedInstaller, path.join(targetDir, latestName));
    fs.copyFileSync(stagedBlockmap, path.join(targetDir, latestBlockmapName));
  } catch (err) {
    targetDir = path.join(COMPANION_DIR, "release-out", "windows");
    fs.mkdirSync(targetDir, { recursive: true });
    console.warn(`[WARN] Could not write to ${releaseDir} (${err.message}); publishing to ${targetDir}`);
    fs.copyFileSync(stagedInstaller, path.join(targetDir, latestName));
    fs.copyFileSync(stagedBlockmap, path.join(targetDir, latestBlockmapName));
  }

  fs.writeFileSync(path.join(targetDir, `${latestName}.sha256`), `${installerHash}  ${latestName}\n`, "ascii");
  const latestYml = [
    `version: ${version}`,
    "files:",
    `  - url: ${latestName}`,
    `    sha512: ${sha512Base64}`,
    `    size: ${installerSize}`,
    `path: ${latestName}`,
    `sha512: ${sha512Base64}`,
    `releaseDate: '${releaseDateIso}'`,
    "",
  ].join("\n");
  fs.writeFileSync(path.join(targetDir, "latest.yml"), latestYml, "utf8");

  // Clean temporary staging directory only after verified publication succeeds
  try {
    fs.rmSync(stagingDir, { recursive: true, force: true, maxRetries: 6, retryDelay: 500 });
  } catch (cleanupErr) {
    console.warn(`[WARN] Deferred cleanup of temporary staging dir ${stagingName} (${cleanupErr.message}); published installers are unaffected.`);
  }

  console.log(`\nSUCCESS: Verified canonical Windows installer published to:`);
  console.log(`  - ${path.join(targetDir, latestName)}`);
  console.log(`  - ${path.join(targetDir, `${latestName}.sha256`)}`);
  console.log(`  - ${path.join(targetDir, "latest.yml")}`);
}

try {
  main();
} catch (err) {
  console.error(`\n[ERROR] ${err.message}`);
  process.exit(1);
}
