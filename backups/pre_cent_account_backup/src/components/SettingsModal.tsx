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
      <div className="bg-arcade-card border border-arcade-border rounded-xl w-full max-w-lg max-h-[90vh] overflow-hidden shadow-2xl flex flex-col text-arcade-text">
        {/* Header */}
        <div className="px-5 py-4 border-b border-arcade-border flex items-center justify-between bg-arcade-surface">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-arcade-secondary text-arcade-primary border border-arcade-border">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-arcade-text">Engine Configuration & Safety</h3>
              <p className="text-[11px] text-arcade-textMuted">Risk parameters, ports, themes and operational modes</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-arcade-secondary rounded-md text-arcade-textMuted hover:text-arcade-text transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleSave} className="p-5 overflow-y-auto flex-1 space-y-4 text-xs">
          {/* Theme Selector (Yardly Automotive Adaptive Theme System) */}
          <div>
            <label className="font-bold text-arcade-text block mb-1">Visual Theme</label>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => setMode("light")}
                className={`py-2 px-2.5 rounded-lg border text-xs font-semibold flex items-center justify-center gap-1.5 transition ${
                  mode === "light"
                    ? "bg-arcade-primary text-white border-arcade-primary shadow-xs"
                    : "bg-arcade-surface text-arcade-text border-arcade-border hover:bg-arcade-secondary"
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
                    ? "bg-arcade-primary text-white border-arcade-primary shadow-xs"
                    : "bg-arcade-surface text-arcade-text border-arcade-border hover:bg-arcade-secondary"
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
                    ? "bg-arcade-primary text-white border-arcade-primary shadow-xs"
                    : "bg-arcade-surface text-arcade-text border-arcade-border hover:bg-arcade-secondary"
                }`}
              >
                <Laptop className="w-3.5 h-3.5" />
                <span>System</span>
              </button>
            </div>
            <p className="text-[10px] text-arcade-textMuted mt-1">
              Yardly Design System • {mode === "system" ? `Following Windows OS (${theme})` : `${mode.charAt(0).toUpperCase() + mode.slice(1)} Mode`}
            </p>
          </div>

          {/* Trading Mode */}
          <div>
            <label className="font-bold text-arcade-text block mb-1">Trading Strategy Mode</label>
            <select
              value={config.tradingMode}
              onChange={(e) => setConfig({ ...config, tradingMode: e.target.value as any })}
              className="w-full bg-arcade-surface border border-arcade-border rounded-lg p-2.5 text-arcade-text outline-none focus:border-arcade-primary transition"
            >
              <option value="CONTINUOUS_SCALPING">Continuous Multi-Symbol Scalping (M15 / M5)</option>
              <option value="SWING_HOLD">Institutional Swing / Hold Mode (H1 / H4)</option>
            </select>
          </div>

          {/* Risk Per Trade */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-bold text-arcade-text block mb-1">Target Risk per Trade (%)</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                max="2.0"
                value={config.riskPerTradePct}
                onChange={(e) => setConfig({ ...config, riskPerTradePct: parseFloat(e.target.value) || 1.0 })}
                className="w-full bg-arcade-surface border border-arcade-border rounded-lg p-2.5 text-arcade-text outline-none font-mono focus:border-arcade-primary transition"
              />
              <span className="text-[10px] text-arcade-textMuted">Max 2.0% hard cap [R9.1]</span>
            </div>

            <div>
              <label className="font-bold text-arcade-text block mb-1">Position Capacity Mode</label>
              <input
                type="text"
                disabled
                value="Dynamic Risk-Capacity (Unlimited)"
                className="w-full bg-arcade-surface/60 border border-arcade-border rounded-lg p-2.5 text-arcade-textMuted font-mono"
              />
              <span className="text-[10px] text-arcade-textMuted">Governed by aggregate &amp; per-symbol risk budgets</span>
            </div>
          </div>

          {/* Allowed Symbols */}
          <div>
            <label className="font-bold text-arcade-text block mb-1">Allowed Trading Symbols</label>
            <input
              type="text"
              value={symbolsInput}
              onChange={(e) => setSymbolsInput(e.target.value)}
              placeholder="XAUUSD, BTCUSD, USDJPY"
              className="w-full bg-arcade-surface border border-arcade-border rounded-lg p-2.5 text-arcade-text outline-none font-mono focus:border-arcade-primary transition"
            />
            <span className="text-[10px] text-arcade-textMuted">Comma-separated symbol tickers</span>
          </div>

          {/* Ports */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="font-bold text-arcade-text block mb-1">EA Bridge Port</label>
              <input
                type="number"
                disabled
                value={config.bridgePort}
                className="w-full bg-arcade-surface/60 border border-arcade-border rounded-lg p-2.5 text-arcade-textMuted font-mono"
              />
              <span className="text-[10px] text-arcade-textMuted">Fixed native MQL5 port (5555)</span>
            </div>

            <div>
              <label className="font-bold text-arcade-text block mb-1">Local IPC Port</label>
              <input
                type="number"
                disabled
                value={config.ipcPort}
                className="w-full bg-arcade-surface/60 border border-arcade-border rounded-lg p-2.5 text-arcade-textMuted font-mono"
              />
              <span className="text-[10px] text-arcade-textMuted">Internal IPC switchboard (5556)</span>
            </div>
          </div>

          {/* Background and Real Account Switches */}
          <div className="space-y-2 pt-2 border-t border-arcade-border">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.runInBackground}
                onChange={(e) => setConfig({ ...config, runInBackground: e.target.checked })}
                className="rounded bg-arcade-surface border-arcade-border text-arcade-primary focus:ring-0"
              />
              <span className="text-arcade-text font-medium">Run in background when window is closed (System Tray)</span>
            </label>

            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config.autoStartOnBoot}
                onChange={(e) => setConfig({ ...config, autoStartOnBoot: e.target.checked })}
                className="rounded bg-arcade-surface border-arcade-border text-arcade-primary focus:ring-0"
              />
              <span className="text-arcade-text font-medium">Start Companion automatically on system startup</span>
            </label>

            <div className="p-3 bg-[var(--arcade-loss-soft)] border border-arcade-loss/30 rounded-xl mt-3">
              <label className="flex items-start gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.allowRealAccount}
                  onChange={(e) => setConfig({ ...config, allowRealAccount: e.target.checked })}
                  className="rounded bg-arcade-surface border-arcade-loss text-arcade-loss focus:ring-0 mt-0.5"
                />
                <div>
                  <span className="font-bold text-arcade-loss flex items-center gap-1">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Allow Real Capital Automated Trading
                  </span>
                  <p className="text-[10px] text-arcade-textSecondary mt-0.5 leading-relaxed">
                    By default, the engine refuses live orders on REAL accounts (DEMO/Simulation only).
                    Checking this enables real money order submission.
                  </p>
                </div>
              </label>
            </div>
          </div>

          {/* Footer */}
          <div className="pt-3 border-t border-arcade-border flex items-center justify-between">
            {saveSuccess ? (
              <span className="text-arcade-profit font-semibold flex items-center gap-1">
                <Check className="w-4 h-4" /> Saved successfully
              </span>
            ) : (
              <span></span>
            )}

            <div className="flex gap-2">
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 bg-arcade-surface hover:bg-arcade-secondary text-arcade-text rounded-lg text-xs font-semibold border border-arcade-border transition"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={saving}
                className="px-5 py-2 bg-arcade-primary hover:bg-arcade-primaryHover active:bg-arcade-primaryActive text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5"
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
