import React, { useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  Switch,
  Modal,
  Alert,
  ActivityIndicator,
} from "react-native";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as LocalAuthentication from "expo-local-authentication";
import { MOBILE_SYNC_SCHEMA_VERSION } from "@institutional-ea/data-contract";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { QrIcon } from "../components/Icons.tsx";
import {
  claimCloudPairing,
  DEFAULT_CLOUD_API_URL,
  pairWithCompanion,
  parseAnyPairingQrPayload,
  pollCloudPairingApproval,
  type CloudClaimResult,
} from "../services/MobileSyncClient.ts";
import { formatClockTime, formatShortDateTime } from "../utils/formatters.ts";
import { triggerLightHaptic } from "../services/haptics.ts";
import type { PairingCredentials } from "../services/SecureStorage.ts";

const APP_VERSION = "1.3.5";

interface SecurityScreenProps {
  theme: ThemeMode;
  credentials: PairingCredentials | null;
  connectionLabel: string;
  lastSyncedMs: number | null;
  biometricEnabled: boolean;
  onToggleBiometric: (enabled: boolean) => void;
  onPaired: (creds: PairingCredentials) => void;
  onUnpair: () => Promise<void>;
  onClearCache: () => Promise<void>;
}

export function SecurityScreen({
  theme,
  credentials,
  connectionLabel,
  lastSyncedMs,
  biometricEnabled,
  onToggleBiometric,
  onPaired,
  onUnpair,
  onClearCache,
}: SecurityScreenProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("8766");
  const [code, setCode] = useState("");
  const [deviceName, setDeviceName] = useState("Android Phone");
  const [showAdvancedLan, setShowAdvancedLan] = useState(false);
  const [pendingCloudClaim, setPendingCloudClaim] = useState<CloudClaimResult | null>(null);
  const [pairingBusy, setPairingBusy] = useState(false);
  const [pairError, setPairError] = useState<string | null>(null);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scanHandled, setScanHandled] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();

  const waitForCloudApproval = async (claim: CloudClaimResult) => {
    setPendingCloudClaim(claim);
    setPairingBusy(true);
    setPairError(null);
    const deadline = Math.min(claim.expiresAt * 1000, Date.now() + 120_000);
    try {
      while (Date.now() < deadline) {
        const res = await pollCloudPairingApproval(claim);
        if (res.status === "approved" && res.credentials) {
          triggerLightHaptic();
          setPendingCloudClaim(null);
          setCode("");
          onPaired(res.credentials);
          return;
        }
        await new Promise((r) => setTimeout(r, 2500));
      }
      setPairError("Timed out waiting for approval on Windows Companion. Try again.");
    } catch (err: unknown) {
      setPairError(err instanceof Error ? err.message : "Cloud pairing approval failed");
    } finally {
      setPendingCloudClaim(null);
      setPairingBusy(false);
    }
  };

  const executeCloudPairing = async (params: {
    cloudUrl?: string;
    code?: string;
    sessionId?: string;
    sessionToken?: string;
  }) => {
    setPairingBusy(true);
    setPairError(null);
    try {
      const claim = await claimCloudPairing({
        cloudUrl: params.cloudUrl || DEFAULT_CLOUD_API_URL,
        code: params.code,
        sessionId: params.sessionId,
        sessionToken: params.sessionToken,
        deviceName,
      });
      await waitForCloudApproval(claim);
    } catch (err: unknown) {
      setPairError(err instanceof Error ? err.message : "Cloud pairing failed");
      setPairingBusy(false);
    }
  };

  const handleOpenScanner = async () => {
    setPairError(null);
    if (!permission?.granted) {
      const res = await requestPermission();
      if (!res.granted) {
        setPairError("Camera permission denied. Enter Host IP and 6-digit code manually below.");
        return;
      }
    }
    setScanHandled(false);
    setScannerOpen(true);
  };

  const executePairing = async (params: {
    host: string;
    hosts?: string[];
    port: number;
    code: string;
  }) => {
    setPairingBusy(true);
    setPairError(null);
    try {
      const creds = await pairWithCompanion({
        host: params.host,
        hosts: params.hosts,
        port: params.port,
        code: params.code,
        deviceName,
      });
      triggerLightHaptic();
      onPaired(creds);
      setCode("");
    } catch (err: unknown) {
      setPairError(err instanceof Error ? err.message : "Pairing failed");
    } finally {
      setPairingBusy(false);
    }
  };

  const handleQrScanned = ({ data }: { data: string }) => {
    if (scanHandled) return;
    setScanHandled(true);
    setScannerOpen(false);
    try {
      const qr = parseAnyPairingQrPayload(data);
      if (qr.expiresAt < Math.floor(Date.now() / 1000)) {
        setPairError("QR code expired. Click 'Regenerate' on your PC and scan again.");
        return;
      }
      if (qr.v === 2) {
        setCode(qr.code);
        executeCloudPairing({
          cloudUrl: qr.cloudUrl,
          sessionId: qr.sessionId,
          sessionToken: qr.sessionToken,
          code: qr.code,
        });
        return;
      }
      setHost(qr.host);
      setPort(String(qr.port));
      setCode(qr.code);
      executePairing({
        host: qr.host,
        hosts: qr.hosts,
        port: qr.port,
        code: qr.code,
      });
    } catch {
      setPairError("Invalid QR code. Scan the QR displayed in Windows Companion → Android Pairing.");
    }
  };

  const handleSixDigitCloudPair = () => {
    const cleanCode = code.trim();
    if (!/^[0-9]{6}$/.test(cleanCode)) {
      setPairError("Enter the 6-digit pairing code shown on your Windows Companion.");
      return;
    }
    executeCloudPairing({ code: cleanCode });
  };

  const handleManualLanPair = () => {
    const cleanHost = host.trim();
    const parsedPort = Number(port.trim() || "8766");
    const cleanCode = code.trim();
    if (!cleanHost) {
      setPairError("Enter the Companion Host IP shown on your PC.");
      return;
    }
    if (!Number.isInteger(parsedPort) || parsedPort < 1024 || parsedPort > 65535) {
      setPairError("Port must be between 1024 and 65535.");
      return;
    }
    if (!/^[0-9]{6}$/.test(cleanCode)) {
      setPairError("Enter the 6-digit pairing code.");
      return;
    }
    executePairing({ host: cleanHost, port: parsedPort, code: cleanCode });
  };

  const handleBiometricSwitch = async (next: boolean) => {
    if (next) {
      try {
        const hasHardware = await LocalAuthentication.hasHardwareAsync();
        const isEnrolled = await LocalAuthentication.isEnrolledAsync();
        if (!hasHardware || !isEnrolled) {
          Alert.alert(
            "Biometric Unavailable",
            "Set up fingerprint, face unlock, or device PIN in Android Settings first."
          );
          return;
        }
        const auth = await LocalAuthentication.authenticateAsync({
          promptMessage: "Enable Institutional EA App Lock",
        });
        if (!auth.success) return;
      } catch {
        return;
      }
    }
    onToggleBiometric(next);
  };

  const confirmUnpair = () => {
    Alert.alert(
      "Unpair Device",
      "This revokes this phone's read-only token and clears local credentials.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Unpair",
          style: "destructive",
          onPress: () => {
            onUnpair();
          },
        },
      ]
    );
  };

  return (
    <ScrollView
      style={[styles.scroll, { backgroundColor: tokens.background }]}
      contentContainerStyle={styles.content}
    >
      {/* Pairing / Connected Companion Card */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <Text style={[styles.cardTitle, { color: tokens.text }]}>
          {credentials ? "Paired Companion" : "Pair with Windows Companion"}
        </Text>

        {credentials ? (
          <View>
            <InfoRow label="Companion" value={credentials.companionName} tokens={tokens} />
            <InfoRow label="Address" value={`${credentials.host}:${credentials.port}`} tokens={tokens} />
            <InfoRow label="Device ID" value={credentials.deviceId} tokens={tokens} />
            <InfoRow label="Status" value={connectionLabel} tokens={tokens} valueColor={tokens.accent} />
            <InfoRow label="Paired" value={formatShortDateTime(credentials.pairedAt)} tokens={tokens} />
            <InfoRow
              label="Token Storage"
              value="Android Keystore"
              tokens={tokens}
              valueColor={tokens.profit}
            />

            <TouchableOpacity
              onPress={confirmUnpair}
              style={[styles.dangerBtn, { backgroundColor: tokens.lossBg, borderColor: tokens.loss }]}
              accessibilityRole="button"
              accessibilityLabel="Unpair this device"
            >
              <Text style={[styles.dangerBtnText, { color: tokens.loss }]}>Unpair Device</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={styles.pairForm}>
            {/* Method 1: Scan QR Code (Works across ANY network) */}
            <TouchableOpacity
              onPress={handleOpenScanner}
              disabled={pairingBusy}
              style={[styles.qrBtn, { backgroundColor: tokens.accent }]}
              accessibilityRole="button"
              accessibilityLabel="Scan QR code from Windows Companion"
            >
              <QrIcon size={18} color={tokens.accentText} />
              <Text style={[styles.qrBtnText, { color: tokens.accentText }]}>
                Scan Companion QR Code
              </Text>
            </TouchableOpacity>

            <Text style={[styles.orText, { color: tokens.textDim }]}>
              — or enter 6-digit code (works on mobile data &amp; any Wi-Fi) —
            </Text>

            {/* Method 2: 6-Digit Cloud Code (NO Host IP or Port required) */}
            <View style={styles.inputRow}>
              <TextInput
                value={code}
                onChangeText={(t) => setCode(t.replace(/[^0-9]/g, "").slice(0, 6))}
                placeholder="6-digit code"
                placeholderTextColor={tokens.textDim}
                keyboardType="number-pad"
                maxLength={6}
                style={[
                  styles.input,
                  { flex: 1, backgroundColor: tokens.cardSecondary, color: tokens.text, borderColor: tokens.borderSubtle, letterSpacing: 4, fontWeight: "700" },
                ]}
              />
              <TextInput
                value={deviceName}
                onChangeText={setDeviceName}
                placeholder="Device name"
                placeholderTextColor={tokens.textDim}
                style={[
                  styles.input,
                  { flex: 1, backgroundColor: tokens.cardSecondary, color: tokens.text, borderColor: tokens.borderSubtle },
                ]}
              />
            </View>

            {pendingCloudClaim && (
              <Text style={[styles.rowSub, { color: tokens.accent }]}>
                Waiting for approval on "{pendingCloudClaim.companionName}"… Confirm on your Windows PC.
              </Text>
            )}

            {pairError && (
              <Text style={[styles.errorText, { color: tokens.loss }]}>{pairError}</Text>
            )}

            <TouchableOpacity
              onPress={handleSixDigitCloudPair}
              disabled={pairingBusy}
              style={[styles.secondaryBtn, { backgroundColor: tokens.cardSecondary, borderColor: tokens.border }]}
              accessibilityRole="button"
              accessibilityLabel="Pair with 6-digit code"
            >
              {pairingBusy ? (
                <ActivityIndicator size="small" color={tokens.accent} />
              ) : (
                <Text style={[styles.secondaryBtnText, { color: tokens.text }]}>
                  Pair with 6-Digit Code
                </Text>
              )}
            </TouchableOpacity>

            {/* Optional Advanced Local Wi-Fi Fallback */}
            <TouchableOpacity
              onPress={() => setShowAdvancedLan((prev) => !prev)}
              style={{ paddingTop: 6, alignItems: "center" }}
            >
              <Text style={[styles.rowSub, { color: tokens.textDim }]}>
                {showAdvancedLan ? "Hide Local Wi-Fi Fallback ▲" : "Advanced: Local Wi-Fi Fallback ▼"}
              </Text>
            </TouchableOpacity>

            {showAdvancedLan && (
              <View style={{ gap: 8, marginTop: 4 }}>
                <View style={styles.inputRow}>
                  <TextInput
                    value={host}
                    onChangeText={setHost}
                    placeholder="LAN Host IP (optional)"
                    placeholderTextColor={tokens.textDim}
                    autoCapitalize="none"
                    keyboardType="numbers-and-punctuation"
                    style={[
                      styles.input,
                      { flex: 2, backgroundColor: tokens.cardSecondary, color: tokens.text, borderColor: tokens.borderSubtle },
                    ]}
                  />
                  <TextInput
                    value={port}
                    onChangeText={setPort}
                    placeholder="8766"
                    placeholderTextColor={tokens.textDim}
                    keyboardType="number-pad"
                    style={[
                      styles.input,
                      { flex: 1, backgroundColor: tokens.cardSecondary, color: tokens.text, borderColor: tokens.borderSubtle },
                    ]}
                  />
                </View>
                <TouchableOpacity
                  onPress={handleManualLanPair}
                  disabled={pairingBusy}
                  style={[styles.secondaryBtn, { backgroundColor: tokens.cardSecondary, borderColor: tokens.borderSubtle }]}
                >
                  <Text style={[styles.secondaryBtnText, { color: tokens.textDim }]}>
                    Pair via Local Wi-Fi
                  </Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        )}
      </View>

      {/* App Lock & Cache Controls */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <Text style={[styles.cardTitle, { color: tokens.text }]}>Device Security & Data</Text>

        <View style={[styles.toggleRow, { borderBottomColor: tokens.borderSubtle }]}>
          <View style={styles.toggleText}>
            <Text style={[styles.rowTitle, { color: tokens.text }]}>Biometric / PIN App Lock</Text>
            <Text style={[styles.rowSub, { color: tokens.textDim }]}>
              Require Android BiometricPrompt when opening the app
            </Text>
          </View>
          <Switch
            value={biometricEnabled}
            onValueChange={handleBiometricSwitch}
            trackColor={{ false: tokens.cardSecondary, true: tokens.accent }}
            thumbColor="#FFFFFF"
          />
        </View>

        <View style={styles.cacheRow}>
          <View style={styles.toggleText}>
            <Text style={[styles.rowTitle, { color: tokens.text }]}>Offline Snapshot Cache</Text>
            <Text style={[styles.rowSub, { color: tokens.textDim }]}>
              {lastSyncedMs
                ? `Last cached at ${formatClockTime(lastSyncedMs)}`
                : "No cached snapshot stored"}
            </Text>
          </View>
          <TouchableOpacity
            onPress={async () => {
              await onClearCache();
              Alert.alert("Cache Cleared", "Offline snapshot cache has been cleared.");
            }}
            style={[styles.smallBtn, { backgroundColor: tokens.cardSecondary }]}
          >
            <Text style={[styles.smallBtnText, { color: tokens.text }]}>Clear</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Read-Only Enforcement & Version Info */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <Text style={[styles.cardTitle, { color: tokens.text }]}>Read-Only Mode: Enforced</Text>
        <Text style={[styles.descText, { color: tokens.textMuted }]}>
          This Android companion is strictly read-only at both client and server protocol levels. It can never start/stop the bot, close positions, modify SL/TP, change settings, or receive MT5 broker credentials.
        </Text>
        <InfoRow label="Protocol Scope" value="GET + SSE only (telemetry:read)" tokens={tokens} valueColor={tokens.profit} />
        <InfoRow label="App Version" value={`v${APP_VERSION}`} tokens={tokens} />
        <InfoRow label="Sync Schema" value={`v${MOBILE_SYNC_SCHEMA_VERSION}`} tokens={tokens} />
      </View>

      {/* QR Scanner Modal */}
      <Modal
        visible={scannerOpen}
        animationType="slide"
        onRequestClose={() => setScannerOpen(false)}
      >
        <View style={styles.scannerRoot}>
          <CameraView
            style={StyleSheet.absoluteFillObject}
            barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
            onBarcodeScanned={handleQrScanned}
          />
          <View style={styles.scannerOverlay}>
            <View style={[styles.scannerFrame, { borderColor: tokens.accent }]} />
            <Text style={styles.scannerHint}>
              Point at the QR code in Windows Companion → Mobile Sync
            </Text>
            <TouchableOpacity
              onPress={() => setScannerOpen(false)}
              style={[styles.cancelScanBtn, { backgroundColor: tokens.surface }]}
            >
              <Text style={[styles.cancelScanText, { color: tokens.text }]}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

function InfoRow({
  label,
  value,
  tokens,
  valueColor,
}: {
  label: string;
  value: string;
  tokens: ReturnType<typeof getThemeTokens>;
  valueColor?: string;
}) {
  return (
    <View style={[styles.infoRow, { borderBottomColor: tokens.borderSubtle }]}>
      <Text style={[styles.infoLabel, { color: tokens.textMuted }]}>{label}</Text>
      <Text style={[styles.infoValue, { color: valueColor || tokens.text }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1 },
  content: { padding: 12, paddingBottom: 28, gap: 12 },
  card: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 16,
  },
  cardTitle: {
    fontSize: 15,
    fontWeight: "800",
    marginBottom: 10,
  },
  descText: {
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 12,
  },
  pairForm: { gap: 10 },
  qrBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingVertical: 13,
    borderRadius: 10,
    minHeight: 48,
  },
  qrBtnText: {
    fontSize: 14,
    fontWeight: "800",
  },
  orText: {
    textAlign: "center",
    fontSize: 11,
  },
  inputRow: {
    flexDirection: "row",
    gap: 8,
  },
  input: {
    height: 44,
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    fontSize: 13,
    fontFamily: "monospace",
  },
  errorText: {
    fontSize: 12,
    lineHeight: 17,
  },
  secondaryBtn: {
    borderRadius: 10,
    borderWidth: 1,
    paddingVertical: 12,
    alignItems: "center",
    minHeight: 46,
  },
  secondaryBtnText: {
    fontSize: 13,
    fontWeight: "700",
  },
  dangerBtn: {
    marginTop: 14,
    borderRadius: 10,
    borderWidth: 1,
    paddingVertical: 12,
    alignItems: "center",
    minHeight: 46,
  },
  dangerBtnText: {
    fontSize: 13,
    fontWeight: "800",
  },
  infoRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 9,
    borderBottomWidth: 1,
  },
  infoLabel: {
    fontSize: 12,
  },
  infoValue: {
    fontSize: 12,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingBottom: 12,
    borderBottomWidth: 1,
    gap: 10,
  },
  cacheRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingTop: 12,
    gap: 10,
  },
  toggleText: { flex: 1 },
  rowTitle: { fontSize: 13, fontWeight: "700" },
  rowSub: { fontSize: 11, marginTop: 2 },
  smallBtn: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
    minHeight: 36,
    justifyContent: "center",
  },
  smallBtnText: { fontSize: 12, fontWeight: "700" },
  scannerRoot: { flex: 1, backgroundColor: "#000" },
  scannerOverlay: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 24,
    gap: 20,
    backgroundColor: "rgba(0,0,0,0.45)",
  },
  scannerFrame: {
    width: 240,
    height: 240,
    borderWidth: 3,
    borderRadius: 18,
  },
  scannerHint: {
    color: "#FFFFFF",
    fontSize: 13,
    fontWeight: "600",
    textAlign: "center",
  },
  cancelScanBtn: {
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 10,
    minHeight: 46,
  },
  cancelScanText: {
    fontSize: 14,
    fontWeight: "700",
  },
});
