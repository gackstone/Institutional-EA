/**
 * Institutional EA — Production Supabase Client (GoTrue Auth + PostgREST + Storage + Edge Functions)
 *
 * Security Invariants:
 * - Uses ONLY public VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.
 * - NEVER embeds or accepts SUPABASE_SERVICE_ROLE_KEY in frontend code.
 * - All database queries are protected by PostgreSQL Row Level Security (RLS).
 * - All privileged administrative operations execute via authenticated Edge Functions.
 */

import type {
  AuditLogRecord,
  DeviceRecord,
  PaymentRecord,
  PlanRecord,
  ProfileRecord,
  SubscriptionRecord,
} from "@institutional-ea/cloud-contract";

export interface SupabaseSession {
  access_token: string;
  refresh_token: string;
  expires_at: number; // Unix seconds
  token_type: string;
  user: {
    id: string;
    email: string;
    email_confirmed_at?: string | null;
    user_metadata?: Record<string, unknown>;
  };
}

const SESSION_STORAGE_KEY = "iea_web_supabase_session_v1";

function getEnvVar(key: string): string {
  try {
    const meta = (import.meta as unknown as { env?: Record<string, string> })?.env;
    return (meta?.[key] || "").trim();
  } catch {
    return "";
  }
}

export const SUPABASE_URL = getEnvVar("VITE_SUPABASE_URL").replace(/\/+$/, "");
export const SUPABASE_ANON_KEY = getEnvVar("VITE_SUPABASE_ANON_KEY");
export const PUBLIC_SITE_URL =
  getEnvVar("VITE_PUBLIC_SITE_URL").replace(/\/+$/, "") ||
  (typeof window !== "undefined" ? window.location.origin : "http://localhost:5173");

export function isSupabaseConfigured(): boolean {
  return (
    Boolean(SUPABASE_URL) &&
    Boolean(SUPABASE_ANON_KEY) &&
    !SUPABASE_URL.includes("your-project-ref") &&
    !SUPABASE_ANON_KEY.includes("your-supabase-anon-key")
  );
}

export class SupabaseClientError extends Error {
  status: number;
  code?: string;

  constructor(message: string, status = 500, code?: string) {
    super(message);
    this.name = "SupabaseClientError";
    this.status = status;
    this.code = code;
  }
}

export function loadStoredSession(): SupabaseSession | null {
  try {
    const raw =
      localStorage.getItem(SESSION_STORAGE_KEY) ||
      sessionStorage.getItem(SESSION_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SupabaseSession;
    if (!parsed?.access_token || !parsed?.user?.id) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveStoredSession(session: SupabaseSession | null, remember = true): void {
  try {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
    if (session) {
      const target = remember ? localStorage : sessionStorage;
      target.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
    }
  } catch {
    // Ignore storage quota errors
  }
}

async function parseErrorResponse(res: Response): Promise<SupabaseClientError> {
  let msg = `Request failed (${res.status})`;
  let code: string | undefined;
  try {
    const data = await res.json();
    msg =
      data?.error_description ||
      data?.msg ||
      data?.message ||
      data?.error ||
      msg;
    code = data?.code || data?.error_code;
  } catch {
    // keep default message
  }
  return new SupabaseClientError(msg, res.status, code);
}

function assertConfigured(): void {
  if (!isSupabaseConfigured()) {
    throw new SupabaseClientError(
      "Supabase backend is not configured yet. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in your environment.",
      503,
      "SUPABASE_NOT_CONFIGURED"
    );
  }
}

function baseHeaders(accessToken?: string): Record<string, string> {
  const headers: Record<string, string> = {
    apikey: SUPABASE_ANON_KEY,
    "Content-Type": "application/json",
  };
  if (accessToken) {
    headers["Authorization"] = `Bearer ${accessToken}`;
  }
  return headers;
}

// -----------------------------------------------------------------------------
// Auth API (GoTrue /auth/v1)
// -----------------------------------------------------------------------------
export const supabaseAuth = {
  async signUp(params: {
    email: string;
    password: string;
    fullName: string;
  }): Promise<{ session: SupabaseSession | null; needsEmailVerification: boolean }> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/auth/v1/signup`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify({
        email: params.email.trim().toLowerCase(),
        password: params.password,
        data: { full_name: params.fullName.trim() },
        email_redirect_to: `${PUBLIC_SITE_URL}/auth/callback`,
      }),
    });

    if (!res.ok) throw await parseErrorResponse(res);
    const data = await res.json();

    if (data?.access_token && data?.user) {
      const session: SupabaseSession = {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_at:
          typeof data.expires_at === "number"
            ? data.expires_at
            : Math.floor(Date.now() / 1000) + Number(data.expires_in || 3600),
        token_type: data.token_type || "bearer",
        user: data.user,
      };
      return { session, needsEmailVerification: !data.user.email_confirmed_at };
    }

    return { session: null, needsEmailVerification: true };
  },

  async signInWithPassword(params: {
    email: string;
    password: string;
    remember?: boolean;
  }): Promise<SupabaseSession> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify({
        email: params.email.trim().toLowerCase(),
        password: params.password,
      }),
    });

    if (!res.ok) throw await parseErrorResponse(res);
    const data = await res.json();
    const session: SupabaseSession = {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at:
        typeof data.expires_at === "number"
          ? data.expires_at
          : Math.floor(Date.now() / 1000) + Number(data.expires_in || 3600),
      token_type: data.token_type || "bearer",
      user: data.user,
    };
    saveStoredSession(session, params.remember ?? true);
    return session;
  },

  async refreshSession(refreshToken: string): Promise<SupabaseSession> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=refresh_token`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) throw await parseErrorResponse(res);
    const data = await res.json();
    const session: SupabaseSession = {
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      expires_at:
        typeof data.expires_at === "number"
          ? data.expires_at
          : Math.floor(Date.now() / 1000) + Number(data.expires_in || 3600),
      token_type: data.token_type || "bearer",
      user: data.user,
    };
    saveStoredSession(session, Boolean(localStorage.getItem(SESSION_STORAGE_KEY)));
    return session;
  },

  async getUser(accessToken: string) {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/auth/v1/user`, {
      method: "GET",
      headers: baseHeaders(accessToken),
    });
    if (!res.ok) throw await parseErrorResponse(res);
    return res.json();
  },

  async recoverPassword(email: string): Promise<void> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/auth/v1/recover`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify({
        email: email.trim().toLowerCase(),
        redirect_to: `${PUBLIC_SITE_URL}/auth/callback?type=recovery`,
      }),
    });
    if (!res.ok) throw await parseErrorResponse(res);
  },

  async resendVerificationEmail(email: string): Promise<void> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/auth/v1/resend`, {
      method: "POST",
      headers: baseHeaders(),
      body: JSON.stringify({
        type: "signup",
        email: email.trim().toLowerCase(),
        options: { emailRedirectTo: `${PUBLIC_SITE_URL}/auth/callback` },
      }),
    });
    if (!res.ok) throw await parseErrorResponse(res);
  },

  async signOut(accessToken?: string): Promise<void> {
    saveStoredSession(null);
    if (!isSupabaseConfigured() || !accessToken) return;
    try {
      await fetch(`${SUPABASE_URL}/auth/v1/logout`, {
        method: "POST",
        headers: baseHeaders(accessToken),
      });
    } catch {
      // Best-effort server logout; local session is already cleared
    }
  },
};

// -----------------------------------------------------------------------------
// PostgREST Data API (/rest/v1)
// -----------------------------------------------------------------------------
async function restFetch<T>(
  path: string,
  accessToken: string,
  init?: RequestInit & { prefer?: string }
): Promise<T> {
  assertConfigured();
  const headers: Record<string, string> = {
    ...baseHeaders(accessToken),
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (init?.prefer) {
    headers["Prefer"] = init.prefer;
  }
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) throw await parseErrorResponse(res);
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const supabaseDb = {
  async getOwnProfile(accessToken: string, userId: string): Promise<ProfileRecord | null> {
    const rows = await restFetch<ProfileRecord[]>(
      `profiles?id=eq.${encodeURIComponent(userId)}&select=*&limit=1`,
      accessToken
    );
    return rows[0] ?? null;
  },

  async updateOwnProfileName(accessToken: string, userId: string, fullName: string): Promise<ProfileRecord> {
    const rows = await restFetch<ProfileRecord[]>(
      `profiles?id=eq.${encodeURIComponent(userId)}`,
      accessToken,
      {
        method: "PATCH",
        prefer: "return=representation",
        body: JSON.stringify({ full_name: fullName.trim() }),
      }
    );
    return rows[0];
  },

  async getActivePlans(accessToken?: string): Promise<PlanRecord[]> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/rest/v1/plans?is_active=eq.true&select=*`, {
      headers: baseHeaders(accessToken),
    });
    if (!res.ok) throw await parseErrorResponse(res);
    return res.json();
  },

  async getOwnSubscription(accessToken: string, userId: string): Promise<SubscriptionRecord | null> {
    const rows = await restFetch<SubscriptionRecord[]>(
      `subscriptions?user_id=eq.${encodeURIComponent(userId)}&select=*,plan:plans(*)&order=created_at.desc&limit=1`,
      accessToken
    );
    return rows[0] ?? null;
  },

  async getOwnPayments(accessToken: string, userId: string): Promise<PaymentRecord[]> {
    return restFetch<PaymentRecord[]>(
      `payments?user_id=eq.${encodeURIComponent(userId)}&select=*&order=submitted_at.desc`,
      accessToken
    );
  },

  async submitBinancePayment(
    accessToken: string,
    payload: {
      user_id: string;
      subscription_id?: string | null;
      amount: number;
      transaction_reference: string;
      payment_date: string;
      proof_file_path?: string | null;
    }
  ): Promise<PaymentRecord> {
    const rows = await restFetch<PaymentRecord[]>("payments", accessToken, {
      method: "POST",
      prefer: "return=representation",
      body: JSON.stringify({
        user_id: payload.user_id,
        subscription_id: payload.subscription_id ?? null,
        provider: "Binance",
        network: "TRON (TRC20)",
        asset: "USDT",
        amount: payload.amount,
        transaction_reference: payload.transaction_reference.trim(),
        payment_date: payload.payment_date,
        proof_file_path: payload.proof_file_path ?? null,
        status: "submitted",
      }),
    });
    return rows[0];
  },

  async getOwnDevices(accessToken: string, userId: string): Promise<DeviceRecord[]> {
    return restFetch<DeviceRecord[]>(
      `devices?user_id=eq.${encodeURIComponent(userId)}&select=*&order=last_seen_at.desc`,
      accessToken
    );
  },

  async revokeOwnDevice(accessToken: string, deviceId: string): Promise<DeviceRecord> {
    const rows = await restFetch<DeviceRecord[]>(
      `devices?id=eq.${encodeURIComponent(deviceId)}`,
      accessToken,
      {
        method: "PATCH",
        prefer: "return=representation",
        body: JSON.stringify({ status: "revoked" }),
      }
    );
    return rows[0];
  },

  // --- Admin Read Queries (RLS enforces public.is_admin() server-side) ---
  async adminListProfiles(accessToken: string): Promise<ProfileRecord[]> {
    return restFetch<ProfileRecord[]>(
      "profiles?select=*&order=created_at.desc&limit=200",
      accessToken
    );
  },

  async adminListSubscriptions(accessToken: string): Promise<SubscriptionRecord[]> {
    return restFetch<SubscriptionRecord[]>(
      "subscriptions?select=*,plan:plans(*)&order=updated_at.desc&limit=200",
      accessToken
    );
  },

  async adminListPayments(accessToken: string): Promise<PaymentRecord[]> {
    return restFetch<PaymentRecord[]>(
      "payments?select=*&order=submitted_at.desc&limit=200",
      accessToken
    );
  },

  async adminListDevices(accessToken: string): Promise<DeviceRecord[]> {
    return restFetch<DeviceRecord[]>(
      "devices?select=*&order=last_seen_at.desc&limit=200",
      accessToken
    );
  },

  async adminListAuditLogs(accessToken: string): Promise<AuditLogRecord[]> {
    return restFetch<AuditLogRecord[]>(
      "audit_logs?select=*&order=created_at.desc&limit=200",
      accessToken
    );
  },
};

// -----------------------------------------------------------------------------
// Storage API (/storage/v1)
// -----------------------------------------------------------------------------
export const supabaseStorage = {
  async uploadPaymentProof(accessToken: string, userId: string, file: File): Promise<string> {
    assertConfigured();
    if (file.size > 5 * 1024 * 1024) {
      throw new SupabaseClientError("Receipt file must be 5 MB or smaller.", 400);
    }
    const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_").slice(0, 80);
    const objectPath = `${userId}/${Date.now()}-${safeName}`;

    const res = await fetch(
      `${SUPABASE_URL}/storage/v1/object/payment-proofs/${encodeURI(objectPath)}`,
      {
        method: "POST",
        headers: {
          apikey: SUPABASE_ANON_KEY,
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": file.type || "application/octet-stream",
          "x-upsert": "false",
        },
        body: file,
      }
    );

    if (!res.ok) throw await parseErrorResponse(res);
    return objectPath;
  },
};

// -----------------------------------------------------------------------------
// Edge Functions API (/functions/v1) — Server-Side Admin Operations
// -----------------------------------------------------------------------------
export const supabaseFunctions = {
  async invoke<T>(functionName: string, accessToken: string, body: Record<string, unknown>): Promise<T> {
    assertConfigured();
    const res = await fetch(`${SUPABASE_URL}/functions/v1/${functionName}`, {
      method: "POST",
      headers: baseHeaders(accessToken),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw await parseErrorResponse(res);
    return res.json() as Promise<T>;
  },

  adminReviewPayment(
    accessToken: string,
    payload: {
      payment_id: string;
      decision: "under_review" | "approve" | "reject";
      rejection_reason?: string;
    }
  ) {
    return this.invoke<{ ok: boolean; payment: PaymentRecord; subscription?: SubscriptionRecord }>(
      "admin-review-payment",
      accessToken,
      payload
    );
  },

  adminManageSubscription(
    accessToken: string,
    payload: {
      action: "suspend_subscription" | "activate_subscription" | "cancel_subscription" | "revoke_device";
      subscription_id?: string;
      device_id?: string;
      reason?: string;
      duration_days?: number;
    }
  ) {
    return this.invoke<{ ok: boolean }>("admin-manage-subscription", accessToken, payload);
  },
};
