import React, { useState } from "react";
import {
  Play,
  Square,
  Pause,
  RefreshCw,
  Link,
  ExternalLink,
  Send,
  AlertTriangle,
  CheckCircle,
  AlertCircle
} from "lucide-react";
import { BotState } from "../types";
import { IPC } from "../services/ipc";

interface ControlsBarProps {
  botState: BotState;
  onStateChange: (state: BotState) => void;
  onOpenMT5Wizard: () => void;
  onOpenPairing: () => void;
  onOpenTelegram: () => void;
  onOpenDiagnostics?: () => void;
  onScrollToConsole?: () => void;
}

export const ControlsBar: React.FC<ControlsBarProps> = ({
  botState,
  onStateChange,
  onOpenMT5Wizard,
  onOpenPairing,
  onOpenTelegram,
}) => {
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [showCloseAllConfirm, setShowCloseAllConfirm] = useState<boolean>(false);
  const [showKillSwitchConfirm, setShowKillSwitchConfirm] = useState<boolean>(false);
  const [killSwitchCloseAll, setKillSwitchCloseAll] = useState<boolean>(false);

  const showFeedback = (type: "success" | "error", text: string) => {
    setFeedback({ type, text });
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleStartBot = async () => {
    setLoadingAction("start");
    try {
      const res = await IPC.startBot();
      if (res.success) {
        onStateChange("RUNNING");
        showFeedback("success", res.message || "Trading Engine & Bridge started successfully.");
      } else {
        showFeedback("error", res.message || "Failed to start bot.");
      }
    } catch (e: any) {
      showFeedback("error", e.message || "Error starting bot.");
    } finally {
      setLoadingAction(null);
    }
  };

  const handleStopBot = async () => {
    setLoadingAction("stop");
    try {
      const res = await IPC.stopBot();
      if (res.success) {
        onStateChange("STOPPED");
        showFeedback("success", res.message || "Trading Engine stopped safely.");
      } else {
        showFeedback("error", res.message || "Failed to stop bot.");
      }
    } catch (e: any) {
      showFeedback("error", e.message || "Error stopping bot.");
    } finally {
      setLoadingAction(null);
    }
  };

  const handlePauseResume = async () => {
    const isPaused = botState === "PAUSED";
    setLoadingAction(isPaused ? "resume" : "pause");
    try {
      const res = isPaused ? await IPC.resumeTrading() : await IPC.pauseTrading();
      if (res.success) {
        onStateChange(isPaused ? "RUNNING" : "PAUSED");
        showFeedback("success", res.message);
      } else {
        showFeedback("error", res.message);
      }
    } catch (e: any) {
      showFeedback("error", e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleRestart = async () => {
    setLoadingAction("restart");
    try {
      const res = await IPC.restartServices();
      showFeedback(res.success ? "success" : "error", res.message);
    } catch (e: any) {
      showFeedback("error", e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCloseAllConfirmed = async () => {
    setShowCloseAllConfirm(false);
    setLoadingAction("closeall");
    try {
      const res = await IPC.closeAllPositions(true);
      showFeedback(res.success ? "success" : "error", res.message);
    } catch (e: any) {
      showFeedback("error", e.message);
    } finally {
      setLoadingAction(null);
    }
  };

  const handleKillSwitchConfirmed = async () => {
    setShowKillSwitchConfirm(false);
    setLoadingAction("killswitch");
    try {
      const res = await IPC.emergencyKillSwitch(killSwitchCloseAll);
      if (res.success) {
        onStateChange("PAUSED");
        showFeedback("success", res.message);
      } else {
        showFeedback("error", res.message);
      }
    } catch (e: any) {
      showFeedback("error", e.message || "Error engaging Kill Switch.");
    } finally {
      setLoadingAction(null);
    }
  };

  const isRunning = botState === "RUNNING";
  const isPaused = botState === "PAUSED";
  const isActive = isRunning || isPaused;

  return (
    <div className="institutional-ea-glass border-b border-institutional-ea-border px-3 sm:px-4 py-2 flex flex-wrap items-center justify-between gap-2.5 select-none transition-colors duration-150 z-20">
      {/* Group A: Trading Controls */}
      <div className="flex items-center gap-2">
        <span className="hidden xl:inline text-[10px] font-bold uppercase tracking-wider text-institutional-ea-textMuted mr-1">
          Trading:
        </span>

        {/* Start / Stop Bot */}
        {!isActive ? (
          <button
            type="button"
            onClick={handleStartBot}
            disabled={loadingAction !== null}
            className="h-8 px-3.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 active:scale-[0.98] text-white font-bold text-xs uppercase tracking-wider transition-all flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
            title="Start automated trading engine and bridge connection"
          >
            <Play className="w-3.5 h-3.5 fill-white" />
            <span>{loadingAction === "start" ? "Starting..." : "Start Bot"}</span>
          </button>
        ) : (
          <button
            type="button"
            onClick={handleStopBot}
            disabled={loadingAction !== null}
            className="h-8 px-3.5 rounded-lg bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:scale-[0.98] text-white font-bold text-xs uppercase tracking-wider transition-all flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
            title="Safely stop the automated trading engine"
          >
            <Square className="w-3.5 h-3.5 fill-white" />
            <span>{loadingAction === "stop" ? "Stopping..." : "Stop Bot"}</span>
          </button>
        )}

        {/* Pause / Resume Trading */}
        {isActive && (
          <button
            type="button"
            onClick={handlePauseResume}
            disabled={loadingAction !== null}
            className={`h-8 px-3 rounded-lg font-bold text-xs uppercase tracking-wider transition-all flex items-center gap-1.5 border cursor-pointer disabled:opacity-50 ${
              isPaused
                ? "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                : "bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30"
            }`}
            title={
              isPaused
                ? "Resume order generation and automated trade entries"
                : "Pause new automated entries while maintaining active trade management"
            }
          >
            {isPaused ? (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Resume Trading</span>
              </>
            ) : (
              <>
                <Pause className="w-3.5 h-3.5 fill-current" />
                <span>Pause Trading</span>
              </>
            )}
          </button>
        )}

        {/* Restart Services */}
        <button
          type="button"
          onClick={handleRestart}
          disabled={loadingAction !== null}
          className="h-8 px-3 rounded-lg bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs font-semibold border border-institutional-ea-border transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
          title="Restart Python Trading Engine & Bridge Server backend processes"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 text-institutional-ea-textSecondary ${
              loadingAction === "restart" ? "animate-spin text-institutional-ea-primary" : ""
            }`}
          />
          <span>Restart Services</span>
        </button>
      </div>

      <div className="hidden md:block w-[1px] h-5 bg-institutional-ea-border" />

      {/* Group B: Emergency Controls */}
      <div className="flex items-center gap-2">
        <span className="hidden xl:inline text-[10px] font-bold uppercase tracking-wider text-rose-500/80 mr-1">
          Emergency:
        </span>

        {/* Close All */}
        <button
          type="button"
          onClick={() => setShowCloseAllConfirm(true)}
          disabled={loadingAction !== null}
          className="h-8 px-3 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-600 dark:text-rose-400 text-xs font-bold border border-rose-500/30 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          title="Destructive Action: Immediately close all open market positions at broker prices"
        >
          <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />
          <span>Close All</span>
        </button>

        {/* Kill Switch */}
        <button
          type="button"
          onClick={() => {
            setKillSwitchCloseAll(false);
            setShowKillSwitchConfirm(true);
          }}
          disabled={loadingAction !== null}
          className="h-8 px-3.5 rounded-lg bg-rose-600 hover:bg-rose-500 active:scale-[0.98] text-white text-xs font-extrabold uppercase tracking-wider border border-rose-700 transition-all flex items-center gap-1.5 shadow-xs cursor-pointer disabled:opacity-50"
          title="Emergency Action: Halt automated trading and freeze all activities"
        >
          <AlertCircle className="w-3.5 h-3.5 text-white" />
          <span>Kill Switch</span>
        </button>
      </div>

      <div className="hidden md:block w-[1px] h-5 bg-institutional-ea-border" />

      {/* Group C: Connections & Integrations */}
      <div className="flex items-center gap-2">
        <span className="hidden xl:inline text-[10px] font-bold uppercase tracking-wider text-institutional-ea-textMuted mr-1">
          Integrations:
        </span>

        <button
          type="button"
          onClick={onOpenMT5Wizard}
          className="h-8 px-3 rounded-lg bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs font-semibold border border-institutional-ea-border transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
          title="Configure local MetaTrader 5 terminal connection and Expert Advisor"
        >
          <ExternalLink className="w-3.5 h-3.5 text-institutional-ea-primary" />
          <span>Connect MT5</span>
        </button>

        <button
          type="button"
          onClick={onOpenPairing}
          className="h-8 px-3 rounded-lg bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs font-semibold border border-institutional-ea-border transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
          title="Pair Companion desktop with Institutional EA Cloud dashboard"
        >
          <Link className="w-3.5 h-3.5 text-institutional-ea-primary" />
          <span>Pair Institutional EA</span>
        </button>

        <button
          type="button"
          onClick={onOpenTelegram}
          className="h-8 px-3 rounded-lg bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs font-semibold border border-institutional-ea-border transition-colors flex items-center gap-1.5 shadow-xs cursor-pointer"
          title="Configure Telegram bot notifications and remote commands"
        >
          <Send className="w-3.5 h-3.5 text-institutional-ea-primary" />
          <span>Telegram Control</span>
        </button>
      </div>

      {/* Feedback Toast Notification */}
      {feedback && (
        <div className="w-full flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border bg-institutional-ea-surface text-institutional-ea-text border-institutional-ea-border animate-institutional-ea-slide">
          {feedback.type === "success" ? (
            <CheckCircle className="w-4 h-4 text-institutional-ea-profit shrink-0" />
          ) : (
            <AlertCircle className="w-4 h-4 text-institutional-ea-loss shrink-0" />
          )}
          <span>{feedback.text}</span>
        </div>
      )}

      {/* Close All Confirmation Dialog */}
      {showCloseAllConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-institutional-ea-fade">
          <div className="bg-institutional-ea-card border border-rose-500/40 rounded-2xl shadow-2xl p-6 max-w-md w-full text-institutional-ea-text space-y-4">
            <div className="flex items-center gap-3 text-rose-500">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-rose-500" />
              </div>
              <div>
                <h3 className="text-base font-bold text-institutional-ea-text">Confirm Close All Positions</h3>
                <p className="text-xs text-institutional-ea-textMuted">Liquidate all open market orders</p>
              </div>
            </div>
            <p className="text-xs text-institutional-ea-textSecondary leading-relaxed">
              Are you sure you want to immediately liquidate all open market positions at current broker prices?
              This action is executed directly across all active tickets and cannot be undone.
            </p>
            <div className="flex justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setShowCloseAllConfirm(false)}
                className="px-4 py-2 rounded-xl bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-xs font-semibold text-institutional-ea-text border border-institutional-ea-border transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleCloseAllConfirmed}
                className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white transition shadow-sm cursor-pointer"
              >
                Yes, Close All Positions
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Emergency Kill Switch Dialog */}
      {showKillSwitchConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-institutional-ea-fade">
          <div className="bg-institutional-ea-card border border-rose-500/50 rounded-2xl shadow-2xl p-6 max-w-md w-full text-institutional-ea-text space-y-4">
            <div className="flex items-center gap-3 text-rose-500">
              <div className="w-10 h-10 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center shrink-0">
                <AlertCircle className="w-5 h-5 text-rose-500 animate-pulse" />
              </div>
              <div>
                <h3 className="text-base font-extrabold uppercase tracking-wide text-institutional-ea-text">Emergency Kill Switch</h3>
                <p className="text-xs text-rose-400">Immediate automated trading halt</p>
              </div>
            </div>
            <p className="text-xs text-institutional-ea-textSecondary leading-relaxed">
              This will immediately halt automated trade executions, pause signal processing, and freeze bot operations.
              Manual position control and existing risk management remain available.
            </p>
            <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center gap-2.5">
              <input
                type="checkbox"
                id="killSwitchCloseAll"
                checked={killSwitchCloseAll}
                onChange={(e) => setKillSwitchCloseAll(e.target.checked)}
                className="w-4 h-4 rounded text-rose-600 focus:ring-0 bg-institutional-ea-surface border-institutional-ea-border cursor-pointer"
              />
              <label htmlFor="killSwitchCloseAll" className="text-xs text-institutional-ea-text font-semibold cursor-pointer select-none">
                Also close all open market positions immediately
              </label>
            </div>
            <div className="flex justify-end gap-2.5 pt-2">
              <button
                type="button"
                onClick={() => setShowKillSwitchConfirm(false)}
                className="px-4 py-2 rounded-xl bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-xs font-semibold text-institutional-ea-text border border-institutional-ea-border transition cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleKillSwitchConfirmed}
                className="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-xs font-bold text-white transition shadow-sm cursor-pointer"
              >
                Engage Kill Switch
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
