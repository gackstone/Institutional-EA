import React, { useEffect, useState } from "react";
import {
  Link2,
  Play,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { controlClient, formatControlError, IPC } from "../../services/ipc";
import {
  AllowlistedOpInfo,
  ControlStatusPayload,
  DeployEAResult,
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
  const [deployingId, setDeployingId] = useState<string | null>(null);
  const [deployReport, setDeployReport] = useState<DeployEAResult | null>(null);

  const scan = async () => {
    try {
      const list = await IPC.scanMT5Terminals();
      setTerminals(list);
    } catch (e: any) {
      onActionMessage(`Scan failed: ${formatControlError(e)}`, true);
    }
  };

  useEffect(() => {
    scan();
  }, []);

  const handleConnect = async (terminalPath?: string) => {
    setBusy(true);
    try {
      const targetPath = terminalPath || terminals[0]?.executablePath;
      const res = await controlClient.connectMT5(targetPath);
      if (res.success) {
        onActionMessage("MT5 synced.", false);
      } else {
        onActionMessage(`MT5 sync failed: ${res.error || "Unable to connect to MT5 terminal."}`, true);
      }
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`MT5 sync failed: ${formatControlError(e)}`, true);
    } finally {
      setBusy(false);
    }
  };

  const handleDeployEA = async (t: MT5TerminalInfo) => {
    setDeployingId(t.id);
    try {
      const r = await IPC.deployEA({
        executablePath: t.executablePath,
        dataFolder: t.dataFolder,
        expertsFolder: t.expertsFolder,
        compile: true,
      });
      setDeployReport(r);
      onActionMessage(r.message || (r.success ? "EA deployed." : "EA deploy failed."), !r.success);
      await scan();
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`Deploy EA failed: ${formatControlError(e)}`, true);
    } finally {
      setDeployingId(null);
    }
  };

  const acct = status?.mt5.account;

  return (
    <div className="space-y-4">
      <div className="iea-card p-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
            <Link2 className="w-5 h-5 text-iea-accent" />
            <span>MT5 Terminals</span>
          </h2>
          <p className="text-xs text-iea-textSecondary mt-1">
            Conn: <strong className="text-iea-profit">{status?.mt5.connection_status || "DISCONNECTED"}</strong> · Mode:{" "}
            <strong className="text-iea-textPrimary">{acct?.trade_mode || "DEMO"}</strong> · Margin:{" "}
            <strong className="text-iea-accent">{acct?.margin_mode_str || "HEDGING"}</strong>
            {status?.mt5.zmq_bridge && (
              <>
                {" "}· ZMQ 5555:{" "}
                <strong className={status.mt5.zmq_bridge.port_5555 ? "text-iea-profit" : "text-iea-textMuted"}>
                  {status.mt5.zmq_bridge.port_5555 ? "UP" : "IDLE"}
                </strong>
              </>
            )}
          </p>
        </div>
        <div className="flex space-x-2.5">
          <button onClick={scan} className="iea-pill-control px-4 py-1.5 text-xs text-iea-textPrimary font-semibold">
            Scan
          </button>
          <button
            disabled={busy}
            onClick={() => handleConnect()}
            className="px-4 py-1.5 bg-iea-accent hover:bg-iea-accentHover disabled:opacity-50 text-xs text-white font-extrabold rounded-full transition"
          >
            {busy ? "Syncing..." : "Sync MT5"}
          </button>
        </div>
      </div>

      <div className="iea-card p-5 space-y-3">
        <h3 className="text-sm font-bold text-iea-textPrimary">Terminals ({terminals.length})</h3>
        {terminals.length === 0 ? (
          <div className="text-xs text-iea-textMuted py-4">0 terminals detected.</div>
        ) : (
          terminals.map((t) => (
            <div key={t.id} className="iea-inset flex flex-wrap items-center justify-between gap-3 p-4 text-xs">
              <div>
                <div className="font-bold text-iea-textPrimary">
                  {t.name}{" "}
                  {t.isRunning ? (
                    <span className="text-iea-profit font-mono">(PID {t.pid})</span>
                  ) : (
                    <span className="text-iea-textMuted">(Stopped)</span>
                  )}
                </div>
                <div className="font-mono text-[11px] text-iea-textSecondary mt-0.5">{t.executablePath}</div>
                {t.dataFolder && (
                  <div className="font-mono text-[10px] text-iea-textMuted mt-0.5 truncate max-w-[520px]">
                    Data: {t.dataFolder}
                  </div>
                )}
                <div className="text-[11px] text-iea-textMuted mt-0.5">
                  EA: <strong className="text-iea-accent">{t.eaInstalled ? `v${t.eaVersion || "3.10"}` : "None"}</strong>
                </div>
              </div>
              <div className="flex space-x-2">
                <button
                  disabled={deployingId !== null}
                  onClick={() => handleDeployEA(t)}
                  className="iea-pill-control px-3.5 py-1.5 text-iea-textPrimary font-semibold disabled:opacity-50"
                >
                  {deployingId === t.id ? "Deploying..." : "Deploy EA"}
                </button>
                <button
                  onClick={async () => {
                    const r = await IPC.launchMT5(t.executablePath);
                    onActionMessage(r.message, !r.success);
                    scan();
                  }}
                  className="px-3.5 py-1.5 bg-iea-accent hover:bg-iea-accentHover text-white font-extrabold rounded-full transition"
                >
                  Launch
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {deployReport && (
        <div className="iea-card p-5 space-y-2.5 text-xs">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-iea-textPrimary">
              EA Deployment Report —{" "}
              <span className={deployReport.success ? "text-iea-profit" : "text-iea-danger"}>
                {deployReport.success ? "VERIFIED" : "FAILED"}
              </span>
            </h3>
            <button
              onClick={() => setDeployReport(null)}
              className="text-[11px] text-iea-textMuted hover:text-iea-textPrimary"
            >
              Dismiss
            </button>
          </div>
          {deployReport.steps && deployReport.steps.length > 0 && (
            <div className="space-y-1.5">
              {deployReport.steps.map((s, idx) => (
                <div key={`${s.step}-${idx}`} className="iea-inset px-3 py-2 flex items-start justify-between gap-2">
                  <span className="font-mono text-iea-textSecondary">{s.step}</span>
                  <span className={`text-right ${s.ok ? "text-iea-profit" : "text-iea-danger"}`}>{s.detail}</span>
                </div>
              ))}
            </div>
          )}
          {deployReport.chart_attachment?.note && (
            <div className="text-[11px] text-iea-textSecondary bg-iea-inset border border-iea-borderSubtle rounded-xl p-3">
              {deployReport.chart_attachment.note}
            </div>
          )}
        </div>
      )}
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
      <div className="iea-card p-5 space-y-3.5">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-iea-textPrimary flex items-center space-x-2">
            <Terminal className="w-5 h-5 text-iea-accent" />
            <span>Ops Runner</span>
          </h2>
          <button onClick={loadOps} className="iea-pill-control p-1.5 text-iea-textSecondary hover:text-iea-textPrimary">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="space-y-2.5 max-h-[460px] overflow-y-auto">
          {ops.map((op) => (
            <div key={op.op_id} className="iea-inset flex items-center justify-between px-4 py-3 text-xs">
              <div>
                <div className="font-semibold text-iea-textPrimary">{op.name}</div>
                <div className="text-[11px] text-iea-textSecondary mt-0.5">{op.description}</div>
              </div>
              <button
                disabled={runningOp !== null}
                onClick={() => handleRun(op.op_id)}
                className="px-3.5 py-1.5 bg-iea-accent hover:bg-iea-accentHover disabled:opacity-40 text-white font-extrabold rounded-full inline-flex items-center space-x-1 shrink-0 ml-3 transition"
              >
                <Play className="w-3 h-3" />
                <span>{runningOp === op.op_id ? "..." : "Run"}</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="iea-card p-5 space-y-3.5">
        <h3 className="text-sm font-bold text-iea-textPrimary">Output &amp; Audit</h3>
        {selectedOutput && (
          <div className="bg-iea-inset border border-iea-borderSubtle rounded-2xl p-3.5 text-xs space-y-1.5">
            <div className="flex justify-between font-mono">
              <span className="text-iea-accent">{selectedOutput.op_id}</span>
              <span className={selectedOutput.status === "SUCCESS" ? "text-iea-profit" : "text-iea-danger"}>
                {selectedOutput.status || "OK"} ({selectedOutput.duration_ms ?? 120}ms)
              </span>
            </div>
            <pre className="text-[11px] text-iea-textSecondary font-mono whitespace-pre-wrap max-h-44 overflow-y-auto">
              {selectedOutput.stdout || selectedOutput.stderr || "Exit 0"}
            </pre>
          </div>
        )}

        <div className="space-y-2 max-h-[260px] overflow-y-auto text-xs">
          {audits.length === 0 ? (
            <div className="text-xs text-iea-textMuted py-4">0 runs recorded.</div>
          ) : (
            audits.map((a) => (
              <button
                key={a.id}
                onClick={() => setSelectedOutput(a)}
                className="iea-inset w-full text-left flex items-center justify-between px-3.5 py-2 hover:border-iea-borderDefault transition"
              >
                <span className="font-mono text-iea-textPrimary">{a.op_id}</span>
                <span className={`font-mono font-bold ${a.status === "SUCCESS" ? "text-iea-profit" : "text-iea-danger"}`}>
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
