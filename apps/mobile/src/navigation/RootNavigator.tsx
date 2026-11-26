import React from "react";
import { View, Text, StyleSheet, TouchableOpacity, Image } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import {
  ConnectionBanner,
  type ConnectionState,
} from "../components/ConnectionBanner.tsx";
import {
  ChartTabIcon,
  MoonIcon,
  OverviewIcon,
  SecurityTabIcon,
  SunIcon,
  TradesTabIcon,
} from "../components/Icons.tsx";
import { OnboardingScreen } from "../screens/OnboardingScreen.tsx";
import { OverviewScreen } from "../screens/OverviewScreen.tsx";
import { ChartsScreen } from "../screens/ChartsScreen.tsx";
import { TradesScreen } from "../screens/TradesScreen.tsx";
import { SecurityScreen } from "../screens/SecurityScreen.tsx";
import { triggerSelectionHaptic } from "../services/haptics.ts";
import type { EquityRange } from "../components/EquityCurveCard.tsx";
import type { MobileSyncClient } from "../services/MobileSyncClient.ts";
import type { PairingCredentials } from "../services/SecureStorage.ts";
import type { ChartLayerPreferences } from "../services/OfflineCache.ts";
import type {
  MobileAccount,
  MobileActivityEvent,
  MobileBotState,
  MobileCandlesResponse,
  MobileDrawingsResponse,
  MobileEquityResponse,
  MobilePosition,
  MobileStats,
  MobileSymbolSpec,
  MobileTradeRecord,
} from "@institutional-ea/data-contract";

const BRAND_LOGO = require("../../assets/logo.png");

export type MobileTab = "OVERVIEW" | "CHARTS" | "TRADES" | "SECURITY";

interface RootNavigatorProps {
  theme: ThemeMode;
  onToggleTheme: () => void;
  currentTab: MobileTab;
  onSelectTab: (tab: MobileTab) => void;
  connectionState: ConnectionState;
  botState: MobileBotState | null;
  lastSyncedMs: number | null;
  isShowingCache: boolean;
  onRetryConnection: () => void;
  credentials: PairingCredentials | null;
  client: MobileSyncClient | null;
  account: MobileAccount | null;
  stats: MobileStats | null;
  positions: MobilePosition[];
  equity: MobileEquityResponse | null;
  equityRange: EquityRange;
  onSelectEquityRange: (r: EquityRange) => void;
  symbols: MobileSymbolSpec[];
  timeframes: string[];
  selectedSymbol: string | null;
  selectedTimeframe: string;
  onSelectSymbol: (sym: string) => void;
  onSelectTimeframe: (tf: string) => void;
  candlesData: MobileCandlesResponse | null;
  drawings: MobileDrawingsResponse | null;
  layers: ChartLayerPreferences;
  onToggleLayer: (key: keyof ChartLayerPreferences) => void;
  activity: MobileActivityEvent[];
  isLoading: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  chartFullscreen: boolean;
  onToggleChartFullscreen: () => void;
  focusChartTime: number | null;
  onShowPositionOnChart: (pos: MobilePosition) => void;
  onShowTradeOnChart: (trade: MobileTradeRecord) => void;
  onLoadMoreHistory: (beforeTime: number) => void;
  biometricEnabled: boolean;
  onToggleBiometric: (enabled: boolean) => void;
  onPaired: (creds: PairingCredentials) => void;
  onUnpair: () => Promise<void>;
  onClearCache: () => Promise<void>;
}

export function RootNavigator(props: RootNavigatorProps): React.ReactElement {
  const {
    theme,
    onToggleTheme,
    currentTab,
    onSelectTab,
    connectionState,
    botState,
    lastSyncedMs,
    isShowingCache,
    onRetryConnection,
    credentials,
    chartFullscreen,
  } = props;

  const insets = useSafeAreaInsets();
  const tokens = getThemeTokens(theme);
  const isPaired = credentials !== null;
  const hideChrome = chartFullscreen && currentTab === "CHARTS";

  const botChipColor =
    botState === "RUNNING"
      ? tokens.profit
      : botState === "PAUSED"
      ? tokens.warning
      : botState === "ERROR" || botState === "EMERGENCY_STOP"
      ? tokens.loss
      : tokens.textDim;

  const botChipBg =
    botState === "RUNNING"
      ? tokens.profitBg
      : botState === "PAUSED"
      ? tokens.warningBg
      : botState === "ERROR" || botState === "EMERGENCY_STOP"
      ? tokens.lossBg
      : tokens.cardSecondary;

  const connDotColor =
    connectionState === "LIVE"
      ? tokens.profit
      : connectionState === "CONNECTING" ||
        connectionState === "RECONNECTING" ||
        connectionState === "STALE"
      ? tokens.warning
      : connectionState === "NOT_PAIRED"
      ? tokens.textDim
      : tokens.loss;

  const connShortLabel =
    connectionState === "LIVE"
      ? "Live"
      : connectionState === "RECONNECTING"
      ? "Reconnecting"
      : connectionState === "STALE"
      ? "Stale"
      : connectionState === "COMPANION_OFFLINE"
      ? "Offline"
      : connectionState === "MT5_DISCONNECTED"
      ? "MT5 Off"
      : connectionState === "NOT_PAIRED"
      ? "Unpaired"
      : connectionState === "BOT_PAUSED"
      ? "Paused"
      : connectionState === "BOT_STOPPED"
      ? "Stopped"
      : "Syncing";

  return (
    <View style={[styles.screen, { backgroundColor: tokens.background }]}>
      {/* Top Header */}
      {!hideChrome && (
        <View
          style={[
            styles.header,
            {
              backgroundColor: tokens.surface,
              borderBottomColor: tokens.borderSubtle,
              paddingTop: Math.max(insets.top, 10) + 4,
            },
          ]}
        >
          <View style={styles.titleRow}>
            <View style={styles.brandRow}>
              <Image
                source={BRAND_LOGO}
                style={[styles.brandLogo, { borderColor: tokens.border }]}
                resizeMode="contain"
                accessibilityLabel="Institutional EA Logo"
              />
              <View>
                <Text style={[styles.appTitle, { color: tokens.text }]}>
                  Institutional EA
                </Text>
                <View style={styles.statusInlineRow}>
                  <View style={[styles.connDot, { backgroundColor: connDotColor }]} />
                  <Text style={[styles.connText, { color: tokens.textMuted }]}>
                    {connShortLabel}
                  </Text>
                  {botState && isPaired && (
                    <View style={[styles.botChip, { backgroundColor: botChipBg }]}>
                      <Text style={[styles.botChipText, { color: botChipColor }]}>
                        {botState}
                      </Text>
                    </View>
                  )}
                </View>
              </View>
            </View>

            <View style={styles.headerRight}>
              <View style={[styles.roBadge, { backgroundColor: tokens.accentLight, borderColor: tokens.border }]}>
                <Text style={[styles.roText, { color: tokens.accent }]}>READ-ONLY</Text>
              </View>
              <TouchableOpacity
                onPress={() => {
                  triggerSelectionHaptic();
                  onToggleTheme();
                }}
                style={[styles.themeBtn, { backgroundColor: tokens.cardSecondary }]}
                accessibilityRole="button"
                accessibilityLabel={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
              >
                {theme === "dark" ? (
                  <SunIcon size={16} color={tokens.warning} />
                ) : (
                  <MoonIcon size={16} color={tokens.accent} />
                )}
              </TouchableOpacity>
            </View>
          </View>

          <ConnectionBanner
            state={connectionState}
            lastSyncedMs={lastSyncedMs}
            isShowingCache={isShowingCache}
            theme={theme}
            onRetry={onRetryConnection}
          />
        </View>
      )}

      {/* Main Content */}
      <View
        style={[
          styles.content,
          hideChrome && { paddingTop: Math.max(insets.top, 4) },
        ]}
      >
        {!isPaired && currentTab !== "SECURITY" ? (
          <OnboardingScreen
            theme={theme}
            onStartPairing={() => onSelectTab("SECURITY")}
          />
        ) : currentTab === "OVERVIEW" ? (
          <OverviewScreen
            theme={theme}
            account={props.account}
            stats={props.stats}
            positions={props.positions}
            equity={props.equity}
            equityRange={props.equityRange}
            onSelectEquityRange={props.onSelectEquityRange}
            candlesData={props.candlesData}
            drawings={props.drawings}
            activeSymbol={props.selectedSymbol}
            activeTimeframe={props.selectedTimeframe}
            layers={props.layers}
            activity={props.activity}
            isLoading={props.isLoading}
            isRefreshing={props.isRefreshing}
            onRefresh={props.onRefresh}
            onOpenCharts={() => onSelectTab("CHARTS")}
            onShowPositionOnChart={props.onShowPositionOnChart}
          />
        ) : currentTab === "CHARTS" ? (
          <ChartsScreen
            theme={theme}
            symbols={props.symbols}
            timeframes={props.timeframes}
            selectedSymbol={props.selectedSymbol}
            selectedTimeframe={props.selectedTimeframe}
            onSelectSymbol={props.onSelectSymbol}
            onSelectTimeframe={props.onSelectTimeframe}
            candlesData={props.candlesData}
            drawings={props.drawings}
            layers={props.layers}
            onToggleLayer={props.onToggleLayer}
            isLive={connectionState === "LIVE" && !isShowingCache}
            isLoading={props.isLoading}
            focusTime={props.focusChartTime}
            isFullscreen={chartFullscreen}
            onToggleFullscreen={props.onToggleChartFullscreen}
            onLoadMoreHistory={props.onLoadMoreHistory}
          />
        ) : currentTab === "TRADES" ? (
          <TradesScreen
            theme={theme}
            client={props.client}
            symbols={props.symbols}
            onShowTradeOnChart={props.onShowTradeOnChart}
          />
        ) : (
          <SecurityScreen
            theme={theme}
            credentials={credentials}
            connectionLabel={connShortLabel}
            lastSyncedMs={lastSyncedMs}
            biometricEnabled={props.biometricEnabled}
            onToggleBiometric={props.onToggleBiometric}
            onPaired={props.onPaired}
            onUnpair={props.onUnpair}
            onClearCache={props.onClearCache}
          />
        )}
      </View>

      {/* Bottom Tab Navigation */}
      {!hideChrome && (
        <View
          style={[
            styles.tabBar,
            {
              backgroundColor: tokens.surface,
              borderTopColor: tokens.borderSubtle,
              paddingBottom: Math.max(insets.bottom, 10),
            },
          ]}
        >
          {(
            [
              { id: "OVERVIEW", label: "Overview", Icon: OverviewIcon },
              { id: "CHARTS", label: "Charts", Icon: ChartTabIcon },
              { id: "TRADES", label: "Trades", Icon: TradesTabIcon },
              { id: "SECURITY", label: "Security", Icon: SecurityTabIcon },
            ] as const
          ).map(({ id, label, Icon }) => {
            const active = currentTab === id;
            const tint = active ? tokens.accent : tokens.textDim;
            return (
              <TouchableOpacity
                key={id}
                onPress={() => {
                  triggerSelectionHaptic();
                  onSelectTab(id);
                }}
                style={styles.tabBtn}
                accessibilityRole="tab"
                accessibilityState={{ selected: active }}
                accessibilityLabel={label}
              >
                <Icon size={20} color={tint} />
                <Text
                  style={[
                    styles.tabLabel,
                    { color: tint, fontWeight: active ? "700" : "500" },
                  ]}
                >
                  {label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  header: {
    borderBottomWidth: 1,
  },
  titleRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingBottom: 8,
  },
  brandRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  brandLogo: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: "#000000",
    borderWidth: 1,
  },
  appTitle: {
    fontSize: 16,
    fontWeight: "800",
  },
  statusInlineRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    marginTop: 1,
  },
  connDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  connText: {
    fontSize: 10,
    fontWeight: "600",
  },
  botChip: {
    paddingHorizontal: 5,
    paddingVertical: 1,
    borderRadius: 4,
    marginLeft: 2,
  },
  botChipText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.3,
  },
  headerRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  roBadge: {
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 5,
    borderWidth: 1,
  },
  roText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.5,
  },
  themeBtn: {
    width: 36,
    height: 36,
    borderRadius: 9,
    alignItems: "center",
    justifyContent: "center",
  },
  content: {
    flex: 1,
  },
  tabBar: {
    flexDirection: "row",
    borderTopWidth: 1,
    paddingTop: 8,
  },
  tabBtn: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 48,
    gap: 3,
  },
  tabLabel: {
    fontSize: 11,
  },
});
