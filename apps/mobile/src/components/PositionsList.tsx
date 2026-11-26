import React, { memo, useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity, Modal, Pressable } from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import {
  computeSlTpDistance,
  formatDuration,
  formatPrice,
  formatSignedPnl,
} from "../utils/formatters.ts";
import { triggerSelectionHaptic } from "../services/haptics.ts";
import type { MobilePosition } from "@institutional-ea/data-contract";

interface PositionsListProps {
  positions: MobilePosition[];
  currency?: string;
  theme?: ThemeMode;
  onShowOnChart?: (pos: MobilePosition) => void;
}

export const PositionsList = memo(function PositionsList({
  positions,
  currency = "USD",
  theme = "dark",
  onShowOnChart,
}: PositionsListProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const [selected, setSelected] = useState<MobilePosition | null>(null);
  const nowSec = Math.floor(Date.now() / 1000);

  if (positions.length === 0) {
    return (
      <View
        style={[
          styles.emptyContainer,
          { backgroundColor: tokens.card, borderColor: tokens.borderSubtle },
        ]}
      >
        <Text style={[styles.emptyText, { color: tokens.textDim }]}>
          No active open positions
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.listWrap}>
      {positions.map((item) => {
        const isProfit = item.profit >= 0;
        const isBuy = item.type === "BUY";
        const durationSec = item.openTime > 0 ? Math.max(0, nowSec - item.openTime) : null;
        const slDist = computeSlTpDistance(item.currentPrice, item.sl, item.digits);
        const tpDist = computeSlTpDistance(item.currentPrice, item.tp, item.digits);

        return (
          <TouchableOpacity
            key={String(item.ticket)}
            activeOpacity={0.85}
            onPress={() => {
              triggerSelectionHaptic();
              setSelected(item);
            }}
            style={[
              styles.positionCard,
              { backgroundColor: tokens.card, borderColor: tokens.border },
            ]}
            accessibilityRole="button"
            accessibilityLabel={`${item.canonicalSymbol} ${item.type} ${item.volume} lots`}
          >
            <View style={styles.topRow}>
              <View style={styles.symbolBadge}>
                <Text style={[styles.symbolText, { color: tokens.text }]}>
                  {item.canonicalSymbol}
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
                    {item.type} {item.volume}
                  </Text>
                </View>
                {durationSec !== null && (
                  <Text style={[styles.durationTag, { color: tokens.textDim }]}>
                    {formatDuration(durationSec)}
                  </Text>
                )}
              </View>

              <Text
                style={[
                  styles.profitText,
                  { color: isProfit ? tokens.profit : tokens.loss },
                ]}
              >
                {formatSignedPnl(item.profit, currency)}
              </Text>
            </View>

            <View style={styles.detailsRow}>
              <Text style={[styles.detailText, { color: tokens.textDim }]}>
                Open {formatPrice(item.openPrice, item.digits)}
              </Text>
              <Text style={[styles.detailText, { color: tokens.textMuted }]}>
                Now {formatPrice(item.currentPrice, item.digits)}
              </Text>
              <Text style={[styles.detailText, { color: tokens.loss }]}>
                SL {item.sl ? `${formatPrice(item.sl, item.digits)} (${slDist})` : "—"}
              </Text>
              <Text style={[styles.detailText, { color: tokens.profit }]}>
                TP {item.tp ? `${formatPrice(item.tp, item.digits)} (${tpDist})` : "—"}
              </Text>
            </View>
          </TouchableOpacity>
        );
      })}

      {/* Position Detail Bottom Sheet */}
      <Modal
        visible={selected !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setSelected(null)}
      >
        <Pressable
          style={[styles.modalBackdrop, { backgroundColor: tokens.overlayBg }]}
          onPress={() => setSelected(null)}
        >
          <Pressable
            style={[styles.sheet, { backgroundColor: tokens.surface, borderColor: tokens.border }]}
            onPress={() => {}}
          >
            {selected && (
              <>
                <View style={[styles.sheetHandle, { backgroundColor: tokens.border }]} />
                <View style={styles.sheetHeader}>
                  <Text style={[styles.sheetTitle, { color: tokens.text }]}>
                    {selected.canonicalSymbol} · #{selected.ticket}
                  </Text>
                  <Text
                    style={[
                      styles.sheetPnl,
                      { color: selected.profit >= 0 ? tokens.profit : tokens.loss },
                    ]}
                  >
                    {formatSignedPnl(selected.profit, currency)}
                  </Text>
                </View>

                <View style={styles.sheetRows}>
                  <Row label="Side / Lots" value={`${selected.type} · ${selected.volume} lots`} tokens={tokens} />
                  <Row label="Entry Price" value={formatPrice(selected.openPrice, selected.digits)} tokens={tokens} />
                  <Row label="Current Price" value={formatPrice(selected.currentPrice, selected.digits)} tokens={tokens} />
                  <Row label="Stop Loss" value={formatPrice(selected.sl, selected.digits)} tokens={tokens} />
                  <Row label="Take Profit" value={formatPrice(selected.tp, selected.digits)} tokens={tokens} />
                  <Row label="Swap" value={formatSignedPnl(selected.swap, currency)} tokens={tokens} />
                  <Row label="Ownership" value={selected.ownership} tokens={tokens} />
                  {selected.comment ? (
                    <Row label="Tag" value={selected.comment} tokens={tokens} />
                  ) : null}
                </View>

                <View style={styles.sheetActions}>
                  {onShowOnChart && (
                    <TouchableOpacity
                      onPress={() => {
                        const p = selected;
                        setSelected(null);
                        onShowOnChart(p);
                      }}
                      style={[styles.primaryBtn, { backgroundColor: tokens.accent }]}
                      accessibilityRole="button"
                      accessibilityLabel="Show position on chart"
                    >
                      <Text style={[styles.primaryBtnText, { color: tokens.accentText }]}>
                        Show on Chart
                      </Text>
                    </TouchableOpacity>
                  )}
                  <TouchableOpacity
                    onPress={() => setSelected(null)}
                    style={[styles.secondaryBtn, { backgroundColor: tokens.cardSecondary }]}
                    accessibilityRole="button"
                    accessibilityLabel="Close position details"
                  >
                    <Text style={[styles.secondaryBtnText, { color: tokens.text }]}>Close</Text>
                  </TouchableOpacity>
                </View>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
});

function Row({
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
  listWrap: {
    paddingHorizontal: 12,
  },
  positionCard: {
    borderRadius: 10,
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
    paddingHorizontal: 7,
    paddingVertical: 2,
    borderRadius: 5,
  },
  typeText: {
    fontSize: 11,
    fontWeight: "700",
  },
  durationTag: {
    fontSize: 10,
    fontFamily: "monospace",
  },
  profitText: {
    fontSize: 15,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  detailsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    gap: 6,
  },
  detailText: {
    fontSize: 10,
    fontFamily: "monospace",
  },
  emptyContainer: {
    marginHorizontal: 12,
    borderRadius: 10,
    borderWidth: 1,
    padding: 20,
    alignItems: "center",
  },
  emptyText: {
    fontSize: 12,
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
  sheetHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 12,
  },
  sheetTitle: {
    fontSize: 16,
    fontWeight: "700",
  },
  sheetPnl: {
    fontSize: 17,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  sheetRows: {
    marginBottom: 16,
  },
  detailRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 8,
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
  sheetActions: {
    flexDirection: "row",
    gap: 10,
  },
  primaryBtn: {
    flex: 1,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
    minHeight: 44,
  },
  primaryBtnText: {
    fontSize: 14,
    fontWeight: "700",
  },
  secondaryBtn: {
    flex: 1,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
    minHeight: 44,
  },
  secondaryBtnText: {
    fontSize: 14,
    fontWeight: "700",
  },
});
