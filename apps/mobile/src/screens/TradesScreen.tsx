import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  TouchableOpacity,
  Modal,
  Pressable,
  ActivityIndicator,
  ScrollView,
} from "react-native";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import {
  formatDuration,
  formatPercent,
  formatPrice,
  formatShortDateTime,
  formatSignedPnl,
} from "../utils/formatters.ts";
import { triggerSelectionHaptic } from "../services/haptics.ts";
import {
  formatSyncErrorMessage,
  type MobileSyncClient,
} from "../services/MobileSyncClient.ts";
import {
  DEFAULT_TRADE_FILTER_PREFS,
  OfflineCache,
} from "../services/OfflineCache.ts";
import type {
  MobileSymbolSpec,
  MobileTradeRecord,
  MobileTradesPage,
} from "@institutional-ea/data-contract";

interface TradesScreenProps {
  theme: ThemeMode;
  client: MobileSyncClient | null;
  symbols: MobileSymbolSpec[];
  onShowTradeOnChart: (trade: MobileTradeRecord) => void;
}

type OutcomeFilter = "ALL" | "WIN" | "LOSS";
type SortOption = "time_desc" | "time_asc" | "pnl_desc" | "pnl_asc";
type DateRangeOption = "ALL" | "1D" | "1W" | "1M";

export const TradesScreen = memo(function TradesScreen({
  theme,
  client,
  symbols,
  onShowTradeOnChart,
}: TradesScreenProps): React.ReactElement {
  const tokens = getThemeTokens(theme);
  const [symbolFilter, setSymbolFilter] = useState<string>(DEFAULT_TRADE_FILTER_PREFS.symbolFilter);
  const [outcome, setOutcome] = useState<OutcomeFilter>(DEFAULT_TRADE_FILTER_PREFS.outcome);
  const [dateRange, setDateRange] = useState<DateRangeOption>(DEFAULT_TRADE_FILTER_PREFS.dateRange);
  const [sort, setSort] = useState<SortOption>(DEFAULT_TRADE_FILTER_PREFS.sort);
  const [search, setSearch] = useState(DEFAULT_TRADE_FILTER_PREFS.search);
  const [prefsLoaded, setPrefsLoaded] = useState(false);

  const [pageData, setPageData] = useState<MobileTradesPage | null>(null);
  const [items, setItems] = useState<MobileTradeRecord[]>([]);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTrade, setSelectedTrade] = useState<MobileTradeRecord | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Restore saved trade filter state so filters survive rotation & tab changes
  useEffect(() => {
    let active = true;
    OfflineCache.loadTradeFilterPreferences()
      .then((prefs) => {
        if (!active) return;
        setSymbolFilter(prefs.symbolFilter);
        setOutcome(prefs.outcome);
        setDateRange(prefs.dateRange);
        setSort(prefs.sort);
        setSearch(prefs.search);
        setPrefsLoaded(true);
      })
      .catch(() => {
        if (active) setPrefsLoaded(true);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!prefsLoaded) return;
    OfflineCache.saveTradeFilterPreferences({
      symbolFilter,
      outcome,
      dateRange,
      sort,
      search,
    }).catch(() => {});
  }, [prefsLoaded, symbolFilter, outcome, dateRange, sort, search]);

  const computeFromIso = useCallback((rng: DateRangeOption): string | undefined => {
    if (rng === "ALL") return undefined;
    const ms =
      rng === "1D" ? 86400_000 : rng === "1W" ? 7 * 86400_000 : 30 * 86400_000;
    return new Date(Date.now() - ms).toISOString();
  }, []);

  const fetchPage = useCallback(
    async (targetPage: number, append: boolean) => {
      if (!client) return;
      if (abortRef.current) abortRef.current.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);

      try {
        const res = await client.getTrades(
          {
            page: targetPage,
            limit: 25,
            symbol: symbolFilter,
            outcome,
            from: computeFromIso(dateRange),
            sort,
            q: search.trim() || undefined,
          },
          ctrl.signal
        );
        setPageData(res);
        setPage(targetPage);
        setItems((prev) => (append ? [...prev, ...res.items] : res.items));
      } catch (err: any) {
        if (err?.name === "AbortError") return;
        setError(formatSyncErrorMessage(err, "Unable to load trade history. Tap Retry."));
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [client, symbolFilter, outcome, dateRange, sort, search, computeFromIso]
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchPage(1, false);
    }, 180);
    return () => {
      clearTimeout(timer);
      abortRef.current?.abort();
    };
  }, [fetchPage]);

  const handleLoadMore = () => {
    if (loading || loadingMore || !pageData?.hasMore) return;
    fetchPage(page + 1, true);
  };

  const currency = pageData?.currency ?? "USD";

  const symbolChoices = [
    "ALL",
    ...Array.from(
      new Set(
        (symbols.length > 0 ? symbols.map((s) => s.symbol) : ["XAUUSD", "USDJPY", "BTCUSD"]).filter(
          Boolean
        )
      )
    ),
  ];

  const sortLabel =
    sort === "time_desc"
      ? "Sort: Newest"
      : sort === "time_asc"
      ? "Sort: Oldest"
      : sort === "pnl_desc"
      ? "Sort: Best P/L"
      : "Sort: Worst P/L";

  const renderTrade = useCallback(
    ({ item }: { item: MobileTradeRecord }) => {
      const isWin = item.pnl >= 0;
      const isBuy = item.direction === "BUY";
      return (
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => {
            triggerSelectionHaptic();
            setSelectedTrade(item);
          }}
          style={[
            styles.tradeCard,
            { backgroundColor: tokens.card, borderColor: tokens.borderSubtle },
          ]}
          accessibilityRole="button"
          accessibilityLabel={`Trade ${item.canonicalSymbol} ${item.direction} ${item.pnl}`}
        >
          <View style={styles.tradeTop}>
            <View style={styles.tradeLeft}>
              <Text style={[styles.symText, { color: tokens.text }]}>
                {item.canonicalSymbol}
              </Text>
              <View
                style={[
                  styles.sideBadge,
                  { backgroundColor: isBuy ? tokens.profitBg : tokens.lossBg },
                ]}
              >
                <Text
                  style={[
                    styles.sideText,
                    { color: isBuy ? tokens.profit : tokens.loss },
                  ]}
                >
                  {item.direction} {item.volume}
                </Text>
              </View>
              <Text style={[styles.timeText, { color: tokens.textDim }]}>
                {formatShortDateTime(item.closedAt || item.openedAt)}
              </Text>
            </View>
            <Text
              style={[
                styles.pnlText,
                { color: isWin ? tokens.profit : tokens.loss },
              ]}
            >
              {formatSignedPnl(item.pnl, currency)}
            </Text>
          </View>
          <View style={styles.tradeBottom}>
            <Text style={[styles.metaText, { color: tokens.textDim }]}>
              In {formatPrice(item.entryPrice, item.digits)} → Out{" "}
              {formatPrice(item.exitPrice, item.digits)}
            </Text>
            <Text style={[styles.metaText, { color: tokens.textDim }]}>
              {formatDuration(item.durationSec)}
            </Text>
          </View>
        </TouchableOpacity>
      );
    },
    [tokens, currency]
  );

  return (
    <View style={[styles.container, { backgroundColor: tokens.background }]}>
      {/* Search + Separated Mutually-Exclusive Filter Groups (E9 Fix) */}
      <View
        style={[
          styles.filterBox,
          { backgroundColor: tokens.surface, borderBottomColor: tokens.borderSubtle },
        ]}
      >
        {/* Row 1: Search Input + Dedicated Unclipped Sort Button */}
        <View style={styles.searchSortRow}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search ticket, symbol, or strategy tag…"
            placeholderTextColor={tokens.textDim}
            style={[
              styles.searchInput,
              {
                backgroundColor: tokens.cardSecondary,
                color: tokens.text,
                borderColor: tokens.borderSubtle,
              },
            ]}
            accessibilityLabel="Search trades"
          />
          <TouchableOpacity
            onPress={() => {
              triggerSelectionHaptic();
              const order: SortOption[] = ["time_desc", "time_asc", "pnl_desc", "pnl_asc"];
              setSort(order[(order.indexOf(sort) + 1) % order.length]);
            }}
            style={[
              styles.sortBtn,
              { backgroundColor: tokens.cardSecondary, borderColor: tokens.borderSubtle },
            ]}
            accessibilityRole="button"
            accessibilityLabel={sortLabel}
          >
            <Text style={[styles.sortBtnText, { color: tokens.text }]} numberOfLines={1}>
              {sortLabel}
            </Text>
          </TouchableOpacity>
        </View>

        {/* Row 2: Symbol Group (Single-Select) */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipRow}
        >
          <Text style={[styles.groupLabel, { color: tokens.textDim }]}>Symbol</Text>
          {symbolChoices.map((sym) => {
            const active = symbolFilter === sym;
            return (
              <TouchableOpacity
                key={`sym-${sym}`}
                onPress={() => {
                  triggerSelectionHaptic();
                  setSymbolFilter(sym);
                }}
                style={[
                  styles.chip,
                  {
                    backgroundColor: active ? tokens.accent : tokens.cardSecondary,
                    borderColor: active ? tokens.accent : tokens.borderSubtle,
                    borderWidth: 1,
                  },
                ]}
                accessibilityRole="radio"
                accessibilityState={{ selected: active }}
              >
                <Text
                  style={[
                    styles.chipText,
                    { color: active ? tokens.accentText : tokens.textMuted },
                  ]}
                >
                  {sym === "ALL" ? "All Symbols" : sym}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Row 3: Result Group (Single-Select) + Period Group (Single-Select) with divider */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chipRow}
        >
          <Text style={[styles.groupLabel, { color: tokens.textDim }]}>Result</Text>
          {(["ALL", "WIN", "LOSS"] as OutcomeFilter[]).map((o) => {
            const active = outcome === o;
            return (
              <TouchableOpacity
                key={`o-${o}`}
                onPress={() => {
                  triggerSelectionHaptic();
                  setOutcome(o);
                }}
                style={[
                  styles.chip,
                  {
                    backgroundColor: active ? tokens.accentLight : tokens.card,
                    borderColor: active ? tokens.accent : tokens.borderSubtle,
                    borderWidth: 1,
                  },
                ]}
                accessibilityRole="radio"
                accessibilityState={{ selected: active }}
              >
                <Text
                  style={[
                    styles.chipText,
                    { color: active ? tokens.accent : tokens.textMuted },
                  ]}
                >
                  {o === "ALL" ? "All Results" : o === "WIN" ? "Wins" : "Losses"}
                </Text>
              </TouchableOpacity>
            );
          })}

          <View style={[styles.groupDivider, { backgroundColor: tokens.borderSubtle }]} />

          <Text style={[styles.groupLabel, { color: tokens.textDim }]}>Period</Text>
          {(["ALL", "1D", "1W", "1M"] as DateRangeOption[]).map((r) => {
            const active = dateRange === r;
            return (
              <TouchableOpacity
                key={`r-${r}`}
                onPress={() => {
                  triggerSelectionHaptic();
                  setDateRange(r);
                }}
                style={[
                  styles.chip,
                  {
                    backgroundColor: active ? tokens.accent : tokens.card,
                    borderColor: active ? tokens.accent : tokens.borderSubtle,
                    borderWidth: 1,
                  },
                ]}
                accessibilityRole="radio"
                accessibilityState={{ selected: active }}
              >
                <Text
                  style={[
                    styles.chipText,
                    { color: active ? tokens.accentText : tokens.textMuted },
                  ]}
                >
                  {r === "ALL" ? "All Time" : r}
                </Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
      </View>

      {/* Summary Strip */}
      <View
        style={[
          styles.summaryStrip,
          { backgroundColor: tokens.card, borderBottomColor: tokens.borderSubtle },
        ]}
      >
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryLabel, { color: tokens.textDim }]}>Deals</Text>
          <Text style={[styles.summaryValue, { color: tokens.text }]}>
            {pageData ? String(pageData.summary.count) : "—"}
          </Text>
        </View>
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryLabel, { color: tokens.textDim }]}>Net P/L</Text>
          <Text
            style={[
              styles.summaryValue,
              {
                color: pageData
                  ? pageData.summary.netPnl >= 0
                    ? tokens.profit
                    : tokens.loss
                  : tokens.textMuted,
              },
            ]}
          >
            {pageData ? formatSignedPnl(pageData.summary.netPnl, currency) : "—"}
          </Text>
        </View>
        <View style={styles.summaryItem}>
          <Text style={[styles.summaryLabel, { color: tokens.textDim }]}>Win Rate</Text>
          <Text style={[styles.summaryValue, { color: tokens.accent }]}>
            {pageData ? formatPercent(pageData.summary.winRate, 1) : "—"}
          </Text>
        </View>
      </View>

      {/* Virtualized Paginated List */}
      {error ? (
        <View style={styles.centerBox}>
          <Text style={[styles.errorText, { color: tokens.loss }]}>{error}</Text>
          <TouchableOpacity
            onPress={() => fetchPage(1, false)}
            style={[styles.retryBtn, { backgroundColor: tokens.cardSecondary }]}
          >
            <Text style={[styles.retryText, { color: tokens.text }]}>Retry</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => `${item.ticket}-${item.closedAt || item.openedAt || ""}`}
          renderItem={renderTrade}
          contentContainerStyle={styles.listContent}
          onRefresh={() => fetchPage(1, false)}
          refreshing={loading}
          onEndReached={handleLoadMore}
          onEndReachedThreshold={0.4}
          removeClippedSubviews
          maxToRenderPerBatch={15}
          windowSize={7}
          ListEmptyComponent={
            !loading ? (
              <View style={styles.centerBox}>
                <Text style={[styles.emptyText, { color: tokens.textDim }]}>
                  {symbolFilter !== "ALL" || outcome !== "ALL" || dateRange !== "ALL" || search.trim()
                    ? "No closed deals match your active filters"
                    : "No closed deals recorded on this account yet"}
                </Text>
              </View>
            ) : null
          }
          ListFooterComponent={
            loadingMore ? (
              <ActivityIndicator size="small" color={tokens.accent} style={{ padding: 14 }} />
            ) : null
          }
        />
      )}

      {/* Trade Detail Bottom Sheet */}
      <Modal
        visible={selectedTrade !== null}
        transparent
        animationType="slide"
        onRequestClose={() => setSelectedTrade(null)}
      >
        <Pressable
          style={[styles.modalBackdrop, { backgroundColor: tokens.overlayBg }]}
          onPress={() => setSelectedTrade(null)}
        >
          <Pressable
            style={[styles.sheet, { backgroundColor: tokens.surface, borderColor: tokens.border }]}
            onPress={() => {}}
          >
            {selectedTrade && (
              <>
                <View style={[styles.sheetHandle, { backgroundColor: tokens.border }]} />
                <View style={styles.sheetHeader}>
                  <Text style={[styles.sheetTitle, { color: tokens.text }]}>
                    {selectedTrade.canonicalSymbol} · #{selectedTrade.ticket}
                  </Text>
                  <Text
                    style={[
                      styles.sheetPnl,
                      { color: selectedTrade.pnl >= 0 ? tokens.profit : tokens.loss },
                    ]}
                  >
                    {formatSignedPnl(selectedTrade.pnl, currency)}
                  </Text>
                </View>

                <View style={styles.sheetRows}>
                  <DetailRow label="Direction" value={`${selectedTrade.direction} · ${selectedTrade.volume} lots`} tokens={tokens} />
                  <DetailRow label="Entry" value={formatPrice(selectedTrade.entryPrice, selectedTrade.digits)} tokens={tokens} />
                  <DetailRow label="Exit" value={formatPrice(selectedTrade.exitPrice, selectedTrade.digits)} tokens={tokens} />
                  <DetailRow label="Stop Loss" value={formatPrice(selectedTrade.sl, selectedTrade.digits)} tokens={tokens} />
                  <DetailRow label="Take Profit" value={formatPrice(selectedTrade.tp, selectedTrade.digits)} tokens={tokens} />
                  <DetailRow label="Duration" value={formatDuration(selectedTrade.durationSec)} tokens={tokens} />
                  <DetailRow label="Opened" value={formatShortDateTime(selectedTrade.openedAt)} tokens={tokens} />
                  <DetailRow label="Closed" value={formatShortDateTime(selectedTrade.closedAt)} tokens={tokens} />
                  {selectedTrade.strategyTag ? (
                    <DetailRow label="Strategy" value={selectedTrade.strategyTag} tokens={tokens} />
                  ) : null}
                </View>

                <View style={styles.sheetActions}>
                  <TouchableOpacity
                    onPress={() => {
                      const t = selectedTrade;
                      setSelectedTrade(null);
                      onShowTradeOnChart(t);
                    }}
                    style={[styles.primaryBtn, { backgroundColor: tokens.accent }]}
                    accessibilityRole="button"
                    accessibilityLabel="Show trade on chart"
                  >
                    <Text style={[styles.primaryBtnText, { color: tokens.accentText }]}>
                      Show on Chart
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => setSelectedTrade(null)}
                    style={[styles.secondaryBtn, { backgroundColor: tokens.cardSecondary }]}
                    accessibilityRole="button"
                    accessibilityLabel="Close trade details"
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
  container: { flex: 1 },
  filterBox: {
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 8,
    borderBottomWidth: 1,
    gap: 7,
  },
  searchSortRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  searchInput: {
    flex: 1,
    height: 38,
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 12,
    fontSize: 12,
  },
  sortBtn: {
    height: 38,
    paddingHorizontal: 11,
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: "center",
    alignItems: "center",
    flexShrink: 0,
  },
  sortBtnText: {
    fontSize: 11,
    fontWeight: "700",
  },
  chipRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
  },
  groupLabel: {
    fontSize: 9,
    fontWeight: "700",
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginRight: 2,
  },
  groupDivider: {
    width: 1,
    height: 16,
    marginHorizontal: 4,
  },
  chip: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8,
  },
  chipText: {
    fontSize: 11,
    fontWeight: "700",
  },
  summaryStrip: {
    flexDirection: "row",
    justifyContent: "space-around",
    paddingVertical: 9,
    borderBottomWidth: 1,
  },
  summaryItem: {
    alignItems: "center",
  },
  summaryLabel: {
    fontSize: 9,
    fontWeight: "700",
    textTransform: "uppercase",
  },
  summaryValue: {
    fontSize: 13,
    fontWeight: "700",
    fontFamily: "monospace",
    marginTop: 2,
  },
  listContent: {
    padding: 12,
    paddingBottom: 24,
  },
  tradeCard: {
    borderRadius: 10,
    borderWidth: 1,
    padding: 12,
    marginBottom: 8,
  },
  tradeTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 6,
  },
  tradeLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
    flexShrink: 1,
  },
  symText: {
    fontSize: 14,
    fontWeight: "700",
  },
  sideBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 5,
  },
  sideText: {
    fontSize: 10,
    fontWeight: "700",
  },
  timeText: {
    fontSize: 10,
    fontFamily: "monospace",
  },
  pnlText: {
    fontSize: 14,
    fontWeight: "700",
    fontFamily: "monospace",
  },
  tradeBottom: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  metaText: {
    fontSize: 11,
    fontFamily: "monospace",
  },
  centerBox: {
    padding: 32,
    alignItems: "center",
    gap: 10,
  },
  emptyText: {
    fontSize: 13,
    textAlign: "center",
  },
  errorText: {
    fontSize: 13,
    textAlign: "center",
  },
  retryBtn: {
    paddingHorizontal: 18,
    paddingVertical: 9,
    borderRadius: 8,
  },
  retryText: {
    fontSize: 13,
    fontWeight: "700",
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
