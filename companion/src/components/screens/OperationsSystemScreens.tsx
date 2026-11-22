import React, { useEffect, useState } from "react";
import {
  Link2,
  Play,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { controlClient, IPC } from "../../services/ipc";
import {
  AllowlistedOpInfo,
  ControlStatusPayload,
  MT5TerminalInfo,
  OperationAuditRecord,
} from "../../types";

export const MT5ConnectionScreen: React.FC<{
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ status, onRefresh, onActionMessage }) => {
  const [terminals, setTerminals] = useState<MT5TerminalInfo[]>([]);
  const [busy, setBusy] = useState(false);

  const scan = async () => {
    try {
      const list = await IPC.scanMT5Terminals();
      setTerminals(list);
    } catch (e: any) {
      onActionMessage(`Scan failed: ${e.message}`, true);
    }
  };

  useEffect(() => {
    scan();
  }, []);

  const handleConnect = async () => {
    setBusy(true);
    try {
      const res = await controlClient.connectMT5();
      onActionMessage(res.success ? "MT5 synced." : "MT5 connect failed.", !res.success);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`MT5 error: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  const acct = status?.mt5.account;

  return (
    <div className="space-y-4">
      <div className="iea-glass-card p-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Link2 className="w-5 h-5 text-[#B0F648]" />
            <span>MT5 Terminals</span>
          </h2>
          <p className="text-xs text-[#B6C5E0] mt-1">
            Conn: <strong className="text-[#B0F648]">{status?.mt5.connection_status}</strong> · Mode:{" "}
            <strong className="text-[#F4F7FF]">{acct?.trade_mode || "DEMO"}</strong> · Margin:{" "}
            <strong className="text-[#5EEAD4]">{acct?.margin_mode_str || "HEDGING"}</strong>
          </p>
        </div>
        <div className="flex space-x-2.5">
          <button onClick={scan} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold">
            Scan
          </button>
          <button
            disabled={busy}
            onClick={handleConnect}
            className="px-4 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-xs text-[#081321] font-extrabold rounded-full shadow-[0_0_16px_rgba(176,246,72,0.28)]"
          >
            Sync MT5
          </button>
        </div>
      </div>

      <div className="iea-glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold text-[#F4F7FF]">Terminals ({terminals.length})</h3>
        {terminals.length === 0 ? (
          <div className="text-xs text-[#8496B8] py-4">0 terminals detected.</div>
        ) : (
          terminals.map((t) => (
            <div key={t.id} className="iea-glass-tile flex flex-wrap items-center justify-between gap-3 p-4 text-xs">
              <div>
                <div className="font-bold text-[#F4F7FF]">
                  {t.name}{" "}
                  {t.isRunning ? (
                    <span className="text-[#B0F648] font-mono">(PID {t.pid})</span>
                  ) : (
                    <span className="text-[#8496B8]">(Stopped)</span>
                  )}
                </div>
                <div className="font-mono text-[11px] text-[#B6C5E0] mt-0.5">{t.executablePath}</div>
                <div className="text-[11px] text-[#8496B8] mt-0.5">
                  EA: <strong className="text-[#5EEAD4]">{t.eaInstalled ? `v${t.eaVersion}` : "None"}</strong>
                </div>
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={async () => {
                    const r = await IPC.deployEA(t.expertsFolder);
                    onActionMessage(r.message, !r.success);
                    scan();
                  }}
                  className="iea-pill-control px-3.5 py-1.5 text-[#F4F7FF] font-semibold"
                >
                  Deploy EA
                </button>
                <button
                  onClick={async () => {
                    const r = await IPC.launchMT5(t.executablePath);
                    onActionMessage(r.message, !r.success);
                    scan();
                  }}
                  className="px-3.5 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] font-extrabold rounded-full"
                >
                  Launch
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export const OperationsCentreScreen: React.FC<{
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ onActionMessage }) => {
  const [ops, setOps] = useState<AllowlistedOpInfo[]>([
    {
      op_id: "selfcheck",
      name: "System Self-Check",
      description: "Verify ZMQ 5555/5556, SQLite & DEMO lock.",
      timeout_sec: 30,
    },
    {
      op_id: "sync_instruments",
      name: "Sync Symbol Specs",
      description: "Refresh XAUUSD, USDJPY & BTCUSD contract specs.",
      timeout_sec: 20,
    },
  ]);
  const [audits, setAudits] = useState<OperationAuditRecord[]>([]);
  const [selectedOutput, setSelectedOutput] = useState<OperationAuditRecord | null>(null);
  const [runningOp, setRunningOp] = useState<string | null>(null);

  const loadOps = async () => {
    try {
      const data = await controlClient.getOperations();
      if (data.operations && data.operations.length > 0) setOps(data.operations);
      setAudits(data.audits || []);
    } catch {
      // keep fallback allowlist
    }
  };

  useEffect(() => {
    loadOps();
  }, []);

  const handleRun = async (opId: string) => {
    setRunningOp(opId);
    try {
      const res = await controlClient.runOperation(opId);
      setSelectedOutput(res);
      onActionMessage(`Op '${opId}' -> ${res.status || "OK"}`, false);
      await loadOps();
    } catch (e: any) {
      onActionMessage(`Op failed: ${e.message}`, true);
    } finally {
      setRunningOp(null);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="iea-glass-card p-5 space-y-3.5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Terminal className="w-5 h-5 text-[#B0F648]" />
            <span>Ops Runner</span>
          </h2>
          <button onClick={loadOps} className="iea-pill-control p-1.5 text-[#B6C5E0] hover:text-white">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="space-y-2.5 max-h-[460px] overflow-y-auto">
          {ops.map((op) => (
            <div key={op.op_id} className="iea-glass-tile flex items-center justify-between px-4 py-3 text-xs">
              <div>
                <div className="font-semibold text-[#F4F7FF]">{op.name}</div>
                <div className="text-[11px] text-[#B6C5E0] mt-0.5">{op.description}</div>
              </div>
              <button
                disabled={runningOp !== null}
                onClick={() => handleRun(op.op_id)}
                className="px-3.5 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] disabled:opacity-40 text-[#081321] font-extrabold rounded-full inline-flex items-center space-x-1 shrink-0 ml-3"
              >
                <Play className="w-3 h-3" />
                <span>{runningOp === op.op_id ? "..." : "Run"}</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="iea-glass-card p-5 space-y-3.5">
        <h3 className="text-sm font-semibold text-[#F4F7FF]">Output &amp; Audit</h3>
        {selectedOutput && (
          <div className="bg-[#071020]/85 border border-[rgba(186,214,255,0.16)] rounded-2xl p-3.5 text-xs space-y-1.5">
            <div className="flex justify-between font-mono">
              <span className="text-[#5EEAD4]">{selectedOutput.op_id}</span>
              <span className={selectedOutput.status === "SUCCESS" ? "text-[#B0F648]" : "text-[#FF5A6E]"}>
                {selectedOutput.status || "OK"} ({selectedOutput.duration_ms ?? 120}ms)
              </span>
            </div>
            <pre className="text-[11px] text-[#B6C5E0] font-mono whitespace-pre-wrap max-h-44 overflow-y-auto">
              {selectedOutput.stdout || selectedOutput.stderr || "Exit 0"}
            </pre>
          </div>
        )}

        <div className="space-y-2 max-h-[260px] overflow-y-auto text-xs">
          {audits.length === 0 ? (
            <div className="text-xs text-[#8496B8] py-4">0 runs recorded.</div>
          ) : (
            audits.map((a) => (
              <button
                key={a.id}
                onClick={() => setSelectedOutput(a)}
                className="iea-glass-tile w-full text-left flex items-center justify-between px-3.5 py-2 hover:border-[rgba(186,214,255,0.28)]"
              >
                <span className="font-mono text-[#F4F7FF]">{a.op_id}</span>
                <span className={`font-mono font-bold ${a.status === "SUCCESS" ? "text-[#B0F648]" : "text-[#FF5A6E]"}`}>
                  {a.status}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
