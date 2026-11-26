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
  stop_loss?: number;
  take_profit?: number;
  initial_stop_loss?: number;
  open_time?: string | null;
  open_timestamp?: number | null;
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
  | "positions"
  | "signals"
  | "alerts"
  | "history"
  | "analytics"
  | "mt5"
  | "operations"
  | "logs"
  | "health"
  | "account"
  | "settings";

export type OperatingMode =
  | "OBSERVE"
  | "DRY_RUN"
  | "DEMO_SCALPING"
  | "DEMO_FAST"
  | "DEMO_MANUAL_ASSIST"
  | "BTCUSD_DEMO_SAMPLE_MODE";

export interface ControlSymbolSpec {
  canonical?: string;
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
  trade_mode?: number;
  trade_mode_label?: string;
  tick_volume?: number;
  tick_time_utc?: string | null;
  tick_age_sec?: number | null;
  stale?: boolean;
  market_closed?: boolean;
  entries_blocked?: boolean;
  freshness_reason?: string;
  source?: "MT5";
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
    state?: string;
    operating_mode: OperatingMode;
    dry_run: boolean;
    live_trading_locked: boolean;
    stop_flag_active: boolean;
    stop_flag_present?: boolean;
    pause_flag_active: boolean;
    pause_flag_present?: boolean;
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
    terminal_path?: string | null;
    zmq_bridge?: {
      port_5555: boolean;
      port_5556: boolean;
      connected: boolean;
      checked_at: string | null;
    };
    last_candle_times?: Record<string, string>;
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

export interface AuditLogRecord {
  id: number;
  actor: string;
  action: string;
  component: string;
  details: string;
  created_at: string;
}

export interface BalanceSnapshotRecord {
  id: number;
  balance: number;
  equity: number;
  floating_pnl: number;
  source: string;
  created_at: string;
}

export interface TradeScreenshotRecord {
  id: number;
  ticket: number;
  symbol: string;
  stage: string;
  filename: string;
  created_at: string;
}

export interface SignalRecord {
  id: number;
  signal_id: string;
  symbol: string;
  direction: string;
  score: number;
  entry_price: number;
  stop_loss: number;
  take_profit: number;
  rr: number;
  status: "WATCHING" | "TAKEN" | "REJECTED" | string;
  rejection_reason: string;
  created_at: string;
}

export interface AlertEventRecord {
  id: number;
  alert_type: string;
  severity: string;
  symbol: string;
  message: string;
  telegram_status: string;
  dedup_key: string;
  created_at: string;
}

export interface AlertSettings {
  enabled_types: Record<string, boolean>;
  telegram_enabled: boolean;
  quiet_hours_enabled: boolean;
  quiet_start_utc: string;
  quiet_end_utc: string;
  rate_limit_per_min: number;
  dedup_window_sec: number;
}

export interface TradeReplayPayload {
  trade: TradeHistoryRecord;
  events: Array<{
    id: number;
    event_type: string;
    symbol: string;
    ticket: number;
    details_json: string;
    created_at: string;
  }>;
  screenshots: TradeScreenshotRecord[];
  candles: Array<{
    time: number;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
  }>;
  source: string;
}

export interface ControlServiceStatus {
  status: "STARTING" | "ONLINE" | "OFFLINE" | "ERROR";
  host: string;
  port: number;
  baseUrl: string;
  pid: number | null;
  restarts: number;
  lastError: string | null;
  checkedAt: string | null;
}

export interface SelfCheckItem {
  id: string;
  name: string;
  status: "PASS" | "WARN" | "FAIL";
  detail: string;
}

export interface SelfCheckReport {
  status: "HEALTHY" | "DEGRADED";
  checked_at: string;
  checks: SelfCheckItem[];
  zmq_bridge?: {
    port_5555: boolean;
    port_5556: boolean;
    connected: boolean;
    checked_at: string | null;
  };
  last_candle_times?: Record<string, string>;
}

export interface DeployEAResult {
  success: boolean;
  message: string;
  ea_version?: string;
  ex5_path?: string;
  ex5_size_bytes?: number;
  backup_dir?: string | null;
  verified_hashes?: Record<string, string>;
  compile?: {
    compiled: boolean;
    errors: number;
    warnings: number;
    metaeditor?: string;
    log_path?: string;
    log_tail?: string[];
  };
  settings_check?: {
    exists: boolean;
    path: string;
    allow_algo_trading: boolean | null;
    allow_dll_imports: boolean | null;
    note: string;
  };
  zmq_bridge?: {
    port_5555: boolean;
    port_5556: boolean;
    connected: boolean;
  };
  chart_attachment?: {
    automated: boolean;
    note: string;
  };
  steps?: Array<{ step: string; ok: boolean; detail: string }>;
}
