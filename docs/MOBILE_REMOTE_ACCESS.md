# Mobile Companion View & Optional Safe Remote Access

The Institutional EA Companion provides a responsive **Read-Only Mobile Companion View** automatically on phone-sized viewports (`< 768px`), featuring a fixed bottom navigation bar (**Dashboard**, **Positions**, **Signals**, **Alerts**). All order-execution controls are disabled on mobile except the existing two-step **Pause** control.

---

## Network Safety Policy (Non-Negotiable)

- The Python Control Service binds **exclusively** to `127.0.0.1:8765` with Bearer/session token authentication (`state/companion_token.txt`).
- **NEVER** bind the Control Service to `0.0.0.0`, and **NEVER** expose port `8765` or `5173` to the public internet via router port forwarding.

---

## Optional Safe Remote Access (Phone on Private Network)

If you want to view the read-only mobile dashboard from your phone while away from your trading PC, use an encrypted private tunnel instead of port forwarding:

### Option 1: Tailscale (Recommended Private Mesh VPN)
1. Install [Tailscale](https://tailscale.com/) on both your Windows trading PC and your mobile phone, signed into the same private tailnet.
2. On your Windows PC, use `tailscale serve` to proxy localhost `127.0.0.1:5173` strictly within your private tailnet (never `--funnel`):
   ```powershell
   tailscale serve --bg 5173
   ```
3. Open the private Tailscale MagicDNS URL from your phone's browser. Traffic stays end-to-end encrypted over WireGuard and is unreachable from the public internet.

### Option 2: SSH Local Port Forwarding
1. Enable OpenSSH Server on your trading PC with key-based authentication only.
2. From a mobile SSH client (e.g., Termius or Blink Shell), open a local tunnel:
   ```bash
   ssh -N -L 5173:127.0.0.1:5173 -L 8765:127.0.0.1:8765 <user>@<private-host>
   ```
3. Browse to `http://127.0.0.1:5173` on your phone.

> [!CAUTION]
> Never use router port forwarding, ngrok public URLs without auth, or `0.0.0.0` binding for a trading control surface.
