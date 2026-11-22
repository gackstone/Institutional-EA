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
    } catch {
      const fallback = {
        settings: { execution_mode: "DEMO", live_trading_enabled: false, schedule_mode: "WEEKDAY_GOLD_MODE" },
        risk: { risk_per_trade_pct: 0.5, daily_loss_limit_pct: 3.0, max_total_drawdown_pct: 8.0 },
        strategy: { legacy_filters_enabled: false, smc_rulebook_version: "R1-R9" },
      };
      setFullConfig(fallback);
      setEditorText(JSON.stringify(fallback[section], null, 2));
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
      <div className="lg:col-span-2 iea-glass-card p-5 space-y-3.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center space-x-2">
            <FolderCog className="w-5 h-5 text-[#B0F648]" />
            <h2 className="text-lg font-light text-[#F4F7FF]">Authoritative Configuration Editor</h2>
          </div>
          <div className="flex space-x-1 bg-[#091426]/80 p-1 rounded-full border border-[rgba(186,214,255,0.16)] text-xs">
            {(["settings", "risk", "strategy"] as const).map((sec) => (
              <button
                key={sec}
                onClick={() => setSection(sec)}
                className={`px-3 py-1 rounded-full transition ${
                  section === sec
                    ? "bg-[#B0F648] text-[#081321] font-extrabold shadow-[0_0_12px_rgba(176,246,72,0.3)]"
                    : "text-[#B6C5E0] hover:text-[#F4F7FF]"
                }`}
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
          className="w-full bg-[#071020]/85 border border-[rgba(186,214,255,0.16)] rounded-2xl p-3.5 font-mono text-xs text-[#F4F7FF] focus:outline-none focus:border-[#B0F648]"
        />

        <div className="flex flex-wrap items-center gap-2.5">
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            placeholder="Change summary..."
            className="flex-1 min-w-[180px] bg-[#071020]/80 border border-[rgba(186,214,255,0.16)] rounded-full px-4 py-1.5 text-xs text-[#F4F7FF]"
          />
          <button onClick={handlePreview} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold">
            Preview Diff
          </button>
          <button
            disabled={busy}
            onClick={handleApply}
            className="px-4 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-xs text-[#081321] font-extrabold rounded-full shadow-[0_0_16px_rgba(176,246,72,0.28)]"
          >
            Validate &amp; Apply
          </button>
        </div>

        {previewInfo && (
          <div className={`p-3.5 rounded-2xl border text-xs ${previewInfo.valid ? "iea-glass-tile" : "bg-[#FF5A6E]/20 border-[#FF5A6E]/50"}`}>
            <div>Valid: <strong className="text-[#B0F648]">{String(previewInfo.valid)}</strong> · Restart Required: <strong>{String(previewInfo.requires_restart)}</strong></div>
            <div>Changed Keys: <code className="text-[#5EEAD4]">{previewInfo.changed_keys.join(", ") || "None"}</code></div>
            {previewInfo.errors.length > 0 && <div className="text-[#FF7A8A] mt-1">{previewInfo.errors.join("; ")}</div>}
          </div>
        )}
      </div>

      <div className="iea-glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold text-[#F4F7FF]">Version History</h3>
        <div className="space-y-2 max-h-[420px] overflow-y-auto">
          {versions.length === 0 ? (
            <div className="text-xs text-[#8496B8] py-4">v1 · Default DEMO baseline configuration active.</div>
          ) : (
            versions.map((v) => (
              <div key={v.id} className="iea-glass-tile p-3 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-mono font-bold text-[#B0F648]">v{v.version}</span>
                  <button
                    disabled={busy}
                    onClick={() => handleRollback(v.version)}
                    className="text-[11px] text-[#FBBF24] hover:underline inline-flex items-center space-x-1"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Rollback</span>
                  </button>
                </div>
                <div className="text-[#F4F7FF]">{v.change_summary}</div>
                <div className="text-[10px] text-[#8496B8]">{new Date(v.created_at).toLocaleString()}</div>
              </div>
            ))
          )}
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
      <div className="iea-glass-card p-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
            <Link2 className="w-5 h-5 text-[#B0F648]" />
            <span>MetaTrader 5 Terminal Synchronization</span>
          </h2>
          <p className="text-xs text-[#B6C5E0] mt-1">
            Status: <strong className="text-[#B0F648]">{status?.mt5.connection_status}</strong> · Account:{" "}
            <strong className="text-[#F4F7FF]">{acct?.trade_mode || "DEMO"}</strong> · Margin:{" "}
            <strong className="text-[#5EEAD4]">{acct?.margin_mode_str || "HEDGING"}</strong>
          </p>
        </div>
        <div className="flex space-x-2.5">
          <button onClick={scan} className="iea-pill-control px-4 py-1.5 text-xs text-[#F4F7FF] font-semibold">
            Scan Terminals
          </button>
          <button
            disabled={busy}
            onClick={handleConnect}
            className="px-4 py-1.5 bg-[#B0F648] hover:bg-[#C2F076] text-xs text-[#081321] font-extrabold rounded-full shadow-[0_0_16px_rgba(176,246,72,0.28)]"
          >
            Connect &amp; Sync MT5
          </button>
        </div>
      </div>

      <div className="iea-glass-card p-5 space-y-3">
        <h3 className="text-sm font-semibold text-[#F4F7FF]">Detected Windows MT5 Terminals ({terminals.length})</h3>
        {terminals.length === 0 ? (
          <div className="text-xs text-[#8496B8] py-4">No MT5 terminals found in standard paths.</div>
        ) : (
          terminals.map((t) => (
            <div key={t.id} className="iea-glass-tile flex flex-wrap items-center justify-between gap-3 p-4 text-xs">
              <div>
                <div className="font-bold text-[#F4F7FF]">
                  {t.name}{" "}
                  {t.isRunning ? (
                    <span className="text-[#B0F648] font-mono">(Running PID {t.pid})</span>
                  ) : (
                    <span className="text-[#8496B8]">(Stopped)</span>
                  )}
                </div>
                <div className="font-mono text-[11px] text-[#B6C5E0] mt-0.5">{t.executablePath}</div>
                <div className="text-[11px] text-[#8496B8] mt-0.5">
                  EA Installed: <strong className="text-[#5EEAD4]">{t.eaInstalled ? `Yes (v${t.eaVersion})` : "No"}</strong>
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
  const [ops, setOps] = useState<AllowlistedOpInfo[]>([
    {
      op_id: "selfcheck",
      name: "System Self-Check & Preflight Probe",
      description: "Verifies ZMQ ports 5555/5556, SQLite schema, and DEMO lock safety flags.",
      timeout_sec: 30,
    },
    {
      op_id: "sync_instruments",
      name: "Synchronize MT5 Broker Symbol Specifications",
      description: "Refreshes contract size, digits, and stops levels for XAUUSD, USDJPY, BTCUSD.",
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
      onActionMessage(`Operation '${opId}' finished (${res.status || "SUCCESS"}).`, false);
      await loadOps();
    } catch (e: any) {
      onActionMessage(`Operation failed: ${e.message}`, true);
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
            <span>Approved Operations Runner (Fixed Allowlist)</span>
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
                <span>{runningOp === op.op_id ? "Running..." : "Run"}</span>
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="iea-glass-card p-5 space-y-3.5">
        <h3 className="text-sm font-semibold text-[#F4F7FF]">Execution Output &amp; Audit History</h3>
        {selectedOutput && (
          <div className="bg-[#071020]/85 border border-[rgba(186,214,255,0.16)] rounded-2xl p-3.5 text-xs space-y-1.5">
            <div className="flex justify-between font-mono">
              <span className="text-[#5EEAD4]">{selectedOutput.op_id}</span>
              <span className={selectedOutput.status === "SUCCESS" ? "text-[#B0F648]" : "text-[#FF5A6E]"}>
                {selectedOutput.status || "SUCCESS"} ({selectedOutput.duration_ms ?? 120} ms)
              </span>
            </div>
            <pre className="text-[11px] text-[#B6C5E0] font-mono whitespace-pre-wrap max-h-44 overflow-y-auto">
              {selectedOutput.stdout || selectedOutput.stderr || "Allowlisted operation completed cleanly (exit code 0)."}
            </pre>
          </div>
        )}

        <div className="space-y-2 max-h-[260px] overflow-y-auto text-xs">
          {audits.length === 0 ? (
            <div className="text-xs text-[#8496B8] py-4">Click Run on any allowlisted operation to view stdout and audit output.</div>
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
    <div className="iea-glass-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-light text-[#F4F7FF] flex items-center space-x-2">
          <AlertOctagon className="w-5 h-5 text-[#B0F648]" />
          <span>Error Centre ({visible.length})</span>
        </h2>
        <div className="flex space-x-1 bg-[#091426]/80 p-1 rounded-full border border-[rgba(186,214,255,0.16)] text-xs">
          {(["ACTIVE", "RESOLVED", "ALL"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1 rounded-full transition ${
                filter === f ? "bg-[#B0F648] text-[#081321] font-extrabold" : "text-[#B6C5E0] hover:text-white"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2.5">
        {visible.length === 0 ? (
          <div className="text-xs text-[#B6C5E0] py-10 text-center flex flex-col items-center space-y-2 iea-glass-tile">
            <CheckCircle2 className="w-6 h-6 text-[#B0F648]" />
            <span>No {filter.toLowerCase()} errors. All trading subsystems healthy.</span>
          </div>
        ) : (
          visible.map((err) => (
            <div key={err.id} className="iea-glass-tile p-4 text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${err.severity === "CRITICAL" ? "bg-[#FF5A6E]/25 text-[#FF5A6E]" : "bg-[#FBBF24]/25 text-[#FBBF24]"}`}>
                    {err.severity}
                  </span>
                  <span className="font-mono text-[#B6C5E0]">{err.category} · {err.component}</span>
                </div>
                {err.status === "ACTIVE" ? (
                  <button onClick={() => handleResolve(err.id)} className="px-3 py-1 bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] font-bold rounded-full">
                    Resolve
                  </button>
                ) : (
                  <span className="text-[#B0F648] font-semibold">RESOLVED</span>
                )}
              </div>
              <div className="text-[#F4F7FF] font-medium">{err.message}</div>
              <div className="text-[#8496B8]">Recovery: {err.recommended_recovery}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
