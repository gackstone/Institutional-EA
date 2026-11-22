import React, { useState, useEffect } from "react";
import { Send, CheckCircle2, AlertTriangle, RefreshCw, X, Shield, Bell } from "lucide-react";
import { IPC } from "../services/ipc";
import { TelegramStatus } from "../types";

interface TelegramPairingModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStatusUpdated?: () => void;
}

export const TelegramPairingModal: React.FC<TelegramPairingModalProps> = ({
  isOpen,
  onClose,
  onStatusUpdated
}) => {
  const [status, setStatus] = useState<TelegramStatus>({
    isPaired: false,
    botTokenMasked: null,
    chatIdMasked: null,
    botUsername: null,
    enabled: false
  });
  const [botTokenInput, setBotTokenInput] = useState<string>("");
  const [isPairing, setIsPairing] = useState<boolean>(false);
  const [isTesting, setIsTesting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadStatus();
      setErrorMsg(null);
      setSuccessMsg(null);
    }
  }, [isOpen]);

  const loadStatus = async () => {
    try {
      const s = await IPC.getTelegramStatus();
      setStatus(s);
    } catch (e) {
      console.error(e);
    }
  };

  const handleStartPairing = async () => {
    setIsPairing(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await IPC.startTelegramPairing(botTokenInput);
      if (res.success) {
        setSuccessMsg(res.message);
        await loadStatus();
        if (onStatusUpdated) onStatusUpdated();
      } else {
        setErrorMsg(res.message);
      }
    } catch (e: any) {
      setErrorMsg(e.message || "Failed pairing Telegram.");
    } finally {
      setIsPairing(false);
    }
  };

  const handleTestAlert = async () => {
    setIsTesting(true);
    try {
      const res = await IPC.testTelegramMessage();
      if (res.success) {
        setSuccessMsg("Test alert sent to Telegram successfully!");
      } else {
        setErrorMsg(res.message);
      }
    } catch (e: any) {
      setErrorMsg(e.message || "Test alert failed.");
    } finally {
      setIsTesting(false);
    }
  };

  const handleDisconnect = async () => {
    try {
      await IPC.disconnectTelegram();
      await loadStatus();
      setSuccessMsg("Telegram remote control unlinked.");
      if (onStatusUpdated) onStatusUpdated();
    } catch (e: any) {
      setErrorMsg(e.message || "Disconnect failed.");
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay-bg)] backdrop-blur-sm p-4 select-none animate-fadeIn">
      <div className="relative w-full max-w-lg bg-institutional-ea-card border border-institutional-ea-border rounded-xl shadow-2xl p-6 text-institutional-ea-text">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-institutional-ea-textMuted hover:text-institutional-ea-text hover:bg-institutional-ea-secondary transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-3 mb-5">
          <div className="p-2.5 rounded-xl bg-[var(--institutional-ea-primary-soft)] border border-institutional-ea-primary/30 text-institutional-ea-primary">
            <Send className="w-6 h-6" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-institutional-ea-text">Telegram Remote Control</h2>
            <p className="text-xs text-institutional-ea-textMuted">Pair your Telegram account for trade alerts and remote command execution</p>
          </div>
        </div>

        {status.isPaired ? (
          <div className="space-y-4">
            <div className="p-4 rounded-xl bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 flex items-start gap-3">
              <CheckCircle2 className="w-5 h-5 text-institutional-ea-profit mt-0.5 shrink-0" />
              <div className="text-sm">
                <div className="font-semibold text-institutional-ea-profit">Telegram Channel Verified & Active</div>
                <div className="text-xs text-institutional-ea-textSecondary mt-1">
                  Bot Username: <code className="text-institutional-ea-primary font-mono">{status.botUsername || "Configured"}</code>
                </div>
                <div className="text-xs text-institutional-ea-textSecondary">
                  Authorized Chat ID: <code className="text-institutional-ea-text font-mono">{status.chatIdMasked}</code>
                </div>
              </div>
            </div>

            <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border text-xs text-institutional-ea-textMuted space-y-1">
              <div className="font-medium text-institutional-ea-text flex items-center gap-1.5">
                <Shield className="w-3.5 h-3.5 text-institutional-ea-primary" /> Authorized Commands Available:
              </div>
              <div className="font-mono text-[11px] text-institutional-ea-textSecondary pl-5">
                /status • /positions • /pause • /resume • /closeall • /health
              </div>
            </div>

            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={handleTestAlert}
                disabled={isTesting}
                className="flex-1 py-2.5 px-4 rounded-xl bg-institutional-ea-surface hover:bg-institutional-ea-secondary border border-institutional-ea-border text-institutional-ea-text font-medium text-xs flex items-center justify-center gap-2 transition"
              >
                <Bell className="w-4 h-4 text-institutional-ea-warning" />
                {isTesting ? "Sending Test..." : "Send Test Alert"}
              </button>

              <button
                onClick={handleDisconnect}
                className="py-2.5 px-4 rounded-xl bg-[var(--institutional-ea-loss-soft)] hover:brightness-105 border border-institutional-ea-loss/30 text-institutional-ea-loss font-medium text-xs transition"
              >
                Unlink Telegram
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 text-xs">
            <div className="p-3.5 rounded-xl bg-institutional-ea-surface border border-institutional-ea-border text-institutional-ea-textSecondary space-y-2">
              <div className="font-semibold text-institutional-ea-text">How to connect your Telegram Bot:</div>
              <ol className="list-decimal pl-4 space-y-1 text-institutional-ea-textMuted text-[11px]">
                <li>Open Telegram and message <span className="text-institutional-ea-primary font-mono font-medium">@BotFather</span></li>
                <li>Send <code className="font-mono bg-institutional-ea-card px-1 py-0.5 rounded border border-institutional-ea-border">/newbot</code> and follow prompts to get your Bot API Token</li>
                <li>Paste the API Token below and press Start Listening</li>
                <li>Message your new bot with <code className="font-mono bg-institutional-ea-card px-1 py-0.5 rounded border border-institutional-ea-border">/start</code> to bind your Chat ID</li>
              </ol>
            </div>

            <div>
              <label className="block text-xs font-semibold text-institutional-ea-text mb-1">
                Telegram Bot Token (Optional if set in .env)
              </label>
              <input
                type="text"
                value={botTokenInput}
                onChange={(e) => setBotTokenInput(e.target.value)}
                placeholder="123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
                className="w-full px-3 py-2 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl text-institutional-ea-text font-mono text-xs focus:border-institutional-ea-primary outline-none transition"
              />
            </div>

            <button
              onClick={handleStartPairing}
              disabled={isPairing}
              className="w-full py-2.5 px-4 rounded-xl bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive text-white font-bold text-xs flex items-center justify-center gap-2 transition"
            >
              <RefreshCw className={`w-4 h-4 ${isPairing ? "animate-spin" : ""}`} />
              {isPairing ? "Waiting for Telegram /start command..." : "Start Listening for /start"}
            </button>
          </div>
        )}

        {/* Feedback alerts */}
        {errorMsg && (
          <div className="mt-4 p-3 rounded-xl bg-[var(--institutional-ea-loss-soft)] border border-institutional-ea-loss/30 text-institutional-ea-loss text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {successMsg && (
          <div className="mt-4 p-3 rounded-xl bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 text-institutional-ea-profit text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}
      </div>
    </div>
  );
};
