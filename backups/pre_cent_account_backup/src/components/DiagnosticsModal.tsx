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
        return <CheckCircle className="w-4 h-4 text-institutional-ea-profit" />;
      case "WARN":
        return <AlertTriangle className="w-4 h-4 text-institutional-ea-warning" />;
      case "FAIL":
        return <XCircle className="w-4 h-4 text-institutional-ea-loss" />;
      default:
        return <RefreshCw className="w-4 h-4 text-institutional-ea-info animate-spin" />;
    }
  };

  const passCount = items.filter((i) => i.status === "PASS").length;

  return (
    <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4 select-none animate-fadeIn">
      <div className="bg-institutional-ea-card border border-institutional-ea-border rounded-xl w-full max-w-xl max-h-[85vh] overflow-hidden shadow-2xl flex flex-col text-institutional-ea-text">
        {/* Header */}
        <div className="px-5 py-4 border-b border-institutional-ea-border flex items-center justify-between bg-institutional-ea-surface">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-[var(--institutional-ea-profit-soft)] text-institutional-ea-profit border border-institutional-ea-profit/30">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm text-institutional-ea-text">System Pre-Flight Diagnostics</h3>
              <p className="text-[11px] text-institutional-ea-textMuted">Comprehensive hardware, runtime, network & trading checks</p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-institutional-ea-secondary rounded-md text-institutional-ea-textMuted hover:text-institutional-ea-text transition">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto flex-1 space-y-3">
          <div className="flex items-center justify-between text-xs text-institutional-ea-textSecondary mb-2">
            <span>
              Diagnostic Results: <b className="text-institutional-ea-text">{passCount} / {items.length} Passed</b>
            </span>
            <button
              onClick={runChecks}
              disabled={running}
              className="flex items-center gap-1 text-[11px] text-institutional-ea-primary hover:text-institutional-ea-primaryHover transition"
            >
              <RefreshCw className={`w-3 h-3 ${running ? "animate-spin" : ""}`} />
              Re-run
            </button>
          </div>

          <div className="divide-y divide-institutional-ea-border border border-institutional-ea-border rounded-xl bg-institutional-ea-surface overflow-hidden">
            {items.map((item) => (
              <div key={item.id} className="p-3 flex items-start justify-between gap-3 text-xs">
                <div>
                  <div className="font-semibold text-institutional-ea-text">{item.name}</div>
                  <div className="text-[11px] text-institutional-ea-textMuted font-mono mt-0.5">{item.details}</div>
                </div>
                <div className="shrink-0 mt-0.5">{getStatusIcon(item.status)}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-institutional-ea-border bg-institutional-ea-surface flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text rounded-lg text-xs font-semibold border border-institutional-ea-border transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
