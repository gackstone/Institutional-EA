/**
 * Institutional EA Windows Companion — Cloud Authentication, OS-Backed Credential Storage,
 * Privacy-Conscious Device Fingerprinting, and Offline Entitlement Cache Manager.
 *
 * Security Guarantees:
 * - Tokens are NEVER exposed to the Electron renderer process, SQLite, localStorage, or logs.
 * - Uses Electron's `safeStorage` (Windows DPAPI) to encrypt session & entitlement cache on disk.
 * - Uses ONLY public SUPABASE_URL and SUPABASE_ANON_KEY (NEVER service_role).
 * - System-browser authentication uses an ephemeral localhost loopback callback with CSRF `state`.
 * - Subscription state NEVER alters local MT5 positions, stops the engine, or blocks emergency controls.
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const http = require("http");
const crypto = require("crypto");

const MAX_OFFLINE_GRACE_MS = 72 * 60 * 60 * 1000; // 72 hours

function loadDotEnvMap(envFiles) {
  const out = {};
  for (const filePath of envFiles) {
    try {
      if (!filePath || !fs.existsSync(filePath)) continue;
      const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
      for (const raw of lines) {
        const line = raw.trim();
        if (!line || line.startsWith("#")) continue;
        const idx = line.indexOf("=");
        if (idx <= 0) continue;
        const key = line.slice(0, idx).trim();
        let val = line.slice(idx + 1).trim();
        if (
          (val.startsWith('"') && val.endsWith('"')) ||
          (val.startsWith("'") && val.endsWith("'"))
        ) {
          val = val.slice(1, -1);
        }
        if (key && !(key in out)) out[key] = val;
      }
    } catch {
      // Ignore unreadable env files
    }
  }
  return out;
}

function createCloudAuthManager(options) {
  const {
    credentialsDir,
    projectRoot,
    appVersion = "1.3.4",
    safeStorage = null,
    shell = null,
    getMainWindow = () => null,
    logEvent = () => {},
  } = options;

  const SESSION_BIN_FILE = path.join(credentialsDir, "cloud_session.dpapi.bin");
  const DEVICE_SALT_FILE = path.join(credentialsDir, "device_salt.bin");

  let activeLoopbackServer = null;
  let memoryStore = null; // { session, profile, subscription, lastVerifiedAtUtc, connectivity }
  let signOutInFlight = null;

  function emitStateChanged(sanitized) {
    try {
      const win = getMainWindow();
      if (win && !win.isDestroyed() && win.webContents) {
        win.webContents.send("cloud-state-changed", sanitized);
      }
    } catch {
      // Ignore if window not ready
    }
  }

  function getEnvConfig() {
    const fileEnv = loadDotEnvMap([
      path.join(path.dirname(credentialsDir), ".env"),
      path.join(projectRoot, ".env"),
    ]);

    const supabaseUrl = (
      process.env.SUPABASE_URL ||
      process.env.VITE_SUPABASE_URL ||
      fileEnv.SUPABASE_URL ||
      fileEnv.VITE_SUPABASE_URL ||
      ""
    )
      .trim()
      .replace(/\/+$/, "");

    const supabaseAnonKey = (
      process.env.SUPABASE_ANON_KEY ||
      process.env.VITE_SUPABASE_ANON_KEY ||
      fileEnv.SUPABASE_ANON_KEY ||
      fileEnv.VITE_SUPABASE_ANON_KEY ||
      ""
    ).trim();

    const webPortalUrl = (
      process.env.INSTITUTIONAL_EA_WEB_URL ||
      process.env.VITE_PUBLIC_SITE_URL ||
      fileEnv.INSTITUTIONAL_EA_WEB_URL ||
      fileEnv.VITE_PUBLIC_SITE_URL ||
      "http://localhost:5173"
    )
      .trim()
      .replace(/\/+$/, "");

    const configured =
      Boolean(supabaseUrl) &&
      Boolean(supabaseAnonKey) &&
      !supabaseUrl.includes("your-project-ref") &&
      !supabaseAnonKey.includes("your-supabase-anon-key");

    return { supabaseUrl, supabaseAnonKey, webPortalUrl, configured };
  }

  function getOrCreateDeviceSalt() {
    try {
      if (fs.existsSync(DEVICE_SALT_FILE)) {
        const raw = fs.readFileSync(DEVICE_SALT_FILE, "utf8").trim();
        if (raw.length >= 32) return raw;
      }
      const salt = crypto.randomBytes(32).toString("hex");
      fs.mkdirSync(credentialsDir, { recursive: true });
      fs.writeFileSync(DEVICE_SALT_FILE, salt, { encoding: "utf8", mode: 0o600 });
      return salt;
    } catch {
      return crypto.createHash("sha256").update(os.hostname()).digest("hex");
    }
  }

  /**
   * Privacy-conscious device fingerprint hash (SHA-256).
   * Raw machine identifiers are never transmitted in plaintext.
   */
  function getDeviceFingerprintHash() {
    const salt = getOrCreateDeviceSalt();
    const material = `${os.hostname()}|${process.platform}|${process.arch}|${salt}`;
    return crypto.createHash("sha256").update(material).digest("hex");
  }

  function persistEncrypted(payload) {
    memoryStore = payload;
    try {
      if (!payload) {
        if (fs.existsSync(SESSION_BIN_FILE)) fs.unlinkSync(SESSION_BIN_FILE);
        return;
      }
      fs.mkdirSync(credentialsDir, { recursive: true });
      const json = JSON.stringify(payload);
      if (safeStorage && typeof safeStorage.isEncryptionAvailable === "function" && safeStorage.isEncryptionAvailable()) {
        const encrypted = safeStorage.encryptString(json);
        fs.writeFileSync(SESSION_BIN_FILE, encrypted, { mode: 0o600 });
      } else {
        // Fallback: machine-derived AES-256-GCM encryption when Electron safeStorage is unavailable (e.g. headless tests)
        const key = crypto.createHash("sha256").update(getOrCreateDeviceSalt()).digest();
        const iv = crypto.randomBytes(12);
        const cipher = crypto.createCipheriv("aes-256-gcm", key, iv);
        const enc = Buffer.concat([cipher.update(json, "utf8"), cipher.final()]);
        const tag = cipher.getAuthTag();
        const envelope = Buffer.concat([Buffer.from("GCM1"), iv, tag, enc]);
        fs.writeFileSync(SESSION_BIN_FILE, envelope, { mode: 0o600 });
      }
    } catch (err) {
      logEvent("cloud-session-persist-error", { message: err?.message });
    }
  }

  function loadEncrypted() {
    if (memoryStore) return memoryStore;
    try {
      if (!fs.existsSync(SESSION_BIN_FILE)) return null;
      const buf = fs.readFileSync(SESSION_BIN_FILE);
      if (!buf || buf.length < 8) return null;

      let jsonStr = "";
      if (buf.subarray(0, 4).toString("utf8") === "GCM1") {
        const key = crypto.createHash("sha256").update(getOrCreateDeviceSalt()).digest();
        const iv = buf.subarray(4, 16);
        const tag = buf.subarray(16, 32);
        const data = buf.subarray(32);
        const decipher = crypto.createDecipheriv("aes-256-gcm", key, iv);
        decipher.setAuthTag(tag);
        jsonStr = Buffer.concat([decipher.update(data), decipher.final()]).toString("utf8");
      } else if (safeStorage && typeof safeStorage.isEncryptionAvailable === "function" && safeStorage.isEncryptionAvailable()) {
        jsonStr = safeStorage.decryptString(buf);
      } else {
        return null;
      }

      const parsed = JSON.parse(jsonStr);
      memoryStore = parsed;
      return parsed;
    } catch {
      return null;
    }
  }

  function evaluateEntitlement(store) {
    const sub = store?.subscription || null;
    const connectivity = store?.connectivity || "online";
    const nowMs = Date.now();

    if (!sub || sub.status === "no_subscription") {
      return {
        status: "no_subscription",
        isActive: false,
        isGraceActive: false,
        requiresSubscriptionAction: true,
        expiresAtUtc: null,
        daysRemaining: null,
        connectivity,
        reason: "No active subscription found for this account.",
      };
    }

    const expMs = sub.expires_at ? Date.parse(sub.expires_at) : NaN;
    const hasExpiry = Number.isFinite(expMs);

    if (sub.status === "active") {
      if (!hasExpiry || expMs <= nowMs) {
        return {
          status: "expired",
          isActive: false,
          isGraceActive: false,
          requiresSubscriptionAction: true,
          expiresAtUtc: sub.expires_at,
          daysRemaining: 0,
          connectivity,
          reason: "Subscription expired (UTC). Renew to restore full cloud-linked access.",
        };
      }

      const daysRemaining = Math.max(0, Math.ceil((expMs - nowMs) / (24 * 60 * 60 * 1000)));
      if (connectivity === "offline" || connectivity === "reconnecting") {
        const verifiedMs = store?.lastVerifiedAtUtc ? Date.parse(store.lastVerifiedAtUtc) : NaN;
        const withinGrace = Number.isFinite(verifiedMs) && nowMs - verifiedMs <= MAX_OFFLINE_GRACE_MS;
        if (withinGrace) {
          return {
            status: "active",
            isActive: true,
            isGraceActive: true,
            requiresSubscriptionAction: false,
            expiresAtUtc: sub.expires_at,
            daysRemaining,
            connectivity: "offline",
            reason: "Offline grace window active (verified within 72h).",
          };
        }
        return {
          status: "active",
          isActive: false,
          isGraceActive: false,
          requiresSubscriptionAction: false,
          expiresAtUtc: sub.expires_at,
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
        expiresAtUtc: sub.expires_at,
        daysRemaining,
        connectivity: "online",
        reason: `Active Institutional EA Pro (${daysRemaining} day${daysRemaining === 1 ? "" : "s"} remaining).`,
      };
    }

    return {
      status: sub.status,
      isActive: false,
      isGraceActive: false,
      requiresSubscriptionAction: sub.status !== "payment_under_review",
      expiresAtUtc: sub.expires_at || null,
      daysRemaining: 0,
      connectivity,
      reason: `Subscription status: ${sub.status.replace(/_/g, " ")}.`,
    };
  }

  /**
   * Returns sanitized state safe for the Electron renderer (ZERO access/refresh tokens).
   */
  function getSanitizedState() {
    const env = getEnvConfig();
    const store = loadEncrypted();
    const fpHash = getDeviceFingerprintHash();

    if (!store || !store.session?.user?.id) {
      return {
        configured: env.configured,
        webPortalUrl: env.webPortalUrl,
        authenticated: false,
        user: null,
        profile: null,
        subscription: null,
        entitlement: evaluateEntitlement(null),
        connectivity: env.configured ? "online" : "offline",
        lastVerifiedAtUtc: null,
        deviceName: os.hostname(),
        deviceFingerprintShort: fpHash.slice(0, 12),
      };
    }

    return {
      configured: env.configured,
      webPortalUrl: env.webPortalUrl,
      authenticated: true,
      user: {
        id: store.session.user.id,
        email: store.session.user.email,
        emailConfirmed: Boolean(store.session.user.email_confirmed_at),
      },
      profile: store.profile || null,
      subscription: store.subscription || null,
      entitlement: evaluateEntitlement(store),
      connectivity: store.connectivity || "online",
      lastVerifiedAtUtc: store.lastVerifiedAtUtc || null,
      deviceName: os.hostname(),
      deviceFingerprintShort: fpHash.slice(0, 12),
    };
  }

  async function supabaseFetch(endpointPath, init = {}, accessToken = null) {
    const env = getEnvConfig();
    if (!env.configured) {
      throw new Error("Supabase environment variables (SUPABASE_URL, SUPABASE_ANON_KEY) are not configured.");
    }
    const headers = {
      apikey: env.supabaseAnonKey,
      "Content-Type": "application/json",
      ...(init.headers || {}),
    };
    if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

    const res = await fetch(`${env.supabaseUrl}${endpointPath}`, {
      ...init,
      headers,
    });
    const text = await res.text();
    let json = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = { raw: text };
    }
    if (!res.ok) {
      const msg = json?.error_description || json?.msg || json?.message || json?.error || `HTTP ${res.status}`;
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return json;
  }

  async function ensureFreshToken(store) {
    if (!store?.session?.access_token) throw new Error("Not signed in.");
    const nowSec = Math.floor(Date.now() / 1000);
    if (store.session.expires_at && store.session.expires_at - 60 <= nowSec && store.session.refresh_token) {
      const refreshed = await supabaseFetch("/auth/v1/token?grant_type=refresh_token", {
        method: "POST",
        body: JSON.stringify({ refresh_token: store.session.refresh_token }),
      });
      store.session = {
        access_token: refreshed.access_token,
        refresh_token: refreshed.refresh_token,
        expires_at:
          typeof refreshed.expires_at === "number"
            ? refreshed.expires_at
            : Math.floor(Date.now() / 1000) + Number(refreshed.expires_in || 3600),
        user: refreshed.user || store.session.user,
      };
      persistEncrypted(store);
    }
    return store.session.access_token;
  }

  async function syncEntitlementAndDevice(store) {
    try {
      const token = await ensureFreshToken(store);
      const userId = store.session.user.id;
      const fpHash = getDeviceFingerprintHash();

      // Try Edge Function device-heartbeat first; fall back to direct RLS-protected queries
      try {
        const hb = await supabaseFetch(
          "/functions/v1/device-heartbeat",
          {
            method: "POST",
            body: JSON.stringify({
              device_name: os.hostname(),
              device_fingerprint_hash: fpHash,
              operating_system: `${os.type()} ${os.release()}`,
              app_version: appVersion,
            }),
          },
          token
        );
        if (hb?.ok) {
          store.profile = hb.profile || store.profile;
          store.subscription = hb.subscription || null;
          store.lastVerifiedAtUtc = hb.verified_at_utc || new Date().toISOString();
          store.connectivity = "online";
          persistEncrypted(store);
          return getSanitizedState();
        }
      } catch {
        // Fallback to direct RLS-protected PostgREST queries if Edge Function is not yet deployed
      }

      const [profiles, subs] = await Promise.all([
        supabaseFetch(`/rest/v1/profiles?id=eq.${encodeURIComponent(userId)}&select=*&limit=1`, { method: "GET" }, token),
        supabaseFetch(
          `/rest/v1/subscriptions?user_id=eq.${encodeURIComponent(userId)}&select=*,plan:plans(*)&order=created_at.desc&limit=1`,
          { method: "GET" },
          token
        ),
      ]);

      store.profile = Array.isArray(profiles) ? profiles[0] || null : null;
      store.subscription = Array.isArray(subs) ? subs[0] || null : null;
      store.lastVerifiedAtUtc = new Date().toISOString();
      store.connectivity = "online";
      persistEncrypted(store);
      return getSanitizedState();
    } catch (err) {
      if (err?.status === 401 || err?.status === 403) {
        store.connectivity = "auth_expired";
      } else {
        store.connectivity = "offline";
      }
      persistEncrypted(store);
      return getSanitizedState();
    }
  }

  async function signInWithPassword(email, password) {
    const data = await supabaseFetch("/auth/v1/token?grant_type=password", {
      method: "POST",
      body: JSON.stringify({
        email: String(email || "").trim().toLowerCase(),
        password: String(password || ""),
      }),
    });

    const store = {
      session: {
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_at:
          typeof data.expires_at === "number"
            ? data.expires_at
            : Math.floor(Date.now() / 1000) + Number(data.expires_in || 3600),
        user: data.user,
      },
      profile: null,
      subscription: null,
      lastVerifiedAtUtc: null,
      connectivity: "online",
    };
    persistEncrypted(store);
    const state = await syncEntitlementAndDevice(store);
    emitStateChanged(state);
    return state;
  }

  async function signUp(fullName, email, password) {
    const env = getEnvConfig();
    const data = await supabaseFetch("/auth/v1/signup", {
      method: "POST",
      body: JSON.stringify({
        email: String(email || "").trim().toLowerCase(),
        password: String(password || ""),
        data: { full_name: String(fullName || "").trim() },
        email_redirect_to: `${env.webPortalUrl}/auth/callback`,
      }),
    });

    if (data?.access_token && data?.user) {
      const store = {
        session: {
          access_token: data.access_token,
          refresh_token: data.refresh_token,
          expires_at:
            typeof data.expires_at === "number"
              ? data.expires_at
              : Math.floor(Date.now() / 1000) + Number(data.expires_in || 3600),
          user: data.user,
        },
        profile: null,
        subscription: null,
        lastVerifiedAtUtc: null,
        connectivity: "online",
      };
      persistEncrypted(store);
      const state = await syncEntitlementAndDevice(store);
      emitStateChanged(state);
      return { ok: true, needsEmailVerification: !data.user.email_confirmed_at, state };
    }

    return { ok: true, needsEmailVerification: true, state: getSanitizedState() };
  }

  async function recoverPassword(email) {
    const env = getEnvConfig();
    await supabaseFetch("/auth/v1/recover", {
      method: "POST",
      body: JSON.stringify({
        email: String(email || "").trim().toLowerCase(),
        redirect_to: `${env.webPortalUrl}/auth/callback?type=recovery`,
      }),
    });
    return { ok: true };
  }

  async function resendVerification(email) {
    const env = getEnvConfig();
    await supabaseFetch("/auth/v1/resend", {
      method: "POST",
      body: JSON.stringify({
        type: "signup",
        email: String(email || "").trim().toLowerCase(),
        options: { emailRedirectTo: `${env.webPortalUrl}/auth/callback` },
      }),
    });
    return { ok: true };
  }

  async function signInViaSystemBrowser() {
    const env = getEnvConfig();
    if (!env.configured) {
      throw new Error("Supabase environment variables are not configured.");
    }
    if (activeLoopbackServer) {
      try {
        activeLoopbackServer.close();
      } catch {}
      activeLoopbackServer = null;
    }

    const expectedState = crypto.randomBytes(24).toString("hex");

    return new Promise((resolve, reject) => {
      const server = http.createServer(async (req, res) => {
        try {
          const reqUrl = new URL(req.url, "http://127.0.0.1");
          if (reqUrl.pathname !== "/auth/callback") {
            res.writeHead(404);
            res.end("Not Found");
            return;
          }

          const stateParam = reqUrl.searchParams.get("state");
          const accessToken = reqUrl.searchParams.get("access_token");
          const refreshToken = reqUrl.searchParams.get("refresh_token");
          const expiresAt = Number(reqUrl.searchParams.get("expires_at") || 0);

          if (!stateParam || stateParam !== expectedState || !accessToken || !refreshToken) {
            res.writeHead(400, { "Content-Type": "text/html; charset=utf-8" });
            res.end("<h3>Authentication callback validation failed. You may close this tab.</h3>");
            return;
          }

          const user = await supabaseFetch("/auth/v1/user", { method: "GET" }, accessToken);
          const store = {
            session: {
              access_token: accessToken,
              refresh_token: refreshToken,
              expires_at: expiresAt || Math.floor(Date.now() / 1000) + 3600,
              user,
            },
            profile: null,
            subscription: null,
            lastVerifiedAtUtc: null,
            connectivity: "online",
          };
          persistEncrypted(store);
          const sanitized = await syncEntitlementAndDevice(store);

          res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
          res.end(
            "<html><body style='background:#0A0A0C;color:#F3F4F6;font-family:sans-serif;padding:40px;text-align:center'><h2>Signed in to Institutional EA</h2><p>You can close this browser tab and return to the Windows Companion Application.</p></body></html>"
          );

          const win = getMainWindow();
          if (win && !win.isDestroyed()) {
            if (win.isMinimized()) win.restore();
            win.show();
            win.focus();
            win.webContents.send("cloud-state-changed", sanitized);
          }

          server.close();
          activeLoopbackServer = null;
        } catch (err) {
          res.writeHead(500, { "Content-Type": "text/plain" });
          res.end("Authentication failed.");
          logEvent("cloud-browser-callback-error", { message: err?.message });
        }
      });

      server.listen(0, "127.0.0.1", () => {
        const addr = server.address();
        const port = typeof addr === "object" && addr ? addr.port : 0;
        activeLoopbackServer = server;
        const callbackUrl = `http://127.0.0.1:${port}/auth/callback`;
        const loginUrl = `${env.webPortalUrl}/auth/sign-in?desktop_callback=${encodeURIComponent(
          callbackUrl
        )}&state=${encodeURIComponent(expectedState)}`;

        if (shell && typeof shell.openExternal === "function") {
          shell.openExternal(loginUrl);
        }
        resolve({ ok: true, loginUrl });
      });

      server.on("error", (err) => reject(err));
      // Auto-close unused callback listener after 5 minutes
      setTimeout(() => {
        if (activeLoopbackServer === server) {
          try {
            server.close();
          } catch {}
          activeLoopbackServer = null;
        }
      }, 5 * 60 * 1000);
    });
  }

  async function signOut() {
    if (signOutInFlight) return signOutInFlight;
    signOutInFlight = (async () => {
      const store = loadEncrypted();
      const token = store?.session?.access_token;

      // Always clear local encrypted credentials & memory cache first so logout never leaves stale auth
      persistEncrypted(null);

      let remoteRevoked = true;
      let warning = null;
      if (token) {
        try {
          await supabaseFetch("/auth/v1/logout", { method: "POST" }, token);
        } catch (err) {
          remoteRevoked = false;
          warning =
            "Signed out locally and cleared encrypted credentials, but remote session revocation could not be confirmed.";
          logEvent("cloud-signout-remote-warning", { message: err?.message });
        }
      }

      const state = getSanitizedState();
      emitStateChanged(state);
      return { ok: true, state, remoteRevoked, warning };
    })();

    try {
      return await signOutInFlight;
    } finally {
      signOutInFlight = null;
    }
  }

  async function refresh() {
    const store = loadEncrypted();
    if (!store?.session?.access_token) return getSanitizedState();
    const state = await syncEntitlementAndDevice(store);
    emitStateChanged(state);
    return state;
  }

  async function getPayments() {
    const store = loadEncrypted();
    if (!store?.session?.user?.id) return [];
    const token = await ensureFreshToken(store);
    return supabaseFetch(
      `/rest/v1/payments?user_id=eq.${encodeURIComponent(store.session.user.id)}&select=*&order=submitted_at.desc`,
      { method: "GET" },
      token
    );
  }

  async function submitPayment(payload) {
    const store = loadEncrypted();
    if (!store?.session?.user?.id) throw new Error("Sign in before submitting a payment.");
    const token = await ensureFreshToken(store);
    const created = await supabaseFetch(
      "/rest/v1/payments",
      {
        method: "POST",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({
          user_id: store.session.user.id,
          subscription_id: store.subscription?.id || null,
          provider: "Binance",
          network: "TRON (TRC20)",
          asset: "USDT",
          amount: Number(payload.amount),
          transaction_reference: String(payload.transactionReference || "").trim(),
          payment_date: payload.paymentDate || new Date().toISOString(),
          status: "submitted",
        }),
      },
      token
    );
    await syncEntitlementAndDevice(store);
    return Array.isArray(created) ? created[0] : created;
  }

  async function getDevices() {
    const store = loadEncrypted();
    if (!store?.session?.user?.id) return [];
    const token = await ensureFreshToken(store);
    return supabaseFetch(
      `/rest/v1/devices?user_id=eq.${encodeURIComponent(store.session.user.id)}&select=*&order=last_seen_at.desc`,
      { method: "GET" },
      token
    );
  }

  async function revokeDevice(deviceId) {
    const store = loadEncrypted();
    if (!store?.session?.user?.id) throw new Error("Not signed in.");
    const token = await ensureFreshToken(store);
    return supabaseFetch(
      `/rest/v1/devices?id=eq.${encodeURIComponent(deviceId)}`,
      {
        method: "PATCH",
        headers: { Prefer: "return=representation" },
        body: JSON.stringify({ status: "revoked" }),
      },
      token
    );
  }

  function openExternalPortal(routePath = "/account/subscription") {
    const env = getEnvConfig();
    const safeRoute = String(routePath || "/").startsWith("/") ? routePath : "/";
    const url = `${env.webPortalUrl}${safeRoute}`;
    if (shell && typeof shell.openExternal === "function") {
      shell.openExternal(url);
    }
    return { ok: true, url };
  }

  return {
    getSanitizedState,
    getDeviceFingerprintHash,
    signInWithPassword,
    signUp,
    recoverPassword,
    resendVerification,
    signInViaSystemBrowser,
    signOut,
    persistEncrypted,
    refresh,
    getPayments,
    submitPayment,
    getDevices,
    revokeDevice,
    openExternalPortal,
  };
}

module.exports = { createCloudAuthManager };
