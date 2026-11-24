import React from "react";
import { View, Text, StyleSheet } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";

export type ConnectionState = "CONNECTED" | "SYNCING" | "RECONNECTING" | "OFFLINE";

interface ConnectionBannerProps {
  state: ConnectionState;
  lastSyncedAt?: string;
  theme?: ThemeMode;
}

export function ConnectionBanner({
  state,
  lastSyncedAt,
  theme = "dark",
}: ConnectionBannerProps): React.ReactElement | null {
  const tokens = getThemeTokens(theme);

  if (state === "CONNECTED") {
    return null; // Silent when fully synchronized
  }

  const stateConfig = {
    SYNCING: {
      label: "Syncing live telemetry...",
      bg: tokens.accentLight,
      color: tokens.accent,
      dotColor: tokens.accent,
    },
    RECONNECTING: {
      label: "Reconnecting to host stream...",
      bg: tokens.warningBg,
      color: tokens.warning,
      dotColor: tokens.warning,
    },
    OFFLINE: {
      label: lastSyncedAt ? `Offline • Last synced ${lastSyncedAt}` : "Host offline • No connection",
      bg: tokens.lossBg,
      color: tokens.loss,
      dotColor: tokens.loss,
    },
  }[state];

  return (
    <View style={[styles.banner, { backgroundColor: stateConfig.bg }]}>
      <View style={[styles.dot, { backgroundColor: stateConfig.dotColor }]} />
      <Text style={[styles.label, { color: stateConfig.color }]}>
        {stateConfig.label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 6,
  },
  label: {
    fontSize: 12,
    fontWeight: "600",
  },
});
