/**
 * Single source of truth for public Supabase configuration in the Android Read-Only app.
 * Reads build-time generated public config (anon/publishable key only, NEVER service_role).
 */

import { MOBILE_SUPABASE_PUBLIC_CONFIG } from "../generated/supabasePublicConfig.ts";

export interface MobileSupabaseConfig {
  supabaseUrl: string;
  supabaseAnonKey: string;
  configured: boolean;
}

export function getMobileSupabaseConfig(): MobileSupabaseConfig {
  const envUrl =
    typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_SUPABASE_URL : undefined;
  const envKey =
    typeof process !== "undefined" ? process.env?.EXPO_PUBLIC_SUPABASE_ANON_KEY : undefined;

  const supabaseUrl = String(
    MOBILE_SUPABASE_PUBLIC_CONFIG.supabaseUrl || envUrl || "https://itnxilvehaeokxvauujk.supabase.co"
  )
    .trim()
    .replace(/\/+$/, "");

  const supabaseAnonKey = String(
    MOBILE_SUPABASE_PUBLIC_CONFIG.supabaseAnonKey || envKey || ""
  ).trim();

  const configured = Boolean(supabaseUrl) && !supabaseUrl.includes("your-project-ref");
  return { supabaseUrl, supabaseAnonKey, configured };
}
