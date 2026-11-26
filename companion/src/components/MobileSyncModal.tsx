import React, { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import {
  AlertCircle,
  CheckCircle,
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
  deviceId: string;
  deviceName: string;
  platform: string;
  pairedAt: string;
  lastSeenAt: string;
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

export const MobileSyncModal: React.FC<MobileSyncModalProps> = ({ isOpen, onClose }) => {
  const [status, setStatus] = useState<MobileSyncStatus | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number>(0);

  const loadStatus = useCallback(async () => {
    try {
      const res = await controlClient.getMobileSyncStatus();
      setStatus(res);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load Mobile Sync status");
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    loadStatus();
    const timer = setInterval(loadStatus, 5000);
    return () => clearInterval(timer);
  }, [isOpen, loadStatus]);

  useEffect(() => {
    if (!status?.qrPayload) {
      setQrDataUrl(null);
      return;
    }
    const payloadStr = JSON.stringify(status.qrPayload);
    QRCode.toDataURL(payloadStr, {
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

  const handleToggle = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = status?.enabled
        ? await controlClient.disableMobileSync()
        : await controlClient.enableMobileSync();
      setStatus(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to toggle Mobile Sync");
    } finally {
      setLoading(false);
    }
  };

  const handleRefreshCode = async () => {
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

  const handleRevoke = async (deviceId: string) => {
    setLoading(true);
    try {
      const res = await controlClient.revokeMobileDevice(deviceId);
      if (res?.status) setStatus(res.status);
      else await loadStatus();
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
              <h3 className="font-bold text-sm">Mobile Sync (Android Read-Only)</h3>
              <p className="text-[11px] text-iea-textSecondary">
                Opt-in local network monitoring · Strictly read-only
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

        {/* Body */}
        <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
          {/* Opt-in Toggle */}
          <div className="iea-inset p-3.5 rounded-xl flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              {status?.enabled ? (
                <Wifi className="w-5 h-5 text-iea-profit" />
              ) : (
                <WifiOff className="w-5 h-5 text-iea-textSecondary" />
              )}
              <div>
                <div className="text-xs font-bold">
                  {status?.enabled ? "Mobile Sync Enabled" : "Mobile Sync Disabled (Default)"}
                </div>
                <div className="text-[11px] text-iea-textSecondary">
                  {status?.enabled
                    ? `Listening on ${status.primaryHost}:${status.port} (GET/SSE only)`
                    : "Enable to pair your Android phone on the same Wi-Fi network."}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={handleToggle}
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

          {/* QR + 6-Digit Pairing Code */}
          {status?.enabled && (
            <div className="iea-inset p-4 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold">Pair New Phone</span>
                <button
                  type="button"
                  onClick={handleRefreshCode}
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
                    <img src={qrDataUrl} alt="Mobile Sync Pairing QR Code" className="w-44 h-44" />
                  ) : (
                    <div className="w-44 h-44 flex items-center justify-center text-xs text-gray-500">
                      Click New Code
                    </div>
                  )}
                </div>

                <div className="flex-1 space-y-2 text-xs">
                  <div>
                    <div className="text-[10px] uppercase tracking-wider text-iea-textSecondary">
                      6-Digit Pairing Code
                    </div>
                    <div className="font-mono text-2xl font-bold tracking-[0.25em] text-iea-accent mt-0.5">
                      {status.pairingCode || "------"}
                    </div>
                    <div className="text-[11px] text-iea-textSecondary mt-0.5">
                      {secondsLeft > 0
                        ? `Expires in ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, "0")}`
                        : "Code expired — click New Code"}
                    </div>
                  </div>
                  <div className="text-[11px] font-mono text-iea-textSecondary">
                    Host: {status.primaryHost}:{status.port}
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-emerald-400">
                    <Shield className="w-3.5 h-3.5" />
                    <span>Read-only enforced at protocol level</span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Paired Devices */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold">
                Paired Devices ({status?.devices?.length ?? 0})
              </span>
              {status?.devices && status.devices.length > 0 && (
                <button
                  type="button"
                  onClick={async () => {
                    setLoading(true);
                    try {
                      const res = await controlClient.revokeAllMobileDevices();
                      if (res?.status) setStatus(res.status);
                    } finally {
                      setLoading(false);
                    }
                  }}
                  className="text-[11px] text-red-400 hover:underline"
                >
                  Revoke All
                </button>
              )}
            </div>

            {!status?.devices?.length ? (
              <div className="iea-inset p-3 rounded-lg text-xs text-iea-textSecondary text-center">
                No paired mobile devices yet.
              </div>
            ) : (
              <div className="space-y-2">
                {status.devices.map((dev) => (
                  <div
                    key={dev.deviceId}
                    className="iea-inset px-3 py-2.5 rounded-lg flex items-center justify-between gap-2 text-xs"
                  >
                    <div>
                      <div className="font-semibold flex items-center gap-1.5">
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>{dev.deviceName}</span>
                        <span className="text-[10px] uppercase px-1.5 py-0.5 rounded bg-iea-accentSoft text-iea-accent">
                          {dev.platform}
                        </span>
                      </div>
                      <div className="text-[10px] text-iea-textSecondary mt-0.5">
                        Last seen: {new Date(dev.lastSeenAt).toLocaleString()}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRevoke(dev.deviceId)}
                      disabled={loading}
                      className="p-1.5 rounded-md text-red-400 hover:bg-red-500/15 transition"
                      title="Revoke device access"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
