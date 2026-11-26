import React, { memo, useCallback, useMemo, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Modal,
  Pressable,
  useWindowDimensions,
} from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import {
  ChartWebView,
  type ChartWebViewHandle,
  type CrosshairData,
} from "../components/ChartWebView.tsx";
import { FullscreenIcon, ResetIcon } from "../components/Icons.tsx";
import { formatPrice } from "../utils/formatters.ts";
import { triggerSelectionHaptic } from "../services/haptics.ts";
import type {
  MobileCandlesResponse,
  MobileDrawingsResponse,
  MobileSymbolSpec,
} from "@institutional-ea/data-contract";
import type { ChartLayerPreferences } from "../services/OfflineCache.ts";

interface ChartsScreenProps {
  theme: ThemeMode;
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
  isLive: boolean;
  isLoading: boolean;
  focusTime: number | null;
  isFullscreen: boolean;
  onToggleFullscreen: () => void;
  onLoadMoreHistory: (beforeTime: number) => void;
}

const LAYER_CHIPS: Array<{
  key: keyof ChartLayerPreferences;
  label: string;
  countKeys: string[];
}> = [
  { key: "liquidity", label: "Liq", countKeys: ["LIQ"] },
  { key: "fvgOb", label: "FVG/OB", countKeys: ["FVG", "OB"] },
  { key: "structure", label: "Struct", countKeys: ["STRUCT"] },
  { key: "sessions", label: "Sess", countKeys: ["SESS"] },
  { key: "trades", label: "Trades", countKeys: ["TRADE"] },
];

export const ChartsScreen = memo(function ChartsScreen({
  theme,
  symbols,
  timeframes,
  selectedSymbol,
  selectedTimeframe,
  onSelectSymbol,
  onSelectTimeframe,
  candlesData,
  drawings,
  layers,
  onToggleLayer,
  isLive,
  isLoading,
  focusTime,
  isFullscreen,
  onToggleFullscreen,
  onLoadMoreHistory,
}: ChartsScreenProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const chartRef = useRef<ChartWebViewHandle>(null);
  const [crosshair, setCrosshair] = useState<CrosshairData | null>(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const { width, height } = useWindowDimensions();
  const isLandscape = width > height;

  const digits = candlesData?.digits ?? 2;
  const lastCandle = useMemo(() => {
    const arr = candlesData?.candles ?? [];
    return arr.length > 0 ? arr[arr.length - 1] : null;
  }, [candlesData]);

  const activeOhlc = crosshair ?? lastCandle;

  const getLayerCount = useCallback(
    (countKeys: string[]): number => {
      if (!drawings) return 0;
      if (drawings.counts) {
        return countKeys.reduce((acc, k) => acc + Number(drawings.counts?.[k] ?? 0), 0);
      }
      return drawings.items.filter((i) => countKeys.includes(i.type)).length;
    },
    [drawings]
  );

  return (
    <View style={[styles.container, { backgroundColor: tokens.background }]}>
      {/* Symbol Tabs + Action Controls */}
      <View
        style={[
          styles.topControlRow,
          { backgroundColor: tokens.surface, borderBottomColor: tokens.borderSubtle },
        ]}
      >
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipScroll}
        >
          {symbols.length === 0 ? (
            <Text style={[styles.emptyChipText, { color: tokens.textDim }]}>
              Waiting for symbols…
            </Text>
          ) : (
            symbols.map((s) => {
              const active = s.symbol === selectedSymbol;
              return (
                <TouchableOpacity
                  key={s.symbol}
                  onPress={() => {
                    triggerSelectionHaptic();
                    onSelectSymbol(s.symbol);
                  }}
                  style={[
                    styles.symbolTab,
                    {
                      backgroundColor: active ? tokens.accent : tokens.cardSecondary,
                      borderColor: active ? tokens.accent : tokens.borderSubtle,
                    },
                  ]}
                  accessibilityRole="tab"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={`Symbol ${s.symbol}`}
                >
                  <Text
                    style={[
                      styles.symbolTabText,
                      { color: active ? tokens.accentText : tokens.text },
                    ]}
                  >
                    {s.symbol}
                  </Text>
                </TouchableOpacity>
              );
            })
          )}
        </ScrollView>

        <View style={styles.topActions}>
          <TouchableOpacity
            onPress={() => {
              triggerSelectionHaptic();
              chartRef.current?.resetView();
            }}
            style={[styles.iconBtn, { backgroundColor: tokens.cardSecondary }]}
            accessibilityRole="button"
            accessibilityLabel="Reset chart view"
          >
            <ResetIcon size={15} color={tokens.textMuted} />
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => {
              triggerSelectionHaptic();
              onToggleFullscreen();
            }}
            style={[
              styles.iconBtn,
              { backgroundColor: isFullscreen ? tokens.accentLight : tokens.cardSecondary },
            ]}
            accessibilityRole="button"
            accessibilityLabel={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
          >
            <FullscreenIcon size={15} color={isFullscreen ? tokens.accent : tokens.textMuted} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Timeframes + Bid/Ask/Spread + LIVE strip */}
      <View
        style={[
          styles.metaRow,
          { backgroundColor: tokens.surface, borderBottomColor: tokens.borderSubtle },
        ]}
      >
        <View style={styles.tfRow}>
          {timeframes.map((tf) => {
            const active = tf === selectedTimeframe;
            return (
              <TouchableOpacity
                key={tf}
                onPress={() => {
                  triggerSelectionHaptic();
                  onSelectTimeframe(tf);
                }}
                style={[
                  styles.tfChip,
                  active && { backgroundColor: tokens.accentLight, borderColor: tokens.accent },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`Timeframe ${tf}`}
              >
                <Text
                  style={[
                    styles.tfText,
                    { color: active ? tokens.accent : tokens.textMuted },
                  ]}
                >
                  {tf}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={styles.quoteRight}>
          {candlesData?.bid !== null && candlesData?.bid !== undefined && (
            <Text style={[styles.quoteText, { color: tokens.textMuted }]}>
              B {formatPrice(candlesData.bid, digits)} · A {formatPrice(candlesData.ask, digits)}
              {candlesData.spreadPoints !== null ? ` · Sp ${candlesData.spreadPoints}` : ""}
            </Text>
          )}
          <View
            style={[
              styles.livePill,
              { backgroundColor: isLive ? tokens.profitBg : tokens.warningBg },
            ]}
          >
            <View
              style={[
                styles.liveDot,
                { backgroundColor: isLive ? tokens.profit : tokens.warning },
              ]}
            />
            <Text
              style={[
                styles.livePillText,
                { color: isLive ? tokens.profit : tokens.warning },
              ]}
            >
              {isLive ? "LIVE" : "CACHED"}
            </Text>
          </View>
        </View>
      </View>

      {/* Layer Toggle Chips (hidden only in compact landscape fullscreen to maximize chart height) */}
      {!(isFullscreen && isLandscape) && (
        <View
          style={[
            styles.layerBar,
            { backgroundColor: tokens.background, borderBottomColor: tokens.borderSubtle },
          ]}
        >
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipScroll}
          >
            {LAYER_CHIPS.map((chip) => {
              const active = layers[chip.key];
              const count = getLayerCount(chip.countKeys);
              return (
                <TouchableOpacity
                  key={chip.key}
                  onPress={() => {
                    triggerSelectionHaptic();
                    onToggleLayer(chip.key);
                  }}
                  style={[
                    styles.layerChip,
                    {
                      backgroundColor: active ? tokens.accentLight : tokens.card,
                      borderColor: active ? tokens.accent : tokens.borderSubtle,
                    },
                  ]}
                  accessibilityRole="switch"
                  accessibilityState={{ checked: active }}
                  accessibilityLabel={`${chip.label} layer (${count})`}
                >
                  <Text
                    style={[
                      styles.layerChipText,
                      { color: active ? tokens.accent : tokens.textDim },
                    ]}
                  >
                    {chip.label} ({count})
                  </Text>
                </TouchableOpacity>
              );
            })}
            <TouchableOpacity
              onPress={() => {
                triggerSelectionHaptic();
                setLegendOpen(true);
              }}
              style={[
                styles.layerChip,
                { backgroundColor: tokens.card, borderColor: tokens.borderSubtle },
              ]}
              accessibilityRole="button"
              accessibilityLabel="Open zone legend"
            >
              <Text style={[styles.layerChipText, { color: tokens.textMuted }]}>Legend ?</Text>
            </TouchableOpacity>
          </ScrollView>
        </View>
      )}

      {/* OHLC Crosshair Strip */}
      {activeOhlc && (
        <View style={[styles.ohlcStrip, { backgroundColor: tokens.chartBackground }]}>
          <Text style={[styles.ohlcText, { color: tokens.textDim }]}>
            O <Text style={{ color: tokens.text }}>{formatPrice(activeOhlc.open, digits)}</Text>
            {"  "}H <Text style={{ color: tokens.profit }}>{formatPrice(activeOhlc.high, digits)}</Text>
            {"  "}L <Text style={{ color: tokens.loss }}>{formatPrice(activeOhlc.low, digits)}</Text>
            {"  "}C <Text style={{ color: tokens.text }}>{formatPrice(activeOhlc.close, digits)}</Text>
          </Text>
        </View>
      )}

      {/* Main Interactive Chart Canvas */}
      <View style={styles.chartHost}>
        {selectedSymbol && candlesData && candlesData.candles.length > 0 ? (
          <ChartWebView
            ref={chartRef}
            candles={candlesData.candles}
            drawings={drawings}
            symbol={selectedSymbol}
            timeframe={selectedTimeframe}
            digits={digits}
            point={candlesData.point}
            layers={layers}
            theme={theme}
            height="flex"
            focusTime={focusTime}
            onCrosshairChange={setCrosshair}
            onLoadMoreHistory={onLoadMoreHistory}
          />
        ) : (
          <View style={[styles.emptyChart, { backgroundColor: tokens.chartBackground }]}>
            <Text style={[styles.emptyText, { color: tokens.textMuted }]}>
              {isLoading
                ? "Fetching candles & bot SMC analysis…"
                : "No candles available from companion yet"}
            </Text>
          </View>
        )}
      </View>

      {/* Collapsible Zone Legend Bottom Sheet */}
      <Modal
        visible={legendOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setLegendOpen(false)}
      >
        <Pressable
          style={[styles.modalBackdrop, { backgroundColor: tokens.overlayBg }]}
          onPress={() => setLegendOpen(false)}
        >
          <Pressable
            style={[styles.sheet, { backgroundColor: tokens.surface, borderColor: tokens.border }]}
            onPress={() => {}}
          >
            <View style={[styles.sheetHandle, { backgroundColor: tokens.border }]} />
            <Text style={[styles.sheetTitle, { color: tokens.text }]}>
              Bot Chart Zone Legend
            </Text>
            <LegendItem code="FVG" meaning="Fair Value Gap (imbalance zone)" color="#10B981" tokens={tokens} />
            <LegendItem code="OB" meaning="Order Block (institutional supply/demand)" color="#3B82F6" tokens={tokens} />
            <LegendItem code="IFVG" meaning="Inverse Fair Value Gap (flipped imbalance)" color="#F59E0B" tokens={tokens} />
            <LegendItem code="BOS / CHoCH" meaning="Break of Structure / Change of Character" color={tokens.accent} tokens={tokens} />
            <LegendItem code="EQH / EQL" meaning="Equal Highs / Equal Lows liquidity" color={tokens.textMuted} tokens={tokens} />
            <LegendItem code="TP / SL" meaning="Long/Short position template (green TP, red SL)" color="#0A997D" tokens={tokens} />

            <TouchableOpacity
              onPress={() => setLegendOpen(false)}
              style={[styles.closeBtn, { backgroundColor: tokens.cardSecondary }]}
              accessibilityRole="button"
              accessibilityLabel="Close zone legend"
            >
              <Text style={[styles.closeBtnText, { color: tokens.text }]}>Done</Text>
            </TouchableOpacity>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
});

function LegendItem({
  code,
  meaning,
  color,
  tokens,
}: {
  code: string;
  meaning: string;
  color: string;
  tokens: ReturnType<typeof getThemeTokens>;
}) {
  return (
    <View style={[styles.legendRow, { borderBottomColor: tokens.borderSubtle }]}>
      <Text style={[styles.legendCode, { color }]}>{code}</Text>
      <Text style={[styles.legendMeaning, { color: tokens.textMuted }]}>{meaning}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  topControlRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderBottomWidth: 1,
    gap: 8,
  },
  chipScroll: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  emptyChipText: {
    fontSize: 11,
  },
  symbolTab: {
    paddingHorizontal: 11,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 32,
    justifyContent: "center",
  },
  symbolTabText: {
    fontSize: 12,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  topActions: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  iconBtn: {
    width: 34,
    height: 34,
    borderRadius: 8,
    alignItems: "center",
    justifyContent: "center",
  },
  metaRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderBottomWidth: 1,
    gap: 6,
  },
  tfRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
  },
  tfChip: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: "transparent",
  },
  tfText: {
    fontSize: 11,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  quoteRight: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  quoteText: {
    fontSize: 10,
    fontFamily: "monospace",
  },
  livePill: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 5,
    gap: 4,
  },
  liveDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  livePillText: {
    fontSize: 9,
    fontWeight: "800",
    letterSpacing: 0.4,
  },
  layerBar: {
    paddingVertical: 6,
    paddingHorizontal: 10,
    borderBottomWidth: 1,
  },
  layerChip: {
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 7,
    borderWidth: 1,
  },
  layerChipText: {
    fontSize: 11,
    fontWeight: "700",
  },
  ohlcStrip: {
    paddingHorizontal: 12,
    paddingTop: 4,
    paddingBottom: 2,
  },
  ohlcText: {
    fontSize: 10,
    fontFamily: "monospace",
  },
  chartHost: {
    flex: 1,
  },
  emptyChart: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
  },
  emptyText: {
    fontSize: 13,
    textAlign: "center",
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
    marginBottom: 10,
  },
  legendRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: 10,
    borderBottomWidth: 1,
    gap: 10,
  },
  legendCode: {
    fontSize: 12,
    fontWeight: "800",
    fontFamily: "monospace",
    width: 88,
  },
  legendMeaning: {
    fontSize: 12,
    flex: 1,
    textAlign: "right",
  },
  closeBtn: {
    marginTop: 16,
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
