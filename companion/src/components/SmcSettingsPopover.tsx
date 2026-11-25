import React, { useEffect, useRef, useState } from "react";
import { RotateCcw, X } from "lucide-react";
import {
  cloneDefaultSmcSettings,
  formatCssRgba,
  parseCssColor,
  type FvgTimeframeOption,
  type LabelSizeOption,
  type LineStyleOption,
  type ObFilterOption,
  type ObMitigationOption,
  type SmcChartSettings,
  type SmcMode,
  type SmcStyle,
  type StructureFilter,
} from "../utils/smcChartSettings";

type SettingsTab = "Inputs" | "Style" | "Visibility";

interface SmcSettingsPopoverProps {
  open: boolean;
  settings: SmcChartSettings;
  onLiveChange: (draft: SmcChartSettings) => void;
  onConfirm: (next: SmcChartSettings) => void;
  onCancel: () => void;
}

const SectionHeader: React.FC<{ title: string }> = ({ title }) => (
  <div className="pt-2.5 pb-1 text-[10px] font-bold uppercase tracking-wider text-iea-textMuted border-t border-iea-borderSubtle first:border-t-0 first:pt-0">
    {title}
  </div>
);

const Row: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div className="flex items-center justify-between gap-2 py-1 text-[11px] text-iea-textPrimary">
    <span className="truncate">{label}</span>
    <div className="flex items-center gap-1.5 shrink-0">{children}</div>
  </div>
);

const ColorAlphaPicker: React.FC<{
  value: string;
  onChange: (next: string) => void;
  allowAlpha?: boolean;
  ariaLabel: string;
}> = ({ value, onChange, allowAlpha = false, ariaLabel }) => {
  const { hex, alpha } = parseCssColor(value);
  return (
    <div className="inline-flex items-center gap-1">
      <label
        className="relative w-5 h-5 rounded border border-iea-borderStrong overflow-hidden cursor-pointer shrink-0"
        style={{ backgroundColor: value }}
        title={`${ariaLabel} (${value})`}
      >
        <input
          type="color"
          aria-label={ariaLabel}
          value={hex}
          onChange={(e) => onChange(allowAlpha ? formatCssRgba(e.target.value, alpha) : e.target.value)}
          className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
        />
      </label>
      {allowAlpha && (
        <input
          type="number"
          aria-label={`${ariaLabel} opacity percent`}
          min={5}
          max={100}
          step={5}
          value={Math.round(alpha * 100)}
          onChange={(e) => {
            const pct = Math.min(100, Math.max(5, Number(e.target.value) || 20));
            onChange(formatCssRgba(hex, pct / 100));
          }}
          className="w-11 px-1 py-0.5 rounded bg-iea-inset border border-iea-borderDefault text-[10px] font-mono text-iea-textPrimary text-right focus:outline-none focus:ring-1 focus:ring-iea-accent"
          title="Opacity (%)"
        />
      )}
    </div>
  );
};

const selectCls =
  "px-1.5 py-0.5 rounded bg-iea-inset border border-iea-borderDefault text-[11px] text-iea-textPrimary focus:outline-none focus:ring-1 focus:ring-iea-accent";
const numCls =
  "w-14 px-1.5 py-0.5 rounded bg-iea-inset border border-iea-borderDefault text-[11px] font-mono text-iea-textPrimary text-right focus:outline-none focus:ring-1 focus:ring-iea-accent";
const checkCls = "w-3.5 h-3.5 accent-[var(--iea-accent-primary)] rounded cursor-pointer";

const NaBadge: React.FC<{ tooltip?: string }> = ({
  tooltip = "Detection setting: determined by bot engine",
}) => (
  <span
    className="px-1 py-0.2 rounded text-[9px] font-mono bg-iea-inset border border-iea-borderSubtle text-iea-textMuted select-none shrink-0"
    title={tooltip}
  >
    n/a
  </span>
);

export const SmcSettingsPopover: React.FC<SmcSettingsPopoverProps> = ({
  open,
  settings,
  onLiveChange,
  onConfirm,
  onCancel,
}) => {
  const [tab, setTab] = useState<SettingsTab>("Inputs");
  const [draft, setDraft] = useState<SmcChartSettings>(settings);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (open) {
      setDraft({ ...settings, visibleTimeframes: { ...settings.visibleTimeframes } });
      setTimeout(() => dialogRef.current?.focus(), 0);
    }
  }, [open, settings]);

  if (!open) return null;

  const update = (patch: Partial<SmcChartSettings>) => {
    const next: SmcChartSettings = { ...draft, ...patch };
    setDraft(next);
    onLiveChange(next);
  };

  const handleResetDefaults = () => {
    const def = cloneDefaultSmcSettings();
    setDraft(def);
    onLiveChange(def);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Escape") {
      e.stopPropagation();
      onCancel();
    }
  };

  return (
    <div
      ref={dialogRef}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label="Smart Money Concepts Settings"
      data-testid="smc-settings-popover"
      onKeyDown={handleKeyDown}
      onClick={(e) => e.stopPropagation()}
      className="absolute right-2 top-2 z-50 w-[min(360px,calc(100%-16px))] max-h-[min(78vh,540px)] flex flex-col rounded-xl bg-iea-card border border-iea-borderDefault text-iea-textPrimary shadow-2xl backdrop-blur-md focus:outline-none"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-iea-borderSubtle shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-bold tracking-tight truncate">
            Smart Money Concepts [LuxAlgo]
          </span>
        </div>
        <button
          type="button"
          onClick={onCancel}
          aria-label="Close settings"
          className="p-1 rounded hover:bg-iea-elevated text-iea-textSecondary hover:text-iea-textPrimary focus:outline-none focus:ring-1 focus:ring-iea-accent"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Tabs: Inputs | Style | Visibility */}
      <div className="flex items-center border-b border-iea-borderSubtle px-3 shrink-0" role="tablist">
        {(["Inputs", "Style", "Visibility"] as const).map((t) => {
          const active = tab === t;
          return (
            <button
              key={t}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 text-[11px] font-semibold border-b-2 transition ${
                active
                  ? "border-iea-accent text-iea-accent"
                  : "border-transparent text-iea-textSecondary hover:text-iea-textPrimary"
              }`}
            >
              {t}
            </button>
          );
        })}
      </div>

      {/* Scrollable Body */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1">
        {tab === "Inputs" && (
          <>
            <SectionHeader title="Smart Money Concepts" />
            <Row label="Mode">
              <select
                aria-label="SMC Mode"
                value={draft.mode}
                onChange={(e) => update({ mode: e.target.value as SmcMode })}
                className={selectCls}
              >
                <option value="Historical">Historical</option>
                <option value="Present">Present</option>
              </select>
            </Row>
            <Row label="Style">
              <select
                aria-label="SMC Style"
                value={draft.style}
                onChange={(e) => update({ style: e.target.value as SmcStyle })}
                className={selectCls}
              >
                <option value="Colored">Colored</option>
                <option value="Monochrome">Monochrome</option>
              </select>
            </Row>
            <Row label="Color Candles">
              <input
                type="checkbox"
                aria-label="Color Candles"
                checked={draft.colorCandles}
                onChange={(e) => update({ colorCandles: e.target.checked })}
                className={checkCls}
              />
            </Row>

            <SectionHeader title="Real Time Internal Structure" />
            <Row label="Show Internal Structure">
              <input
                type="checkbox"
                aria-label="Show Internal Structure"
                checked={draft.showInternalStructure}
                onChange={(e) => update({ showInternalStructure: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="Bullish Structure">
              <select
                aria-label="Internal Bullish Structure Filter"
                value={draft.internalBullishFilter}
                onChange={(e) => update({ internalBullishFilter: e.target.value as StructureFilter })}
                className={selectCls}
              >
                <option value="All">All</option>
                <option value="BOS">BOS</option>
                <option value="CHoCH">CHoCH</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Internal Bullish Color"
                value={draft.internalBullishColor}
                onChange={(c) => update({ internalBullishColor: c })}
              />
            </Row>
            <Row label="Bearish Structure">
              <select
                aria-label="Internal Bearish Structure Filter"
                value={draft.internalBearishFilter}
                onChange={(e) => update({ internalBearishFilter: e.target.value as StructureFilter })}
                className={selectCls}
              >
                <option value="All">All</option>
                <option value="BOS">BOS</option>
                <option value="CHoCH">CHoCH</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Internal Bearish Color"
                value={draft.internalBearishColor}
                onChange={(c) => update({ internalBearishColor: c })}
              />
            </Row>
            <Row label="Confluence Filter">
              <input
                type="checkbox"
                aria-label="Confluence Filter"
                checked={draft.internalConfluenceFilter}
                disabled
                className={`${checkCls} opacity-40 cursor-not-allowed`}
              />
              <NaBadge />
            </Row>
            <Row label="Internal Label Size">
              <select
                aria-label="Internal Label Size"
                value={draft.internalLabelSize}
                onChange={(e) => update({ internalLabelSize: e.target.value as LabelSizeOption })}
                className={selectCls}
              >
                <option value="Tiny">Tiny</option>
                <option value="Small">Small</option>
                <option value="Normal">Normal</option>
              </select>
            </Row>

            <SectionHeader title="Real Time Swing Structure" />
            <Row label="Show Swing Structure">
              <input
                type="checkbox"
                aria-label="Show Swing Structure"
                checked={draft.showSwingStructure}
                onChange={(e) => update({ showSwingStructure: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="Bullish Structure">
              <select
                aria-label="Swing Bullish Structure Filter"
                value={draft.swingBullishFilter}
                onChange={(e) => update({ swingBullishFilter: e.target.value as StructureFilter })}
                className={selectCls}
              >
                <option value="All">All</option>
                <option value="BOS">BOS</option>
                <option value="CHoCH">CHoCH</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Swing Bullish Color"
                value={draft.swingBullishColor}
                onChange={(c) => update({ swingBullishColor: c })}
              />
            </Row>
            <Row label="Bearish Structure">
              <select
                aria-label="Swing Bearish Structure Filter"
                value={draft.swingBearishFilter}
                onChange={(e) => update({ swingBearishFilter: e.target.value as StructureFilter })}
                className={selectCls}
              >
                <option value="All">All</option>
                <option value="BOS">BOS</option>
                <option value="CHoCH">CHoCH</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Swing Bearish Color"
                value={draft.swingBearishColor}
                onChange={(c) => update({ swingBearishColor: c })}
              />
            </Row>
            <Row label="Swing Label Size">
              <select
                aria-label="Swing Label Size"
                value={draft.swingLabelSize}
                onChange={(e) => update({ swingLabelSize: e.target.value as LabelSizeOption })}
                className={selectCls}
              >
                <option value="Tiny">Tiny</option>
                <option value="Small">Small</option>
                <option value="Normal">Normal</option>
              </select>
            </Row>
            <Row label="Show Swings Points">
              <input
                type="checkbox"
                aria-label="Show Swing Points"
                checked={draft.showSwingPoints}
                onChange={(e) => update({ showSwingPoints: e.target.checked })}
                className={checkCls}
              />
              <input
                type="number"
                aria-label="Swing Points Length"
                value={draft.swingPointsLength}
                disabled
                className={`${numCls} opacity-40 cursor-not-allowed`}
              />
              <NaBadge />
            </Row>
            <Row label="Show Strong/Weak High/Low">
              <input
                type="checkbox"
                aria-label="Show Strong/Weak High/Low"
                checked={draft.showStrongWeakHL}
                onChange={(e) => update({ showStrongWeakHL: e.target.checked })}
                className={checkCls}
              />
            </Row>

            <SectionHeader title="OB - Order Block" />
            <Row label="Internal OB (Order Block)">
              <input
                type="checkbox"
                aria-label="Show Internal Order Blocks"
                checked={draft.showInternalOB}
                onChange={(e) => update({ showInternalOB: e.target.checked })}
                className={checkCls}
              />
              <input
                type="number"
                aria-label="Internal Order Blocks Count"
                min={1}
                max={20}
                value={draft.internalOBCount}
                onChange={(e) =>
                  update({ internalOBCount: Math.max(1, Math.min(20, Number(e.target.value) || 5)) })
                }
                className={numCls}
              />
            </Row>
            <Row label="Swing OB (Order Block)">
              <input
                type="checkbox"
                aria-label="Show Swing Order Blocks"
                checked={draft.showSwingOB}
                onChange={(e) => update({ showSwingOB: e.target.checked })}
                className={checkCls}
              />
              <input
                type="number"
                aria-label="Swing Order Blocks Count"
                min={1}
                max={20}
                value={draft.swingOBCount}
                onChange={(e) =>
                  update({ swingOBCount: Math.max(1, Math.min(20, Number(e.target.value) || 5)) })
                }
                className={numCls}
              />
            </Row>
            <Row label="Order Block Filter">
              <select
                aria-label="Order Block Filter"
                value={draft.obFilter}
                disabled
                className={`${selectCls} opacity-40 cursor-not-allowed`}
              >
                <option value="Atr">Atr</option>
                <option value="Cumulative Mean Range">Cumulative Mean Range</option>
              </select>
              <NaBadge />
            </Row>
            <Row label="Order Block Mitigation">
              <select
                aria-label="Order Block Mitigation"
                value={draft.obMitigation}
                disabled
                className={`${selectCls} opacity-40 cursor-not-allowed`}
              >
                <option value="High/Low">High/Low</option>
                <option value="Close">Close</option>
              </select>
              <NaBadge />
            </Row>
            <Row label="Internal Bullish OB">
              <ColorAlphaPicker
                ariaLabel="Internal Bullish OB Color"
                value={draft.internalBullOBColor}
                allowAlpha
                onChange={(c) => update({ internalBullOBColor: c })}
              />
            </Row>
            <Row label="Internal Bearish OB">
              <ColorAlphaPicker
                ariaLabel="Internal Bearish OB Color"
                value={draft.internalBearOBColor}
                allowAlpha
                onChange={(c) => update({ internalBearOBColor: c })}
              />
            </Row>
            <Row label="Swing Bullish OB">
              <ColorAlphaPicker
                ariaLabel="Swing Bullish OB Color"
                value={draft.swingBullOBColor}
                allowAlpha
                onChange={(c) => update({ swingBullOBColor: c })}
              />
            </Row>
            <Row label="Swing Bearish OB">
              <ColorAlphaPicker
                ariaLabel="Swing Bearish OB Color"
                value={draft.swingBearOBColor}
                allowAlpha
                onChange={(c) => update({ swingBearOBColor: c })}
              />
            </Row>

            <SectionHeader title="EQH/EQL" />
            <Row label="Equal High/Low">
              <input
                type="checkbox"
                aria-label="Show Equal High/Low"
                checked={draft.showEqhEql}
                onChange={(e) => update({ showEqhEql: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="Bars Confirmation">
              <input
                type="number"
                aria-label="EQH/EQL Bars Confirmation"
                value={draft.eqhBarsConfirmation}
                disabled
                className={`${numCls} opacity-40 cursor-not-allowed`}
              />
              <NaBadge />
            </Row>
            <Row label="Threshold">
              <input
                type="number"
                aria-label="EQH/EQL Threshold"
                value={draft.eqhThreshold}
                disabled
                className={`${numCls} opacity-40 cursor-not-allowed`}
              />
              <NaBadge />
            </Row>
            <Row label="Label Size">
              <select
                aria-label="EQH/EQL Label Size"
                value={draft.eqhLabelSize}
                onChange={(e) => update({ eqhLabelSize: e.target.value as LabelSizeOption })}
                className={selectCls}
              >
                <option value="Tiny">Tiny</option>
                <option value="Small">Small</option>
                <option value="Normal">Normal</option>
              </select>
            </Row>

            <SectionHeader title="FVG - Fair Value Gap / IFVG - Inverse Fair Value Gap" />
            <Row label="FVG (Fair Value Gaps)">
              <input
                type="checkbox"
                aria-label="Show Fair Value Gaps"
                checked={draft.showFvg}
                onChange={(e) => update({ showFvg: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="Auto Threshold">
              <input
                type="checkbox"
                aria-label="FVG Auto Threshold"
                checked={draft.fvgAutoThreshold}
                disabled
                className={`${checkCls} opacity-40 cursor-not-allowed`}
              />
              <NaBadge />
            </Row>
            <Row label="Timeframe">
              <select
                aria-label="FVG Timeframe"
                value={draft.fvgTimeframe}
                disabled
                className={`${selectCls} opacity-40 cursor-not-allowed`}
              >
                <option value="Chart">Chart</option>
                <option value="M15">M15</option>
                <option value="H1">H1</option>
                <option value="H4">H4</option>
                <option value="D1">D1</option>
              </select>
              <NaBadge />
            </Row>
            <Row label="Bullish FVG">
              <ColorAlphaPicker
                ariaLabel="Bullish FVG Color"
                value={draft.fvgBullColor}
                allowAlpha
                onChange={(c) => update({ fvgBullColor: c })}
              />
            </Row>
            <Row label="Bearish FVG">
              <ColorAlphaPicker
                ariaLabel="Bearish FVG Color"
                value={draft.fvgBearColor}
                allowAlpha
                onChange={(c) => update({ fvgBearColor: c })}
              />
            </Row>
            <Row label="Extend FVG">
              <input
                type="number"
                aria-label="Extend FVG Bars"
                min={0}
                max={20}
                value={draft.fvgExtend}
                onChange={(e) =>
                  update({ fvgExtend: Math.max(0, Math.min(20, Number(e.target.value) || 0)) })
                }
                className={numCls}
              />
            </Row>

            <SectionHeader title="Highs & Lows MTF" />
            <Row label="Daily">
              <input
                type="checkbox"
                aria-label="Show Daily High/Low"
                checked={draft.showDailyHL}
                onChange={(e) => update({ showDailyHL: e.target.checked })}
                className={checkCls}
              />
              <select
                aria-label="Daily Line Style"
                value={draft.dailyStyle}
                onChange={(e) => update({ dailyStyle: e.target.value as LineStyleOption })}
                className={selectCls}
              >
                <option value="solid">Solid</option>
                <option value="dashed">Dashed</option>
                <option value="dotted">Dotted</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Daily Line Color"
                value={draft.dailyColor}
                onChange={(c) => update({ dailyColor: c })}
              />
            </Row>
            <Row label="Weekly">
              <input
                type="checkbox"
                aria-label="Show Weekly High/Low"
                checked={draft.showWeeklyHL}
                onChange={(e) => update({ showWeeklyHL: e.target.checked })}
                className={checkCls}
              />
              <select
                aria-label="Weekly Line Style"
                value={draft.weeklyStyle}
                onChange={(e) => update({ weeklyStyle: e.target.value as LineStyleOption })}
                className={selectCls}
              >
                <option value="solid">Solid</option>
                <option value="dashed">Dashed</option>
                <option value="dotted">Dotted</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Weekly Line Color"
                value={draft.weeklyColor}
                onChange={(c) => update({ weeklyColor: c })}
              />
            </Row>
            <Row label="Monthly">
              <input
                type="checkbox"
                aria-label="Show Monthly High/Low"
                checked={draft.showMonthlyHL}
                onChange={(e) => update({ showMonthlyHL: e.target.checked })}
                className={checkCls}
              />
              <select
                aria-label="Monthly Line Style"
                value={draft.monthlyStyle}
                onChange={(e) => update({ monthlyStyle: e.target.value as LineStyleOption })}
                className={selectCls}
              >
                <option value="solid">Solid</option>
                <option value="dashed">Dashed</option>
                <option value="dotted">Dotted</option>
              </select>
              <ColorAlphaPicker
                ariaLabel="Monthly Line Color"
                value={draft.monthlyColor}
                onChange={(c) => update({ monthlyColor: c })}
              />
            </Row>

            <SectionHeader title="Premium & Discount Zones" />
            <Row label="Premium/Discount Zones">
              <input
                type="checkbox"
                aria-label="Show Premium/Discount Zones"
                checked={draft.showPremiumDiscount}
                onChange={(e) => update({ showPremiumDiscount: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="Premium Zone">
              <ColorAlphaPicker
                ariaLabel="Premium Zone Color"
                value={draft.premiumColor}
                allowAlpha
                onChange={(c) => update({ premiumColor: c })}
              />
            </Row>
            <Row label="Equilibrium Zone">
              <ColorAlphaPicker
                ariaLabel="Equilibrium Zone Color"
                value={draft.equilibriumColor}
                allowAlpha
                onChange={(c) => update({ equilibriumColor: c })}
              />
            </Row>
            <Row label="Discount Zone">
              <ColorAlphaPicker
                ariaLabel="Discount Zone Color"
                value={draft.discountColor}
                allowAlpha
                onChange={(c) => update({ discountColor: c })}
              />
            </Row>

            <SectionHeader title="Range Liquidity Filters (IRL / ERL)" />
            <Row label="IRL (Internal Structure, Internal OB, FVG, Eq)">
              <input
                type="checkbox"
                aria-label="Show IRL"
                checked={draft.showIRL}
                onChange={(e) => update({ showIRL: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="ERL (Swing, Strong/Weak, EQH/EQL, MTF H/L)">
              <input
                type="checkbox"
                aria-label="Show ERL"
                checked={draft.showERL}
                onChange={(e) => update({ showERL: e.target.checked })}
                className={checkCls}
              />
            </Row>
          </>
        )}

        {tab === "Style" && (
          <>
            <SectionHeader title="Palette & Theme" />
            <Row label="Palette Mode">
              <select
                aria-label="Palette Mode"
                value={draft.style}
                onChange={(e) => update({ style: e.target.value as SmcStyle })}
                className={selectCls}
              >
                <option value="Colored">Colored</option>
                <option value="Monochrome">Monochrome</option>
              </select>
            </Row>
            <Row label="Color Candles by Trend">
              <input
                type="checkbox"
                aria-label="Color Candles by Trend"
                checked={draft.colorCandles}
                onChange={(e) => update({ colorCandles: e.target.checked })}
                className={checkCls}
              />
            </Row>

            <SectionHeader title="Structure Colors" />
            <Row label="Internal Bullish / Bearish">
              <ColorAlphaPicker
                ariaLabel="Internal Bullish"
                value={draft.internalBullishColor}
                onChange={(c) => update({ internalBullishColor: c })}
              />
              <ColorAlphaPicker
                ariaLabel="Internal Bearish"
                value={draft.internalBearishColor}
                onChange={(c) => update({ internalBearishColor: c })}
              />
            </Row>
            <Row label="Swing Bullish / Bearish">
              <ColorAlphaPicker
                ariaLabel="Swing Bullish"
                value={draft.swingBullishColor}
                onChange={(c) => update({ swingBullishColor: c })}
              />
              <ColorAlphaPicker
                ariaLabel="Swing Bearish"
                value={draft.swingBearishColor}
                onChange={(c) => update({ swingBearishColor: c })}
              />
            </Row>

            <SectionHeader title="OB (Order Block) & FVG (Fair Value Gap) Fills" />
            <Row label="Internal Bull / Bear OB">
              <ColorAlphaPicker
                ariaLabel="Internal Bull OB"
                value={draft.internalBullOBColor}
                allowAlpha
                onChange={(c) => update({ internalBullOBColor: c })}
              />
              <ColorAlphaPicker
                ariaLabel="Internal Bear OB"
                value={draft.internalBearOBColor}
                allowAlpha
                onChange={(c) => update({ internalBearOBColor: c })}
              />
            </Row>
            <Row label="Swing Bull / Bear OB">
              <ColorAlphaPicker
                ariaLabel="Swing Bull OB"
                value={draft.swingBullOBColor}
                allowAlpha
                onChange={(c) => update({ swingBullOBColor: c })}
              />
              <ColorAlphaPicker
                ariaLabel="Swing Bear OB"
                value={draft.swingBearOBColor}
                allowAlpha
                onChange={(c) => update({ swingBearOBColor: c })}
              />
            </Row>
            <Row label="Bullish / Bearish FVG">
              <ColorAlphaPicker
                ariaLabel="Bullish FVG"
                value={draft.fvgBullColor}
                allowAlpha
                onChange={(c) => update({ fvgBullColor: c })}
              />
              <ColorAlphaPicker
                ariaLabel="Bearish FVG"
                value={draft.fvgBearColor}
                allowAlpha
                onChange={(c) => update({ fvgBearColor: c })}
              />
            </Row>
          </>
        )}

        {tab === "Visibility" && (
          <>
            <SectionHeader title="Timeframes" />
            {(["M1", "M5", "M15", "H1", "H4"] as const).map((tf) => (
              <Row key={tf} label={`Show SMC on ${tf}`}>
                <input
                  type="checkbox"
                  aria-label={`Show SMC on ${tf}`}
                  checked={draft.visibleTimeframes[tf]}
                  onChange={(e) =>
                    update({
                      visibleTimeframes: {
                        ...draft.visibleTimeframes,
                        [tf]: e.target.checked,
                      },
                    })
                  }
                  className={checkCls}
                />
              </Row>
            ))}

            <SectionHeader title="Companion Chart Layers" />
            <Row label="Sessions & Killzones">
              <input
                type="checkbox"
                aria-label="Show Sessions"
                checked={draft.showSessions}
                onChange={(e) => update({ showSessions: e.target.checked })}
                className={checkCls}
              />
            </Row>
            <Row label="Trades (Open / Pending / Closed)">
              <input
                type="checkbox"
                aria-label="Show Trades"
                checked={draft.showTrades}
                onChange={(e) => update({ showTrades: e.target.checked })}
                className={checkCls}
              />
            </Row>
          </>
        )}
      </div>

      {/* Footer: Defaults | Cancel | OK */}
      <div className="flex items-center justify-between px-3 py-2 border-t border-iea-borderSubtle bg-iea-inset rounded-b-xl shrink-0">
        <button
          type="button"
          onClick={handleResetDefaults}
          data-testid="smc-settings-defaults"
          className="px-2 py-1 rounded text-[11px] font-medium text-iea-textSecondary hover:text-iea-textPrimary hover:bg-iea-elevated inline-flex items-center gap-1 transition focus:outline-none focus:ring-1 focus:ring-iea-accent"
        >
          <RotateCcw className="w-3 h-3" />
          <span>Defaults</span>
        </button>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={onCancel}
            data-testid="smc-settings-cancel"
            className="px-2.5 py-1 rounded text-[11px] font-medium text-iea-textPrimary bg-iea-card hover:bg-iea-elevated border border-iea-borderDefault transition focus:outline-none focus:ring-1 focus:ring-iea-accent"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(draft)}
            data-testid="smc-settings-ok"
            className="px-3 py-1 rounded text-[11px] font-semibold bg-iea-accent hover:bg-iea-accentHover text-white transition focus:outline-none focus:ring-1 focus:ring-iea-accent"
          >
            OK
          </button>
        </div>
      </div>
    </div>
  );
};
