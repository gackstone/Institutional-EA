import React, { useState, useEffect } from "react";
import { Server, X, Check, Save, ShieldAlert, Sun, Moon, Laptop } from "lucide-react";
import { CompanionConfig } from "../types";
import { IPC } from "../services/ipc";
import { useTheme } from "../context/ThemeContext";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
  const { theme, mode, setMode } = useTheme();
  const [config, setConfig] = useState<CompanionConfig | null>(null);
  const [symbolsInput, setSymbolsInput] = useState<string>("");
  const [saving, setSaving] = useState<boolean>(false);
  const [saveSuccess, setSaveSuccess] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
    }
  }, [isOpen]);

  const loadConfig = async () => {
    try {
      const cfg = await IPC.getConfig();
      setConfig(cfg);
      setSymbolsInput(cfg.allowedSymbols.join(", "));
    } catch (e) {
      console.error(e);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!config) return;

    setSaving(true);
    setSaveSuccess(false);

    const symbols = symbolsInput
      .split(",")
      .map((s) => s.trim().toUpperCase())
      .filter((s) => s.length > 0);

    const updated = {
      ...config,
      allowedSymbols: symbols,
    };

    try {
      await IPC.saveConfig(updated);
      setConfig(updated);
      setSaveSuccess(true);
      setTimeout(() => {
        setSaveSuccess(false);
        onClose();
      }, 1000);
    } catch (e) {
      console.error(e);
    } finally {
      setSaving(false);
    }
  };

  if (!isOpen || !config) return null;

  return (
    <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4 select-none animate-fadeIn">
      <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-xl w-full max-w-lg max-h-[90vh] overflow-hidden shadow-2xl flex flex-col text-institutional-ea-text">
        {/* Header */}
        <div className="px-5 py-4 border-b border-institutional-ea-border flex items-center justify-between bg-institutional-ea-surface">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-institutional-ea-secondary text-institutional-ea-primary border border-institutional-ea-border">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-institutional-ea-text">Engine Configuration & Safety</h3>
              <p className="text-[11px] text-institutional-ea-textMuted">Risk parameters, ports, themes and operational modes</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-institutional-ea-secondary rounded-md text-institutional-ea-textMuted hover:text-institutional-ea-text transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleSave} className="p-5 overflow-y-auto flex-1 space-y-4 text-xs">
          {/* Theme Selector (Institutional EA Adaptive Theme System) */}
          <div>
            <label className="font-bold text-institutional-ea-text block mb-1">Visual Theme</label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setMode("light")}
                className={`py-2 px-2.5 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "light"
                    ? "bg-institutional-ea-primary text-white border-institutional-ea-primary shadow-xs"
                    : "bg-institutional-ea-surface text-institutional-ea-text border-institutional-ea-border hover:bg-institutional-ea-secondary"
                }`}
              >
                <Sun className="w-3.5 h-3.5" />
                <span>Light</span>
              </button>
              <button
                type="button"
                onClick={() => setMode("dark")}
                className={`py-2 px-2.5 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "dark"
                    ? "bg-institutional-ea-primary text-white border-institutional-ea-primary shadow-xs"
                    : "bg-institutional-ea-surface text-institutional-ea-text border-institutional-ea-border hover:bg-institutional-ea-secondary"
                }`}
              >
                <Moon className="w-3.5 h-3.5" />
                <span>Dark</span>
              </button>
              <button
                type="button"
                onClick={() => setMode("system")}
                className={`py-2 px-2.5 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "system"
                    ? "bg-institutional-ea-primary text-white border-institutional-ea-primary shadow-xs"
                    : "bg-institutional-ea-surface text-institutional-ea-text border-institutional-ea-border hover:bg-institutional-ea-secondary"
                }`}
              >
                <Laptop className="w-3.5 h-3.5" />
                <span>System</span>
              </button>
            </div>
            <p className="text-[10px] text-institutional-ea-textMuted mt-1">
              Institutional EA Design System • {mode === "system" ? `Following Windows OS (${theme})` : `${mode.charAt(0).toUpperCase() + mode.slice(1)} Mode`}
            </p>
          </div>

          {/* Trading Mode */}
          <div>
            <label className="font-bold text-institutional-ea-text block mb-1">Trading Strategy Mode</label>
            <select
              value={config.tradingMode}
              onChange={(e) => setConfig({ ...config, tradingMode: e.target.value as any })}
              className="w-full bg-institutional-ea-surface border border-institutional-ea-border rounded-lg p-2.5 text-institutional-ea-text outline-none focus:border-institutional-ea-primary transition"
            >
              <option value="CONTINUOUS_SCALPING">Continuous Multi-Symbol Scalping (M15 / M5)</option>
              <option value="SWING_HOLD">Institutional Swing / Hold Mode (H1 / H4)</option>
            </select>
          </div>

          {/* Risk Per Trade */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-bold text-institutional-ea-text block mb-1">Target Risk per Trade (%)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="2.0"
                value={config.riskPerTradePct}
                onChange={(e) => setConfig({ ...config, riskPerTradePct: parseFloat(e.target.value) || 1.0 })}
                className="w-full bg-institutional-ea-surface border border-institutional-ea-border rounded-lg p-2.5 text-institutional-ea-text outline-none font-mono focus:border-institutional-ea-primary transition"
              />
              <span className="text-[10px] text-institutional-ea-textMuted">Max 2.0% hard cap [R9.1]</span>
            </div>

            <div>
              <label className="font-bold text-institutional-ea-text block mb-1">Position Capacity Mode</label>
              <input
                type="text"
                disabled
                value="Dynamic Risk-Capacity (Unlimited)"
                className="w-full bg-institutional-ea-surface/60 border border-institutional-ea-border rounded-lg p-2.5 text-institutional-ea-textMuted font-mono"
              />
              <span className="text-[10px] text-institutional-ea-textMuted">Governed by aggregate &amp; per-symbol risk budgets</span>
            </div>
          </div>

          {/* Allowed Symbols */}
          <div>
            <label className="font-bold text-institutional-ea-text block mb-1">Permitted Canonical Universe (Strict)</label>
            <input
              type="text"
              disabled
              value="XAUUSD, BTCUSD"
              className="w-full bg-institutional-ea-surface/60 border border-institutional-ea-border rounded-lg p-2.5 text-institutional-ea-textMuted font-mono"
            />
            <span className="text-[10px] text-institutional-ea-textMuted">Strict 2-symbol institutional universe (Gold and Bitcoin). Broker suffix variants (.m, .c, .pro) auto-discovered. Unauthorized instruments blocked fail-closed.</span>
          </div>

          {/* Account Compatibility & Cent Account Section */}
          <div className="p-3.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <span className="font-bold text-institutional-ea-text block text-xs">Account Compatibility &amp; Broker Detection</span>
                <span className="text-[10px] text-institutional-ea-textMuted">Standard vs Cent Account (.c / USC) execution configuration</span>
              </div>
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                ACTIVE
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <label className="font-semibold text-institutional-ea-textMuted block mb-0.5 text-[11px]">Account Type Detection</label>
                <input
                  type="text"
                  disabled
                  value="AUTO (Verified by Broker Registry)"
                  className="w-full bg-institutional-ea-card border border-institutional-ea-border rounded p-2 text-institutional-ea-text font-mono text-xs"
                />
              </div>
              <div>
                <label className="font-semibold text-institutional-ea-textMuted block mb-0.5 text-[11px]">Position Sizing Mode</label>
                <select
                  defaultValue="RISK_PERCENT"
                  className="w-full bg-institutional-ea-card border border-institutional-ea-border rounded p-2 text-institutional-ea-text font-mono text-xs outline-none"
                >
                  <option value="RISK_PERCENT">Risk % of Normalized Equity (R9)</option>
                  <option value="FIXED_RISK">Fixed Monetary Risk ($ USD)</option>
                  <option value="FIXED_LOT">Fixed Lot Sizing</option>
                  <option value="BROKER_MIN_VOLUME">Broker Minimum Volume</option>
                </select>
              </div>
            </div>

            <div className="text-[10px] space-y-1 text-institutional-ea-textMuted font-mono bg-institutional-ea-card p-2.5 rounded border border-institutional-ea-border">
              <div className="flex justify-between">
                <span>Cent Denomination Factor:</span>
                <span className="text-institutional-ea-text font-bold">100.0 (1 USD = 100 USC)</span>
              </div>
              <div className="flex justify-between">
                <span>Risk Accounting Currency:</span>
                <span className="text-institutional-ea-text font-bold">USD (Normalized)</span>
              </div>
              <div className="flex justify-between">
                <span>Cent Symbol Suffix Discovery:</span>
                <span className="text-emerald-500 font-bold">ENABLED (.c, .cent, -cent, c)</span>
              </div>
              <div className="flex justify-between">
                <span>Symbol Whitelist Policy:</span>
                <span className="text-emerald-500 font-bold">FAIL-CLOSED (XAUUSD, BTCUSD ONLY)</span>
              </div>
            </div>
          </div>

          {/* Ports */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-bold text-institutional-ea-text block mb-1">EA Bridge Port</label>
              <input
                type="number"
                disabled
                value={config.bridgePort}
                className="w-full bg-institutional-ea-surface/60 border border-institutional-ea-border rounded-lg p-2.5 text-institutional-ea-textMuted font-mono"
              />
              <span className="text-[10px] text-institutional-ea-textMuted">Fixed native MQL5 port (5555)</span>
            </div>

            <div>
              <label className="font-bold text-institutional-ea-text block mb-1">Local IPC Port</label>
              <input
                type="number"
                disabled
                value={config.ipcPort}
                className="w-full bg-institutional-ea-surface/60 border border-institutional-ea-border rounded-lg p-2.5 text-institutional-ea-textMuted font-mono"
              />
              <span className="text-[10px] text-institutional-ea-textMuted">Internal IPC switchboard (5556)</span>
            </div>
          </div>

          {/* Background and Real Account Switches */}
          <div className="space-y-2 pt-2 border-t border-institutional-ea-border">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.runInBackground}
                onChange={(e) => setConfig({ ...config, runInBackground: e.target.checked })}
                className="rounded bg-institutional-ea-surface border-institutional-ea-border text-institutional-ea-primary focus:ring-0"
              />
              <span className="text-institutional-ea-text font-medium">Run in background when window is closed (System Tray)</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.autoStartOnBoot}
                onChange={(e) => setConfig({ ...config, autoStartOnBoot: e.target.checked })}
                className="rounded bg-institutional-ea-surface border-institutional-ea-border text-institutional-ea-primary focus:ring-0"
              />
              <span className="text-institutional-ea-text font-medium">Start Companion automatically on system startup</span>
            </label>

            <div className="p-3 bg-[var(--institutional-ea-loss-soft)] border border-institutional-ea-loss/30 rounded-xl mt-3">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.allowRealAccount}
                  onChange={(e) => setConfig({ ...config, allowRealAccount: e.target.checked })}
                  className="rounded bg-institutional-ea-surface border-institutional-ea-loss text-institutional-ea-loss focus:ring-0 mt-0.5"
                />
                <div>
                  <span className="font-bold text-institutional-ea-loss flex items-center gap-1">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Allow Real Capital Automated Trading
                  </span>
                  <p className="text-[10px] text-institutional-ea-textSecondary mt-0.5 leading-relaxed">
                    By default, the engine refuses live orders on REAL accounts (DEMO/Simulation only).
                    Checking this enables real money order submission.
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Footer */}
          <div className="pt-3 border-t border-institutional-ea-border flex items-center justify-between">
            {saveSuccess ? (
              <span className="text-institutional-ea-profit font-semibold flex items-center gap-1">
                <Check className="w-4 h-4" /> Saved successfully
              </span>
            ) : (
              <span></span>
            )}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text rounded-lg text-xs font-semibold border border-institutional-ea-border transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5"
              >
                <Save className="w-3.5 h-3.5" />
                {saving ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
