import React, { memo, useMemo } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import Svg, { Defs, LinearGradient, Path, Stop } from "react-native-svg";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { formatSignedPnl } from "../utils/formatters.ts";
import { triggerSelectionHaptic } from "../services/haptics.ts";
import type { MobileEquityResponse } from "@institutional-ea/data-contract";

export type EquityRange = "1D" | "1W" | "1M" | "ALL";
const RANGES: EquityRange[] = ["1D", "1W", "1M", "ALL"];

interface EquityCurveCardProps {
  equity: MobileEquityResponse | null;
  range: EquityRange;
  onSelectRange: (r: EquityRange) => void;
  isLoading: boolean;
  theme: ThemeMode;
}

export const EquityCurveCard = memo(function EquityCurveCard({
  equity,
  range,
  onSelectRange,
  isLoading,
  theme,
}: EquityCurveCardProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const points = equity?.points ?? [];
  const currency = equity?.currency ?? "USD";

  const { linePath, areaPath, deltaPnl } = useMemo(() => {
    if (points.length < 2) {
      return { linePath: "", areaPath: "", deltaPnl: points[0]?.pnl ?? 0 };
    }
    const w = 300;
    const h = 88;
    const padY = 8;
    const vals = points.map((p) => p.equity);
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const span = max - min || 1;

    const coords = points.map((p, idx) => {
      const x = (idx / (points.length - 1)) * w;
      const y = padY + (1 - (p.equity - min) / span) * (h - padY * 2);
      return { x, y };
    });

    const line = coords
      .map((c, idx) => `${idx === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`)
      .join(" ");
    const area = `${line} L${w},${h} L0,${h} Z`;
    const delta = points[points.length - 1].equity - points[0].equity;
    return { linePath: line, areaPath: area, deltaPnl: delta };
  }, [points]);

  const strokeColor = deltaPnl >= 0 ? tokens.profit : tokens.loss;

  return (
    <View style={[styles.card, { backgroundColor: tokens.card, borderColor: tokens.border }]}>
      <View style={styles.headerRow}>
        <View>
          <Text style={[styles.title, { color: tokens.textMuted }]}>Equity Curve</Text>
          <Text
            style={[
              styles.deltaText,
              { color: points.length >= 2 ? strokeColor : tokens.textDim },
            ]}
          >
            {points.length >= 2 ? formatSignedPnl(deltaPnl, currency) : "No history yet"}
          </Text>
        </View>
        <View style={[styles.rangeGroup, { backgroundColor: tokens.cardSecondary }]}>
          {RANGES.map((r) => {
            const active = range === r;
            return (
              <TouchableOpacity
                key={r}
                onPress={() => {
                  triggerSelectionHaptic();
                  onSelectRange(r);
                }}
                style={[styles.rangeChip, active && { backgroundColor: tokens.accent }]}
                accessibilityRole="button"
                accessibilityLabel={`Equity curve range ${r}`}
              >
                <Text
                  style={[
                    styles.rangeText,
                    { color: active ? tokens.accentText : tokens.textDim },
                  ]}
                >
                  {r}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>

      {isLoading && points.length === 0 ? (
        <View style={[styles.emptyBox, { backgroundColor: tokens.cardSecondary }]} />
      ) : points.length < 2 ? (
        <View style={styles.emptyTextBox}>
          <Text style={[styles.emptyText, { color: tokens.textDim }]}>
            Waiting for equity snapshots from companion
          </Text>
        </View>
      ) : (
        <View style={styles.svgWrap}>
          <Svg width="100%" height={88} viewBox="0 0 300 88" preserveAspectRatio="none">
            <Defs>
              <LinearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                <Stop offset="0" stopColor={strokeColor} stopOpacity="0.28" />
                <Stop offset="1" stopColor={strokeColor} stopOpacity="0.01" />
              </LinearGradient>
            </Defs>
            <Path d={areaPath} fill="url(#eqGrad)" />
            <Path d={linePath} stroke={strokeColor} strokeWidth={2} fill="none" />
          </Svg>
        </View>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 12,
    marginTop: 10,
    borderRadius: 12,
    borderWidth: 1,
    padding: 12,
  },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 8,
  },
  title: {
    fontSize: 10,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.6,
  },
  deltaText: {
    fontSize: 15,
    fontWeight: "700",
    fontFamily: "monospace",
    marginTop: 2,
  },
  rangeGroup: {
    flexDirection: "row",
    borderRadius: 8,
    padding: 2,
    gap: 2,
  },
  rangeChip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  rangeText: {
    fontSize: 10,
    fontWeight: "700",
  },
  svgWrap: {
    height: 88,
    width: "100%",
  },
  emptyBox: {
    height: 72,
    borderRadius: 8,
    opacity: 0.5,
  },
  emptyTextBox: {
    height: 64,
    justifyContent: "center",
    alignItems: "center",
  },
  emptyText: {
    fontSize: 11,
  },
});
