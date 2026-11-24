import React, { useState, useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaView, StyleSheet } from "react-native";
import { MobileErrorBoundary } from "./components/ErrorBoundary.tsx";
import { RootNavigator } from "./navigation/RootNavigator.tsx";
import { type ThemeMode } from "./theme/themeTokens.ts";
import { SecureStorage } from "./services/SecureStorage.ts";
import type { ConnectionState } from "./components/ConnectionBanner.tsx";
import type { KpiData } from "./components/KpiCards.tsx";
import type { Position, Candle, SmcZone } from "@institutional-ea/data-contract";

export default function App(): React.ReactElement {
  const [theme, setTheme] = useState<ThemeMode>("dark");
  const [connectionState, setConnectionState] = useState<ConnectionState>("CONNECTED");

  // Telemetry state
  const [kpiData, setKpiData] = useState<KpiData>({
    balance: 10450.25,
    equity: 10582.4,
    todayPnl: 132.15,
    totalProfit: 2450.8,
    winRate: 72.4,
    todayTradesCount: 4,
    totalDealsCount: 58,
    isLoading: false,
  });

  const [positions, setPositions] = useState<Position[]>([
    {
      ticket: 104921,
      symbol: "XAUUSD",
      type: "BUY",
      volume: 0.1,
      openPrice: 2652.5,
      currentPrice: 2656.8,
      sl: 2645.0,
      tp: 2670.0,
      profit: 43.0,
      swap: -0.4,
      openTime: Math.floor(Date.now() / 1000) - 3600,
      comment: "Inst-EA Swing FVG",
    },
  ]);

  const [zones, setZones] = useState<SmcZone[]>([
    {
      id: "zone-fvg-1",
      type: "FVG",
      direction: "BULL",
      timeframe: "M5",
      symbol: "XAUUSD",
      top: 2655.0,
      bottom: 2650.0,
      startTime: Math.floor(Date.now() / 1000) - 7200,
      endTime: null,
      status: "UNMITIGATED",
      label: "FVG",
    },
    {
      id: "zone-ob-1",
      type: "OB",
      direction: "BEAR",
      timeframe: "M5",
      symbol: "XAUUSD",
      top: 2672.0,
      bottom: 2668.0,
      startTime: Math.floor(Date.now() / 1000) - 14400,
      endTime: null,
      status: "UNMITIGATED",
      label: "OB",
    },
  ]);

  // Load stored theme on startup
  useEffect(() => {
    SecureStorage.getStoredTheme().then((stored) => {
      if (stored === "light" || stored === "dark") {
        setTheme(stored);
      }
    });
  }, []);

  const handleToggleTheme = () => {
    const nextTheme: ThemeMode = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    SecureStorage.setStoredTheme(nextTheme).catch(() => {});
  };

  return (
    <MobileErrorBoundary>
      <SafeAreaView style={styles.container}>
        <StatusBar style={theme === "dark" ? "light" : "dark"} />
        <RootNavigator
          theme={theme}
          onToggleTheme={handleToggleTheme}
          connectionState={connectionState}
          kpiData={kpiData}
          positions={positions}
          zones={zones}
          activeSymbol="XAUUSD"
        />
      </SafeAreaView>
    </MobileErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
