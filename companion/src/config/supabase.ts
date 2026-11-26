/**
 * Single source of truth for public Supabase client configuration metadata in the renderer.
 * Note: Sensitive auth tokens and actual Supabase requests run inside Electron's main process
 * (`companion/electron/cloudAuthManager.cjs`) using OS-encrypted Windows DPAPI storage.
 */

export interface PublicSupabaseConfig {
  supabaseUrl: string;
  supabaseAnonKey: string;
  webPortalUrl: string;
  configured: boolean;
}

export function getPublicSupabaseConfig(): PublicSupabaseConfig {
  const env = (import.meta as unknown as { env?: Record<string, string | undefined> }).env || {};
  const supabaseUrl = String(env.VITE_SUPABASE_URL || "").trim().replace(/\/+$/, "");
  const supabaseAnonKey = String(env.VITE_SUPABASE_ANON_KEY || "").trim();
  const webPortalUrl = String(env.VITE_PUBLIC_SITE_URL || "https://arcadefx.live")
    .trim()
    .replace(/\/+$/, "");

  const configured =
    Boolean(supabaseUrl) &&
    Boolean(supabaseAnonKey) &&
    !supabaseUrl.includes("your-project-ref") &&
    !supabaseAnonKey.includes("your-supabase");

  return { supabaseUrl, supabaseAnonKey, webPortalUrl, configured };
}
