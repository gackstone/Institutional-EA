# Restyle Diagnosis (`c95a619`)

**Commit Investigated**: `c95a619d9d9798ae5e8c5078b8d05da8f1a24550`  
*"feat(companion): restyle dashboard, live chart, and all 16 screens to navy-lime glassmorphism theme"*

---

## 1. Git & Branch Check

| Check | Result |
| :--- | :--- |
| Commit exists locally? | **Yes** (`c95a619d9d9798ae5e8c5078b8d05da8f1a24550`) |
| Branches containing `c95a619` | `ui/glass-redesign`, `origin/ui/glass-redesign`, `origin/main` (via merge commit `901afc9`), `chore/audit-chart-copy`, `chore/remove-features-layout` |
| Local `main` status | **Behind `origin/main`** — local `main` pointed to `324df8c` (pre-glassmorphism v1.3.0 installer build), while `origin/main` had merged `ui/glass-redesign` (`901afc9`). |
| Working tree integrity | All 5 files modified by `c95a619` (`LiveTradingChart.tsx`, `CoreTradingScreens.tsx`, `ExecutionRiskScreens.tsx`, `MonitoringSettingsScreens.tsx`, `OperationsSystemScreens.tsx`) plus prerequisite token/sidebar commits `8ba358d` and `e82e41e` are intact in `chore/remove-features-layout`. |

---

## 2. Theme Wiring & Asset Verification

- **CSS & Token Imports**: `companion/src/main.tsx` imports `@fontsource-variable/plus-jakarta-sans`, `@fontsource-variable/jetbrains-mono`, and `./index.css`. All `--iea-*` variables and `.iea-bg-atmosphere`, `.iea-glass-card`, `.iea-chart-glass-shell`, `.iea-sidebar-rail` classes are defined in `companion/src/index.css`.
- **Tailwind Config**: `companion/tailwind.config.js` scans `./index.html` and `./src/**/*.{js,ts,jsx,tsx}` and maps all `iea.*` and `institutional-ea.*` color utilities and fonts.
- **Offline Fonts**: Variable `.woff2` font files are bundled into `companion/dist/assets/` by Vite and load offline inside Electron without external CDN requests.
- **Python Control Service**: `companion/service/api/server.py` serves JSON/SSE endpoints only on `127.0.0.1:8765` and does **not** serve any static UI directory.

---

## 3. Root Causes Found (Why `c95a619` Was Not Visible)

1. **`npm run electron:dev` Silently Loaded Stale `companion/dist/index.html` Instead of Vite Dev Server**:
   - `companion/package.json` defined `"electron:dev": "concurrently \"vite\" \"wait-on tcp:5173 && electron electron/main.cjs\""` **without** `--dev` or `VITE_DEV_SERVER_URL`.
   - `companion/electron/main.cjs` only loads `http://localhost:5173` when `process.env.VITE_DEV_SERVER_URL || process.argv.includes("--dev")` is truthy; otherwise it loads `../dist/index.html` if that file exists.
   - As a result, running `npm run electron:dev` whenever an older `dist/` folder existed displayed the stale build instead of the live restyled source.

2. **Older Installed Application Directory (`Institutional EA Companion`) Still Present on Disk**:
   - `%LOCALAPPDATA%\Programs\` contained an older installation under `Institutional EA Companion` (built from pre-restyle commit `324df8c`) alongside `MT5-OO1 Companion` and the newer `Institutional EA` directory.
   - Launching any pinned shortcut pointing to `Institutional EA Companion` opened the pre-`c95a619` UI.
   - `companion/resources/installer.nsh` cleaned up `mt5-001-companion` and `MT5-OO1 Companion` on upgrade, but did not clean up `Institutional EA Companion`.

3. **Light-Mode `colorScheme` Fallback on Windows Light Theme**:
   - `companion/index.html` removed the `dark` class and set `colorScheme = 'light'` when Windows reported light mode, causing native browser/Electron controls (scrollbars, `<select>` dropdowns) to render light chrome against the dark navy-lime glassmorphism theme.

---

## 4. Fixes Applied

1. **`companion/package.json`**: Added `--dev` flag to `electron:dev` (`electron electron/main.cjs --dev`) so Electron always connects to the live Vite dev server on `http://localhost:5173`.
2. **`companion/resources/installer.nsh`**: Added automatic cleanup of legacy `Institutional EA Companion` shortcuts and silent uninstall of `%LOCALAPPDATA%\Programs\Institutional EA Companion` during `customInit`.
3. **`companion/index.html`**: Enforced `class="dark"`, `data-theme="dark"`, and `colorScheme = 'dark'` on startup so native controls match the navy-lime glassmorphism theme consistently.

---

## 5. How to Run the Correct Build

- **Development (Browser)**:
  ```powershell
  cd companion
  npm run dev
  ```
  Open `http://localhost:5173`.
- **Development (Electron + Live Vite)**:
  ```powershell
  cd companion
  npm run electron:dev
  ```
- **Clean Production Build & Electron**:
  ```powershell
  cd companion
  Remove-Item -Recurse -Force dist, node_modules\.vite -ErrorAction SilentlyContinue
  npm run build
  npm run electron
  ```
- **Windows Installer**:
  ```powershell
  cd companion
  npm run dist:win
  ```
  Run `companion\release\Institutional-EA-Setup-1.3.0.exe` (or `companion\release\setup.exe`).
