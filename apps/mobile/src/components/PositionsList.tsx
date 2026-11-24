import React from "react";
import { View, Text, StyleSheet, FlatList } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import type { Position } from "@institutional-ea/data-contract";

interface PositionsListProps {
  positions: Position[];
  theme?: ThemeMode;
}

export function PositionsList({
  positions,
  theme = "dark",
}: PositionsListProps): React.ReactElement {
  const tokens = getThemeTokens(theme);

  const formatPrice = (val: number | null | undefined): string => {
    if (val === null || val === undefined) return "-";
    return val.toFixed(2);
  };

  const renderPositionItem = ({ item }: { item: Position }) => {
    const isProfit = item.profit >= 0;
    const isBuy = item.type === "BUY";

    return (
      <View
        style={[
          styles.positionCard,
          { backgroundColor: tokens.card, borderColor: tokens.border },
        ]}
      >
        <View style={styles.topRow}>
          <View style={styles.symbolBadge}>
            <Text style={[styles.symbolText, { color: tokens.text }]}>
              {item.symbol}
            </Text>
            <View
              style={[
                styles.typeTag,
                { backgroundColor: isBuy ? tokens.profitBg : tokens.lossBg },
              ]}
            >
              <Text
                style={[
                  styles.typeText,
                  { color: isBuy ? tokens.profit : tokens.loss },
                ]}
              >
                {item.type} {item.volume} lots
              </Text>
            </View>
          </View>

          <Text
            style={[
              styles.profitText,
              { color: isProfit ? tokens.profit : tokens.loss },
            ]}
          >
            {isProfit ? "+" : ""}
            ${item.profit.toFixed(2)}
          </Text>
        </View>

        <View style={styles.detailsRow}>
          <Text style={[styles.detailText, { color: tokens.textDim }]}>
            Open: {formatPrice(item.openPrice)}
          </Text>
          <Text style={[styles.detailText, { color: tokens.textDim }]}>
            Current: {formatPrice(item.currentPrice)}
          </Text>
          <Text style={[styles.detailText, { color: tokens.textDim }]}>
            SL: {formatPrice(item.sl)}
          </Text>
          <Text style={[styles.detailText, { color: tokens.textDim }]}>
            TP: {formatPrice(item.tp)}
          </Text>
        </View>
      </View>
    );
  };

  if (positions.length === 0) {
    return (
      <View style={styles.emptyContainer}>
        <Text style={[styles.emptyText, { color: tokens.textDim }]}>
          No active positions running
        </Text>
      </View>
    );
  }

  return (
    <FlatList
      data={positions}
      keyExtractor={(item) => String(item.ticket)}
      renderItem={renderPositionItem}
      contentContainerStyle={styles.listContent}
    />
  );
}

const styles = StyleSheet.create({
  listContent: {
    paddingHorizontal: 12,
    paddingBottom: 24,
  },
  positionCard: {
    borderRadius: 8,
    borderWidth: 1,
    padding: 12,
    marginBottom: 8,
  },
  topRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 8,
  },
  symbolBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  symbolText: {
    fontSize: 14,
    fontWeight: "700",
  },
  typeTag: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  typeText: {
    fontSize: 11,
    fontWeight: "600",
  },
  profitText: {
    fontSize: 14,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  detailsRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  detailText: {
    fontSize: 11,
    fontFamily: "monospace",
  },
  emptyContainer: {
    padding: 24,
    alignItems: "center",
  },
  emptyText: {
    fontSize: 13,
  },
});
