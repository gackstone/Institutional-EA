# Institutional EA — Mobile Sync Architecture & API Contract

> **Schema Version:** `1.0.0` (`/api/mobile/v1/...`)  
> **Access Model:** Opt-in LAN, Authenticated, Revocable, **Strictly Read-Only**

---

## 1. Security Model & Read-Only Enforcement

1. **Opt-In by Default:** The Mobile Sync LAN server (`companion/service/mobile/sync_server.py`) is **OFF by default**. When disabled, the companion binds **only** to `127.0.0.1:8765` (localhost). No LAN socket is opened until the desktop operator explicitly enables **Settings -> Mobile Sync** in the Windows Companion.
2. **Protocol-Level Read-Only Separation:**
   - The desktop control server (`127.0.0.1:8765`) remains strictly localhost-only and accepts only the desktop session token (`LocalAuthManager`).
   - The opt-in Mobile Sync server (default port `8766`) exposes **only** `/api/mobile/v1/...` read-only endpoints plus pairing/self-unpair:
     - `POST /api/mobile/v1/pair` (unauthenticated, rate-limited: max 5 failed attempts per IP per 5 minutes -> `429 RATE_LIMITED`, single-use 6-digit code with 5-minute TTL).
     - `POST /api/mobile/v1/unpair` (authenticated; revokes only the calling device's own token).
     - Every other `POST`, `PUT`, `PATCH`, or `DELETE` request (including `/api/engine/*`, `/api/trades/*`, `/api/config/*`) is rejected with **HTTP `403 Forbidden`** and `{"error": "READ_ONLY_ENFORCED"}`.
   - Mobile device tokens (`iea_ro_<random>`) are completely isolated from the desktop session token. A mobile token cannot authenticate against `127.0.0.1:8765`, and the desktop token cannot authenticate against the mobile server.
3. **Token Storage & Revocation:**
   - **Companion side:** Device tokens are stored in `data/mobile_sync.db` as **SHA-256 hashes** only (never plaintext) and compared with `hmac.compare_digest`. Revoking a device from either the desktop or the phone immediately invalidates the token and sends a `revoked` SSE event to disconnect active streams.
   - **Android side:** Pairing credentials (`deviceToken`, `host`, `port`, `deviceId`) are stored in **Android Keystore / EncryptedSharedPreferences** via `expo-secure-store`, never in plain `AsyncStorage`.
   - **No Broker/API Secrets:** Account numbers are masked (`50***654`). MT5 passwords, broker credentials, Telegram tokens, and API keys are never transmitted to or stored on the phone.
4. **LAN Transport & Trade-Offs:**
   - Direct LAN pairing uses HTTP over the user's private Wi-Fi network (RFC1918 subnets: `192.168.0.0/16`, `10.0.0.0/8`, `172.16.0.0/12`) rather than self-signed HTTPS, because Android's WebView and `fetch` reject self-signed certificates for dynamic LAN IP addresses without a user-installed CA.
   - On Android 9+ (API 28+), `network_security_config.xml` restricts cleartext traffic exclusively to local LAN hosts while keeping HTTPS enforced for public domains.
   - **Mitigations:** Opt-in toggle (off by default), per-device high-entropy bearer tokens, short-lived single-use 6-digit pairing codes, rate limiting, and strict read-only scope (even a compromised token on a shared LAN cannot place, modify, or close trades).

---

## 2. Pairing Flow

1. On the Windows Companion, open **Settings -> Mobile Sync** and click **Enable**.
2. The companion starts the read-only LAN server (port `8766`), discovers local LAN IPv4 addresses, and displays:
   - A **QR code** encoding:
     ```json
     {
       "v": 1,
       "host": "192.168.1.42",
       "hosts": ["192.168.1.42"],
       "port": 8766,
       "code": "482910",
       "expiresAt": 1764162000,
       "companionName": "DESKTOP-PC"
     }
     ```
   - The **6-digit code** with a live 5-minute expiry countdown and `Host:Port` for manual entry.
3. On the Android app (**Security** tab or unpaired onboarding screen), tap **Scan QR Code** or enter `Host:Port` + 6-digit code manually.
4. The app sends `POST /api/mobile/v1/pair` with `{ code, deviceName, platform: "android" }`.
5. The companion validates the code (single-use), stores the hashed device token, and returns `{ deviceId, deviceToken, companionName, schemaVersion, readOnly: true, pairedAt }`.
6. The app saves credentials into Android Keystore (`expo-secure-store`) and opens the live SSE stream (`/api/mobile/v1/events`).

---

## 3. Versioned Read-Only API Contract (`/api/mobile/v1`)

All endpoints (except `/health` and `/pair`) require `Authorization: Bearer <deviceToken>` (or `?token=<deviceToken>` for SSE). All JSON payloads are runtime-validated on the phone with **Zod** (`@institutional-ea/data-contract`). Responses > 512 bytes support `Accept-Encoding: gzip`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/mobile/v1/health` | Unauthenticated liveness probe (`{ ok, schemaVersion, readOnlyEnforced }`). |
| `POST` | `/api/mobile/v1/pair` | Exchange 6-digit code for revocable read-only device token (rate-limited). |
| `POST` | `/api/mobile/v1/unpair` | Revoke the calling device's own token. |
| `GET` | `/api/mobile/v1/status` | Bot state (`RUNNING`/`PAUSED`/`STOPPED`/etc.), MT5 connection, demo flag, masked account, last heartbeat, server time, `readOnlyEnforced: true`. |
| `GET` | `/api/mobile/v1/account` | Balance, equity, margin, free margin, margin level, floating P/L, currency, leverage, open positions count. |
| `GET` | `/api/mobile/v1/stats` | Today P/L, total profit, win rate, deals count, trades today, wins/losses — computed by the companion from real deal history. |
| `GET` | `/api/mobile/v1/positions` | Live open positions with symbol, digits, volume, open/current price, SL/TP, profit, swap, openTime, ownership. |
| `GET` | `/api/mobile/v1/trades` | Paginated, filterable trade history (`?page&limit&symbol&from&to&outcome&sort&q`) + filtered summary strip (`count`, `netPnl`, `winRate`, `wins`, `losses`). |
| `GET` | `/api/mobile/v1/candles` | OHLCV bars + live bid/ask/spread/digits/point (`?symbol&tf&from&to&limit`). |
| `GET` | `/api/mobile/v1/drawings` | Exact `EngineDrawingsFeed` (`LIQ`, `FVG`, `OB`, `IFVG`, `STRUCT`, `SESS`, `TRADE`, `mtf_levels`) matching the desktop chart. |
| `GET` | `/api/mobile/v1/symbols` | Available symbols (with live quote & specs), supported timeframes (`M1`–`H4`), and layer keys. |
| `GET` | `/api/mobile/v1/equity` | Real equity/balance curve (`?range=1D|1W|1M|ALL`). |
| `GET` | `/api/mobile/v1/activity` | Recent bot activity feed (trades, alerts, structure/engine events). |
| `GET` | `/api/mobile/v1/events` | Server-Sent Events (SSE) stream pushing initial `snapshot`, live updates, 15s `ping` heartbeats, and `revoked` notifications. |

---

## 4. Desktop Management Endpoints (Localhost-Only `127.0.0.1:8765`)

Authenticated with desktop `LocalAuthManager` token only:
- `GET /api/mobile-sync/status`
- `POST /api/mobile-sync/enable`
- `POST /api/mobile-sync/disable`
- `POST /api/mobile-sync/pairing-code`
- `POST /api/mobile-sync/devices/revoke`
- `POST /api/mobile-sync/devices/revoke-all`

---

## 5. Troubleshooting

- **Phone cannot reach PC after pairing:** Ensure both devices are on the same Wi-Fi network (not Guest Wi-Fi with client isolation) and allow inbound TCP port `8766` on Private networks in Windows Defender Firewall.
- **PC IP address changed:** Re-open **Mobile Sync** on the PC and scan the new QR code (or update the host IP in **Security** tab).
- **"Stale" or "Companion Offline" banner:** The app uses exponential backoff (`1s -> 2s -> 4s -> ... -> 30s`) and automatically reconnects when the PC wakes or the companion restarts. Cached data is always clearly labeled `Last synced <time>` and never shown as live.
- **401 / Revoked:** If the device was revoked on the PC, the app clears its token and returns to the pairing screen.
