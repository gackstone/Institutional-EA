import React, { useEffect, useState } from "react";
import {
  AlertOctagon,
  CheckCircle2,
  FolderCog,
  Link2,
  Play,
  RefreshCw,
  RotateCcw,
  Terminal,
} from "lucide-react";
import { controlClient, IPC } from "../../services/ipc";
import {
  AllowlistedOpInfo,
  ConfigVersionRecord,
  ControlErrorEvent,
  ControlStatusPayload,
  MT5TerminalInfo,
  OperationAuditRecord,
} from "../../types";

export const ConfigurationScreen: React.FC<{
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ onActionMessage }) => {
  const [section, setSection] = useState<"settings" | "risk" | "strategy">("settings");
  const [fullConfig, setFullConfig] = useState<Record<string, any>>({});
  const [versions, setVersions] = useState<ConfigVersionRecord[]>([]);
  const [editorText, setEditorText] = useState("");
  const [summary, setSummary] = useState("Updated via Companion Control Centre");
  const [previewInfo, setPreviewInfo] = useState<{
    valid: boolean;
    errors: string[];
    changed_keys: string[];
    requires_restart: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const loadAll = async () => {
    try {
      const [cfg, hist] = await Promise.all([controlClient.getConfig(), controlClient.getConfigHistory()]);
      setFullConfig(cfg);
      setVersions(hist.versions || []);
      setEditorText(JSON.stringify(cfg[section] || {}, null, 2));
      setPreviewInfo(null);
    } catch (e: any) {
      onActionMessage(`Failed to load config: ${e.message}`, true);
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    if (fullConfig[section]) {
      setEditorText(JSON.stringify(fullConfig[section], null, 2));
      setPreviewInfo(null);
    }
  }, [section]);

  const handlePreview = async () => {
    try {
      const parsed = JSON.parse(editorText);
      const res = await controlClient.previewConfig({ [section]: parsed });
      setPreviewInfo(res);
    } catch (e: any) {
      onActionMessage(`Invalid JSON or preview failed: ${e.message}`, true);
    }
  };

  const handleApply = async () => {
    setBusy(true);
    try {
      const parsed = JSON.parse(editorText);
      const res = await controlClient.applyConfig({ [section]: parsed }, summary);
      onActionMessage(
        `Config v${res.version} applied (${res.changed_keys.length} changes).${
          res.requires_restart ? " Engine restart required!" : ""
        }`
      );
      await loadAll();
    } catch (e: any) {
      onActionMessage(`Apply rejected: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  const handleRollback = async (ver: number) => {
    if (!window.confirm(`Rollback configuration to v${ver}?`)) return;
    setBusy(true);
    try {
      const res = await controlClient.rollbackConfig(ver);
      onActionMessage(`Rolled back to v${ver} -> new v${res.version}.`);
      await loadAll();
    } catch (e: any) {
      onActionMessage(`Rollback failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <FolderCog className="w-4 h-4 text-sky-400" />
            <h2 className="text-sm font-bold text-slate-100">Authoritative Configuration Editor</h2>
          </div>
          <div className="flex space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            {(["settings", "risk", "strategy"] as const).map((sec) => (
              <button
                key={sec}
                onClick={() => setSection(sec)}
                className={`px-2.5 py-1 rounded ${section === sec ? "bg-sky-600 text-white font-semibold" : "text-slate-400 hover:text-slate-200"}`}
              >
                {sec}
              </button>
            ))}
          </div>
        </div>

        <textarea
          value={editorText}
          onChange={(e) => setEditorText(e.target.value)}
          rows={15}
          spellCheck={false}
          className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-200 focus:outline-none focus:border-sky-500"
        />

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Change summary..."
            className="flex-1 min-w-[180px] bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200"
          />
          <button onClick={handlePreview} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
            Preview Diff
          </button>
          <button disabled={busy} onClick={handleApply} className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-xs text-white font-semibold rounded-lg">
            Validate &amp; Apply
          </button>
        </div>

        {previewInfo && (
          <div className={`p-3 rounded-lg border text-xs ${previewInfo.valid ? "bg-slate-950 border-slate-700" : "bg-rose-950/60 border-rose-500/50"}`}>
            <div>Valid: <strong>{String(previewInfo.valid)}</strong> · Restart Required: <strong>{String(previewInfo.requires_restart)}</strong></div>
            <div>Changed Keys: <code className="text-sky-300">{previewInfo.changed_keys.join(", ") || "None"}</code></div>
            {previewInfo.errors.length > 0 && <div className="text-rose-300 mt-1">{previewInfo.errors.join("; ")}</div>}
          </div>
        )}
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-bold text-slate-100">Version History</h3>
        <div className="space-y-2 max-h-[420px] overflow-y-auto">
          {versions.map((v) => (
            <div key={v.id} className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5 text-xs space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-sky-400">v{v.version}</span>
                <button
                  disabled={busy}
                  onClick={() => handleRollback(v.version)}
                  className="text-[11px] text-amber-400 hover:text-amber-300 inline-flex items-center space-x-1"
                >
                  <RotateCcw className="w-3 h-3" />
                  <span>Rollback</span>
                </button>
              </div>
              <div className="text-slate-200">{v.change_summary}</div>
              <div className="text-[10px] text-slate-500">{new Date(v.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

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
      onActionMessage(`Terminal scan failed: ${e.message}`, true);
    }
  };

  useEffect(() => {
    scan();
  }, []);

  const handleConnect = async () => {
    setBusy(true);
    try {
      const res = await controlClient.connectMT5();
      onActionMessage(res.success ? "Connected & synced with MT5." : "MT5 connection failed — check Error Centre.", !res.success);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`MT5 connect error: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  const acct = status?.mt5.account;

  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <Link2 className="w-4 h-4 text-sky-400" />
            <span>MetaTrader 5 Terminal Synchronization</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Status: <strong className="text-slate-200">{status?.mt5.connection_status}</strong> · Account:{" "}
            <strong className="text-slate-200">{acct?.trade_mode || "UNKNOWN"}</strong> · Margin:{" "}
            <strong className="text-slate-200">{acct?.margin_mode_str || "HEDGING"}</strong>
          </p>
        </div>
        <div className="flex space-x-2">
          <button onClick={scan} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
            Scan Terminals
          </button>
          <button disabled={busy} onClick={handleConnect} className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-xs text-white font-semibold rounded-lg">
            Connect &amp; Sync MT5
          </button>
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400">Detected Windows MT5 Terminals ({terminals.length})</h3>
        {terminals.length === 0 ? (
          <div className="text-xs text-slate-500 py-4">No MT5 terminals found in standard paths.</div>
        ) : (
          terminals.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center justify-between gap-2 bg-slate-950/70 border border-slate-800 rounded-lg p-3 text-xs">
              <div>
                <div className="font-bold text-slate-100">{t.name} {t.isRunning ? <span className="text-emerald-400">(Running PID {t.pid})</span> : <span className="text-slate-500">(Stopped)</span>}</div>
                <div className="font-mono text-[11px] text-slate-400">{t.executablePath}</div>
                <div className="text-[11px] text-slate-500">EA Installed: {t.eaInstalled ? `Yes (${t.eaVersion})` : "No"}</div>
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={async () => {
                    const r = await IPC.deployEA(t.expertsFolder);
                    onActionMessage(r.message, !r.success);
                    scan();
                  }}
                  className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded"
                >
                  Deploy EA
                </button>
                <button
                  onClick={async () => {
                    const r = await IPC.launchMT5(t.executablePath);
                    onActionMessage(r.message, !r.success);
                    scan();
                  }}
                  className="px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded"
                >
                  Launch MT5
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
  const [ops, setOps] = useState<AllowlistedOpInfo[]>([]);
  const [audits, setAudits] = useState<OperationAuditRecord[]>([]);
  const [selectedOutput, setSelectedOutput] = useState<OperationAuditRecord | null>(null);
  const [runningOp, setRunningOp] = useState<string | null>(null);

  const loadOps = async () => {
    try {
      const data = await controlClient.getOperations();
      setOps(data.operations || []);
      setAudits(data.audits || []);
    } catch (e: any) {
      onActionMessage(`Failed to load operations: ${e.message}`, true);
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
      onActionMessage(`Operation '${opId}' finished (${res.status}, exit ${res.exit_code}).`, res.status !== "SUCCESS");
      await loadOps();
    } catch (e: any) {
      onActionMessage(`Operation failed: ${e.message}`, true);
    } finally {
      setRunningOp(null);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-sky-400" />
            <span>Approved Operations Runner (Fixed Allowlist)</span>
          </h2>
          <button onClick={loadOps} className="text-xs text-slate-400 hover:text-slate-200">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="space-y-2 max-h-[460px] overflow-y-auto">
          {ops.map((op) => (
            <div key={op.op_id} className="flex items-center justify-between bg-slate-950/70 border border-slate-800 rounded-lg px-3 py-2 text-xs">
              <div>
                <div className="font-semibold text-slate-100">{op.name}</div>
                <div className="text-[11px] text-slate-400">{op.description}</div>
              </div>
              <button
                disabled={runningOp !== null}
                onClick={() => handleRun(op.op_id)}
                className="px-2.5 py-1 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white rounded inline-flex items-center space-x-1 shrink-0"
              >
                <Play className="w-3 h-3" />
                <span>{runningOp === op.op_id ? "Running..." : "Run"}</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-bold text-slate-100">Execution Output &amp; Audit History</h3>
        {selectedOutput && (
          <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 text-xs space-y-1">
            <div className="flex justify-between font-mono">
              <span className="text-sky-400">{selectedOutput.op_id}</span>
              <span className={selectedOutput.status === "SUCCESS" ? "text-emerald-400" : "text-rose-400"}>
                {selectedOutput.status} ({selectedOutput.duration_ms ?? 0} ms)
              </span>
            </div>
            <pre className="text-[11px] text-slate-300 font-mono whitespace-pre-wrap max-h-44 overflow-y-auto">
              {selectedOutput.stdout || selectedOutput.stderr || "(no output)"}
            </pre>
          </div>
        )}

        <div className="space-y-1.5 max-h-[260px] overflow-y-auto text-xs">
          {audits.map((a) => (
            <button
              key={a.id}
              onClick={() => setSelectedOutput(a)}
              className="w-full text-left flex items-center justify-between bg-slate-950/60 hover:bg-slate-800/70 border border-slate-800 rounded px-2.5 py-1.5"
            >
              <span className="font-mono text-slate-200">{a.op_id}</span>
              <span className={`font-mono ${a.status === "SUCCESS" ? "text-emerald-400" : "text-rose-400"}`}>
                {a.status}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};

export const ErrorCentreScreen: React.FC<{
  errors: ControlErrorEvent[];
  onReload: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}> = ({ errors, onReload, onActionMessage }) => {
  const [filter, setFilter] = useState<"ALL" | "ACTIVE" | "RESOLVED">("ACTIVE");
  const visible = errors.filter((e) => filter === "ALL" || e.status === filter);

  const handleResolve = async (id: number) => {
    const note = window.prompt("Resolution note:", "Verified and resolved by operator") || "Resolved by operator";
    try {
      await controlClient.resolveError(id, note);
      onActionMessage(`Error #${id} marked RESOLVED.`);
      await onReload();
    } catch (e: any) {
      onActionMessage(`Resolve failed: ${e.message}`, true);
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
          <AlertOctagon className="w-4 h-4 text-rose-400" />
          <span>Error Centre ({visible.length})</span>
        </h2>
        <div className="flex space-x-1 text-xs">
          {(["ACTIVE", "RESOLVED", "ALL"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2.5 py-1 rounded ${filter === f ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-300"}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {visible.length === 0 ? (
          <div className="text-xs text-slate-500 py-8 text-center flex flex-col items-center space-y-1">
            <CheckCircle2 className="w-5 h-5 text-emerald-500" />
            <span>No {filter.toLowerCase()} errors.</span>
          </div>
        ) : (
          visible.map((err) => (
            <div key={err.id} className="bg-slate-950/70 border border-slate-800 rounded-lg p-3 text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${err.severity === "CRITICAL" ? "bg-rose-500/20 text-rose-300" : "bg-amber-500/20 text-amber-300"}`}>
                    {err.severity}
                  </span>
                  <span className="font-mono text-slate-300">{err.category} · {err.component}</span>
                </div>
                {err.status === "ACTIVE" ? (
                  <button onClick={() => handleResolve(err.id)} className="px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded">
                    Resolve
                  </button>
                ) : (
                  <span className="text-emerald-400 font-semibold">RESOLVED</span>
                )}
              </div>
              <div className="text-slate-100 font-medium">{err.message}</div>
              <div className="text-slate-400">Recovery: {err.recommended_recovery}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
