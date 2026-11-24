import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";

export interface KpiData {
  balance: number;
  equity: number;
  todayPnl: number;
  totalProfit: number;
  winRate: number;
  todayTradesCount: number;
  totalDealsCount: number;
  isLoading?: boolean;
}

interface KpiCardsProps {
  data?: KpiData;
  theme?: ThemeMode;
  initialAccountMode?: "balance" | "equity";
  onAccountModeChange?: (mode: "balance" | "equity") => void;
}

export function KpiCards({
  data,
  theme = "dark",
  initialAccountMode = "balance",
  onAccountModeChange,
}: KpiCardsProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const [accountMode, setAccountMode] = useState<"balance" | "equity">(initialAccountMode);

  const toggleAccountMode = (mode: "balance" | "equity") => {
    setAccountMode(mode);
    if (onAccountModeChange) {
      onAccountModeChange(mode);
    }
  };

  const formatCurrency = (val: number | undefined): string => {
    if (val === undefined || isNaN(val)) return "-";
    return `$${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const formatPnl = (val: number | undefined): string => {
    if (val === undefined || isNaN(val)) return "-";
    const prefix = val > 0 ? "+" : "";
    return `${prefix}$${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  const isTodayPositive = (data?.todayPnl ?? 0) >= 0;
  const isTotalPositive = (data?.totalProfit ?? 0) >= 0;

  return (
    <View style={styles.grid}>
      {/* 1. Account Card (Balance | Equity toggle) */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <View style={styles.headerRow}>
          <Text style={[styles.label, { color: tokens.textMuted }]}>Account</Text>
          <View style={[styles.switchContainer, { backgroundColor: tokens.cardSecondary }]}>
            <TouchableOpacity
              onPress={() => toggleAccountMode("balance")}
              style={[
                styles.switchBtn,
                accountMode === "balance" && { backgroundColor: tokens.accent },
              ]}
            >
              <Text
                style={[
                  styles.switchText,
                  { color: accountMode === "balance" ? "#FFF" : tokens.textDim },
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
            >
              <Text
                style={[
                  styles.switchText,
                  { color: accountMode === "equity" ? "#FFF" : tokens.textDim },
                ]}
              >
                Eq
              </Text>
            </TouchableOpacity>
          </View>
        </View>

        <Text style={[styles.bigValue, { color: tokens.text }]}>
          {data?.isLoading ? "..." : formatCurrency(accountMode === "balance" ? data?.balance : data?.equity)}
        </Text>
        <Text style={[styles.caption, { color: tokens.textDim }]}>
          {accountMode === "balance"
            ? `Equity: ${formatCurrency(data?.equity)}`
            : `Balance: ${formatCurrency(data?.balance)}`}
        </Text>
      </View>

      {/* 2. Today P/L Card */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <Text style={[styles.label, { color: tokens.textMuted }]}>Today P/L</Text>
        <Text
          style={[
            styles.bigValue,
            { color: isTodayPositive ? tokens.profit : tokens.loss },
          ]}
        >
          {data?.isLoading ? "..." : formatPnl(data?.todayPnl)}
        </Text>
        <Text style={[styles.caption, { color: tokens.textDim }]}>
          {data ? `${data.todayTradesCount} trades today` : "-"}
        </Text>
      </View>

      {/* 3. Total Profits Card */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <Text style={[styles.label, { color: tokens.textMuted }]}>Total Profits</Text>
        <Text
          style={[
            styles.bigValue,
            { color: isTotalPositive ? tokens.profit : tokens.loss },
          ]}
        >
          {data?.isLoading ? "..." : formatPnl(data?.totalProfit)}
        </Text>
        <Text style={[styles.caption, { color: tokens.textDim }]}>
          {data ? `${data.totalDealsCount} deals total` : "-"}
        </Text>
      </View>

      {/* 4. Win Rate Card */}
      <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
        <Text style={[styles.label, { color: tokens.textMuted }]}>Win Rate</Text>
        <Text style={[styles.bigValue, { color: tokens.text }]}>
          {data?.isLoading ? "..." : data?.winRate !== undefined ? `${data.winRate.toFixed(1)}%` : "-"}
        </Text>
        <Text style={[styles.caption, { color: tokens.textDim }]}>
          Execution accuracy
        </Text>
      </View>
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
    width: "48.5%",
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    marginBottom: 8,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  label: {
    fontSize: 11,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  switchContainer: {
    flexDirection: "row",
    borderRadius: 6,
    padding: 2,
  },
  switchBtn: {
    paddingHorizontal: 6,
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
    marginVertical: 4,
    fontFamily: "monospace",
  },
  caption: {
    fontSize: 10,
  },
});
