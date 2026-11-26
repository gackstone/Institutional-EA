import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  evaluateSubscriptionEntitlement,
  type DeviceRecord,
  type EffectiveEntitlement,
  type PaymentRecord,
  type ProfileRecord,
  type SubscriptionRecord,
} from "@institutional-ea/cloud-contract";
import {
  isSupabaseConfigured,
  loadStoredSession,
  saveStoredSession,
  supabaseAuth,
  supabaseDb,
  type SupabaseSession,
} from "../lib/supabaseClient";

interface AuthContextValue {
  configured: boolean;
  loading: boolean;
  session: SupabaseSession | null;
  profile: ProfileRecord | null;
  subscription: SubscriptionRecord | null;
  entitlement: EffectiveEntitlement;
  payments: PaymentRecord[];
  devices: DeviceRecord[];
  isAdmin: boolean;
  error: string | null;
  refreshAccount: () => Promise<void>;
  setSessionDirect: (session: SupabaseSession | null, remember?: boolean) => void;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const configured = useMemo(() => isSupabaseConfigured(), []);
  const [loading, setLoading] = useState<boolean>(true);
  const [session, setSession] = useState<SupabaseSession | null>(() => loadStoredSession());
  const [profile, setProfile] = useState<ProfileRecord | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionRecord | null>(null);
  const [payments, setPayments] = useState<PaymentRecord[]>([]);
  const [devices, setDevices] = useState<DeviceRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  const setSessionDirect = useCallback((next: SupabaseSession | null, remember = true) => {
    saveStoredSession(next, remember);
    setSession(next);
    if (!next) {
      setProfile(null);
      setSubscription(null);
      setPayments([]);
      setDevices([]);
    }
  }, []);

  const refreshAccount = useCallback(async () => {
    if (!configured || !session) {
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      let activeSession = session;
      const nowSec = Math.floor(Date.now() / 1000);
      if (activeSession.expires_at && activeSession.expires_at - 60 <= nowSec && activeSession.refresh_token) {
        activeSession = await supabaseAuth.refreshSession(activeSession.refresh_token);
        setSession(activeSession);
      }

      const [prof, sub, pmts, devs] = await Promise.all([
        supabaseDb.getOwnProfile(activeSession.access_token, activeSession.user.id),
        supabaseDb.getOwnSubscription(activeSession.access_token, activeSession.user.id),
        supabaseDb.getOwnPayments(activeSession.access_token, activeSession.user.id),
        supabaseDb.getOwnDevices(activeSession.access_token, activeSession.user.id),
      ]);

      setProfile(prof);
      setSubscription(sub);
      setPayments(pmts);
      setDevices(devs);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to synchronize account state.";
      setError(msg);
      if (msg.toLowerCase().includes("jwt") || msg.toLowerCase().includes("expired") || msg.toLowerCase().includes("invalid")) {
        setSessionDirect(null);
      }
    } finally {
      setLoading(false);
    }
  }, [configured, session, setSessionDirect]);

  useEffect(() => {
    refreshAccount();
  }, [refreshAccount]);

  const signOut = useCallback(async () => {
    const token = session?.access_token;
    setSessionDirect(null);
    await supabaseAuth.signOut(token);
  }, [session, setSessionDirect]);

  const entitlement = useMemo(
    () =>
      evaluateSubscriptionEntitlement(subscription, {
        isOnline: typeof navigator !== "undefined" ? navigator.onLine : true,
      }),
    [subscription]
  );

  const isAdmin = profile?.role === "admin";

  const value = useMemo<AuthContextValue>(
    () => ({
      configured,
      loading,
      session,
      profile,
      subscription,
      entitlement,
      payments,
      devices,
      isAdmin,
      error,
      refreshAccount,
      setSessionDirect,
      signOut,
    }),
    [
      configured,
      loading,
      session,
      profile,
      subscription,
      entitlement,
      payments,
      devices,
      isAdmin,
      error,
      refreshAccount,
      setSessionDirect,
      signOut,
    ]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
