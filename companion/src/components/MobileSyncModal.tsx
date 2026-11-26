import React, { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import {
  AlertCircle,
  CheckCircle,
  Cloud,
  RefreshCw,
  Shield,
  Smartphone,
  Trash2,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { controlClient } from "../services/ipc";

interface MobileDevice {
  deviceId?: string;
  id?: string;
  deviceName?: string;
  device_name?: string;
  platform: string;
  pairedAt?: string;
  paired_at?: string;
  lastSeenAt?: string;
  last_seen_at?: string;
}

interface PendingCloudSession {
  id: string;
  status: string;
  pending_android_name?: string | null;
  pending_android_platform?: string | null;
  expires_at?: string;
}

interface CloudPairingState {
  sessionId: string;
  code: string;
  expiresAt: number;
  companionName: string;
  qrPayload: Record<string, unknown>;
}

interface MobileSyncStatus {
  enabled: boolean;
  port: number;
  hosts: string[];
  primaryHost: string;
  companionName: string;
  schemaVersion: string;
  readOnlyEnforced: boolean;
  pairingCode: string | null;
  pairingCodeExpiresAt: number | null;
  qrPayload: Record<string, unknown> | null;
  devices: MobileDevice[];
}

interface MobileSyncModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const electronCloud = () => (window as any)?.electronAPI;

function formatFriendlyCloudPairingError(raw: unknown): { message: string; showLanHint: boolean } {
  const text = raw instanceof Error ? raw.message : String(raw || "");
  if (/requested function was not found|not_found|404/i.test(text)) {
    return {
      message:
        "Cloud Pairing service is not deployed on your Supabase project yet. Deploy the mobile-pairing and mobile-sync Edge Functions, or switch to Local Wi-Fi Fallback.",
      showLanHint: true,
    };
  }
  if (/401|unauthorized|not signed in|sign in/i.test(text)) {
    return {
      message: "Your cloud session expired. Sign out and sign back in, or use Local Wi-Fi Fallback.",
      showLanHint: true,
    };
  }
  if (/429|rate_limited|too many/i.test(text)) {
    return {
      message: "Too many pairing attempts. Wait a minute and click Regenerate.",
      showLanHint: false,
    };
  }
  if (/failed to fetch|network|enotfound|etimedout|offline/i.test(text)) {
    return {
      message: "Cannot reach Cloud Pairing right now. Check your internet connection or use Local Wi-Fi Fallback.",
      showLanHint: true,
    };
  }
  return {
    message: text || "Cloud pairing request failed. Try again or use Local Wi-Fi Fallback.",
    showLanHint: true,
  };
}

export const MobileSyncModal: React.FC<MobileSyncModalProps> = ({ isOpen, onClose }) => {
  const [tab, setTab] = useState<"cloud" | "lan">("cloud");

  // Cloud cross-network pairing state
  const [cloudSession, setCloudSession] = useState<CloudPairingState | null>(null);
  const [cloudQrUrl, setCloudQrUrl] = useState<string | null>(null);
  const [cloudSecondsLeft, setCloudSecondsLeft] = useState<number>(0);
  const [pendingApproval, setPendingApproval] = useState<PendingCloudSession | null>(null);
  const [cloudDevices, setCloudDevices] = useState<MobileDevice[]>([]);
  const [cloudBusy, setCloudBusy] = useState(false);
  const [cloudError, setCloudError] = useState<string | null>(null);
  const [cloudSuccess, setCloudSuccess] = useState<string | null>(null);

  // Optional LAN fallback state
  const [status, setStatus] = useState<MobileSyncStatus | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number>(0);

  const loadCloudState = useCallback(async () => {
    const api = electronCloud();
    if (!api?.cloudMobilePairing) return;
    try {
      const [devRes, pendRes] = await Promise.all([
        api.cloudMobilePairing("list"),
        api.cloudMobilePairing("pending"),
      ]);
      if (devRes?.ok && Array.isArray(devRes.devices)) {
        setCloudDevices(devRes.devices);
      }
      if (pendRes?.ok && Array.isArray(pendRes.sessions)) {
        const waiting = pendRes.sessions.find(
          (s: PendingCloudSession) => s.status === "awaiting_approval"
        );
        setPendingApproval(waiting || null);
      }
    } catch {
      // Keep quiet on background poll failure
    }
  }, []);

  const loadLanStatus = useCallback(async () => {
    try {
      const res = await controlClient.getMobileSyncStatus();
      setStatus(res);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load Local Wi-Fi sync status");
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    loadCloudState();
    loadLanStatus();
    const timer = setInterval(() => {
      loadCloudState();
      if (tab === "lan") loadLanStatus();
    }, 3000);
    return () => clearInterval(timer);
  }, [isOpen, tab, loadCloudState, loadLanStatus]);

  useEffect(() => {
    if (!cloudSession?.qrPayload) {
      setCloudQrUrl(null);
      return;
    }
    QRCode.toDataURL(JSON.stringify(cloudSession.qrPayload), {
      width: 220,
      margin: 2,
      color: { dark: "#0D1117", light: "#FFFFFF" },
    })
      .then((url) => setCloudQrUrl(url))
      .catch(() => setCloudQrUrl(null));
  }, [cloudSession?.qrPayload]);

  useEffect(() => {
    if (!cloudSession?.expiresAt) {
      setCloudSecondsLeft(0);
      return;
    }
    const tick = () => {
      const rem = Math.max(0, cloudSession.expiresAt - Math.floor(Date.now() / 1000));
      setCloudSecondsLeft(rem);
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [cloudSession?.expiresAt]);

  useEffect(() => {
    if (!status?.qrPayload) {
      setQrDataUrl(null);
      return;
    }
    QRCode.toDataURL(JSON.stringify(status.qrPayload), {
      width: 220,
      margin: 2,
      color: { dark: "#0D1117", light: "#FFFFFF" },
    })
      .then((url) => setQrDataUrl(url))
      .catch(() => setQrDataUrl(null));
  }, [status?.qrPayload]);

  useEffect(() => {
    if (!status?.pairingCodeExpiresAt) {
      setSecondsLeft(0);
      return;
    }
    const update = () => {
      const rem = Math.max(0, status.pairingCodeExpiresAt! - Math.floor(Date.now() / 1000));
      setSecondsLeft(rem);
    };
    update();
    const iv = setInterval(update, 1000);
    return () => clearInterval(iv);
  }, [status?.pairingCodeExpiresAt]);

  if (!isOpen) return null;

  const handleStartCloudPairing = async () => {
    const api = electronCloud();
    if (!api?.cloudMobilePairing) {
      setCloudError("Cloud pairing requires the Windows Companion desktop app.");
      return;
    }
    setCloudBusy(true);
    setCloudError(null);
    setCloudSuccess(null);
    try {
      const res = await api.cloudMobilePairing("create");
      if (!res?.ok) {
        setCloudError(formatFriendlyCloudPairingError(res?.error).message);
        return;
      }
      setCloudSession({
        sessionId: res.sessionId,
        code: res.code,
        expiresAt: res.expiresAt,
        companionName: res.companionName,
        qrPayload: res.qrPayload,
      });
    } catch (e: unknown) {
      setCloudError(formatFriendlyCloudPairingError(e).message);
    } finally {
      setCloudBusy(false);
    }
  };

  const handleCancelCloudPairing = async () => {
    const api = electronCloud();
    if (api?.cloudMobilePairing && cloudSession) {
      await api.cloudMobilePairing("cancel", { sessionId: cloudSession.sessionId }).catch(() => {});
    }
    setCloudSession(null);
    setPendingApproval(null);
  };

  const handleApproveAndroid = async (sessionId: string) => {
    const api = electronCloud();
    if (!api?.cloudMobilePairing) return;
    setCloudBusy(true);
    setCloudError(null);
    try {
      const res = await api.cloudMobilePairing("approve", { sessionId });
      if (!res?.ok) {
        setCloudError(res?.error || "Approval failed.");
      } else {
        setCloudSuccess(`Approved "${res.device?.device_name || "Android Device"}" (Read-Only).`);
        setPendingApproval(null);
        setCloudSession(null);
        await loadCloudState();
      }
    } finally {
      setCloudBusy(false);
    }
  };

  const handleRejectAndroid = async (sessionId: string) => {
    const api = electronCloud();
    if (!api?.cloudMobilePairing) return;
    setCloudBusy(true);
    try {
      await api.cloudMobilePairing("reject", { sessionId });
      setPendingApproval(null);
      await loadCloudState();
    } finally {
      setCloudBusy(false);
    }
  };

  const handleRevokeCloudDevice = async (deviceId: string) => {
    const api = electronCloud();
    if (!api?.cloudMobilePairing) return;
    setCloudBusy(true);
    try {
      await api.cloudMobilePairing("revoke", { deviceId });
      await loadCloudState();
    } finally {
      setCloudBusy(false);
    }
  };

  const handleToggleLan = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = status?.enabled
        ? await controlClient.disableMobileSync()
        : await controlClient.enableMobileSync();
      setStatus(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to toggle Local Wi-Fi sync");
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshLanCode = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await controlClient.generateMobilePairingCode();
      setStatus(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to generate pairing code");
    } finally {
      setLoading(false);
    }
  };

  const handleRevokeLan = async (deviceId: string) => {
    setLoading(true);
    try {
      const res = await controlClient.revokeMobileDevice(deviceId);
      if (res?.status) setStatus(res.status);
      else await loadLanStatus();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to revoke device");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-[var(--overlay-bg)] backdrop-blur-sm flex items-center justify-center z-50 p-4 select-none">
      <div className="bg-iea-card border border-iea-borderSubtle rounded-xl w-full max-w-lg overflow-hidden shadow-2xl text-iea-textPrimary">
        {/* Header */}
        <div className="px-5 py-4 border-b border-iea-borderSubtle flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-iea-accentSoft text-iea-accent border border-iea-accentBorder">
              <Smartphone className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-sm">Android Read-Only Pairing</h3>
              <p className="text-[11px] text-iea-textSecondary">
                Works across Wi-Fi, 4G/5G &amp; different networks · Strictly read-only
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-md text-iea-textSecondary hover:text-iea-textPrimary transition"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Mode Tabs: Cloud (Primary) vs Optional Local Wi-Fi Fallback */}
        <div className="px-5 pt-3 flex gap-2 border-b border-iea-borderSubtle pb-3">
          <button
            type="button"
            onClick={() => setTab("cloud")}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold inline-flex items-center gap-1.5 transition ${
              tab === "cloud"
                ? "bg-iea-accent text-white"
                : "bg-iea-inset text-iea-textSecondary hover:text-iea-textPrimary"
            }`}
          >
            <Cloud className="w-3.5 h-3.5" />
            <span>Cloud Pairing (Recommended)</span>
          </button>
          <button
            type="button"
            onClick={() => setTab("lan")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold inline-flex items-center gap-1.5 transition ${
              tab === "lan"
                ? "bg-iea-accent text-white"
                : "bg-iea-inset text-iea-textSecondary hover:text-iea-textPrimary"
            }`}
          >
            <Wifi className="w-3.5 h-3.5" />
            <span>Local Wi-Fi Fallback</span>
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 max-h-[75vh] overflow-y-auto">
          {tab === "cloud" ? (
            <>
              {cloudError && (
                <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400 flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2">
                    <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                    <span>{cloudError}</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => setTab("lan")}
                    className="shrink-0 underline font-semibold text-amber-300 hover:text-amber-200"
                  >
                    Use Local Wi-Fi Fallback
                  </button>
                </div>
              )}

              {cloudSuccess && (
                <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-400 flex items-center gap-2">
                  <CheckCircle className="w-4 h-4 shrink-0" />
                  <span>{cloudSuccess}</span>
                </div>
              )}

              {/* Incoming Android Device Approval Prompt */}
              {pendingApproval && (
                <div
                  data-testid="cloud-approval-card"
                  className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/40 space-y-3"
                >
                  <div className="text-xs font-bold text-amber-300">
                    New Android Device Requesting Read-Only Access
                  </div>
                  <div className="text-xs text-iea-textPrimary">
                    Device: <span className="font-bold">{pendingApproval.pending_android_name || "Android Device"}</span>{" "}
                    ({pendingApproval.pending_android_platform || "android"})
                  </div>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={cloudBusy}
                      onClick={() => handleApproveAndroid(pendingApproval.id)}
                      className="px-3.5 py-1.5 rounded-lg bg-emerald-500 hover:opacity-90 text-white text-xs font-bold"
                    >
                      Approve Device
                    </button>
                    <button
                      type="button"
                      disabled={cloudBusy}
                      onClick={() => handleRejectAndroid(pendingApproval.id)}
                      className="px-3.5 py-1.5 rounded-lg bg-red-500/20 text-red-300 border border-red-500/30 text-xs font-semibold"
                    >
                      Decline
                    </button>
                  </div>
                </div>
              )}

              {/* Primary CTA or Active QR / 6-Digit Code */}
              {!cloudSession ? (
                <div className="iea-inset p-4 rounded-xl space-y-3 text-center">
                  <p className="text-xs text-iea-textSecondary">
                    Pair your Android phone securely over the cloud — no shared Wi-Fi, IP address, or port forwarding required.
                  </p>
                  <button
                    type="button"
                    disabled={cloudBusy}
                    onClick={handleStartCloudPairing}
                    data-testid="modal-pair-new-android-btn"
                    className="px-4 py-2.5 rounded-xl bg-iea-accent hover:bg-iea-accentHover text-white text-xs font-bold inline-flex items-center gap-2 transition"
                  >
                    <Smartphone className="w-4 h-4" />
                    <span>{cloudBusy ? "Creating Pairing Session..." : "PAIR NEW ANDROID DEVICE"}</span>
                  </button>
                </div>
              ) : (
                <div className="iea-inset p-4 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold">Scan QR or Enter 6-Digit Code on Android</span>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={handleStartCloudPairing}
                        disabled={cloudBusy}
                        className="text-[11px] font-semibold text-iea-accent flex items-center gap-1 hover:underline"
                      >
                        <RefreshCw className="w-3.5 h-3.5" />
                        Regenerate
                      </button>
                      <button
                        type="button"
                        onClick={handleCancelCloudPairing}
                        className="text-[11px] font-semibold text-iea-textSecondary hover:text-iea-danger"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row items-center gap-4">
                    <div className="bg-white p-2 rounded-lg shrink-0">
                      {cloudQrUrl ? (
                        <img src={cloudQrUrl} alt="Cloud Pairing QR Code" className="w-44 h-44" />
                      ) : (
                        <div className="w-44 h-44 flex items-center justify-center text-xs text-gray-500">
                          Generating QR...
                        </div>
                      )}
                    </div>

                    <div className="flex-1 space-y-2 text-xs">
                      <div>
                        <div className="text-[10px] uppercase tracking-wider text-iea-textSecondary">
                          One-Time 6-Digit Code
                        </div>
                        <div className="font-mono text-2xl font-bold tracking-[0.25em] text-iea-accent mt-0.5">
                          {cloudSession.code}
                        </div>
                        <div className="text-[11px] text-iea-textSecondary mt-0.5">
                          {cloudSecondsLeft > 0
                            ? `Expires in ${Math.floor(cloudSecondsLeft / 60)}:${String(cloudSecondsLeft % 60).padStart(2, "0")}`
                            : "Expired — click Regenerate"}
                        </div>
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px] text-emerald-400">
                        <Shield className="w-3.5 h-3.5" />
                        <span>Read-only enforced server-side &amp; in DB</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Paired Cloud Android Devices */}
              <div className="space-y-2">
                <div className="text-xs font-bold">Paired Android Devices ({cloudDevices.length})</div>
                {cloudDevices.length === 0 ? (
                  <div className="iea-inset p-3 rounded-xl text-xs text-iea-textSecondary">
                    No Android devices paired via Cloud yet.
                  </div>
                ) : (
                  cloudDevices.map((d) => {
                    const id = d.id || d.deviceId || "";
                    return (
                      <div
                        key={id}
                        className="iea-inset px-3.5 py-2.5 rounded-xl flex items-center justify-between gap-2 text-xs"
                      >
                        <div>
                          <div className="font-bold text-iea-textPrimary">
                            {d.device_name || d.deviceName || "Android Device"}
                          </div>
                          <div className="text-[10px] font-mono text-iea-textSecondary">
                            {d.platform} · Read-Only · Paired {d.paired_at ? new Date(d.paired_at).toLocaleDateString() : "—"}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleRevokeCloudDevice(id)}
                          disabled={cloudBusy}
                          className="px-2.5 py-1 rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 inline-flex items-center gap-1 text-[11px] font-semibold"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Revoke</span>
                        </button>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          ) : (
            /* Optional Local Wi-Fi Fallback */
            <>
              <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5">
                  {status?.enabled ? (
                    <Wifi className="w-5 h-5 text-iea-profit" />
                  ) : (
                    <WifiOff className="w-5 h-5 text-iea-textSecondary" />
                  )}
                  <div>
                    <div className="text-xs font-bold">
                      {status?.enabled ? "Local Wi-Fi Sync Enabled" : "Local Wi-Fi Sync Disabled"}
                    </div>
                    <div className="text-[11px] text-iea-textSecondary">
                      {status?.enabled
                        ? `Listening on ${status.primaryHost}:${status.port} (GET/SSE only)`
                        : "Optional fallback when both devices share the same local Wi-Fi."}
                    </div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleToggleLan}
                  disabled={loading}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition ${
                    status?.enabled
                      ? "bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25"
                      : "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-500/30"
                  }`}
                >
                  {loading ? "Working..." : status?.enabled ? "Turn Off" : "Enable"}
                </button>
              </div>

              {error && (
                <div className="p-2.5 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400 flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {status?.enabled && (
                <div className="iea-inset p-4 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold">Local Wi-Fi QR &amp; Code</span>
                    <button
                      type="button"
                      onClick={handleRefreshLanCode}
                      disabled={loading}
                      className="text-[11px] font-semibold text-iea-accent flex items-center gap-1 hover:underline"
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                      New Code
                    </button>
                  </div>

                  <div className="flex flex-col sm:flex-row items-center gap-4">
                    <div className="bg-white p-2 rounded-lg shrink-0">
                      {qrDataUrl ? (
                        <img src={qrDataUrl} alt="Local Wi-Fi Pairing QR Code" className="w-40 h-40" />
                      ) : (
                        <div className="w-40 h-40 flex items-center justify-center text-xs text-gray-500">
                          Click New Code
                        </div>
                      )}
                    </div>
                    <div className="flex-1 space-y-2 text-xs">
                      <div className="font-mono text-xl font-bold tracking-[0.2em] text-iea-accent">
                        {status.pairingCode || "------"}
                      </div>
                      <div className="text-[11px] text-iea-textSecondary">
                        {secondsLeft > 0
                          ? `Expires in ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}`
                          : "Expired"}
                      </div>
                      <div className="text-[11px] font-mono text-iea-textSecondary">
                        LAN: {status.primaryHost}:{status.port}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {status?.devices && status.devices.length > 0 && (
                <div className="space-y-2">
                  <div className="text-xs font-bold">Local Wi-Fi Devices ({status.devices.length})</div>
                  {status.devices.map((d) => (
                    <div
                      key={d.deviceId}
                      className="iea-inset px-3.5 py-2 rounded-xl flex items-center justify-between text-xs"
                    >
                      <span>{d.deviceName}</span>
                      <button
                        type="button"
                        onClick={() => handleRevokeLan(d.deviceId || "")}
                        className="text-red-400 hover:underline text-[11px]"
                      >
                        Revoke
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
