import React, {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { View, StyleSheet, Platform, Text, ActivityIndicator } from "react-native";
import { WebView, type WebViewMessageEvent } from "react-native-webview";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import { CHART_WEBVIEW_BUNDLE_JS } from "../generated/chartBundle.ts";
import type {
  MobileCandle,
  MobileDrawingsResponse,
} from "@institutional-ea/data-contract";
import type { ChartLayerPreferences } from "../services/OfflineCache.ts";

export interface CrosshairData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface ChartWebViewHandle {
  resetView: () => void;
  focusTime: (timestampSec: number) => void;
  updateCandle: (candle: MobileCandle) => void;
}

interface ChartWebViewProps {
  candles: MobileCandle[];
  drawings: MobileDrawingsResponse | null;
  symbol: string;
  timeframe: string;
  digits?: number;
  point?: number;
  layers: ChartLayerPreferences;
  theme: ThemeMode;
  height?: number | "flex";
  focusTime?: number | null;
  onCrosshairChange?: (data: CrosshairData | null) => void;
  onLoadMoreHistory?: (beforeTime: number) => void;
}

export const ChartWebView = forwardRef<ChartWebViewHandle, ChartWebViewProps>(
  function ChartWebView(
    {
      candles,
      drawings,
      symbol,
      timeframe,
      digits = 2,
      point = 0.01,
      layers,
      theme,
      height = 300,
      focusTime = null,
      onCrosshairChange,
      onLoadMoreHistory,
    },
    ref
  ) {
    const webViewRef = useRef<WebView | null>(null);
    const [chartReady, setChartReady] = useState(false);
    const tokens = getThemeTokens(theme);
    const SafeWebView = WebView as unknown as React.ComponentType<any>;

    const postBridge = useCallback((action: string, payload?: unknown) => {
      if (!webViewRef.current) return;
      webViewRef.current.postMessage(JSON.stringify({ action, payload }));
    }, []);

    useImperativeHandle(
      ref,
      () => ({
        resetView: () => postBridge("RESET_VIEW"),
        focusTime: (ts: number) => postBridge("FOCUS_TIME", ts),
        updateCandle: (candle: MobileCandle) => postBridge("UPDATE_CANDLE", candle),
      }),
      [postBridge]
    );

    // Build static offline HTML once (ZERO CDN, ZERO eval, uses locally bundled Lightweight Charts + chart-core)
    const htmlSource = useMemo(() => {
      return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
    html, body { width: 100%; height: 100%; overflow: hidden; background: #0D0E11; touch-action: none; }
    #chart-container { width: 100%; height: 100%; position: relative; }
    #overlay-canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 4; }
  </style>
</head>
<body>
  <div id="chart-container">
    <canvas id="overlay-canvas"></canvas>
  </div>
  <script>${CHART_WEBVIEW_BUNDLE_JS}</script>
</body>
</html>`;
    }, []);

    // Push full dataset once chart signals CHART_READY or when symbol/tf/candles/drawings change
    useEffect(() => {
      if (!chartReady || !symbol) return;
      postBridge("SET_DATA", {
        symbol,
        timeframe,
        digits,
        point,
        theme,
        layers,
        candles,
        drawings,
        focusTime,
      });
    }, [chartReady, symbol, timeframe, digits, point, candles, drawings, focusTime]);

    // Incremental layer update without full candle reset
    useEffect(() => {
      if (!chartReady) return;
      postBridge("UPDATE_LAYERS", layers);
    }, [chartReady, layers, postBridge]);

    // Incremental theme update without full candle reset
    useEffect(() => {
      if (!chartReady) return;
      postBridge("UPDATE_THEME", theme);
    }, [chartReady, theme, postBridge]);

    const handleMessage = useCallback(
      (event: WebViewMessageEvent) => {
        try {
          const msg = JSON.parse(event.nativeEvent.data);
          if (msg.type === "CHART_READY") {
            setChartReady(true);
          } else if (msg.type === "CROSSHAIR" && onCrosshairChange) {
            onCrosshairChange(msg.payload ?? null);
          } else if (msg.type === "LOAD_MORE_HISTORY" && onLoadMoreHistory) {
            const bt = Number(msg.payload?.beforeTime);
            if (Number.isFinite(bt) && bt > 0) {
              onLoadMoreHistory(bt);
            }
          }
        } catch {
          // Ignore malformed bridge messages
        }
      },
      [onCrosshairChange, onLoadMoreHistory]
    );

    const containerStyle =
      height === "flex"
        ? [styles.flexContainer, { backgroundColor: tokens.chartBackground }]
        : [styles.fixedContainer, { height, backgroundColor: tokens.chartBackground }];

    if (Platform.OS === "web") {
      return (
        <View style={containerStyle}>
          <Text style={[styles.fallbackText, { color: tokens.textMuted }]}>
            {symbol ? `${symbol} · ${timeframe} (${candles.length} bars)` : "Waiting for symbol"}
          </Text>
        </View>
      );
    }

    return (
      <View style={containerStyle}>
        <SafeWebView
          ref={webViewRef}
          originWhitelist={["*"]}
          source={{ html: htmlSource }}
          onMessage={handleMessage}
          scrollEnabled={false}
          bounces={false}
          overScrollMode="never"
          javaScriptEnabled={true}
          domStorageEnabled={false}
          allowFileAccess={false}
          mixedContentMode="never"
          androidLayerType="hardware"
          style={styles.webView}
        />
        {!chartReady && (
          <View style={[styles.loadingOverlay, { backgroundColor: tokens.chartBackground }]}>
            <ActivityIndicator size="small" color={tokens.accent} />
          </View>
        )}
      </View>
    );
  }
);

const styles = StyleSheet.create({
  flexContainer: {
    flex: 1,
    width: "100%",
    position: "relative",
  },
  fixedContainer: {
    width: "100%",
    position: "relative",
    overflow: "hidden",
  },
  webView: {
    flex: 1,
    backgroundColor: "transparent",
  },
  loadingOverlay: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
  },
  fallbackText: {
    fontSize: 12,
    textAlign: "center",
    padding: 16,
  },
});
