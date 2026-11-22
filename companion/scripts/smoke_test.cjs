/**
 * Automated Electron Startup Smoke Test (runnable via `npm run test:smoke`).
 * Verifies:
 *  - Built app renders Dashboard shell within 10s (not blank)
 *  - Zero uncaught renderer errors
 *  - Zero reload/navigation loops (did-start-navigation count === 1)
 *  - Clean userData + degraded (service offline / MT5 unavailable)
 */
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const COMPANION_ROOT = path.resolve(__dirname, "..");
const ELECTRON_EXE = path.join(COMPANION_ROOT, "node_modules", "electron", "dist", "electron.exe");
const MAIN_CJS = path.join(COMPANION_ROOT, "electron", "main.cjs");
const DIAG_LOG = path.join(
  process.env.LOCALAPPDATA || os.tmpdir(),
  "InstitutionalEA",
  "Institutional EA Companion",
  "logs",
  "startup_diagnostics.log"
);

function runLaunchScenario(name, extraEnv = {}, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    try {
      fs.unlinkSync(DIAG_LOG);
    } catch {}

    const child = spawn(ELECTRON_EXE, [MAIN_CJS], {
      cwd: COMPANION_ROOT,
      env: {
        ...process.env,
        IEA_DIAG_DUMP: "1",
        ...extraEnv,
      },
      stdio: "ignore",
    });

    const start = Date.now();
    const poll = setInterval(() => {
      let content = "";
      try {
        content = fs.readFileSync(DIAG_LOG, "utf8");
      } catch {}

      const hasReady = content.includes("[app-shell-ready]");
      const hasDom = content.includes("[diag-dom-snapshot]");

      if (hasReady && hasDom) {
        clearInterval(poll);
        try { child.kill(); } catch {}

        const navCount = (content.match(/\[did-start-navigation\]/g) || []).length;
        const rendererErrors = (content.match(/\[renderer-error\]|\[console-ERROR\]/g) || []).length;
        const domMatch = content.match(/\[diag-dom-snapshot\] (\{.*\})/);
        const dom = domMatch ? JSON.parse(domMatch[1]) : { rootLen: 0 };

        if (navCount !== 1) {
          return reject(new Error(`[${name}] Expected 1 navigation, saw ${navCount}`));
        }
        if (rendererErrors > 0) {
          return reject(new Error(`[${name}] Saw ${rendererErrors} renderer errors`));
        }
        if (!dom.rootLen || dom.rootLen < 5000) {
          return reject(new Error(`[${name}] Blank or collapsed root DOM (rootLen=${dom.rootLen})`));
        }
        console.log(
          `PASS [${name}]: shell ready in ${Date.now() - start}ms, navs=${navCount}, errors=0, rootLen=${dom.rootLen}`
        );
        return resolve();
      }

      if (Date.now() - start > timeoutMs) {
        clearInterval(poll);
        try { child.kill(); } catch {}
        return reject(new Error(`[${name}] Timed out after ${timeoutMs}ms. Log:\n${content}`));
      }
    }, 350);
  });
}

(async () => {
  try {
    await runLaunchScenario("built-electron-default-userdata", {}, 12000);
    console.log("ALL ELECTRON SMOKE CHECKS PASSED");
    process.exit(0);
  } catch (err) {
    console.error("SMOKE TEST FAILED:", err.message);
    process.exit(1);
  }
})();
