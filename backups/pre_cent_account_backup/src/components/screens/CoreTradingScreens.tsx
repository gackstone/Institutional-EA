import React, { useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  Square,
  TrendingUp,
  Zap,
} from "lucide-react";
import { controlClient } from "../../services/ipc";
import { BTCUSDSampleStatus, ControlStatusPayload, RiskDecisionRecord } from "../../types";

interface CommonProps {
  status: ControlStatusPayload | null;
  onRefresh: () => Promise<void>;
  onActionMessage: (msg: string, isError?: boolean) => void;
}

export const DashboardScreen: React.FC<
  CommonProps & {
    onNavigate: (s: any) => void;
    btcStatus?: BTCUSDSampleStatus | null;
    onRefreshBtc?: () => Promise<void>;
  }
> = ({
  status,
  onRefresh,
  onNavigate,
  onActionMessage,
  btcStatus,
  onRefreshBtc,
}) => {
  const acct = status?.mt5.account;
  const eng = status?.engine;
  const rec = status?.mt5.reconciliation;
  const health = status?.health;
  const symbols = Object.values(status?.mt5.symbols || {});
  const [btcBusy, setBtcBusy] = useState(false);

  const runBtc = async (label: string, fn: () => Promise<{ success?: boolean; message?: string }>) => {
    setBtcBusy(true);
    try {
      const res = await fn();
      onActionMessage(`${label}: ${res.message || "OK"}`, res.success === false);
      if (onRefreshBtc) await onRefreshBtc();
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`${label} failed: ${e.message}`, true);
    } finally {
      setBtcBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Top KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">Account Balance</div>
          <div className="text-2xl font-mono font-bold text-slate-100 mt-1">
            ${(acct?.balance ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            #{acct?.account_number || "---"} · {acct?.broker || "Not Connected"}
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">Equity & Free Margin</div>
          <div className="text-2xl font-mono font-bold text-emerald-400 mt-1">
            ${(acct?.equity ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Free: ${(acct?.free_margin ?? 0).toFixed(2)} · Margin Lvl: {(acct?.margin_level ?? 0).toFixed(0)}%
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">Open Positions</div>
          <div className="text-2xl font-mono font-bold text-sky-400 mt-1">
            {status?.mt5.positions.length ?? 0}
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Bot: {rec?.bot_owned_count ?? 0} · Manual: {rec?.manual_count ?? 0} · Other EA: {rec?.other_ea_count ?? 0}
          </div>
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="text-[11px] uppercase tracking-wider text-slate-400">Safety & Health</div>
          <div className="flex items-center space-x-2 mt-1">
            <span
              className={`text-lg font-bold ${
                health?.overall === "HEALTHY"
                  ? "text-emerald-400"
                  : health?.overall === "DEGRADED"
                  ? "text-amber-400"
                  : "text-rose-400"
              }`}
            >
              {health?.overall || "UNKNOWN"}
            </span>
          </div>
          <div className="text-xs text-slate-400 mt-1">
            Active Errors: {health?.active_error_count ?? 0} · Mode: {eng?.operating_mode || "DEMO_SCALPING"}
          </div>
        </div>
      </div>

      {/* Banners for STOP.flag / Netting / Unprotected */}
      {eng?.stop_flag_active && (
        <div className="bg-rose-950/60 border border-rose-500/40 rounded-xl p-3 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0" />
            <div>
              <div className="text-sm font-semibold text-rose-200">EMERGENCY STOP ACTIVE (STOP.flag)</div>
              <div className="text-xs text-rose-300/80">All new order entries are blocked until explicitly cleared.</div>
            </div>
          </div>
          <button
            onClick={() => onNavigate("engine")}
            className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg"
          >
            Manage Stop
          </button>
        </div>
      )}

      {acct?.netting_observe_only && (
        <div className="bg-amber-950/50 border border-amber-500/40 rounded-xl p-3 flex items-center space-x-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0" />
          <div className="text-xs text-amber-200">
            MT5 account is in <strong>NETTING</strong> margin mode. Multi-position hedging baskets are restricted to observe-only safety mode.
          </div>
        </div>
      )}

      {/* Market Watch & Engine Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <TrendingUp className="w-4 h-4 text-sky-400" />
              <span>Active Instruments (Gold & BTC)</span>
            </h3>
            <button onClick={() => onRefresh()} className="text-xs text-sky-400 hover:text-sky-300 flex items-center space-x-1">
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Sync</span>
            </button>
          </div>
          {symbols.length === 0 ? (
            <div className="text-xs text-slate-500 py-6 text-center">Connect MT5 to stream live Bid/Ask & Spread specs.</div>
          ) : (
            <div className="space-y-2">
              {symbols.map((sym) => (
                <div key={sym.symbol} className="flex items-center justify-between bg-slate-950/70 border border-slate-800/80 rounded-lg px-3 py-2">
                  <div>
                    <div className="text-sm font-mono font-bold text-slate-100">{sym.symbol}</div>
                    <div className="text-[11px] text-slate-500">Spread: {sym.spread_points} pts · StopsLvl: {sym.stops_level}</div>
                  </div>
                  <div className="text-right font-mono">
                    <div className="text-xs text-emerald-400">Bid: {sym.bid.toFixed(sym.digits)}</div>
                    <div className="text-xs text-rose-400">Ask: {sym.ask.toFixed(sym.digits)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-emerald-400" />
              <span>Engine & Bridge Telemetry</span>
            </h3>
            <button onClick={() => onNavigate("engine")} className="text-xs text-sky-400 hover:text-sky-300">
              Controls →
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="bg-slate-950/70 rounded-lg p-2.5 border border-slate-800/80">
              <div className="text-slate-500">Engine State</div>
              <div className="font-mono font-bold text-slate-100 mt-0.5">{eng?.engine_state || "STOPPED"}</div>
            </div>
            <div className="bg-slate-950/70 rounded-lg p-2.5 border border-slate-800/80">
              <div className="text-slate-500">MT5 Sync</div>
              <div className="font-mono font-bold text-slate-100 mt-0.5">{status?.mt5.connection_status || "DISCONNECTED"}</div>
            </div>
            <div className="bg-slate-950/70 rounded-lg p-2.5 border border-slate-800/80">
              <div className="text-slate-500">Bridge PID</div>
              <div className="font-mono text-slate-200 mt-0.5">{eng?.bridge_pid ?? "Not running"}</div>
            </div>
            <div className="bg-slate-950/70 rounded-lg p-2.5 border border-slate-800/80">
              <div className="text-slate-500">Engine PID</div>
              <div className="font-mono text-slate-200 mt-0.5">{eng?.engine_pid ?? "Not running"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* BTCUSD Sample Trading Control Section */}
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
              <Zap className="w-4 h-4 text-amber-400" />
              <span>BTCUSD DEMO Sample Trading ({btcStatus?.broker_symbol || "BTCUSD.m"})</span>
            </h3>
            <p className="text-xs text-slate-400">
              State: <strong className="text-sky-400">{btcStatus?.state || "DISABLED"}</strong> · MT5:{" "}
              <strong>{btcStatus?.mt5_connection || status?.mt5.connection_status || "DISCONNECTED"}</strong> · Telegram:{" "}
              <strong>{btcStatus?.telegram.enabled ? `Enabled (${btcStatus.telegram.delivery_count} sent)` : "Disabled"}</strong>
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <button disabled={btcBusy} onClick={() => runBtc("Enable BTCUSD", () => controlClient.enableBtcSample())} className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded">
              Enable
            </button>
            <button disabled={btcBusy} onClick={() => runBtc("Disable BTCUSD", () => controlClient.disableBtcSample())} className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded">
              Disable
            </button>
            <button disabled={btcBusy} onClick={() => runBtc("Start Sample Trading", () => controlClient.startBtcSample())} className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded">
              Start Sample
            </button>
            <button
              disabled={btcBusy}
              onClick={() => runBtc(btcStatus?.paused ? "Resume Sample" : "Pause Sample", () => (btcStatus?.paused ? controlClient.resumeBtcSample() : controlClient.pauseBtcSample()))}
              className="px-2.5 py-1 bg-amber-600 hover:bg-amber-500 text-white rounded"
            >
              {btcStatus?.paused ? "Resume" : "Pause"}
            </button>
            <button disabled={btcBusy} onClick={() => runBtc("Stop Sample", () => controlClient.stopBtcSample())} className="px-2.5 py-1 bg-rose-600 hover:bg-rose-500 text-white rounded">
              Stop
            </button>
            <button disabled={btcBusy} onClick={() => runBtc("Test Telegram", () => controlClient.testTelegram(false))} className="px-2.5 py-1 bg-sky-700 hover:bg-sky-600 text-white rounded">
              Test TG
            </button>
            <button disabled={btcBusy} onClick={() => runBtc("Send Test TG", () => controlClient.testTelegram(true))} className="px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-white rounded">
              Send Test TG
            </button>
            <button disabled={btcBusy} onClick={() => runBtc("Sync MT5", () => controlClient.syncMT5(["BTCUSD.m", "XAUUSD"]))} className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded">
              Sync MT5
            </button>
            <button onClick={() => onNavigate("history")} className="px-2.5 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded">
              BTC History
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5">
            <div className="text-slate-500">Live Bid / Ask</div>
            <div className="font-mono text-slate-100 mt-0.5">{btcStatus?.bid ? `${btcStatus.bid.toFixed(2)} / ${btcStatus.ask.toFixed(2)}` : "-"}</div>
            <div className="text-[10px] text-slate-500">Spread: {btcStatus?.spread_points ?? 0} pts</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5">
            <div className="text-slate-500">Open BTC / Floating</div>
            <div className="font-mono text-slate-100 mt-0.5">{btcStatus?.open_positions.length ?? 0} pos · ${(btcStatus?.floating_pnl ?? 0).toFixed(2)}</div>
            <div className="text-[10px] text-slate-500">Daily BTC P/L: ${(btcStatus?.daily_pnl ?? 0).toFixed(2)}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5">
            <div className="text-slate-500">Last Signal / Exec</div>
            <div className="font-mono text-slate-200 truncate mt-0.5">{btcStatus?.last_execution_result || btcStatus?.last_check_note || "Monitoring"}</div>
          </div>
          <div className="bg-slate-950/70 border border-slate-800 rounded-lg p-2.5">
            <div className="text-slate-500">Last Telegram Alert</div>
            <div className="font-mono text-slate-200 truncate mt-0.5">{btcStatus?.telegram.last_notification?.status || "None"}</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export const EngineScreen: React.FC<CommonProps> = ({ status, onRefresh, onActionMessage }) => {
  const [busy, setBusy] = useState(false);
  const [dryRunChoice, setDryRunChoice] = useState<boolean>(status?.engine.dry_run ?? true);
  const eng = status?.engine;

  const runAction = async (label: string, fn: () => Promise<{ success?: boolean; message?: string }>) => {
    setBusy(true);
    try {
      const res = await fn();
      onActionMessage(`${label}: ${res.message || "Completed"}`, res.success === false);
      await onRefresh();
    } catch (e: any) {
      onActionMessage(`${label} failed: ${e.message}`, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-base font-bold text-slate-100 flex items-center space-x-2">
              <Cpu className="w-5 h-5 text-sky-400" />
              <span>Trading Engine Lifecycle Controller</span>
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Controls the single authoritative <code>scripts/start_bot.py</code> &amp; <code>scripts/run_bridge_server.py</code> processes.
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <label className="flex items-center space-x-2 text-xs text-slate-300 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
              <input
                type="checkbox"
                checked={dryRunChoice}
                onChange={(e) => setDryRunChoice(e.target.checked)}
                className="rounded border-slate-700"
              />
              <span>Dry-Run Mode</span>
            </label>
          </div>
        </div>

        <div className="flex flex-wrap gap-2.5 mt-5">
          <button
            disabled={busy || eng?.engine_running}
            onClick={() => runAction("Start Engine", () => controlClient.startEngine(dryRunChoice))}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
          >
            <Play className="w-4 h-4" />
            <span>Start Engine</span>
          </button>

          <button
            disabled={busy}
            onClick={() =>
              runAction(
                eng?.pause_flag_active ? "Resume Entries" : "Pause Entries",
                () => (eng?.pause_flag_active ? controlClient.resumeEntries() : controlClient.pauseEntries())
              )
            }
            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
          >
            <Pause className="w-4 h-4" />
            <span>{eng?.pause_flag_active ? "Resume Entries" : "Pause Entries"}</span>
          </button>

          <button
            disabled={busy || !eng?.engine_running}
            onClick={() => runAction("Stop Engine", () => controlClient.stopEngine())}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
          >
            <Square className="w-4 h-4" />
            <span>Stop Engine</span>
          </button>

          <button
            disabled={busy}
            onClick={() => runAction("Restart Engine", () => controlClient.restartEngine())}
            className="px-4 py-2 bg-sky-600 hover:bg-sky-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Restart Engine</span>
          </button>

          {!eng?.stop_flag_active ? (
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm("Engage Emergency STOP.flag? This immediately halts all new order entries.")) {
                  runAction("Emergency Stop", () => controlClient.emergencyStop(false, true));
                }
              }}
              className="px-4 py-2 bg-rose-600 hover:bg-rose-500 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5 ml-auto"
            >
              <ShieldAlert className="w-4 h-4" />
              <span>Emergency Stop</span>
            </button>
          ) : (
            <button
              disabled={busy}
              onClick={() => {
                if (window.confirm("Clear STOP.flag kill switch? Ensure MT5 terminal and open positions are verified first.")) {
                  runAction("Clear STOP.flag", () => controlClient.clearEmergencyStop(true));
                }
              }}
              className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5 ml-auto"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Clear STOP.flag</span>
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs space-y-1.5">
          <div className="text-slate-400">Process Supervision</div>
          <div>Bridge Running: <span className="font-mono text-slate-100">{String(eng?.bridge_running ?? false)}</span> (PID {eng?.bridge_pid ?? "-"})</div>
          <div>Engine Running: <span className="font-mono text-slate-100">{String(eng?.engine_running ?? false)}</span> (PID {eng?.engine_pid ?? "-"})</div>
        </div>
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs space-y-1.5">
          <div className="text-slate-400">Safety Flags</div>
          <div>STOP.flag: <span className={`font-mono font-bold ${eng?.stop_flag_active ? "text-rose-400" : "text-emerald-400"}`}>{eng?.stop_flag_active ? "ACTIVE" : "CLEAR"}</span></div>
          <div>state/PAUSE: <span className={`font-mono font-bold ${eng?.pause_flag_active ? "text-amber-400" : "text-emerald-400"}`}>{eng?.pause_flag_active ? "PAUSED" : "ACTIVE"}</span></div>
        </div>
        <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 text-xs space-y-1.5">
          <div className="text-slate-400">Execution Mode Lock</div>
          <div>Operating Mode: <span className="font-mono text-sky-400">{eng?.operating_mode || "DEMO_SCALPING"}</span></div>
          <div>Live Trading: <span className="font-mono text-emerald-400 font-bold">LOCKED (DEMO ONLY)</span></div>
        </div>
      </div>
    </div>
  );
};

export const MarketWatchScreen: React.FC<CommonProps> = ({ status, onRefresh, onActionMessage }) => {
  const [syncing, setSyncing] = useState(false);
  const symbols = Object.values(status?.mt5.symbols || {});

  const handleSync = async () => {
    setSyncing(true);
    try {
      await controlClient.syncMT5();
      await onRefresh();
      onActionMessage("Market Watch synchronized with MT5.");
    } catch (e: any) {
      onActionMessage(`Market sync failed: ${e.message}`, true);
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
          <Activity className="w-4 h-4 text-sky-400" />
          <span>Live Market Watch &amp; Broker Specifications</span>
        </h2>
        <button
          disabled={syncing}
          onClick={handleSync}
          className="px-3 py-1.5 bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold rounded-lg flex items-center space-x-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? "animate-spin" : ""}`} />
          <span>Sync Quotes</span>
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3">Bid</th>
              <th className="py-2 pr-3">Ask</th>
              <th className="py-2 pr-3">Spread (pts)</th>
              <th className="py-2 pr-3">Digits</th>
              <th className="py-2 pr-3">Min / Max / Step Lot</th>
              <th className="py-2">Stops Level</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70 font-mono">
            {symbols.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500 font-sans">
                  No symbol quotes cached yet. Connect MT5 terminal and click Sync Quotes.
                </td>
              </tr>
            ) : (
              symbols.map((s) => (
                <tr key={s.symbol} className="hover:bg-slate-800/40">
                  <td className="py-2.5 pr-3 font-bold text-slate-100">{s.symbol}</td>
                  <td className="py-2.5 pr-3 text-emerald-400">{s.bid.toFixed(s.digits)}</td>
                  <td className="py-2.5 pr-3 text-rose-400">{s.ask.toFixed(s.digits)}</td>
                  <td className="py-2.5 pr-3 text-amber-300">{s.spread_points}</td>
                  <td className="py-2.5 pr-3 text-slate-300">{s.digits}</td>
                  <td className="py-2.5 pr-3 text-slate-300">{s.volume_min} / {s.volume_max} / {s.volume_step}</td>
                  <td className="py-2.5 text-slate-300">{s.stops_level}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const SignalsScreen: React.FC<{ decisions: RiskDecisionRecord[]; onReload: () => Promise<void> }> = ({
  decisions,
  onReload,
}) => {
  return (
    <div className="space-y-4">
      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <span>Unfiltered Signal Pipeline &amp; Risk Authorization</span>
          </h2>
          <p className="text-xs text-slate-400 mt-1">
            Strategy layer runs unfiltered (<code>LEGACY_FILTERS_ENABLED=false</code>). All entries pass directly to independent <code>PortfolioRiskEngine</code>.
          </p>
        </div>
        <button onClick={() => onReload()} className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-xs text-slate-200 rounded-lg">
          Refresh
        </button>
      </div>

      <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-4 overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-400 border-b border-slate-800">
            <tr>
              <th className="py-2 pr-3">Time</th>
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3">Direction</th>
              <th className="py-2 pr-3">Decision</th>
              <th className="py-2 pr-3">Lot</th>
              <th className="py-2 pr-3">Risk %</th>
              <th className="py-2">Reason</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/70">
            {decisions.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-8 text-center text-slate-500">
                  No signal/risk authorization events recorded yet.
                </td>
              </tr>
            ) : (
              decisions.map((d) => (
                <tr key={d.id}>
                  <td className="py-2 pr-3 font-mono text-slate-400">{new Date(d.created_at).toLocaleTimeString()}</td>
                  <td className="py-2 pr-3 font-mono font-bold text-slate-100">{d.symbol}</td>
                  <td className="py-2 pr-3 font-mono text-slate-200">{d.direction}</td>
                  <td className="py-2 pr-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${d.approved ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"}`}>
                      {d.approved ? "APPROVED" : "BLOCKED"}
                    </span>
                  </td>
                  <td className="py-2 pr-3 font-mono">{d.lot_size.toFixed(2)}</td>
                  <td className="py-2 pr-3 font-mono">{d.risk_pct.toFixed(2)}%</td>
                  <td className="py-2 text-slate-300">{d.reason}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
