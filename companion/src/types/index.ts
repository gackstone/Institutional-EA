export type BotState = "STOPPED" | "STARTING" | "RUNNING" | "PAUSED" | "ERROR";

export type ServiceStatus = "STOPPED" | "STARTING" | "RUNNING" | "ERROR";

export interface ServiceInfo {
  id: "engine" | "bridge" | "institutional_ea" | "telegram" | "health" | "logs";
  name: string;
  description: string;
  status: ServiceStatus;
  pid: number | null;
  cpu: number;
  memoryMb: number;
  uptimeSeconds: number;
  restarts: number;
  lastHeartbeat: string | null;
  lastError: string | null;
}

export interface AccountMetrics {
  accountNumber: number;
  broker: string;
  server?: string;
  balance: number;
  equity: number;
  profit: number;
  dailyPnl: number;
  margin: number;
  freeMargin: number;
  marginLevel: number;
  currency: string;
  leverage: number;
  tradeMode: "DEMO" | "REAL" | "PROP" | "CONTEST";
  profile: "DEMO" | "LIVE" | "PROP" | "RETAIL";
  positionsCount: number;
  // Cent Account Compatibility Fields
  accountType?: "STANDARD" | "CENT" | "DEMO_STANDARD" | "DEMO_CENT" | "UNKNOWN" | string;
  isCentAccount?: boolean;
  rawCurrency?: string;
  rawBalance?: number;
  rawEquity?: number;
  normalizedBalance?: number;
  normalizedEquity?: number;
  denominationFactor?: number;
  mt5Connected?: boolean;
}

export interface InstrumentMapping {
  canonicalSymbol: string;
  actualBrokerSymbol: string;
  suffix: string;
  contractSize: number;
  tickValue: number;
  tickSize: number;
  minLot: number;
  volumeStep: number;
  status: "VALIDATED" | "UNAVAILABLE" | "TRADE_DISABLED" | "PENDING_DISCOVERY" | string;
  accountType: string;
  brokerServer: string;
}

export interface ActivePosition {
  ticket: number;
  symbol: string;
  canonicalSymbol?: string;
  actualBrokerSymbol?: string;
  orderType: "BUY" | "SELL";
  volume: number;
  openPrice: number;
  currentPrice: number;
  sl: number;
  tp: number;
  profit: number;
  nativeProfit?: number;
  normalizedProfit?: number;
  commission?: number;
  swap?: number;
  accountType?: string;
  brokerIdentity?: string;
  magic: number;
  comment: string;
  isManual?: boolean;
  isProtected?: boolean;
}

export interface PendingOrder {
  ticket: number;
  symbol: string;
  orderType: "BUY_LIMIT" | "SELL_LIMIT" | "BUY_STOP" | "SELL_STOP" | "BUY_STOP_LIMIT" | "SELL_STOP_LIMIT" | string;
  volume: number;
  price: number;
  sl: number;
  tp: number;
  magic: number;
  comment: string;
}

export interface LogMessage {
  id: string;
  timestamp: string;
  service: string;
  level: "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  message: string;
}

export interface MT5TerminalInfo {
  id: string;
  name: string;
  executablePath: string;
  dataFolder: string;
  expertsFolder: string;
  isRunning: boolean;
  pid: number | null;
  eaInstalled: boolean;
  eaVersion: string;
}

export interface PairingStatus {
  isPaired: boolean;
  instanceId: string | null;
  deviceTokenMasked: string | null;
  pairedAt: string | null;
  apiUrl: string;
}

export interface TelegramStatus {
  isPaired: boolean;
  botTokenMasked: string | null;
  chatIdMasked: string | null;
  botUsername: string | null;
  enabled: boolean;
}

export interface DiagnosticResult {
  id: string;
  name: string;
  status: "PASS" | "FAIL" | "WARN" | "CHECKING" | "INFO";
  details: string;
}

export interface CompanionConfig {
  apiUrl: string;
  tradingMode: "CONTINUOUS_SCALPING" | "SWING_HOLD";
  riskPerTradePct: number;
  maxDailyLossPct: number;
  bridgeHost: string;
  bridgePort: number;
  ipcPort: number;
  allowedSymbols: string[];
  autoStartOnBoot: boolean;
  minimizeToTray: boolean;
  runInBackground: boolean;
  allowRealAccount: boolean;
  onboardingComplete?: boolean;
  telegramBotToken?: string;
  telegramChatId?: string;
  telegramEnabled?: boolean;
  telegramUsername?: string;
}

export type ScreenId =
  | "dashboard"
  | "engine"
  | "market"
  | "signals"
  | "positions"
  | "history"
  | "risk"
  | "instruments"
  | "configuration"
  | "mt5"
  | "operations"
  | "errors"
  | "logs"
  | "analytics"
  | "health"
  | "settings";

export type OperatingMode =
  | "OBSERVE"
  | "DRY_RUN"
  | "DEMO_SCALPING"
  | "DEMO_FAST"
  | "DEMO_MANUAL_ASSIST"
  | "BTCUSD_DEMO_SAMPLE_MODE";

export interface BTCUSDSampleStatus {
  enabled: boolean;
  active: boolean;
  paused: boolean;
  state: string;
  operating_mode: string;
  broker_symbol: string;
  bid: number;
  ask: number;
  spread_points: number;
  mt5_connection: string;
  demo_verified: boolean;
  open_positions: ControlPosition[];
  floating_pnl: number;
  daily_pnl: number;
  last_signal: Record<string, any> | null;
  last_executed_trade: Record<string, any> | null;
  last_execution_result: string | null;
  last_check_note: string;
  telegram: {
    enabled: boolean;
    has_token: boolean;
    has_chat_id: boolean;
    delivery_count: number;
    failed_count: number;
    last_notification: { timestamp: string; preview: string; status: string; error?: string } | null;
  };
}

export interface ControlSymbolSpec {
  symbol: string;
  bid: number;
  ask: number;
  spread_points: number;
  digits: number;
  point: number;
  volume_min: number;
  volume_max: number;
  volume_step: number;
  stops_level: number;
}

export interface ControlPosition {
  ticket: number;
  symbol: string;
  direction: string;
  volume: number;
  open_price: number;
  current_price: number;
  sl: number;
  tp: number;
  profit: number;
  magic: number;
  comment: string;
  ownership: "BOT" | "MANUAL" | "OTHER_EA";
  protected: boolean;
}

export interface ControlStatusPayload {
  engine: {
    engine_state: string;
    operating_mode: OperatingMode;
    dry_run: boolean;
    live_trading_locked: boolean;
    stop_flag_active: boolean;
    pause_flag_active: boolean;
    bridge_running: boolean;
    bridge_pid: number | null;
    engine_running: boolean;
    engine_pid: number | null;
    started_at: string | null;
    last_heartbeat: string | null;
    last_signal: Record<string, any> | null;
    last_trade: Record<string, any> | null;
    last_execution_error: string | null;
    portfolio_capacity?: Record<string, any>;
  };
  mt5: {
    connection_status: string;
    last_sync_at: string | null;
    last_error: string | null;
    reconnect_attempts: number;
    account: {
      account_number: number;
      broker: string;
      currency: string;
      balance: number;
      equity: number;
      margin: number;
      free_margin: number;
      margin_level: number;
      leverage: number;
      trade_mode: string;
      margin_mode_str: string;
      demo_verified: boolean;
      netting_observe_only: boolean;
    };
    positions: ControlPosition[];
    pending_orders: Array<Record<string, any>>;
    symbols: Record<string, ControlSymbolSpec>;
    reconciliation: {
      status: string;
      bot_owned_count: number;
      manual_count: number;
      other_ea_count: number;
      unexpected_tickets: number[];
      unprotected_bot_tickets: number[];
      timestamp: string | null;
    };
  };
  health: {
    overall: string;
    sqlite: { healthy: boolean; db_path: string; schema_version?: number; error?: string };
    active_error_count: number;
    stop_flag_active: boolean;
    pause_flag_active: boolean;
    mt5_connected: boolean;
    demo_verified: boolean;
  };
}

export interface ControlErrorEvent {
  id: number;
  category: string;
  severity: string;
  component: string;
  message: string;
  trading_affected: number;
  entries_blocked: number;
  recommended_recovery: string;
  user_action_required: number;
  status: "ACTIVE" | "RESOLVED";
  resolution_note: string | null;
  created_at: string;
  resolved_at: string | null;
}

export interface AllowlistedOpInfo {
  op_id: string;
  name: string;
  description: string;
  timeout_sec: number;
}

export interface OperationAuditRecord {
  id: number;
  op_id: string;
  command_name: string;
  status: string;
  exit_code: number | null;
  stdout: string;
  stderr: string;
  duration_ms: number | null;
  started_at: string;
  finished_at: string | null;
}

export interface ConfigVersionRecord {
  id: number;
  version: number;
  change_summary: string;
  author: string;
  requires_restart: number;
  created_at: string;
}

export interface ControlLogEntry {
  id: string;
  timestamp: string;
  component: string;
  severity: string;
  message: string;
  instrument?: string | null;
  ticket?: number | null;
  correlation_id?: string | null;
}

export interface TradeHistoryRecord {
  id: number;
  ticket: number;
  symbol: string;
  direction: string;
  volume: number;
  open_price: number;
  close_price: number;
  sl: number;
  tp: number;
  profit: number;
  magic: number;
  ownership: string;
  status: string;
  opened_at: string;
  closed_at: string | null;
}

export interface RiskDecisionRecord {
  id: number;
  symbol: string;
  direction: string;
  approved: number;
  reason: string;
  lot_size: number;
  risk_pct: number;
  created_at: string;
}

export interface AuditLogRecord {
  id: number;
  actor: string;
  action: string;
  component: string;
  details: string;
  created_at: string;
}
