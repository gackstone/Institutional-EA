// Shared CORS and server-side JWT / Admin verification helpers for Supabase Edge Functions.
// Uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY strictly inside the protected Deno Edge runtime.

import { createClient } from "https://esm.sh/@supabase/supabase-js@2.49.1";

export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

export function createServiceClient() {
  const url = Deno.env.get("SUPABASE_URL");
  const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (!url || !serviceKey) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in Edge Function environment.");
  }
  return createClient(url, serviceKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });
}

export async function requireAuthenticatedUser(req: Request) {
  const authHeader = req.headers.get("Authorization") || "";
  const token = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!token) {
    return { user: null, profile: null, error: "Missing Authorization Bearer token." };
  }

  const service = createServiceClient();
  const { data: userData, error: userErr } = await service.auth.getUser(token);
  if (userErr || !userData?.user) {
    return { user: null, profile: null, error: "Invalid or expired authentication token." };
  }

  let { data: profile, error: profErr } = await service
    .from("profiles")
    .select("id, full_name, email, role")
    .eq("id", userData.user.id)
    .maybeSingle();

  // Safety net: if an authenticated auth.users record has no profile row yet,
  // auto-provision a lowest-privilege 'user' profile (never admin/pro).
  if (!profile && userData.user.email) {
    const emailLower = userData.user.email.toLowerCase();
    const metaName =
      typeof userData.user.user_metadata?.full_name === "string"
        ? userData.user.user_metadata.full_name.trim()
        : "";
    const fallbackName = metaName || emailLower.split("@")[0] || "Trader";

    const { error: upsertErr } = await service
      .from("profiles")
      .upsert(
        {
          id: userData.user.id,
          full_name: fallbackName,
          email: emailLower,
          role: "user",
        },
        { onConflict: "id", ignoreDuplicates: true }
      );

    if (upsertErr) {
      console.error("[auth] Failed to auto-provision missing profile row:", upsertErr.code || "unknown");
    } else {
      const refetch = await service
        .from("profiles")
        .select("id, full_name, email, role")
        .eq("id", userData.user.id)
        .maybeSingle();
      profile = refetch.data;
      profErr = refetch.error;
    }
  }

  if (profErr || !profile) {
    console.error("[auth] Profile lookup failed for authenticated user:", profErr?.code || "missing_row");
    return {
      user: userData.user,
      profile: null,
      error: "Your account profile could not be initialized. Please try again in a moment.",
    };
  }

  return { user: userData.user, profile, error: null };
}

export async function requireAdminUser(req: Request) {
  const auth = await requireAuthenticatedUser(req);
  if (auth.error || !auth.profile) {
    return { ...auth, status: 401 };
  }
  if (auth.profile.role !== "admin") {
    return {
      user: auth.user,
      profile: auth.profile,
      error: "Forbidden: administrator privileges required.",
      status: 403,
    };
  }
  return { ...auth, status: 200 };
}
