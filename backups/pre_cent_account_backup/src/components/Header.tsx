import React, { useState, useRef, useEffect, memo } from "react";
import {
  Activity,
  Minimize2,
  Square,
  X,
  Server,
  Cloud,
  Send,
  Wand2,
  Sun,
  Moon,
  Laptop,
  Check,
  ShieldCheck,
  ShieldAlert
} from "lucide-react";
import { BotState, AccountMetrics, PairingStatus, TelegramStatus } from "../types";
import { IPC } from "../services/ipc";
import { useTheme } from "../context/ThemeContext";
import { StatusBadge } from "./StatusBadge";

interface HeaderProps {
  botState?: BotState;
  account: AccountMetrics;
  pairing: PairingStatus;
  telegram: TelegramStatus;
  onOpenSettings: () => void;
  onOpenDiagnostics: () => void;
  onOpenPairing: () => void;
  onOpenTelegram: () => void;
  onOpenOnboarding: () => void;
}

export const Header: React.FC<HeaderProps> = memo(({
  botState = "STOPPED",
  account,
  pairing,
  telegram,
  onOpenSettings,
  onOpenDiagnostics,
  onOpenPairing,
  onOpenTelegram,
  onOpenOnboarding,
}) => {
  const { theme, mode, setMode } = useTheme();
  const [isThemeMenuOpen, setIsThemeMenuOpen] = useState(false);
  const themeMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (themeMenuRef.current && !themeMenuRef.current.contains(e.target as Node)) {
        setIsThemeMenuOpen(false);
      }
    };
    if (isThemeMenuOpen) {
      document.addEventListener("mousedown", handleOutside);
      return () => document.removeEventListener("mousedown", handleOutside);
    }
  }, [isThemeMenuOpen]);

  const maskedAccount = account.accountNumber
    ? `****${String(account.accountNumber).slice(-4)}`
    : "****DEMO";

  const brokerName = account.broker && account.broker !== "Connecting..."
    ? account.broker
    : "JustMarkets-Demo3";

  // Actual connection statuses
  const isCloudOnline = pairing.isPaired;
  const isTelegramOnline = telegram.isPaired && telegram.enabled;

  return (
    <header
      className="h-12 yardly-glass border-b border-arcade-border px-3 sm:px-4 flex items-center justify-between select-none transition-colors duration-150 z-30"
      style={{ WebkitAppRegion: "drag" } as React.CSSProperties}
    >
      {/* Left: Brand, Title & Account Identity */}
      <div
        className="flex items-center gap-3 min-w-0"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        <div className="flex items-baseline gap-1.5 shrink-0">
          <span className="font-extrabold text-sm tracking-tight text-arcade-text font-sans">
            MT5-001
          </span>
          <span className="text-xs font-semibold text-arcade-textSecondary font-sans">
            Companion
          </span>
        </div>

        <div className="hidden sm:block w-[1px] h-4 bg-arcade-border shrink-0" />

        {/* Connected Broker & Account Pill */}
        <div className="flex items-center gap-2 px-2.5 py-1 rounded-lg bg-arcade-card border border-arcade-border text-[11px] font-mono text-arcade-textSecondary shadow-xs truncate">
          <span className="font-medium text-arcade-text truncate">
            Broker: <strong className="font-bold text-arcade-text">{brokerName}</strong>
          </span>
          <span className="text-arcade-textMuted select-none">|</span>
          <span className="truncate">
            Account: <strong className="font-bold text-arcade-text">{maskedAccount}</strong>
          </span>
          <span className="text-arcade-textMuted select-none">|</span>
          <span className="text-[10px] font-bold uppercase text-arcade-primary">
            {account.tradeMode || "DEMO"}
          </span>
        </div>

        <div className="hidden sm:flex items-center shrink-0">
          <StatusBadge status={botState} />
        </div>
      </div>

      {/* Center: Live Connectivity & Integration Indicators */}
      <div
        className="hidden md:flex items-center gap-2.5 shrink-0"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        {/* ArcadeFX Cloud Pairing Status */}
        <button
          type="button"
          onClick={onOpenPairing}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-arcade-card hover:bg-arcade-secondary border border-arcade-border text-xs transition cursor-pointer shadow-xs"
          title="Click to view ArcadeFX.live cloud synchronization status"
        >
          <Cloud
            className={`w-3.5 h-3.5 ${
              isCloudOnline ? "text-arcade-profit" : "text-arcade-textMuted"
            }`}
          />
          <span className="text-[11px] font-medium text-arcade-textSecondary">ArcadeFX:</span>
          <StatusBadge status={isCloudOnline ? "CONNECTED" : "DISCONNECTED"} />
        </button>

        {/* Telegram Connection Status */}
        <button
          type="button"
          onClick={onOpenTelegram}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-arcade-card hover:bg-arcade-secondary border border-arcade-border text-xs transition cursor-pointer shadow-xs"
          title="Click to view Telegram remote command & alert status"
        >
          <Send
            className={`w-3.5 h-3.5 ${
              isTelegramOnline ? "text-arcade-primary" : "text-arcade-textMuted"
            }`}
          />
          <span className="text-[11px] font-medium text-arcade-textSecondary">Telegram:</span>
          <StatusBadge status={isTelegramOnline ? "CONNECTED" : "DISCONNECTED"} />
        </button>
      </div>

      {/* Right: Theme, Wizard, Diagnostics, Settings & Window Controls */}
      <div
        className="flex items-center gap-1 shrink-0"
        style={{ WebkitAppRegion: "no-drag" } as React.CSSProperties}
      >
        {/* Theme Selector */}
        <div className="relative" ref={themeMenuRef}>
          <button
            type="button"
            onClick={() => setIsThemeMenuOpen((prev) => !prev)}
            className="p-1.5 hover:bg-arcade-secondary rounded-lg text-arcade-textSecondary hover:text-arcade-text border border-transparent hover:border-arcade-border transition flex items-center justify-center cursor-pointer"
            title={`Appearance: ${mode} mode (click to change)`}
            aria-label="Toggle Theme Menu"
          >
            {theme === "dark" ? (
              <Moon className="w-4 h-4 text-arcade-primary" />
            ) : (
              <Sun className="w-4 h-4 text-arcade-primary" />
            )}
          </button>

          {isThemeMenuOpen && (
            <div className="absolute right-0 mt-1.5 w-36 rounded-xl bg-arcade-card border border-arcade-border shadow-xl p-1.5 z-50 animate-yardly-fade text-xs">
              <div className="px-2 py-1 text-[10px] font-bold uppercase tracking-wider text-arcade-textMuted">
                Theme
              </div>
              <button
                type="button"
                onClick={() => {
                  setMode("light");
                  setIsThemeMenuOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  mode === "light"
                    ? "bg-arcade-primary/10 text-arcade-primary font-bold"
                    : "text-arcade-textSecondary hover:bg-arcade-secondary hover:text-arcade-text"
                }`}
              >
                <Sun className="w-3.5 h-3.5" />
                <span>Light</span>
                {mode === "light" && <Check className="w-3 h-3 ml-auto text-arcade-primary" />}
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode("dark");
                  setIsThemeMenuOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  mode === "dark"
                    ? "bg-arcade-primary/10 text-arcade-primary font-bold"
                    : "text-arcade-textSecondary hover:bg-arcade-secondary hover:text-arcade-text"
                }`}
              >
                <Moon className="w-3.5 h-3.5" />
                <span>Dark</span>
                {mode === "dark" && <Check className="w-3 h-3 ml-auto text-arcade-primary" />}
              </button>

              <button
                type="button"
                onClick={() => {
                  setMode("system");
                  setIsThemeMenuOpen(false);
                }}
                className={`w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                  mode === "system"
                    ? "bg-arcade-primary/10 text-arcade-primary font-bold"
                    : "text-arcade-textSecondary hover:bg-arcade-secondary hover:text-arcade-text"
                }`}
              >
                <Laptop className="w-3.5 h-3.5" />
                <span>System</span>
                {mode === "system" && <Check className="w-3 h-3 ml-auto text-arcade-primary" />}
              </button>
            </div>
          )}
        </div>

        {/* Wizard Quick Access */}
        <button
          type="button"
          onClick={onOpenOnboarding}
          className="px-2.5 py-1 hover:bg-arcade-secondary rounded-lg text-arcade-primary hover:text-arcade-primaryHover transition flex items-center gap-1.5 text-xs font-semibold border border-transparent hover:border-arcade-border cursor-pointer"
          title="Launch Onboarding & Setup Wizard"
        >
          <Wand2 className="w-3.5 h-3.5" />
          <span className="hidden xl:inline text-[11px]">Wizard</span>
        </button>

        {/* Health & Diagnostics Indicator Shortcut */}
        <button
          type="button"
          onClick={onOpenDiagnostics}
          className="p-1.5 hover:bg-arcade-secondary rounded-lg text-arcade-textSecondary hover:text-arcade-text transition border border-transparent hover:border-arcade-border cursor-pointer"
          title="Health Check & System Diagnostics"
        >
          <Activity className="w-4 h-4" />
        </button>

        {/* Application Configuration Settings */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="p-1.5 hover:bg-arcade-secondary rounded-lg text-arcade-textSecondary hover:text-arcade-text transition border border-transparent hover:border-arcade-border cursor-pointer"
          title="Application Settings & Bridge Configuration"
        >
          <Server className="w-4 h-4" />
        </button>

        <div className="w-[1px] h-4 bg-arcade-border mx-1" />

        {/* Desktop Window Controls */}
        <button
          type="button"
          onClick={() => IPC.minimizeWindow()}
          className="p-1.5 hover:bg-arcade-secondary rounded-lg text-arcade-textMuted hover:text-arcade-text transition cursor-pointer"
          title="Minimize to taskbar"
          aria-label="Minimize"
        >
          <Minimize2 className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={() => IPC.maximizeWindow()}
          className="p-1.5 hover:bg-arcade-secondary rounded-lg text-arcade-textMuted hover:text-arcade-text transition cursor-pointer"
          title="Maximize window"
          aria-label="Maximize"
        >
          <Square className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={() => IPC.closeWindow()}
          className="p-1.5 hover:bg-rose-500/10 hover:text-rose-500 rounded-lg text-arcade-textMuted transition cursor-pointer"
          title="Close (runs in system tray if background service active)"
          aria-label="Close"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
});

Header.displayName = "Header";
