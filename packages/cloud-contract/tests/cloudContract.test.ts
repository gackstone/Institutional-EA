import { test } from "node:test";
import assert from "node:assert/strict";
import {
  BINANCE_USDT_TRC20_CONFIG,
  ENTITLEMENT_CACHE_POLICY,
  INSTITUTIONAL_EA_PRO_PLAN,
  evaluateSubscriptionEntitlement,
  validateEmail,
  validatePaymentSubmission,
  validateStrongPassword,
  validateTransactionReference,
} from "../src/index.ts";

test("Centralized Binance USDT TRC20 config matches exact required wallet and plan", () => {
  assert.equal(BINANCE_USDT_TRC20_CONFIG.provider, "Binance");
  assert.equal(BINANCE_USDT_TRC20_CONFIG.asset, "USDT");
  assert.equal(BINANCE_USDT_TRC20_CONFIG.network, "TRON (TRC20)");
  assert.equal(BINANCE_USDT_TRC20_CONFIG.amountUsdt, 50);
  assert.equal(BINANCE_USDT_TRC20_CONFIG.depositAddress, "TPP26iUrsJmstHVGh38rHYBipo6drZvj9D");
  assert.equal(INSTITUTIONAL_EA_PRO_PLAN.name, "Institutional EA Pro");
  assert.equal(INSTITUTIONAL_EA_PRO_PLAN.price, 50);
  assert.equal(INSTITUTIONAL_EA_PRO_PLAN.billing_interval, "monthly");
});

test("evaluateSubscriptionEntitlement enforces UTC expiry and 72h offline grace policy", () => {
  const now = new Date("2026-11-26T12:00:00Z");
  const futureExpiry = "2026-12-26T12:00:00Z";
  const pastExpiry = "2026-11-25T12:00:00Z";

  // Active online
  const activeOnline = evaluateSubscriptionEntitlement(
    { status: "active", expires_at: futureExpiry },
    { nowUtc: now, isOnline: true }
  );
  assert.equal(activeOnline.isActive, true);
  assert.equal(activeOnline.status, "active");
  assert.equal(activeOnline.daysRemaining, 30);

  // Active status with past UTC expiry must be treated as expired
  const expiredActive = evaluateSubscriptionEntitlement(
    { status: "active", expires_at: pastExpiry },
    { nowUtc: now, isOnline: true }
  );
  assert.equal(expiredActive.isActive, false);
  assert.equal(expiredActive.status, "expired");
  assert.equal(expiredActive.requiresSubscriptionAction, true);

  // Offline within 72h grace window
  const recentVerification = new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString();
  const offlineGrace = evaluateSubscriptionEntitlement(
    { status: "active", expires_at: futureExpiry },
    { nowUtc: now, isOnline: false, lastVerifiedAtUtc: recentVerification }
  );
  assert.equal(offlineGrace.isActive, true);
  assert.equal(offlineGrace.isGraceActive, true);
  assert.equal(offlineGrace.connectivity, "offline");

  // Offline past 72h grace window -> verification_unavailable (never assumed active forever)
  const staleVerification = new Date(
    now.getTime() - (ENTITLEMENT_CACHE_POLICY.maxOfflineGraceHours + 2) * 60 * 60 * 1000
  ).toISOString();
  const offlineStale = evaluateSubscriptionEntitlement(
    { status: "active", expires_at: futureExpiry },
    { nowUtc: now, isOnline: false, lastVerifiedAtUtc: staleVerification }
  );
  assert.equal(offlineStale.isActive, false);
  assert.equal(offlineStale.connectivity, "verification_unavailable");

  // Pending / Under review / Rejected
  const underReview = evaluateSubscriptionEntitlement(
    { status: "payment_under_review", expires_at: null },
    { nowUtc: now, isOnline: true }
  );
  assert.equal(underReview.isActive, false);
  assert.equal(underReview.requiresSubscriptionAction, false);
});

test("validateTransactionReference and validatePaymentSubmission reject malformed inputs", () => {
  const validTronTxid = "a1b2c3d4e5f60718293a4b5c6d7e8f901234567890abcdef1234567890abcdef";
  assert.equal(validateTransactionReference(validTronTxid).valid, true);
  assert.equal(validateTransactionReference("short").valid, false);
  assert.equal(validateTransactionReference("has spaces in txid 1234567890123456").valid, false);

  const validSub = validatePaymentSubmission({
    amountSent: 50,
    transactionReference: validTronTxid,
    paymentDate: "2026-11-26T08:00:00Z",
    networkConfirmed: true,
  });
  assert.equal(validSub.valid, true);

  const underpaid = validatePaymentSubmission({
    amountSent: 49.5,
    transactionReference: validTronTxid,
    paymentDate: "2026-11-26T08:00:00Z",
    networkConfirmed: true,
  });
  assert.equal(underpaid.valid, false);

  const unconfirmed = validatePaymentSubmission({
    amountSent: 50,
    transactionReference: validTronTxid,
    paymentDate: "2026-11-26T08:00:00Z",
    networkConfirmed: false,
  });
  assert.equal(unconfirmed.valid, false);
});

test("validateEmail and validateStrongPassword enforce strong account security", () => {
  assert.equal(validateEmail("trader@institutionalea.com"), true);
  assert.equal(validateEmail("not-an-email"), false);

  assert.equal(validateStrongPassword("Weak123").valid, false);
  assert.equal(validateStrongPassword("StrongPass!2026").valid, true);
});
