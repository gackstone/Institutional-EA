import React, { useState, useEffect } from "react";
import { Activity, X, CheckCircle, AlertTriangle, XCircle, RefreshCw } from "lucide-react";
import { DiagnosticResult } from "../types";
import { IPC } from "../services/ipc";

interface DiagnosticsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DiagnosticsModal: React.FC<DiagnosticsModalProps> = ({ isOpen, onClose }) => {
  const [items, setItems] = useState<DiagnosticResult[]>([]);
  const [running, setRunning] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      runChecks();
    }
  }, [isOpen]);

  const runChecks = async () => {
    setRunning(true);
    try {
      const results = await IPC.runDiagnostics();
      setItems(results);
    } catch (e: any) {
      setItems([
        { id: "err", name: "Diagnostics Execution", status: "FAIL", details: e.message }
      ]);
    } finally {
      setRunning(false);
    }
  };

  if (!isOpen) return null;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "PASS":
        return <CheckCircle className="w-4 h-4 text-arcade-profit" />;
      case "WARN":
        return <AlertTriangle className="w-4 h-4 text-arcade-warning" />;
      case "FAIL":
        return <XCircle className="w-4 h-4 text-arcade-loss" />;
      default:
        return <RefreshCw className="w-4 h-4 text-arcade-info animate-spin" />;
    }
  };

  const passCount = items.filter((i) => i.status === "PASS").length;

  return (
    <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4 select-none animate-fadeIn">
      <div className="bg-arcade-card border border-arcade-border rounded-xl w-full max-w-xl max-h-[85vh] overflow-hidden shadow-2xl flex flex-col text-arcade-text">
        {/* Header */}
        <div className="px-5 py-4 border-b border-arcade-border flex items-center justify-between bg-arcade-surface">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[var(--arcade-profit-soft)] text-arcade-profit border border-arcade-profit/30">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-arcade-text">System Pre-Flight Diagnostics</h3>
              <p className="text-[11px] text-arcade-textMuted">Comprehensive hardware, runtime, network & trading checks</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-arcade-secondary rounded-md text-arcade-textMuted hover:text-arcade-text transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-3">
          <div className="flex items-center justify-between text-xs text-arcade-textSecondary mb-2">
            <span>
              Diagnostic Results: <b className="text-arcade-text">{passCount} / {items.length} Passed</b>
            </span>
            <button
              onClick={runChecks}
              disabled={running}
              className="flex items-center gap-1 text-[11px] text-arcade-primary hover:text-arcade-primaryHover transition"
            >
              <RefreshCw className={`w-3 h-3 ${running ? "animate-spin" : ""}`} />
              Re-run
            </button>
          </div>

          <div className="divide-y divide-arcade-border border border-arcade-border rounded-xl bg-arcade-surface overflow-hidden">
            {items.map((item) => (
              <div key={item.id} className="p-3 flex items-start justify-between gap-3 text-xs">
                <div>
                  <div className="font-semibold text-arcade-text">{item.name}</div>
                  <div className="text-[11px] text-arcade-textMuted font-mono mt-0.5">{item.details}</div>
                </div>
                <div className="shrink-0 mt-0.5">{getStatusIcon(item.status)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-arcade-border bg-arcade-surface flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-arcade-card hover:bg-arcade-secondary text-arcade-text rounded-lg text-xs font-semibold border border-arcade-border transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
