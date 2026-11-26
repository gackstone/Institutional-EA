import React, { memo } from "react";
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { KpiCards } from "../components/KpiCards.tsx";
import { EquityCurveCard, type EquityRange } from "../components/EquityCurveCard.tsx";
import { PositionsList } from "../components/PositionsList.tsx";
import { ChartWebView } from "../components/ChartWebView.tsx";
import { formatShortDateTime } from "../utils/formatters.ts";
import type {
  MobileAccount,
  MobileActivityEvent,
  MobileCandlesResponse,
  MobileDrawingsResponse,
  MobileEquityResponse,
  MobilePosition,
  MobileStats,
} from "@institutional-ea/data-contract";
import type { ChartLayerPreferences } from "../services/OfflineCache.ts";

interface OverviewScreenProps {
  theme: ThemeMode;
  account: MobileAccount | null;
  stats: MobileStats | null;
  positions: MobilePosition[];
  equity: MobileEquityResponse | null;
  equityRange: EquityRange;
  onSelectEquityRange: (r: EquityRange) => void;
  candlesData: MobileCandlesResponse | null;
  drawings: MobileDrawingsResponse | null;
  activeSymbol: string | null;
  activeTimeframe: string;
  layers: ChartLayerPreferences;
  activity: MobileActivityEvent[];
  isLoading: boolean;
  isRefreshing: boolean;
  onRefresh: () => void;
  onOpenCharts: () => void;
  onShowPositionOnChart: (pos: MobilePosition) => void;
}

export const OverviewScreen = memo(function OverviewScreen({
  theme,
  account,
  stats,
  positions,
  equity,
  equityRange,
  onSelectEquityRange,
  candlesData,
  drawings,
  activeSymbol,
  activeTimeframe,
  layers,
  activity,
  isLoading,
  isRefreshing,
  onRefresh,
  onOpenCharts,
  onShowPositionOnChart,
}: OverviewScreenProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const currency = account?.currency || stats?.currency || "USD";

  return (
    <ScrollView
      style={styles.scroll}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={isRefreshing}
          onRefresh={onRefresh}
          tintColor={tokens.accent}
          colors={[tokens.accent]}
        />
      }
    >
      {/* KPI Cards */}
      <KpiCards account={account} stats={stats} isLoading={isLoading} theme={theme} />

      {/* Real Equity / PnL Curve */}
      <EquityCurveCard
        equity={equity}
        range={equityRange}
        onSelectRange={onSelectEquityRange}
        isLoading={isLoading}
        theme={theme}
      />

      {/* Mini Live Execution Chart */}
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: tokens.textMuted }]}>
          {activeSymbol
            ? `Live Chart · ${activeSymbol} (${activeTimeframe})`
            : "Live Chart"}
        </Text>
        <TouchableOpacity
          onPress={onOpenCharts}
          accessibilityRole="button"
          accessibilityLabel="Open full interactive chart"
        >
          <Text style={[styles.sectionAction, { color: tokens.accent }]}>Expand →</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        activeOpacity={0.95}
        onPress={onOpenCharts}
        style={[
          styles.miniChartCard,
          { backgroundColor: tokens.chartBackground, borderColor: tokens.border },
        ]}
        accessibilityRole="button"
        accessibilityLabel="Tap to open full interactive chart"
      >
        {activeSymbol && candlesData && candlesData.candles.length > 0 ? (
          <View pointerEvents="none">
            <ChartWebView
              candles={candlesData.candles}
              drawings={drawings}
              symbol={activeSymbol}
              timeframe={activeTimeframe}
              digits={candlesData.digits}
              point={candlesData.point}
              layers={layers}
              theme={theme}
              height={210}
            />
          </View>
        ) : (
          <View style={styles.emptyChartBox}>
            <Text style={[styles.emptyChartText, { color: tokens.textDim }]}>
              {isLoading ? "Loading market candles…" : "Waiting for live candles from companion"}
            </Text>
          </View>
        )}
      </TouchableOpacity>

      {/* Active Positions */}
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: tokens.textMuted }]}>
          Active Positions ({positions.length})
        </Text>
      </View>
      <PositionsList
        positions={positions}
        currency={currency}
        theme={theme}
        onShowOnChart={onShowPositionOnChart}
      />

      {/* Recent Bot Activity Feed */}
      <View style={styles.sectionHeader}>
        <Text style={[styles.sectionTitle, { color: tokens.textMuted }]}>
          Recent Bot Activity ({activity.length})
        </Text>
      </View>
      <View style={styles.activityWrap}>
        {activity.length === 0 ? (
          <View
            style={[
              styles.emptyActivity,
              { backgroundColor: tokens.card, borderColor: tokens.borderSubtle },
            ]}
          >
            <Text style={[styles.emptyChartText, { color: tokens.textDim }]}>
              No recent bot events recorded
            </Text>
          </View>
        ) : (
          activity.slice(0, 12).map((ev) => {
            const sevColor =
              ev.severity === "ERROR" || ev.severity === "CRITICAL"
                ? tokens.loss
                : ev.severity === "WARN" || ev.severity === "WARNING"
                ? tokens.warning
                : tokens.accent;
            return (
              <View
                key={ev.id}
                style={[
                  styles.activityRow,
                  { backgroundColor: tokens.card, borderColor: tokens.borderSubtle },
                ]}
              >
                <View style={[styles.activityDot, { backgroundColor: sevColor }]} />
                <View style={styles.activityBody}>
                  <View style={styles.activityTop}>
                    <Text style={[styles.activityType, { color: sevColor }]}>
                      {ev.type}
                      {ev.symbol ? ` · ${ev.symbol}` : ""}
                    </Text>
                    <Text style={[styles.activityTime, { color: tokens.textDim }]}>
                      {formatShortDateTime(ev.timestamp)}
                    </Text>
                  </View>
                  <Text
                    style={[styles.activityMsg, { color: tokens.text }]}
                    numberOfLines={2}
                  >
                    {ev.message}
                  </Text>
                </View>
              </View>
            );
          })
        )}
      </View>
    </ScrollView>
  );
});

const styles = StyleSheet.create({
  scroll: {
    flex: 1,
  },
  content: {
    paddingTop: 10,
    paddingBottom: 24,
  },
  sectionHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 6,
  },
  sectionTitle: {
    fontSize: 11,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  sectionAction: {
    fontSize: 12,
    fontWeight: "700",
  },
  miniChartCard: {
    marginHorizontal: 12,
    borderRadius: 12,
    borderWidth: 1,
    overflow: "hidden",
    minHeight: 170,
  },
  emptyChartBox: {
    height: 170,
    alignItems: "center",
    justifyContent: "center",
    padding: 16,
  },
  emptyChartText: {
    fontSize: 12,
  },
  activityWrap: {
    paddingHorizontal: 12,
    gap: 6,
  },
  emptyActivity: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 18,
    alignItems: "center",
  },
  activityRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    borderRadius: 10,
    borderWidth: 1,
    padding: 10,
    gap: 9,
  },
  activityDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
    marginTop: 5,
  },
  activityBody: {
    flex: 1,
  },
  activityTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 2,
  },
  activityType: {
    fontSize: 10,
    fontWeight: "700",
  },
  activityTime: {
    fontSize: 10,
    fontFamily: "monospace",
  },
  activityMsg: {
    fontSize: 12,
    lineHeight: 16,
  },
});
