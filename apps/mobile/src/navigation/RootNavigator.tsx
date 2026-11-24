import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { ConnectionBanner, type ConnectionState } from "../components/ConnectionBanner.tsx";
import { KpiCards, type KpiData } from "../components/KpiCards.tsx";
import { PositionsList } from "../components/PositionsList.tsx";
import { ChartWebView } from "../components/ChartWebView.tsx";
import type { Position, Candle, SmcZone } from "@institutional-ea/data-contract";

export type MobileTab = "DASHBOARD" | "CHARTS" | "POSITIONS" | "SETTINGS";

interface RootNavigatorProps {
  theme: ThemeMode;
  onToggleTheme: () => void;
  connectionState: ConnectionState;
  kpiData?: KpiData;
  positions?: Position[];
  candles?: Candle[];
  zones?: SmcZone[];
  activeSymbol?: string;
}

export function RootNavigator({
  theme,
  onToggleTheme,
  connectionState,
  kpiData,
  positions = [],
  candles = [],
  zones = [],
  activeSymbol = "XAUUSD",
}: RootNavigatorProps): React.ReactElement {
  const [currentTab, setCurrentTab] = useState<MobileTab>("DASHBOARD");
  const tokens = getThemeTokens(theme);

  return (
    <View style={[styles.screen, { backgroundColor: tokens.background }]}>
      {/* Top Header */}
      <View style={[styles.header, { backgroundColor: tokens.surface, borderColor: tokens.border }]}>
        <View style={styles.titleRow}>
          <Text style={[styles.appTitle, { color: tokens.text }]}>Institutional EA</Text>
          <View style={styles.headerRight}>
            <View style={[styles.liveBadge, { backgroundColor: tokens.profitBg }]}>
              <Text style={[styles.liveText, { color: tokens.profit }]}>READ-ONLY</Text>
            </View>
            <TouchableOpacity onPress={onToggleTheme} style={styles.themeToggleBtn}>
              <Text style={{ fontSize: 16 }}>{theme === "dark" ? "🌙" : "☀️"}</Text>
            </TouchableOpacity>
          </View>
        </View>

        <ConnectionBanner state={connectionState} theme={theme} />
      </View>

      {/* Main Tab Content */}
      <View style={styles.content}>
        {currentTab === "DASHBOARD" && (
          <View style={styles.tabScroll}>
            <View style={{ marginVertical: 8 }}>
              <KpiCards data={kpiData} theme={theme} />
            </View>
            <View style={styles.sectionHeader}>
              <Text style={[styles.sectionTitle, { color: tokens.textMuted }]}>
                Live Execution Chart ({activeSymbol})
              </Text>
            </View>
            <ChartWebView
              candles={candles}
              zones={zones}
              positions={positions}
              symbol={activeSymbol}
              theme={theme}
            />
            <View style={styles.sectionHeader}>
              <Text style={[styles.sectionTitle, { color: tokens.textMuted }]}>
                Active Positions ({positions.length})
              </Text>
            </View>
            <PositionsList positions={positions} theme={theme} />
          </View>
        )}

        {currentTab === "CHARTS" && (
          <View style={styles.fullscreenChart}>
            <View style={styles.chartControlBar}>
              <Text style={[styles.symbolPill, { color: tokens.text, backgroundColor: tokens.card }]}>
                {activeSymbol} • M5
              </Text>
              <Text style={[styles.legendPill, { color: tokens.textDim }]}>
                SMC: FVG • OB • IFVG
              </Text>
            </View>
            <ChartWebView
              candles={candles}
              zones={zones}
              positions={positions}
              symbol={activeSymbol}
              theme={theme}
            />
          </View>
        )}

        {currentTab === "POSITIONS" && (
          <View style={styles.positionsTab}>
            <View style={styles.sectionHeader}>
              <Text style={[styles.sectionTitle, { color: tokens.textMuted }]}>
                Open Trades ({positions.length})
              </Text>
            </View>
            <PositionsList positions={positions} theme={theme} />
          </View>
        )}

        {currentTab === "SETTINGS" && (
          <View style={styles.settingsTab}>
            <View style={[styles.settingsCard, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
              <Text style={[styles.cardHeading, { color: tokens.text }]}>Security & Pairing</Text>
              <Text style={[styles.cardText, { color: tokens.textDim }]}>
                This device is paired in strict READ-ONLY mode. Trading executions and account mutations are blocked at both client and server protocol levels.
              </Text>
              <View style={styles.securityItem}>
                <Text style={[styles.securityLabel, { color: tokens.textMuted }]}>Scope</Text>
                <Text style={[styles.securityValue, { color: tokens.accent }]}>telemetry:read</Text>
              </View>
              <View style={styles.securityItem}>
                <Text style={[styles.securityLabel, { color: tokens.textMuted }]}>Biometric Lock</Text>
                <Text style={[styles.securityValue, { color: tokens.profit }]}>Hardware Enclave Active</Text>
              </View>
            </View>
          </View>
        )}
      </View>

      {/* Bottom Tab Navigation */}
      <View style={[styles.tabBar, { backgroundColor: tokens.surface, borderColor: tokens.border }]}>
        {(["DASHBOARD", "CHARTS", "POSITIONS", "SETTINGS"] as MobileTab[]).map((tab) => {
          const isActive = currentTab === tab;
          return (
            <TouchableOpacity
              key={tab}
              onPress={() => setCurrentTab(tab)}
              style={styles.tabBtn}
            >
              <Text
                style={[
                  styles.tabLabel,
                  { color: isActive ? tokens.accent : tokens.textDim },
                ]}
              >
                {tab === "DASHBOARD" ? "Overview" : tab === "CHARTS" ? "Charts" : tab === "POSITIONS" ? "Trades" : "Security"}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
  },
  header: {
    paddingTop: 48,
    paddingBottom: 8,
    borderBottomWidth: 1,
  },
  titleRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 16,
    marginBottom: 4,
  },
  appTitle: {
    fontSize: 18,
    fontWeight: "700",
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  liveBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  liveText: {
    fontSize: 9,
    fontWeight: "700",
    letterSpacing: 0.5,
  },
  themeToggleBtn: {
    padding: 4,
  },
  content: {
    flex: 1,
  },
  tabScroll: {
    flex: 1,
  },
  sectionHeader: {
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  fullscreenChart: {
    flex: 1,
    padding: 12,
  },
  chartControlBar: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 8,
  },
  symbolPill: {
    fontSize: 12,
    fontWeight: "700",
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  legendPill: {
    fontSize: 11,
    paddingVertical: 4,
  },
  positionsTab: {
    flex: 1,
    paddingTop: 8,
  },
  settingsTab: {
    flex: 1,
    padding: 16,
  },
  settingsCard: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 16,
  },
  cardHeading: {
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 8,
  },
  cardText: {
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 16,
  },
  securityItem: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 8,
    borderTopWidth: 1,
    borderTopColor: "rgba(255, 255, 255, 0.05)",
  },
  securityLabel: {
    fontSize: 12,
  },
  securityValue: {
    fontSize: 12,
    fontWeight: "600",
  },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: 1,
    paddingBottom: 24,
    paddingTop: 8,
  },
  tabBtn: {
    flex: 1,
    alignItems: "center",
  },
  tabLabel: {
    fontSize: 11,
    fontWeight: "600",
  },
});
