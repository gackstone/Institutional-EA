/**
 * @institutional-ea/cloud-contract
 *
 * Single Source of Truth for:
 * - Subscription plans, lifecycle states, and UTC entitlement evaluation
 * - Centralized Binance USDT (TRON / TRC20) payment configuration
 * - Payment verification workflow states and TXID validation
 * - Password strength & registration validation
 * - Offline entitlement caching policy (72-hour grace window)
 * - Typed Supabase schema DTOs shared across Web Portal, Electron Companion, and Edge Functions
 */

export type UserRole = "user" | "admin";

export type SubscriptionStatus =
  | "no_subscription"
  | "pending_payment"
  | "payment_under_review"
  | "active"
  | "expired"
  | "cancelled"
  | "suspended"
  | "payment_rejected";

export type PaymentStatus =
  | "pending"
  | "submitted"
  | "under_review"
  | "approved"
  | "rejected";

export type DeviceStatus = "active" | "revoked";

export type CloudConnectivityState =
  | "online"
  | "offline"
  | "reconnecting"
  | "auth_expired"
  | "verification_unavailable"
  | "sync_pending";

export interface PlanRecord {
  id: string;
  slug: string;
  name: string;
  price: number;
  currency: "USD" | "USDT";
  billing_interval: "monthly";
  duration_days: number;
  description: string;
  is_active: boolean;
}

export interface ProfileRecord {
  id: string;
  full_name: string;
  email: string;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionRecord {
  id: string;
  user_id: string;
  plan_id: string;
  status: SubscriptionStatus;
  amount: number;
  currency: string;
  billing_interval: string;
  started_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
  plan?: PlanRecord | null;
}

export interface PaymentRecord {
  id: string;
  user_id: string;
  subscription_id: string | null;
  provider: string;
  network: string;
  asset: string;
  amount: number;
  transaction_reference: string;
  payment_date: string;
  proof_file_path: string | null;
  status: PaymentStatus;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by: string | null;
  rejection_reason: string | null;
}

export interface DeviceRecord {
  id: string;
  user_id: string;
  device_name: string;
  device_fingerprint_hash: string;
  operating_system: string;
  app_version: string;
  last_seen_at: string;
  status: DeviceStatus;
  created_at: string;
}

export interface AuditLogRecord {
  id: string;
  user_id: string | null;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

/**
 * Centralized Institutional EA Pro Subscription Plan Definition.
 * Matches the seeded row in supabase/migrations/20261126000001_initial_cloud_schema.sql.
 */
export const INSTITUTIONAL_EA_PRO_PLAN: PlanRecord = {
  id: "00000000-0000-4000-8000-000000000001",
  slug: "institutional-ea-pro-monthly",
  name: "Institutional EA Pro",
  price: 50,
  currency: "USD",
  billing_interval: "monthly",
  duration_days: 30,
  description:
    "Full access to the Institutional EA Windows Companion Application, secure cloud account synchronization, MT5 Companion connectivity, trading analytics, configuration management, risk interface, and ongoing updates.",
  is_active: true,
} as const;

export const PRO_PLAN_BENEFITS: readonly string[] = [
  "Access to the Institutional EA Windows Companion Application",
  "Secure cloud user account with encrypted desktop session",
  "MetaTrader 5 Companion connectivity & EA deployment tooling",
  "Real-time trading dashboard, live SMC chart & position monitoring",
  "Trade history, chart screenshots, trade replay & equity analytics",
  "Versioned configuration management with diff preview & rollback",
  "Quantitative risk management interface (DEMO / PROP / LIVE profiles)",
  "Application updates throughout your active subscription period",
  "Account & privacy-conscious device management",
  "Technical support subject to the published support policy",
] as const;

/**
 * Centralized Binance USDT (TRON / TRC20) Payment Configuration.
 * Never duplicate this deposit address anywhere else in the codebase.
 */
export const BINANCE_USDT_TRC20_CONFIG = {
  provider: "Binance",
  asset: "USDT",
  network: "TRON (TRC20)",
  networkShort: "TRX · Tron (TRC20)",
  amountUsdt: 50,
  amountUsd: 50,
  depositAddress: "TPP26iUrsJmstHVGh38rHYBipo6drZvj9D",
  qrImagePath: "/assets/binance-usdt-trc20-qr.jpg",
  warnings: [
    "Send ONLY USDT over the TRON (TRC20) network. Deposits sent over ERC20, BEP20, Polygon, Arbitrum, or any other network may be permanently lost.",
    "Do not send NFTs or unsupported tokens to this address.",
    "Smart contract deposits are not supported on TRC20.",
    "Submitting a payment receipt or TXID does not automatically activate your subscription. Every payment is manually verified by an authorized administrator.",
  ],
  instructions: [
    "Open Binance (or your TRC20-compatible wallet) and select Withdraw USDT.",
    "Select network: TRON (TRC20) — verify fees so that at least 50 USDT arrives.",
    "Scan the official Binance QR code or copy the TRC20 deposit address below.",
    "Complete the transfer and copy your TRON Transaction ID (TXID / hash).",
    "Submit the TXID, exact amount sent, and payment date in the verification form below.",
  ],
} as const;

/**
 * Offline Entitlement Caching Policy:
 * - When online, entitlement is verified against Supabase.
 * - When offline, an encrypted local entitlement snapshot remains valid for up to 72 hours
 *   provided `expires_at` (UTC) has not passed.
 * - After 72 hours offline without re-verification, status transitions to `verification_unavailable`
 *   (never silently assumed active forever).
 * - Local emergency controls (Stop, Pause, Close All, Emergency Kill Switch) and open MT5 position
 *   visibility are NEVER locked out regardless of subscription or connectivity state.
 */
export const ENTITLEMENT_CACHE_POLICY = {
  maxOfflineGraceHours: 72,
  maxOfflineGraceMs: 72 * 60 * 60 * 1000,
  recheckIntervalMs: 15 * 60 * 1000,
  maxActiveDevicesDefault: 3,
} as const;

export interface EffectiveEntitlement {
  status: SubscriptionStatus;
  isActive: boolean;
  isGraceActive: boolean;
  requiresSubscriptionAction: boolean;
  expiresAtUtc: string | null;
  daysRemaining: number | null;
  connectivity: CloudConnectivityState;
  reason: string;
}

/**
 * Evaluates effective subscription entitlement strictly in UTC.
 * Never trusts client-mutated status if UTC expiry has elapsed.
 */
export function evaluateSubscriptionEntitlement(
  subscription: Pick<SubscriptionRecord, "status" | "expires_at"> | null | undefined,
  options?: {
    nowUtc?: Date;
    lastVerifiedAtUtc?: string | null;
    isOnline?: boolean;
  }
): EffectiveEntitlement {
  const now = options?.nowUtc ?? new Date();
  const isOnline = options?.isOnline ?? true;

  if (!subscription || subscription.status === "no_subscription") {
    return {
      status: "no_subscription",
      isActive: false,
      isGraceActive: false,
      requiresSubscriptionAction: true,
      expiresAtUtc: null,
      daysRemaining: null,
      connectivity: isOnline ? "online" : "offline",
      reason: "No active subscription found for this account.",
    };
  }

  const expiresMs = subscription.expires_at ? Date.parse(subscription.expires_at) : NaN;
  const hasValidExpiry = Number.isFinite(expiresMs);

  // If marked active, enforce UTC expiration timestamp
  if (subscription.status === "active") {
    if (!hasValidExpiry || expiresMs <= now.getTime()) {
      return {
        status: "expired",
        isActive: false,
        isGraceActive: false,
        requiresSubscriptionAction: true,
        expiresAtUtc: subscription.expires_at,
        daysRemaining: 0,
        connectivity: isOnline ? "online" : "offline",
        reason: "Subscription has expired (UTC). Renew to restore full access.",
      };
    }

    const daysRemaining = Math.max(0, Math.ceil((expiresMs - now.getTime()) / (24 * 60 * 60 * 1000)));

    if (!isOnline) {
      const verifiedMs = options?.lastVerifiedAtUtc ? Date.parse(options.lastVerifiedAtUtc) : NaN;
      const withinGrace =
        Number.isFinite(verifiedMs) &&
        now.getTime() - verifiedMs <= ENTITLEMENT_CACHE_POLICY.maxOfflineGraceMs;

      if (withinGrace) {
        return {
          status: "active",
          isActive: true,
          isGraceActive: true,
          requiresSubscriptionAction: false,
          expiresAtUtc: subscription.expires_at,
          daysRemaining,
          connectivity: "offline",
          reason: "Offline grace window active (cached entitlement verified within 72h).",
        };
      }

      return {
        status: "active",
        isActive: false,
        isGraceActive: false,
        requiresSubscriptionAction: false,
        expiresAtUtc: subscription.expires_at,
        daysRemaining,
        connectivity: "verification_unavailable",
        reason: "Offline grace window exceeded (72h). Reconnect to verify subscription.",
      };
    }

    return {
      status: "active",
      isActive: true,
      isGraceActive: false,
      requiresSubscriptionAction: false,
      expiresAtUtc: subscription.expires_at,
      daysRemaining,
      connectivity: "online",
      reason: `Active Institutional EA Pro subscription (${daysRemaining} day${daysRemaining === 1 ? "" : "s"} remaining).`,
    };
  }

  const statusReasons: Record<Exclude<SubscriptionStatus, "active" | "no_subscription">, string> = {
    pending_payment: "Subscription awaiting Binance USDT (TRC20) payment.",
    payment_under_review: "Payment submitted and currently under administrator review.",
    expired: "Subscription expired. Submit a renewal payment to reactivate.",
    cancelled: "Subscription was cancelled.",
    suspended: "Subscription is currently suspended. Contact support.",
    payment_rejected: "Previous payment submission was rejected. Review the reason and resubmit.",
  };

  return {
    status: subscription.status,
    isActive: false,
    isGraceActive: false,
    requiresSubscriptionAction: subscription.status !== "payment_under_review",
    expiresAtUtc: subscription.expires_at,
    daysRemaining: hasValidExpiry && expiresMs > now.getTime()
      ? Math.ceil((expiresMs - now.getTime()) / (24 * 60 * 60 * 1000))
      : 0,
    connectivity: isOnline ? "online" : "offline",
    reason: statusReasons[subscription.status],
  };
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
}

/**
 * Validates a TRON (TRC20) / Binance transaction ID (TXID).
 * TRON on-chain TXIDs are 64-character hex strings; Binance internal transfer IDs are alphanumeric (16–128 chars).
 */
export function validateTransactionReference(txid: string): ValidationResult {
  const trimmed = (txid || "").trim();
  const errors: string[] = [];

  if (!trimmed) {
    errors.push("Transaction ID (TXID) is required.");
    return { valid: false, errors };
  }

  if (/\s/.test(trimmed)) {
    errors.push("Transaction ID must not contain spaces.");
  }

  const isTronHex = /^[a-fA-F0-9]{64}$/.test(trimmed);
  const isBinanceInternal = /^(internal|offchain|tx)?[a-zA-Z0-9_-]{16,128}$/i.test(trimmed);

  if (!isTronHex && !isBinanceInternal) {
    errors.push(
      "Invalid Transaction ID format. Enter the 64-character TRON (TRC20) TXID hash or Binance transfer reference (16–128 alphanumeric characters)."
    );
  }

  return { valid: errors.length === 0, errors };
}

export interface PaymentSubmissionInput {
  amountSent: number;
  transactionReference: string;
  paymentDate: string;
  networkConfirmed: boolean;
}

export function validatePaymentSubmission(input: PaymentSubmissionInput): ValidationResult {
  const errors: string[] = [];

  if (!Number.isFinite(input.amountSent) || input.amountSent < BINANCE_USDT_TRC20_CONFIG.amountUsdt) {
    errors.push(`Amount sent must be at least ${BINANCE_USDT_TRC20_CONFIG.amountUsdt} USDT.`);
  }

  const txCheck = validateTransactionReference(input.transactionReference);
  errors.push(...txCheck.errors);

  const parsedDate = Date.parse(input.paymentDate);
  if (!input.paymentDate || !Number.isFinite(parsedDate)) {
    errors.push("A valid payment date is required.");
  } else if (parsedDate > Date.now() + 24 * 60 * 60 * 1000) {
    errors.push("Payment date cannot be in the future.");
  }

  if (!input.networkConfirmed) {
    errors.push(
      `You must confirm that you sent USDT on the ${BINANCE_USDT_TRC20_CONFIG.network} network to ${BINANCE_USDT_TRC20_CONFIG.depositAddress}.`
    );
  }

  return { valid: errors.length === 0, errors };
}

export function validateEmail(email: string): boolean {
  const trimmed = (email || "").trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(trimmed);
}

export function validateStrongPassword(password: string): ValidationResult {
  const errors: string[] = [];
  if (!password || password.length < 10) {
    errors.push("Password must be at least 10 characters long.");
  }
  if (!/[A-Z]/.test(password)) {
    errors.push("Password must include at least one uppercase letter.");
  }
  if (!/[a-z]/.test(password)) {
    errors.push("Password must include at least one lowercase letter.");
  }
  if (!/[0-9]/.test(password)) {
    errors.push("Password must include at least one number.");
  }
  if (!/[^A-Za-z0-9]/.test(password)) {
    errors.push("Password must include at least one special character.");
  }
  return { valid: errors.length === 0, errors };
}

export function formatSubscriptionStatusLabel(status: SubscriptionStatus): string {
  const map: Record<SubscriptionStatus, string> = {
    no_subscription: "No Subscription",
    pending_payment: "Pending Payment",
    payment_under_review: "Payment Under Review",
    active: "Active",
    expired: "Expired",
    cancelled: "Cancelled",
    suspended: "Suspended",
    payment_rejected: "Payment Rejected",
  };
  return map[status] ?? status;
}

export function formatPaymentStatusLabel(status: PaymentStatus): string {
  const map: Record<PaymentStatus, string> = {
    pending: "Pending Payment",
    submitted: "Submitted for Verification",
    under_review: "Under Review",
    approved: "Approved",
    rejected: "Rejected",
  };
  return map[status] ?? status;
}
