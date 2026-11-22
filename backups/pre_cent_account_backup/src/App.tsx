import React, { useState, useEffect, useCallback } from "react";
import { Header } from "./components/Header";
import { MetricsGrid } from "./components/MetricsGrid";
import { ControlsBar } from "./components/ControlsBar";
import { PositionsTable } from "./components/PositionsTable";
import { LiveConsole } from "./components/LiveConsole";
import { MT5SetupWizard } from "./components/MT5SetupWizard";
import { PairingModal } from "./components/PairingModal";
import { TelegramPairingModal } from "./components/TelegramPairingModal";
import { OnboardingWizard } from "./components/OnboardingWizard";
import { DiagnosticsModal } from "./components/DiagnosticsModal";
import { SettingsModal } from "./components/SettingsModal";

import {
  BotState,
  AccountMetrics,
  ActivePosition,
  PendingOrder,
  LogMessage,
  PairingStatus,
  TelegramStatus,
} from "./types";
import { IPC } from "./services/ipc";

export const App: React.FC = () => {
  const [botState, setBotState] = useState<BotState>("STOPPED");
  const [account, setAccount] = useState<AccountMetrics>({
    accountNumber: 0,
    broker: "Connecting...",
    balance: 0,
    equity: 0,
    profit: 0,
    dailyPnl: 0,
    margin: 0,
    freeMargin: 0,
    marginLevel: 0,
    currency: "USD",
    leverage: 100,
    tradeMode: "DEMO",
    profile: "DEMO",
    positionsCount: 0,
  });
  const [positions, setPositions] = useState<ActivePosition[]>([]);
  const [pendingOrders, setPendingOrders] = useState<PendingOrder[]>([]);
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [pairing, setPairing] = useState<PairingStatus>({
    isPaired: false,
    instanceId: null,
    deviceTokenMasked: null,
    pairedAt: null,
    apiUrl: "https://arcadefx.live/api/v1",
  });
  const [telegram, setTelegram] = useState<TelegramStatus>({
    isPaired: false,
    botTokenMasked: null,
    chatIdMasked: null,
    botUsername: null,
    enabled: false,
  });

  // Modal Dialogs
  const [isMT5WizardOpen, setIsMT5WizardOpen] = useState<boolean>(false);
  const [isPairingOpen, setIsPairingOpen] = useState<boolean>(false);
  const [isTelegramOpen, setIsTelegramOpen] = useState<boolean>(false);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState<boolean>(false);
  const [isDiagnosticsOpen, setIsDiagnosticsOpen] = useState<boolean>(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);

  const refreshData = useCallback(async () => {
    try {
      const [state, acc, pos, orders, pStatus, tStatus, initialLogs, cfg] = await Promise.all([
        IPC.getBotState(),
        IPC.getAccountMetrics(),
        IPC.getPositions(),
        IPC.getPendingOrders(),
        IPC.getPairingStatus(),
        IPC.getTelegramStatus(),
        IPC.getLogs(200),
        IPC.getConfig(),
      ]);
      setBotState(state);
      setAccount(acc);
      setPositions(pos);
      setPendingOrders(orders);
      setPairing(pStatus);
      setTelegram(tStatus);
      setLogs(initialLogs);

      // First launch trigger
      if (!cfg.onboardingComplete && !pStatus.isPaired) {
        setIsOnboardingOpen(true);
      }
    } catch (e) {
      console.error("Error refreshing dashboard state:", e);
    }
  }, []);

  useEffect(() => {
    refreshData();
    const interval = setInterval(refreshData, 3000);

    // Event Subscriptions
    const unsubLogs = IPC.onLogReceived((newLog) => {
      setLogs((prev) => [...prev.slice(-499), newLog]);
    });

    const unsubState = IPC.onStateChanged((newState) => {
      setBotState(newState);
    });

    const unsubMetrics = IPC.onMetricsChanged((newMetrics) => {
      setAccount(newMetrics);
    });

    const unsubPositions = IPC.onPositionsChanged((newPositions) => {
      setPositions(newPositions);
    });

    const unsubPendingOrders = IPC.onPendingOrdersChanged((newOrders) => {
      setPendingOrders(newOrders);
    });

    const unsubPairing = IPC.onPairingStatusChanged((newPairing) => {
      setPairing(newPairing);
    });

    return () => {
      clearInterval(interval);
      unsubLogs();
      unsubState();
      unsubMetrics();
      unsubPositions();
      unsubPendingOrders();
      unsubPairing();
    };
  }, [refreshData]);

  const handleClearLogs = useCallback(async () => {
    await IPC.clearLogs();
    setLogs([]);
  }, []);

  const handleScrollToConsole = useCallback(() => {
    const el = document.getElementById("live-console");
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-arcade-bg text-arcade-text transition-colors duration-150 antialiased font-sans">
      {/* 1. Header with Window Controls, Status & Theme Switcher */}
      <Header
        botState={botState}
        account={account}
        pairing={pairing}
        telegram={telegram}
        onOpenSettings={() => setIsSettingsOpen(true)}
        onOpenDiagnostics={() => setIsDiagnosticsOpen(true)}
        onOpenPairing={() => setIsPairingOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenOnboarding={() => setIsOnboardingOpen(true)}
      />

      {/* 2. Primary Trading Control Toolbar */}
      <ControlsBar
        botState={botState}
        onStateChange={setBotState}
        onOpenMT5Wizard={() => setIsMT5WizardOpen(true)}
        onOpenPairing={() => setIsPairingOpen(true)}
        onOpenTelegram={() => setIsTelegramOpen(true)}
        onOpenDiagnostics={() => setIsDiagnosticsOpen(true)}
        onScrollToConsole={handleScrollToConsole}
      />

      {/* 3. Account Performance Cards (6 Compact Cards) */}
      <MetricsGrid account={account} />

      {/* 4. Scrollable Main Workspace: Positions Table & Docked Live Activity Console */}
      <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
        {/* Open Positions & Pending Orders */}
        <div className="flex-1 min-h-0">
          <PositionsTable
            positions={positions}
            pendingOrders={pendingOrders}
            onRefresh={refreshData}
          />
        </div>

        {/* Live Activity & Telemetry Console */}
        <LiveConsole logs={logs} onClearLogs={handleClearLogs} />
      </div>

      {/* Interactive Modal Dialogs */}
      <OnboardingWizard
        isOpen={isOnboardingOpen}
        onFinish={() => setIsOnboardingOpen(false)}
      />

      <MT5SetupWizard
        isOpen={isMT5WizardOpen}
        onClose={() => setIsMT5WizardOpen(false)}
      />

      <PairingModal
        isOpen={isPairingOpen}
        onClose={() => setIsPairingOpen(false)}
        pairing={pairing}
        onPairingUpdated={setPairing}
      />

      <TelegramPairingModal
        isOpen={isTelegramOpen}
        onClose={() => setIsTelegramOpen(false)}
        onStatusUpdated={async () => {
          const t = await IPC.getTelegramStatus();
          setTelegram(t);
        }}
      />

      <DiagnosticsModal
        isOpen={isDiagnosticsOpen}
        onClose={() => setIsDiagnosticsOpen(false)}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
};

export default App;
