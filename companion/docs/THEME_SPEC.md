# Institutional EA Companion — Neutral Charcoal Theme & Sidebar Design Spec

Single source of truth for the neutral dark charcoal UI/UX theme (sampled from **IMAGE 1: Overlay**) and collapsible hover-expand overlay sidebar (sampled from **IMAGE 2: Sidebar**).

> **Chart Protection Policy**: All theme tokens and global rules are strictly isolated from `LiveTradingChart.tsx`, `chartTheme.ts`, `chartCanvasRenderer.ts`, `chartDrawingsSchema.ts`, and `tradeChartMath.ts`. The chart retains its original TradingView Light theme, toolbar styling, fonts, and colors untouched.

---

## 1. Sampled Color Palette

### 1.1 Main Shell & Surfaces (Sampled from IMAGE 1 — "Overlay")

| Token | CSS Variable | Hex / Value | Sampled Source (IMAGE 1) | Usage |
|---|---|---|---|---|
| Canvas / Window BG | `--iea-bg-canvas` | `#0E0D0B` | `(10,10)` outer window `rgb(14,13,11)` | App root background, Electron window `backgroundColor`, outer gutter |
| Titlebar Strip | `--iea-bg-titlebar` | `#12110F` | Top window chrome | Electron 36px drag strip & `titleBarOverlay.color` |
| Panel Base | `--iea-surface-panel` | `#1E1D1B` | `(720,105)` main panel base `rgb(30,29,27)` | Raised main panel resting surface |
| Panel Gradient | `--iea-surface-panel-grad` | `radial-gradient(ellipse 68% 58% at 0% 0%, #2B2A26 0%, #23221F 42%, #1E1D1B 100%)` | `(515,110) #2A2925` → `(660,105) #21201E` → `(720,700) #1E1D1B` | Raised rounded main content container (`28px` radius) |
| Inset Card | `--iea-surface-card` | `#161513` | `(603,515)` inset card `rgb(27,26,24)` darkened for contrast on `#1E1D1B` | KPI cards, panels, tables, modal bodies |
| Deep Inset / Input | `--iea-surface-inset` | `#100F0D` | `(309,217)` search bar `rgb(14,13,11)` | Inputs, search bars, code/log wells, inner tiles |
| Elevated / Hover | `--iea-surface-elevated` | `#242320` | `(257,371)` active pill `#2B2A26` | Neutral pill controls, table hover rows, dropdowns |
| Active Neutral Pill | `--iea-surface-active` | `#2B2A26` | `(257,371)` active item `rgb(43,42,38)` | Active tabs, active segmented buttons, neutral highlights |
| Border Subtle | `--iea-border-subtle` | `rgba(255, 255, 253, 0.07)` | `#262523` window border | Card borders, panel borders, dividers |
| Border Default | `--iea-border-default` | `rgba(255, 255, 253, 0.11)` | `#2E2D29` | Buttons, inputs, pills |
| Border Strong | `--iea-border-strong` | `#3A3935` | `(200,344)` active item top border | Active pills, focused inputs, hover borders |
| Divider | `--iea-border-divider` | `rgba(255, 255, 253, 0.06)` | `#2A2925` panel divider | Section dividers, table row borders |

### 1.2 Sidebar Surfaces & Accents (Sampled from IMAGE 2 — Sidebar)

*Harmonization note*: IMAGE 1 uses warm charcoal (`#0E0D0B` / `#1E1D1B` / `#2A2925`), while IMAGE 2 uses cool dark blue-gray charcoal (`#191D20` / `#272A2F`). Per spec, the sidebar follows IMAGE 2 (`#191D20` expanded, `#17181A` collapsed rail) separated cleanly from the IMAGE 1 main raised panel by the `#0E0D0B` outer gutter.

| Token | CSS Variable | Hex / Value | Sampled Source (IMAGE 2) | Usage |
|---|---|---|---|---|
| Sidebar Expanded BG | `--iea-sidebar-bg` | `#191D20` | `(257,138)` `rgb(25,29,32)` | Expanded overlay sidebar surface |
| Sidebar Collapsed BG | `--iea-sidebar-rail-bg` | `#17181A` | `(596,138)` `rgb(23,24,26)` | Collapsed 76px icon rail |
| Sidebar Border | `--iea-sidebar-border` | `rgba(255, 255, 255, 0.08)` | Thin edge border | Sidebar outer border & dividers |
| Sidebar Active Fill | `--iea-sidebar-active` | `#272A2F` | `(331,234)` `rgb(39,42,47)` | Active item, open group header, active child |
| Sidebar Collapsed Active | `--iea-sidebar-rail-active` | `#303135` | `(596,234)` `rgb(48,49,53)` | Active icon tile in collapsed rail |
| Sidebar Text Active | `--iea-sidebar-text-active` | `#FFFFFF` | `(155,225)` `#FFFFFF` | Active item label & icon |
| Sidebar Text Inactive | `--iea-sidebar-text` | `#9CA1A6` | `(155,290)` `#979B9E`–`#ABAFB2` | Inactive nav items & icons (6.5:1 AA) |
| Sidebar Tree Line | `--iea-sidebar-tree` | `#303437` | `(132,600)` `#303437` | Vertical tree & elbow connectors |
| Sidebar Logo Tile | `--iea-sidebar-logo-bg` | `#F8F8FA` | `(117,133)` `rgb(248,248,250)` | White rounded-square brand mark tile |
| Badge Mint | `--iea-badge-mint-bg` / `-text` | `#A9ECDA` / `#0E1A16` | `(413,368)` `rgb(169,236,218)` | Normal counts (open positions, trade count) |
| Badge Peach | `--iea-badge-peach-bg` / `-text` | `#F5C59F` / `#1F140B` | `(413,435)` `rgb(245,197,159)` | Attention counts (warnings/errors) |

### 1.3 Typography Hierarchy (WCAG AA Verified)

| Token | CSS Variable | Hex | Contrast on `#161513` | Contrast on `#1E1D1B` | Usage |
|---|---|---|---|---|---|
| Primary Text | `--iea-text-primary` | `#F5F5F2` | 16.8:1 (AAA) | 15.1:1 (AAA) | Headings, KPI values, active labels |
| Secondary Text | `--iea-text-secondary` | `#B4B3B0` | 8.7:1 (AAA) | 7.9:1 (AAA) | Descriptions, table cells, labels |
| Muted Text | `--iea-text-muted` | `#8A8986` | 5.2:1 (AA) | 4.7:1 (AA) | Metadata, timestamps, column headers |
| Dim / Disabled | `--iea-text-dim` | `#666562` | — | — | Disabled controls, decorative separators |
| Primary CTA Fill | `--iea-accent-neutral` | `#F5F5F2` | — | — | Primary monochrome action button (dark text `#121110`) |

### 1.4 Semantic Meaning Palette (Tuned for Dark Charcoal)

Color is reserved strictly for operational & trading meaning:

| Meaning | Foreground Token | Soft BG Token | Border Token | Solid Button | Usage |
|---|---|---|---|---|---|
| **Positive / Profit / Start / Resume** | `--iea-profit: #6EE7B7` | `rgba(54, 179, 126, 0.14)` | `rgba(110, 231, 183, 0.30)` | `#36B37E` (text `#081911`) | Positive P&L, Start, Resume, DEMO lock, Online status |
| **Danger / Loss / Stop / Close All** | `--iea-danger: #F07178` | `rgba(217, 72, 84, 0.14)` | `rgba(240, 113, 120, 0.34)` | `#D94854` (text `#FFFFFF`) | Negative P&L, Close All, Stop, Error/Emergency states |
| **Warning / Pause** | `--iea-warning: #EAB354` | `rgba(234, 179, 84, 0.14)` | `rgba(234, 179, 84, 0.34)` | `#D99B36` (text `#1A1205`) | Pause button, Warning badges, Reconnecting |
| **Info / Connection** | `--iea-info: #5EC2C6` | `rgba(94, 194, 198, 0.13)` | `rgba(94, 194, 198, 0.34)` | — | Connect MT5 outline, SSE/ZMQ telemetry info |

---

## 2. Typography Scale

- **UI Sans (Self-hosted offline)**: `Plus Jakarta Sans Variable` (`@fontsource-variable/plus-jakarta-sans`)
- **Tabular / Code Mono (Self-hosted offline)**: `JetBrains Mono Variable` (`@fontsource-variable/jetbrains-mono`) with `font-variant-numeric: tabular-nums`
- **Weights**: `600` (Semi-bold) for brand & section headings, `500` (Medium) for nav items & buttons, `400` (Regular) for body copy.
- **Scale**:
  - Page Title: `20px` / `1.25rem`, `line-height: 1.3`, `letter-spacing: -0.02em`, `font-weight: 600`
  - Section Heading: `15px` / `0.9375rem`, `line-height: 1.35`, `font-weight: 600`
  - Body / Nav Label: `14px` / `0.875rem`, `line-height: 1.45`, `font-weight: 500`
  - Compact Control / Table Cell: `12px` / `0.75rem`, `line-height: 1.4`
  - Micro Metadata / Chip: `11px` / `0.6875rem`, `font-variant-numeric: tabular-nums`

---

## 3. Shapes, Radii, Shadows & 8px Spacing Grid

- **Main Raised Panel Radius**: `28px` (`--iea-radius-panel`)
- **Sidebar Container Radius**: `20px` (`--iea-radius-sidebar`)
- **Inset Card Radius**: `16px` (`--iea-radius-card`)
- **Sidebar Row / Tile Radius**: `12px` (`--iea-radius-nav`)
- **Pill / Control Radius**: `9999px` (`--iea-radius-pill`)
- **Shadows**:
  - Main Panel: `0 16px 40px -12px rgba(0, 0, 0, 0.55), inset 0 1px 0 0 rgba(255, 255, 253, 0.06)`
  - Inset Card: `inset 0 1px 0 0 rgba(255, 255, 253, 0.04)`
  - Sidebar Expanded Overlay: `18px 0 48px -8px rgba(0, 0, 0, 0.65)`
- **Spacing Grid (8px base)**:
  - Outer shell inset: `8px` (`p-2`)
  - Main panel inner padding: `24px` (`p-6`, `p-4` on narrow viewports)
  - Card internal padding: `16px`–`20px` (`p-4` / `p-5`)
  - Grid gaps: `16px` (`gap-4`)
  - Sidebar collapsed rail width: `76px`
  - Sidebar expanded overlay width: `264px`
  - Sidebar row height: `48px` (top-level / group headers), `42px` (tree children)
  - Icon size: `20px` (`w-5 h-5`) in sidebar, `16px` (`w-4 h-4`) in buttons/bars
  - Motion: `200ms–220ms cubic-bezier(0.16, 1, 0.3, 1)` with `prefers-reduced-motion: reduce` support.
