import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, Image, ScrollView } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { QrIcon } from "../components/Icons.tsx";

const BRAND_LOGO = require("../../assets/logo.png");

interface OnboardingScreenProps {
  theme: ThemeMode;
  onStartPairing: () => void;
}

export function OnboardingScreen({
  theme,
  onStartPairing,
}: OnboardingScreenProps): React.ReactElement {
  const tokens = getThemeTokens(theme);

  return (
    <ScrollView
      contentContainerStyle={[styles.container, { backgroundColor: tokens.background }]}
    >
      <Image source={BRAND_LOGO} style={styles.logo} resizeMode="contain" accessibilityLabel="Institutional EA Logo" />
      <Text style={[styles.title, { color: tokens.text }]}>Pair Your Companion</Text>
      <Text style={[styles.subtitle, { color: tokens.textMuted }]}>
        Connect to your Windows Institutional EA Companion on the same Wi-Fi network for real-time read-only monitoring.
      </Text>

      <View style={[styles.stepsCard, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <StepRow
          num="1"
          title="Enable Mobile Sync on PC"
          desc="Open Windows Companion → Settings → Mobile Sync and turn it on."
          tokens={tokens}
        />
        <StepRow
          num="2"
          title="Scan QR or Enter 6-Digit Code"
          desc="Use your phone camera or type the Host IP, port, and 6-digit pairing code."
          tokens={tokens}
        />
        <StepRow
          num="3"
          title="Monitor Live in Read-Only Mode"
          desc="View live MT5 equity, positions, SMC charts, and deal history safely. Orders cannot be placed or modified from mobile."
          tokens={tokens}
          isLast
        />
      </View>

      <TouchableOpacity
        onPress={onStartPairing}
        style={[styles.pairBtn, { backgroundColor: tokens.accent }]}
        accessibilityRole="button"
        accessibilityLabel="Pair with Windows Companion"
      >
        <QrIcon size={18} color={tokens.accentText} />
        <Text style={[styles.pairBtnText, { color: tokens.accentText }]}>
          Scan QR or Enter Code
        </Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function StepRow({
  num,
  title,
  desc,
  tokens,
  isLast = false,
}: {
  num: string;
  title: string;
  desc: string;
  tokens: ReturnType<typeof getThemeTokens>;
  isLast?: boolean;
}) {
  return (
    <View
      style={[
        styles.stepRow,
        !isLast && { borderBottomWidth: 1, borderBottomColor: tokens.borderSubtle },
      ]}
    >
      <View style={[styles.stepBadge, { backgroundColor: tokens.accentLight }]}>
        <Text style={[styles.stepNum, { color: tokens.accent }]}>{num}</Text>
      </View>
      <View style={styles.stepBody}>
        <Text style={[styles.stepTitle, { color: tokens.text }]}>{title}</Text>
        <Text style={[styles.stepDesc, { color: tokens.textMuted }]}>{desc}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  logo: {
    width: 68,
    height: 68,
    borderRadius: 16,
    marginBottom: 14,
  },
  title: {
    fontSize: 22,
    fontWeight: "800",
    marginBottom: 6,
    textAlign: "center",
  },
  subtitle: {
    fontSize: 13,
    textAlign: "center",
    lineHeight: 19,
    marginBottom: 20,
    maxWidth: 340,
  },
  stepsCard: {
    width: "100%",
    maxWidth: 420,
    borderRadius: 14,
    borderWidth: 1,
    paddingHorizontal: 14,
    marginBottom: 22,
  },
  stepRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    paddingVertical: 14,
    gap: 12,
  },
  stepBadge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  stepNum: {
    fontSize: 13,
    fontWeight: "800",
  },
  stepBody: {
    flex: 1,
  },
  stepTitle: {
    fontSize: 14,
    fontWeight: "700",
    marginBottom: 2,
  },
  stepDesc: {
    fontSize: 12,
    lineHeight: 17,
  },
  pairBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    paddingHorizontal: 24,
    paddingVertical: 14,
    borderRadius: 12,
    minHeight: 48,
    width: "100%",
    maxWidth: 420,
  },
  pairBtnText: {
    fontSize: 15,
    fontWeight: "800",
  },
});
