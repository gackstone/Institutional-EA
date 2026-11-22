import React, { useState } from "react";
import { Cloud, X, CheckCircle, AlertCircle, Link, Unlink, Key, Shield } from "lucide-react";
import { PairingStatus } from "../types";
import { IPC } from "../services/ipc";

interface PairingModalProps {
  isOpen: boolean;
  onClose: () => void;
  pairing: PairingStatus;
  onPairingUpdated: (status: PairingStatus) => void;
}

export const PairingModal: React.FC<PairingModalProps> = ({
  isOpen,
  onClose,
  pairing,
  onPairingUpdated,
}) => {
  const [code, setCode] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Force uppercase, strip non-alphanumeric, max 6 chars
    const cleaned = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 6);
    setCode(cleaned);
    setErrorMsg(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (code.length !== 6) {
      setErrorMsg("Please enter the complete 6-character pairing code.");
      return;
    }

    setLoading(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await IPC.submitPairingCode(code);
      if (res.success) {
        setSuccessMsg("Device successfully paired with Institutional EA Cloud!");
        const updated = await IPC.getPairingStatus();
        onPairingUpdated(updated);
        setTimeout(() => {
          onClose();
        }, 1500);
      } else {
        setErrorMsg(res.message);
      }
    } catch (e: any) {
      setErrorMsg(e.message || "Failed to submit pairing code.");
    } finally {
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm("Are you sure you want to disconnect this device from Institutional EA Cloud?")) {
      return;
    }
    setLoading(true);
    try {
      await IPC.disconnectPairing();
      const updated = await IPC.getPairingStatus();
      onPairingUpdated(updated);
      setSuccessMsg("Device disconnected successfully.");
    } catch (e: any) {
      setErrorMsg(e.message || "Failed to disconnect.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4 select-none animate-fadeIn">
      <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-xl w-full max-w-md overflow-hidden shadow-2xl text-institutional-ea-text">
        {/* Header */}
        <div className="px-5 py-4 border-b border-institutional-ea-border flex items-center justify-between bg-institutional-ea-surface">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
              <Cloud className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-institutional-ea-text">Institutional EA Cloud Pairing</h3>
              <p className="text-[11px] text-institutional-ea-textMuted">Connect to remote AI coach & mobile telemetry</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-institutional-ea-secondary rounded-md text-institutional-ea-textMuted hover:text-institutional-ea-text transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5">
          {pairing.isPaired ? (
            /* Already Paired State */
            <div className="space-y-4">
              <div className="flex items-center gap-3 p-3.5 bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 rounded-xl">
                <CheckCircle className="w-6 h-6 text-institutional-ea-profit shrink-0" />
                <div>
                  <h4 className="text-xs font-bold text-institutional-ea-profit">Device Is Connected & Paired</h4>
                  <p className="text-[11px] text-institutional-ea-textSecondary mt-0.5">
                    Your MT5 instance is securely synchronizing telemetry and heartbeats.
                  </p>
                </div>
              </div>

              <div className="bg-institutional-ea-surface border border-institutional-ea-border rounded-xl p-3 text-xs font-mono space-y-2">
                <div className="flex justify-between">
                  <span className="text-institutional-ea-textMuted font-sans">Instance ID:</span>
                  <span className="text-institutional-ea-text font-semibold">{pairing.instanceId || "Local-MT5"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-institutional-ea-textMuted font-sans">Device Token:</span>
                  <span className="text-institutional-ea-text font-semibold">{pairing.deviceTokenMasked || "afx_dev_***9a8f"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-institutional-ea-textMuted font-sans">Cloud Endpoint:</span>
                  <span className="text-institutional-ea-textSecondary text-[10px] truncate max-w-[200px]">{pairing.apiUrl}</span>
                </div>
              </div>

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text rounded-lg text-xs font-semibold border border-institutional-ea-border transition"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={handleDisconnect}
                  disabled={loading}
                  className="px-4 py-2 bg-[var(--institutional-ea-loss-soft)] hover:brightness-105 text-institutional-ea-loss rounded-lg text-xs font-bold border border-institutional-ea-loss/30 transition flex items-center gap-1.5"
                >
                  <Unlink className="w-3.5 h-3.5" />
                  {loading ? "Disconnecting..." : "Disconnect Cloud"}
                </button>
              </div>
            </div>
          ) : (
            /* Unpaired - Pairing Code Input Form */
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="p-3 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl text-xs text-institutional-ea-textSecondary space-y-1">
                <div className="flex items-center gap-1.5 text-institutional-ea-primary font-semibold">
                  <Shield className="w-4 h-4" />
                  <span>How to connect with Institutional EA Cloud:</span>
                </div>
                <ol className="list-decimal list-inside space-y-0.5 text-[11px] text-institutional-ea-textMuted pt-1">
                  <li>Log in to your account at <b>Institutional EA Cloud</b></li>
                  <li>Navigate to <b>Settings &gt; Bot Management &gt; Pair Desktop</b></li>
                  <li>Generate a 6-character one-time pairing token</li>
                  <li>Enter the token below to authenticate this companion</li>
                </ol>
              </div>

              <div>
                <label className="block text-xs font-bold text-institutional-ea-text mb-1">
                  6-Character Pairing Code
                </label>
                <div className="relative">
                  <Key className="w-4 h-4 text-institutional-ea-textMuted absolute left-3 top-3" />
                  <input
                    type="text"
                    value={code}
                    onChange={handleInputChange}
                    placeholder="e.g. AFX982"
                    maxLength={6}
                    className="w-full pl-9 pr-3 py-2.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl text-center text-lg font-mono font-bold tracking-widest text-institutional-ea-text placeholder:text-institutional-ea-textMuted placeholder:font-normal focus:border-institutional-ea-primary outline-none transition"
                  />
                </div>
              </div>

              {errorMsg && (
                <div className="p-2.5 bg-[var(--institutional-ea-loss-soft)] border border-institutional-ea-loss/30 rounded-lg text-xs text-institutional-ea-loss flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{errorMsg}</span>
                </div>
              )}

              {successMsg && (
                <div className="p-2.5 bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 rounded-lg text-xs text-institutional-ea-profit flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 shrink-0" />
                  <span>{successMsg}</span>
                </div>
              )}

              <div className="pt-2 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 bg-institutional-ea-surface hover:bg-institutional-ea-secondary text-institutional-ea-text rounded-lg text-xs font-semibold border border-institutional-ea-border transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={loading || code.length !== 6}
                  className="px-5 py-2 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive disabled:opacity-50 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5"
                >
                  <Link className="w-3.5 h-3.5" />
                  {loading ? "Authenticating..." : "Pair Device"}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
