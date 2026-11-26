import React from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { formatClockTime } from "../utils/formatters.ts";

export type ConnectionState =
  | "NOT_PAIRED"
  | "CONNECTING"
  | "LIVE"
  | "RECONNECTING"
  | "STALE"
  | "COMPANION_OFFLINE"
  | "MT5_DISCONNECTED"
  | "BOT_PAUSED"
  | "BOT_STOPPED";

interface ConnectionBannerProps {
  state: ConnectionState;
  lastSyncedMs?: number | null;
  isShowingCache?: boolean;
  theme?: ThemeMode;
  onRetry?: () => void;
}

export function ConnectionBanner({
  state,
  lastSyncedMs,
  isShowingCache = false,
  theme = "dark",
  onRetry,
}: ConnectionBannerProps): React.ReactElement | null {
  const tokens = getThemeTokens(theme);

  if (state === "LIVE" && !isShowingCache) {
    return null;
  }

  const timeLabel = lastSyncedMs ? formatClockTime(lastSyncedMs) : null;

  const configMap: Record<
    Exclude<ConnectionState, "LIVE">,
    { label: string; bg: string; color: string; showRetry?: boolean }
  > = {
    NOT_PAIRED: {
      label: "Not paired — pair with Windows Companion to view live data",
      bg: tokens.accentLight,
      color: tokens.accent,
    },
    CONNECTING: {
      label: isShowingCache && timeLabel
        ? `Connecting… showing cached snapshot (Last synced ${timeLabel})`
        : "Connecting to Windows Companion…",
      bg: tokens.accentLight,
      color: tokens.accent,
    },
    RECONNECTING: {
      label: timeLabel
        ? `Reconnecting… Last synced ${timeLabel}`
        : "Reconnecting to Windows Companion…",
      bg: tokens.warningBg,
      color: tokens.warning,
      showRetry: true,
    },
    STALE: {
      label: timeLabel
        ? `Data stale · Last updated ${timeLabel}`
        : "Data stale · Waiting for heartbeat",
      bg: tokens.warningBg,
      color: tokens.warning,
      showRetry: true,
    },
    COMPANION_OFFLINE: {
      label: timeLabel
        ? `Companion offline · Last synced ${timeLabel}`
        : "Companion offline · Check PC & Wi-Fi",
      bg: tokens.lossBg,
      color: tokens.loss,
      showRetry: true,
    },
    MT5_DISCONNECTED: {
      label: "MT5 terminal disconnected on PC",
      bg: tokens.lossBg,
      color: tokens.loss,
    },
    BOT_PAUSED: {
      label: "Bot paused — monitoring active positions",
      bg: tokens.warningBg,
      color: tokens.warning,
    },
    BOT_STOPPED: {
      label: "Bot stopped — live market feed active",
      bg: tokens.cardSecondary,
      color: tokens.textMuted,
    },
  };

  const cfg =
    state === "LIVE"
      ? {
          label: timeLabel ? `Last synced ${timeLabel}` : "Cached snapshot",
          bg: tokens.cardSecondary,
          color: tokens.textMuted,
          showRetry: false,
        }
      : configMap[state];

  return (
    <View
      style={[styles.banner, { backgroundColor: cfg.bg }]}
      accessibilityRole="alert"
      accessibilityLabel={cfg.label}
    >
      <View style={styles.left}>
        <View style={[styles.dot, { backgroundColor: cfg.color }]} />
        <Text style={[styles.label, { color: cfg.color }]} numberOfLines={1}>
          {cfg.label}
        </Text>
      </View>
      {cfg.showRetry && onRetry ? (
        <TouchableOpacity
          onPress={onRetry}
          style={[styles.retryBtn, { borderColor: cfg.color }]}
          accessibilityRole="button"
          accessibilityLabel="Retry connection"
        >
          <Text style={[styles.retryText, { color: cfg.color }]}>Retry</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 6,
    paddingHorizontal: 14,
  },
  left: {
    flexDirection: "row",
    alignItems: "center",
    flex: 1,
    marginRight: 8,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    marginRight: 8,
  },
  label: {
    fontSize: 11,
    fontWeight: "600",
    flexShrink: 1,
  },
  retryBtn: {
    borderWidth: 1,
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  retryText: {
    fontSize: 11,
    fontWeight: "700",
  },
});
