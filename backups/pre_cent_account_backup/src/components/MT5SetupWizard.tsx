import React, { useState, useEffect } from "react";
import {
  ExternalLink,
  X,
  CheckCircle,
  AlertCircle,
  Download,
  FolderOpen,
  Play,
  RefreshCw,
  HelpCircle,
  FileCode,
  Check
} from "lucide-react";
import { MT5TerminalInfo } from "../types";
import { IPC } from "../services/ipc";

interface MT5SetupWizardProps {
  isOpen: boolean;
  onClose: () => void;
}

export const MT5SetupWizard: React.FC<MT5SetupWizardProps> = ({ isOpen, onClose }) => {
  const [terminals, setTerminals] = useState<MT5TerminalInfo[]>([]);
  const [selectedTerminal, setSelectedTerminal] = useState<MT5TerminalInfo | null>(null);
  const [scanning, setScanning] = useState<boolean>(false);
  const [deploying, setDeploying] = useState<boolean>(false);
  const [deploySuccess, setDeploySuccess] = useState<boolean>(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; msg: string } | null>(null);

  useEffect(() => {
    if (isOpen) {
      scanTerminals();
    }
  }, [isOpen]);

  const scanTerminals = async () => {
    setScanning(true);
    setFeedback(null);
    try {
      const detected = await IPC.scanMT5Terminals();
      setTerminals(detected);
      if (detected.length > 0 && !selectedTerminal) {
        setSelectedTerminal(detected[0]);
      }
    } catch (e: any) {
      setFeedback({ type: "error", msg: `Failed to scan MT5 terminals: ${e.message}` });
    } finally {
      setScanning(false);
    }
  };

  const handleDeployEA = async () => {
    if (!selectedTerminal) return;
    setDeploying(true);
    setFeedback(null);
    try {
      const res = await IPC.deployEA(selectedTerminal.expertsFolder);
      if (res.success) {
        setDeploySuccess(true);
        setFeedback({ type: "success", msg: "PythonBridgeEA.mq5 successfully installed in MT5 Experts folder!" });
        await scanTerminals();
      } else {
        setFeedback({ type: "error", msg: res.message });
      }
    } catch (e: any) {
      setFeedback({ type: "error", msg: `Deployment error: ${e.message}` });
    } finally {
      setDeploying(false);
    }
  };

  const handleLaunchMT5 = async () => {
    if (!selectedTerminal) return;
    try {
      const res = await IPC.launchMT5(selectedTerminal.executablePath);
      setFeedback({ type: "success", msg: res.message || "Launched MT5 Terminal." });
      await scanTerminals();
    } catch (e: any) {
      setFeedback({ type: "error", msg: `Could not launch MT5: ${e.message}` });
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4 select-none animate-fadeIn">
      <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-xl w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col text-institutional-ea-text">
        {/* Header */}
        <div className="px-5 py-4 border-b border-institutional-ea-border flex items-center justify-between bg-institutional-ea-surface">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
              <ExternalLink className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-institutional-ea-text">MetaTrader 5 Integration & EA Wizard</h3>
              <p className="text-[11px] text-institutional-ea-textMuted">Automatic detection, EA deployment, and connection verification</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-institutional-ea-secondary rounded-md text-institutional-ea-textMuted hover:text-institutional-ea-text transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 space-y-5 overflow-y-auto flex-1">
          {/* Step 1: Detect Terminal */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-institutional-ea-text flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary flex items-center justify-center text-[11px] font-bold">1</span>
                Installed MetaTrader 5 Terminals
              </h4>
              <button
                onClick={scanTerminals}
                disabled={scanning}
                className="flex items-center gap-1 text-[11px] text-institutional-ea-textMuted hover:text-institutional-ea-text transition"
              >
                <RefreshCw className={`w-3 h-3 ${scanning ? "animate-spin" : ""}`} />
                Rescan
              </button>
            </div>

            {terminals.length === 0 ? (
              <div className="p-4 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl text-center text-xs text-institutional-ea-textMuted">
                {scanning ? "Scanning for installed terminals..." : "No MT5 terminals detected automatically. Verify MT5 is installed on your computer."}
              </div>
            ) : (
              <div className="space-y-2">
                {terminals.map((term) => (
                  <div
                    key={term.id}
                    onClick={() => setSelectedTerminal(term)}
                    className={`p-3 rounded-xl border cursor-pointer transition flex items-center justify-between ${
                      selectedTerminal?.id === term.id
                        ? "bg-[var(--institutional-ea-primary-soft)] border-institutional-ea-primary/50 text-institutional-ea-text"
                        : "bg-institutional-ea-surface border-institutional-ea-border hover:border-institutional-ea-borderStrong text-institutional-ea-textSecondary"
                    }`}
                  >
                    <div>
                      <div className="font-bold text-xs flex items-center gap-2 text-institutional-ea-text">
                        <span>{term.name}</span>
                        {term.isRunning && (
                          <span className="text-[10px] bg-[var(--institutional-ea-profit-soft)] text-institutional-ea-profit px-1.5 py-0.2 rounded border border-institutional-ea-profit/30">
                            RUNNING
                          </span>
                        )}
                        {term.eaInstalled && (
                          <span className="text-[10px] bg-institutional-ea-secondary text-institutional-ea-textSecondary px-1.5 py-0.2 rounded border border-institutional-ea-border">
                            EA v{term.eaVersion} Installed
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-institutional-ea-textMuted font-mono mt-0.5 truncate max-w-md">
                        {term.executablePath}
                      </div>
                    </div>

                    <div className="shrink-0">
                      {selectedTerminal?.id === term.id ? (
                        <CheckCircle className="w-4 h-4 text-institutional-ea-primary" />
                      ) : (
                        <div className="w-4 h-4 rounded-full border border-institutional-ea-border"></div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Step 2: One-Click EA Installation */}
          <div className="pt-2 border-t border-institutional-ea-border">
            <h4 className="text-xs font-bold uppercase tracking-wider text-institutional-ea-text flex items-center gap-2 mb-2">
              <span className="w-5 h-5 rounded-full bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary flex items-center justify-center text-[11px] font-bold">2</span>
              One-Click Python Bridge EA Deployment
            </h4>
            <div className="p-3.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl flex items-center justify-between gap-4">
              <div>
                <div className="text-xs font-semibold text-institutional-ea-text flex items-center gap-1.5">
                  <FileCode className="w-4 h-4 text-institutional-ea-primary" />
                  Install PythonBridgeEA.mq5 into Experts Folder
                </div>
                <p className="text-[11px] text-institutional-ea-textMuted mt-0.5">
                  Deploys the bridge Expert Advisor communicating with the engine on TCP 5555.
                </p>
              </div>

              <button
                onClick={handleDeployEA}
                disabled={deploying || !selectedTerminal}
                className="shrink-0 px-4 py-2 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive text-white rounded-lg text-xs font-bold disabled:opacity-50 transition flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                {deploying ? "Deploying..." : deploySuccess ? "Re-deploy EA" : "Deploy EA"}
              </button>
            </div>
          </div>

          {/* Step 3: Terminal Setup Checklist */}
          <div className="pt-2 border-t border-institutional-ea-border">
            <h4 className="text-xs font-bold uppercase tracking-wider text-institutional-ea-text flex items-center gap-2 mb-2">
              <span className="w-5 h-5 rounded-full bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary flex items-center justify-center text-[11px] font-bold">3</span>
              Required MT5 Terminal Configuration
            </h4>
            <div className="space-y-2 text-xs">
              <div className="flex items-start gap-2.5 p-2.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg">
                <Check className="w-4 h-4 text-institutional-ea-profit shrink-0 mt-0.5" />
                <div>
                  <b className="text-institutional-ea-text">Enable Automated Trading:</b> Press the Algo Trading button in the MT5 toolbar (or Ctrl+E) until the green play icon is displayed.
                </div>
              </div>
              <div className="flex items-start gap-2.5 p-2.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg">
                <Check className="w-4 h-4 text-institutional-ea-profit shrink-0 mt-0.5" />
                <div>
                  <b className="text-institutional-ea-text">Allow DLL / Network Calls:</b> In MT5, open <i>Tools &gt; Options &gt; Expert Advisors</i>, check "Allow Algo Trading" and "Allow DLL imports".
                </div>
              </div>
              <div className="flex items-start gap-2.5 p-2.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-lg">
                <Check className="w-4 h-4 text-institutional-ea-profit shrink-0 mt-0.5" />
                <div>
                  <b className="text-institutional-ea-text">Attach PythonBridgeEA:</b> In MT5 Navigator under Expert Advisors, drag <code>PythonBridgeEA</code> onto any open chart (EURUSD recommended).
                </div>
              </div>
            </div>
          </div>

          {/* Feedback notification */}
          {feedback && (
            <div
              className={`p-3 rounded-xl border text-xs flex items-center gap-2 ${
                feedback.type === "success"
                  ? "bg-[var(--institutional-ea-profit-soft)] text-institutional-ea-profit border-institutional-ea-profit/30"
                  : "bg-[var(--institutional-ea-loss-soft)] text-institutional-ea-loss border-institutional-ea-loss/30"
              }`}
            >
              {feedback.type === "success" ? <CheckCircle className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
              <span>{feedback.msg}</span>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-institutional-ea-border bg-institutional-ea-surface flex items-center justify-between">
          <button
            onClick={handleLaunchMT5}
            disabled={!selectedTerminal}
            className="px-4 py-2 bg-institutional-ea-secondary hover:brightness-105 text-institutional-ea-text rounded-lg text-xs font-bold border border-institutional-ea-border transition flex items-center gap-1.5"
          >
            <Play className="w-3.5 h-3.5 text-institutional-ea-profit" />
            Launch Selected MT5
          </button>

          <button
            onClick={onClose}
            className="px-5 py-2 bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover text-white rounded-lg text-xs font-bold transition"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};
