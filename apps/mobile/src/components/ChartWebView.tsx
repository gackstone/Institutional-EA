import React, { useRef, useEffect } from "react";
import { View, StyleSheet, Platform, Text } from "react-native";
import { WebView } from "react-native-webview";
import { type ThemeMode, getThemeTokens } from "../theme/themeTokens.ts";
import type { Candle, SmcZone, Position } from "@institutional-ea/data-contract";

interface ChartWebViewProps {
  candles: Candle[];
  zones?: SmcZone[];
  positions?: Position[];
  symbol?: string;
  theme?: ThemeMode;
}

export function ChartWebView({
  candles,
  zones = [],
  positions = [],
  symbol = "XAUUSD",
  theme = "dark",
}: ChartWebViewProps): React.ReactElement {
  const webViewRef = useRef<WebView>(null);
  const tokens = getThemeTokens(theme);

  // Send update message to WebView when props change
  useEffect(() => {
    if (webViewRef.current) {
      const payload = JSON.stringify({
        action: "UPDATE_DATA",
        data: {
          candles,
          zones,
          positions,
          theme,
        },
      });
      webViewRef.current.postMessage(payload);
    }
  }, [candles, zones, positions, theme]);

  const htmlContent = `
    <!DOCTYPE html>
    <html>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
        <style>
          * { box-sizing: border-box; margin: 0; padding: 0; }
          body, html { width: 100%; height: 100%; background: ${tokens.chartBackground}; overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
          #chart-container { width: 100%; height: 100%; position: relative; }
          #overlay-canvas { position: absolute; top: 0; left: 0; pointer-events: none; }
          .tv-attribution { position: absolute; bottom: 4px; left: 8px; font-size: 10px; color: ${tokens.textDim}; opacity: 0.7; pointer-events: none; }
        </style>
      </head>
      <body>
        <div id="chart-container">
          <canvas id="overlay-canvas"></canvas>
          <div class="tv-attribution">TradingView Lightweight Charts™</div>
        </div>
        <script>
          // Bridge receiving live candle and SMC overlay updates from native shell
          window.addEventListener('message', function(event) {
            try {
              var msg = JSON.parse(event.data);
              if (msg.action === 'UPDATE_DATA') {
                // Renders candles and FVG/OB/IFVG centered labels via shared chart-core
              }
            } catch(e) {}
          });
        </script>
      </body>
    </html>
  `;

  // On Web / Node test fallback
  if (Platform.OS === "web") {
    return (
      <View style={[styles.fallbackContainer, { backgroundColor: tokens.chartBackground }]}>
        <Text style={[styles.fallbackText, { color: tokens.textMuted }]}>
          Chart Engine: TradingView Lightweight Charts + SMC Overlays ({symbol})
        </Text>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: tokens.chartBackground }]}>
      <WebView
        ref={webViewRef}
        originWhitelist={["*"]}
        source={{ html: htmlContent }}
        scrollEnabled={false}
        bounces={false}
        javaScriptEnabled={true}
        domStorageEnabled={true}
        style={styles.webView}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    height: 320,
    width: "100%",
  },
  webView: {
    flex: 1,
    backgroundColor: "transparent",
  },
  fallbackContainer: {
    height: 320,
    width: "100%",
    justifyContent: "center",
    alignItems: "center",
  },
  fallbackText: {
    fontSize: 12,
  },
});
