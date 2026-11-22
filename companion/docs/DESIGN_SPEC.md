# Institutional EA Companion — Glassmorphism Design Specification

> **Branch:** `ui/glass-redesign`  
> **Scope:** Visual UI/UX Redesign + Supabase-Style Hover-Expand Overlay Sidebar  
> **Single Source of Truth:** `companion/src/styles/designTokens.ts`, `companion/src/index.css`, `companion/tailwind.config.js`

---

## 1. Color Palette (Sampled Directly from Reference Image)

All colors below were pixel-sampled from the visual reference (`576×1024` RGB source):

### 1.1 Background & Atmospheric Glows
| Token | CSS Variable | Sampled Hex / Value | Usage |
| :--- | :--- | :--- | :--- |
| `bg.canvas` | `--iea-bg-canvas` | `#091426` (`rgb(9, 20, 38)`) | Root deep navy viewport canvas |
| `bg.navyTop` | `--iea-bg-navy-top` | `#0A152B` (`rgb(10, 21, 43)`) | Upper shell navy tone |
| `bg.royalGlow` | `--iea-bg-royal-glow` | `#2F497C` (`rgb(47, 73, 124)`) | Mid-left and card ambient royal-blue glow |
| `bg.horizonGlow` | `--iea-bg-horizon-glow` | `#7196CB` (`rgb(113, 150, 203)`) | Soft atmospheric horizon highlight (`opacity: 0.22`, `blur(110px)`) |
| `bg.tealDepth` | `--iea-bg-teal-depth` | `#112B42` (`rgb(17, 43, 66)`) | Lower cyan-navy depth tone |
| `bg.viewportGradient` | `--iea-bg-gradient` | `radial-gradient(circle at 12% 38%, rgba(113, 150, 203, 0.22) 0%, rgba(47, 73, 124, 0.28) 32%, transparent 68%), radial-gradient(circle at 82% 18%, rgba(176, 246, 72, 0.10) 0%, rgba(17, 43, 66, 0.35) 38%, transparent 72%), linear-gradient(155deg, #0A152B 0%, #091426 48%, #0D1E38 100%)` | Fixed full-viewport atmospheric background |

### 1.2 Translucent Glass Surfaces & Borders
| Token | CSS Variable | Value | Usage |
| :--- | :--- | :--- | :--- |
| `surface.glassCard` | `--iea-glass-card` | `linear-gradient(165deg, rgba(32, 54, 101, 0.42) 0%, rgba(15, 29, 56, 0.62) 100%)` | Primary glass card fill |
| `surface.glassElevated` | `--iea-glass-elevated` | `linear-gradient(165deg, rgba(47, 73, 124, 0.48) 0%, rgba(17, 35, 68, 0.78) 100%)` | Featured KPI cards, modals, and expanded overlay sidebar |
| `surface.glassLimeSheen` | `--iea-glass-lime-sheen` | `linear-gradient(160deg, rgba(176, 246, 72, 0.16) 0%, rgba(17, 43, 66, 0.58) 55%, rgba(15, 29, 56, 0.72) 100%)` | Highlighted KPI / positive performance glass card |
| `surface.glassTile` | `--iea-glass-tile` | `rgba(27, 51, 61, 0.46)` | Inner sub-tiles, metric pills, and input wells |
| `surface.tableHeader` | `--iea-table-header` | `rgba(32, 54, 101, 0.32)` | Data table header row fill |
| `surface.tableRowHover` | `--iea-table-row-hover` | `rgba(34, 61, 106, 0.45)` | Table row hover & striped accent (`#223D6A`) |
| `border.glass` | `--iea-border-glass` | `rgba(186, 214, 255, 0.14)` | 1px subtle light rim around every glass card |
| `border.glassStrong` | `--iea-border-glass-strong` | `rgba(194, 240, 118, 0.36)` | Active/focused lime-tinted glass border |
| `border.divider` | `--iea-border-divider` | `rgba(148, 179, 226, 0.10)` | Table row & section dividers |

### 1.3 Accent & Semantic Colors
| Token | CSS Variable | Sampled Hex / Value | Usage |
| :--- | :--- | :--- | :--- |
| `accent.lime` | `--iea-accent-lime` | `#B0F648` (`rgb(176, 246, 72)`) | Primary neon lime-green accent (active states, positive P&L, active underline, primary CTA) |
| `accent.limeSoft` | `--iea-accent-lime-soft` | `#C2F076` (`rgb(194, 240, 118)`) | Soft lime text highlight & glowing badges |
| `accent.limeBright` | `--iea-accent-lime-bright` | `#99EF44` (`rgb(153, 239, 68)`) | High-saturation lime gradient stop |
| `accent.limeGlow` | `--iea-accent-lime-glow` | `rgba(176, 246, 72, 0.18)` | Lime pill background & halo |
| `accent.violet` | `--iea-accent-violet` | `#C077FA` (`rgb(192, 119, 250)`) | Secondary violet accent (symbol chips, SMC structure overlays) |
| `accent.cyan` | `--iea-accent-cyan` | `#5EEAD4` (`rgb(94, 234, 212)`) | Secondary cyan/teal accent (session badges, JPY chip) |
| `semantic.danger` | `--iea-danger` | `#FF5A6E` (`rgb(255, 90, 110)`) | Destructive actions (`Close All`, `Flatten`, `Stop`, negative P&L, `SL`) |
| `semantic.warning` | `--iea-warning` | `#FBBF24` (`rgb(251, 191, 36)`) | Warning actions (`Pause`, stale telemetry, caution gates) |

### 1.4 Text Hierarchy (WCAG AA Checked Against `#0F1D38` Glass Surfaces)
| Token | CSS Variable | Hex | Contrast Ratio | Usage |
| :--- | :--- | :--- | :--- | :--- |
| `text.primary` | `--iea-text-primary` | `#F4F7FF` | `15.4 : 1` | Headings, large KPI figures, primary table values |
| `text.secondary` | `--iea-text-secondary` | `#B6C5E0` | `9.2 : 1` | Body copy, descriptions, inactive nav items |
| `text.muted` | `--iea-text-muted` | `#8496B8` | `5.3 : 1` | Table column headers, sub-labels, timestamps |

---

## 2. Typography & Offline Font Bundling

- **Primary Sans-Serif (`--font-sans`)**: **Plus Jakarta Sans** (self-hosted variable WOFF2 in `companion/public/fonts/PlusJakartaSans-Variable.woff2`, weights `300`–`800`), matching the reference image's clean geometric display numerals (`font-weight: 300/400` on large stat numbers like `$678.567` and `1.632.67`) and crisp medium labels (`font-weight: 500/600`).
- **Tabular Monospace (`--font-mono`)**: **JetBrains Mono** (self-hosted variable WOFF2 in `companion/public/fonts/JetBrainsMono-Variable.woff2`) + `font-variant-numeric: tabular-nums` on all prices, tickets, PIDs, R-multiples, and live countdowns so numbers never jitter when streaming ticks arrive.
- **Scale & Weights**:
  - **Screen / Hero Title**: `1.5rem` (`24px`), `font-weight: 300` (`font-light`), tracking `-0.025em`
  - **KPI Stat Value**: `1.65rem` (`26px`), `font-weight: 400`, `tabular-nums`, tracking `-0.03em`
  - **Card Section Header**: `0.8125rem` (`13px`), `font-weight: 600`, sentence-case (replacing harsh all-caps)
  - **Table Column Header**: `0.75rem` (`12px`), `font-weight: 500`, sentence-case (`text-[#8496B8]`)

---

## 3. Component Language

1. **Glass Cards (`.iea-glass-card`)**:
   - `border-radius: 18px` (`1.125rem`)
   - `border: 1px solid rgba(186, 214, 255, 0.14)`
   - `box-shadow: 0 18px 42px -12px rgba(4, 10, 24, 0.65), inset 0 1px 0 0 rgba(255, 255, 255, 0.12)`
   - `backdrop-filter: blur(16px)` (omitted on the high-frequency chart canvas wrapper for 60fps rendering performance).
2. **Segmented Tabs with Neon Lime Underline**:
   - Modeled directly on the reference image's `Portfolio | Transactions | Time Machine` bar: clean text tabs with a glowing `2.5px` `#B0F648` underline bar (`box-shadow: 0 0 12px rgba(176, 246, 72, 0.65)`) beneath the active tab.
3. **Circular Symbol Icon Chips**:
   - Modeled on the reference image's circular coin badges (`Ethereum` lime circle, `Cardano` violet circle):
     - `XAUUSD`: Neon lime circular chip (`#B0F648` fill/ring with dark icon glyph)
     - `USDJPY`: Cyan-blue circular chip (`#5EEAD4` / `#38BDF8`)
     - `BTCUSD`: Violet-purple circular chip (`#C077FA`)
4. **Pill Dropdowns & Status Chips**:
   - Rounded pill containers (`border-radius: 9999px`, `bg-[#162749]/75`, `border: 1px solid rgba(186, 214, 255, 0.16)`) matching the `Period: Last year` and `Sort by: Increase` pills in the reference image.

---

## 4. Supabase-Style Hover-Expand Overlay Sidebar

1. **Collapsed Default Rail (`60px` width)**:
   - Fixed on the left edge (`position: fixed; top: 0; bottom: 0; left: 0; z-index: 40`).
   - Main application workspace maintains a constant `padding-left: 60px` (`pl-[60px]`) so expanding the sidebar **overlays** the dashboard without pushing, resizing, or reflowing the chart or KPI cards.
2. **Hover & Focus-Within Expansion (`252px` width)**:
   - On `mouseenter` or keyboard `focus-within`, smoothly transitions width from `60px` to `252px` (`transition: width 200ms cubic-bezier(0.16, 1, 0.3, 1)`).
   - On `mouseleave`, applies a `120ms` hover-intent collapse delay so accidental edge grazing never causes flicker.
   - Labels, section headers (`MONITOR`, `CONTROL`, `DIAGNOSE`), badge counters, and the footer (`DEMO LOCK ACTIVE · 127.0.0.1:8765`) fade and slide in smoothly without text wrapping (`whitespace-nowrap`).
   - Active navigation item displays a glowing `#B0F648` left accent bar and translucent lime-tinted glass pill.
