import React, { memo, useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Modal, Pressable } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { formatCurrency, formatPercent, formatSignedPnl } from "../utils/formatters.ts";
import { triggerSelectionHaptic } from "../services/haptics.ts";
import type { MobileAccount, MobileStats } from "@institutional-ea/data-contract";

interface KpiCardsProps {
  account: MobileAccount | null;
  stats: MobileStats | null;
  isLoading: boolean;
  theme?: ThemeMode;
}

type DetailCardKey = "account" | "today" | "total" | "winrate" | null;

export const KpiCards = memo(function KpiCards({
  account,
  stats,
  isLoading,
  theme = "dark",
}: KpiCardsProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const [accountMode, setAccountMode] = useState<"balance" | "equity">("balance");
  const [detailCard, setDetailCard] = useState<DetailCardKey>(null);

  const currency = account?.currency || stats?.currency || "USD";

  const toggleAccountMode = (mode: "balance" | "equity") => {
    setAccountMode(mode);
    triggerSelectionHaptic();
  };

  const openDetail = (key: DetailCardKey) => {
    setDetailCard(key);
    triggerSelectionHaptic();
  };

  const isTodayPositive = (stats?.todayPnl ?? 0) >= 0;
  const isTotalPositive = (stats?.totalProfit ?? 0) >= 0;
  const isFloatingPositive = (account?.floatingPnl ?? 0) >= 0;

  const renderSkeleton = () => (
    <View style={[styles.skeletonBar, { backgroundColor: tokens.cardSecondary }]} />
  );

  return (
    <View>
      <View style={styles.grid}>
        {/* 1. Account Card (Balance | Equity switch) */}
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => openDetail("account")}
          style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}
          accessibilityRole="button"
          accessibilityLabel="Account balance and equity details"
        >
          <View style={styles.headerRow}>
            <Text style={[styles.label, { color: tokens.textMuted }]}>Account</Text>
            <View style={[styles.switchContainer, { backgroundColor: tokens.cardSecondary }]}>
              <TouchableOpacity
                onPress={() => toggleAccountMode("balance")}
                style={[
                  styles.switchBtn,
                  accountMode === "balance" && { backgroundColor: tokens.accent },
                ]}
                accessibilityRole="button"
                accessibilityLabel="Show Balance"
              >
                <Text
                  style={[
                    styles.switchText,
                    { color: accountMode === "balance" ? tokens.accentText : tokens.textDim },
                  ]}
                >
                  Bal
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => toggleAccountMode("equity")}
                style={[
                  styles.switchBtn,
                  accountMode === "equity" && { backgroundColor: tokens.accent },
                ]}
                accessibilityRole="button"
                accessibilityLabel="Show Equity"
              >
                <Text
                  style={[
                    styles.switchText,
                    { color: accountMode === "equity" ? tokens.accentText : tokens.textDim },
                  ]}
                >
                  Eq
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          {isLoading && !account ? (
            renderSkeleton()
          ) : (
            <Text style={[styles.bigValue, { color: tokens.text }]} numberOfLines={1} adjustsFontSizeToFit>
              {account
                ? formatCurrency(accountMode === "balance" ? account.balance : account.equity, currency)
                : "—"}
            </Text>
          )}
          <Text style={[styles.caption, { color: tokens.textDim }]} numberOfLines={1}>
            {account
              ? accountMode === "balance"
                ? `Eq ${formatCurrency(account.equity, currency)}`
                : `Bal ${formatCurrency(account.balance, currency)}`
              : "Waiting for companion"}
          </Text>
        </TouchableOpacity>

        {/* 2. Today P/L Card */}
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => openDetail("today")}
          style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}
          accessibilityRole="button"
          accessibilityLabel="Today profit and loss details"
        >
          <Text style={[styles.label, { color: tokens.textMuted }]}>Today P/L</Text>
          {isLoading && !stats ? (
            renderSkeleton()
          ) : (
            <Text
              style={[
                styles.bigValue,
                { color: stats ? (isTodayPositive ? tokens.profit : tokens.loss) : tokens.textMuted },
              ]}
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              {stats ? formatSignedPnl(stats.todayPnl, currency) : "—"}
            </Text>
          )}
          <Text style={[styles.caption, { color: tokens.textDim }]}>
            {stats ? `${stats.tradesToday} trades today` : "No deals synced"}
          </Text>
        </TouchableOpacity>

        {/* 3. Total Profits Card */}
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => openDetail("total")}
          style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}
          accessibilityRole="button"
          accessibilityLabel="Total profits details"
        >
          <Text style={[styles.label, { color: tokens.textMuted }]}>Total Profits</Text>
          {isLoading && !stats ? (
            renderSkeleton()
          ) : (
            <Text
              style={[
                styles.bigValue,
                { color: stats ? (isTotalPositive ? tokens.profit : tokens.loss) : tokens.textMuted },
              ]}
              numberOfLines={1}
              adjustsFontSizeToFit
            >
              {stats ? formatSignedPnl(stats.totalProfit, currency) : "—"}
            </Text>
          )}
          <Text style={[styles.caption, { color: tokens.textDim }]}>
            {stats ? `${stats.dealsCount} deals total` : "No history yet"}
          </Text>
        </TouchableOpacity>

        {/* 4. Win Rate Card */}
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => openDetail("winrate")}
          style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}
          accessibilityRole="button"
          accessibilityLabel="Win rate details"
        >
          <Text style={[styles.label, { color: tokens.textMuted }]}>Win Rate</Text>
          {isLoading && !stats ? (
            renderSkeleton()
          ) : (
            <Text style={[styles.bigValue, { color: tokens.text }]}>
              {stats ? formatPercent(stats.winRate, 1) : "—"}
            </Text>
          )}
          <Text style={[styles.caption, { color: tokens.textDim }]}>
            {stats ? `${stats.winsCount}W / ${stats.lossesCount}L` : "Execution accuracy"}
          </Text>
        </TouchableOpacity>
      </View>

      {/* Compact Secondary Strip: Floating P/L · Margin Level · Open Positions */}
      <View
        style={[
          styles.secondaryStrip,
          { backgroundColor: tokens.card, borderColor: tokens.borderSubtle },
        ]}
      >
        <View style={styles.stripItem}>
          <Text style={[styles.stripLabel, { color: tokens.textDim }]}>Floating P/L</Text>
          <Text
            style={[
              styles.stripValue,
              {
                color: account
                  ? isFloatingPositive
                    ? tokens.profit
                    : tokens.loss
                  : tokens.textMuted,
              },
            ]}
          >
            {account ? formatSignedPnl(account.floatingPnl, currency) : "—"}
          </Text>
        </View>
        <View style={[styles.stripDivider, { backgroundColor: tokens.borderSubtle }]} />
        <View style={styles.stripItem}>
          <Text style={[styles.stripLabel, { color: tokens.textDim }]}>Margin Level</Text>
          <Text style={[styles.stripValue, { color: tokens.text }]}>
            {account
              ? account.marginLevel > 0
                ? formatPercent(account.marginLevel, 0)
                : account.margin === 0 && account.openPositionsCount === 0
                ? "n/a"
                : "—"
              : "—"}
          </Text>
        </View>
        <View style={[styles.stripDivider, { backgroundColor: tokens.borderSubtle }]} />
        <View style={styles.stripItem}>
          <Text style={[styles.stripLabel, { color: tokens.textDim }]}>Open Positions</Text>
          <Text style={[styles.stripValue, { color: tokens.accent }]}>
            {account ? String(account.openPositionsCount) : "—"}
          </Text>
        </View>
      </View>

      {/* KPI Detail Bottom Sheet */}
      <Modal
        visible={detailCard !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setDetailCard(null)}
      >
        <Pressable
          style={[styles.modalBackdrop, { backgroundColor: tokens.overlayBg }]}
          onPress={() => setDetailCard(null)}
        >
          <Pressable
            style={[styles.sheet, { backgroundColor: tokens.surface, borderColor: tokens.border }]}
            onPress={() => {}}
          >
            <View style={[styles.sheetHandle, { backgroundColor: tokens.border }]} />
            <Text style={[styles.sheetTitle, { color: tokens.text }]}>
              {detailCard === "account"
                ? "Account Overview"
                : detailCard === "today"
                ? "Today Performance"
                : detailCard === "total"
                ? "Cumulative Performance"
                : "Win Rate Breakdown"}
            </Text>

            {detailCard === "account" && (
              <View style={styles.sheetRows}>
                <DetailRow label="Broker" value={account?.broker || "—"} tokens={tokens} />
                <DetailRow label="Account" value={account?.accountMasked || "—"} tokens={tokens} />
                <DetailRow label="Mode" value={account?.tradeMode || "—"} tokens={tokens} />
                <DetailRow label="Balance" value={formatCurrency(account?.balance, currency)} tokens={tokens} />
                <DetailRow label="Equity" value={formatCurrency(account?.equity, currency)} tokens={tokens} />
                <DetailRow label="Margin Used" value={formatCurrency(account?.margin, currency)} tokens={tokens} />
                <DetailRow label="Free Margin" value={formatCurrency(account?.freeMargin, currency)} tokens={tokens} />
                <DetailRow
                  label="Leverage"
                  value={account?.leverage ? `1:${account.leverage}` : "—"}
                  tokens={tokens}
                />
              </View>
            )}

            {detailCard === "today" && (
              <View style={styles.sheetRows}>
                <DetailRow label="Today Realized P/L" value={formatSignedPnl(stats?.todayPnl, currency)} tokens={tokens} />
                <DetailRow label="Trades Closed Today" value={String(stats?.tradesToday ?? 0)} tokens={tokens} />
                <DetailRow label="Floating P/L" value={formatSignedPnl(account?.floatingPnl, currency)} tokens={tokens} />
                <DetailRow label="Currency" value={currency} tokens={tokens} />
              </View>
            )}

            {detailCard === "total" && (
              <View style={styles.sheetRows}>
                <DetailRow label="Total Realized Profit" value={formatSignedPnl(stats?.totalProfit, currency)} tokens={tokens} />
                <DetailRow label="Total Closed Deals" value={String(stats?.dealsCount ?? 0)} tokens={tokens} />
                <DetailRow label="Winning Deals" value={String(stats?.winsCount ?? 0)} tokens={tokens} />
                <DetailRow label="Losing Deals" value={String(stats?.lossesCount ?? 0)} tokens={tokens} />
              </View>
            )}

            {detailCard === "winrate" && (
              <View style={styles.sheetRows}>
                <DetailRow label="Win Rate" value={formatPercent(stats?.winRate, 2)} tokens={tokens} />
                <DetailRow label="Wins" value={String(stats?.winsCount ?? 0)} tokens={tokens} />
                <DetailRow label="Losses" value={String(stats?.lossesCount ?? 0)} tokens={tokens} />
                <DetailRow label="Total Deals" value={String(stats?.dealsCount ?? 0)} tokens={tokens} />
              </View>
            )}

            <TouchableOpacity
              onPress={() => setDetailCard(null)}
              style={[styles.closeBtn, { backgroundColor: tokens.cardSecondary }]}
              accessibilityRole="button"
              accessibilityLabel="Close details"
            >
              <Text style={[styles.closeBtnText, { color: tokens.text }]}>Done</Text>
            </TouchableOpacity>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
});

function DetailRow({
  label,
  value,
  tokens,
}: {
  label: string;
  value: string;
  tokens: ReturnType<typeof getThemeTokens>;
}) {
  return (
    <View style={[styles.detailRow, { borderBottomColor: tokens.borderSubtle }]}>
      <Text style={[styles.detailLabel, { color: tokens.textMuted }]}>{label}</Text>
      <Text style={[styles.detailValue, { color: tokens.text }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    paddingHorizontal: 12,
    gap: 8,
  },
  card: {
    width: "48.6%",
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
    marginBottom: 4,
    minHeight: 88,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  label: {
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  switchContainer: {
    flexDirection: "row",
    borderRadius: 6,
    padding: 2,
  },
  switchBtn: {
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 4,
  },
  switchText: {
    fontSize: 9,
    fontWeight: "700",
  },
  bigValue: {
    fontSize: 18,
    fontWeight: "700",
    marginVertical: 5,
    fontFamily: "monospace",
  },
  caption: {
    fontSize: 10,
  },
  skeletonBar: {
    height: 22,
    width: "75%",
    borderRadius: 6,
    marginVertical: 6,
  },
  secondaryStrip: {
    flexDirection: "row",
    alignItems: "center",
    marginHorizontal: 12,
    marginTop: 4,
    borderRadius: 10,
    borderWidth: 1,
    paddingVertical: 9,
    paddingHorizontal: 8,
  },
  stripItem: {
    flex: 1,
    alignItems: "center",
  },
  stripLabel: {
    fontSize: 9,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
  stripValue: {
    fontSize: 13,
    fontWeight: "700",
    fontFamily: "monospace",
    marginTop: 2,
  },
  stripDivider: {
    width: 1,
    height: 24,
  },
  modalBackdrop: {
    flex: 1,
    justifyContent: "flex-end",
  },
  sheet: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderTopWidth: 1,
    padding: 20,
    paddingBottom: 28,
  },
  sheetHandle: {
    width: 38,
    height: 4,
    borderRadius: 2,
    alignSelf: "center",
    marginBottom: 14,
  },
  sheetTitle: {
    fontSize: 16,
    fontWeight: "700",
    marginBottom: 12,
  },
  sheetRows: {
    marginBottom: 16,
  },
  detailRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 9,
    borderBottomWidth: 1,
  },
  detailLabel: {
    fontSize: 13,
  },
  detailValue: {
    fontSize: 13,
    fontWeight: "600",
    fontFamily: "monospace",
  },
  closeBtn: {
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
    minHeight: 44,
  },
  closeBtnText: {
    fontSize: 14,
    fontWeight: "700",
  },
});
