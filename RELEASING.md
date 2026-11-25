# Releasing Institutional EA

This guide documents how to build, sign, verify, and publish **Institutional EA** across all four platforms (Windows, macOS, Android, iOS) and update the Vercel download landing page.

> **Security Rule:** Never commit `.env`, `.jks`/`.keystore`, `.p12`, `.pem`, `.mobileprovision`, or API tokens to Git. All signing materials are supplied strictly via GitHub Actions Secrets or EAS Secrets.

---

## 1. Stable Public Download Links

Every GitHub Release automatically publishes both versioned files and **fixed-name assets** so landing page buttons never break between versions:

| Platform | Fixed Asset Name | Stable Public URL |
|---|---|---|
| Windows | `InstitutionalEA-Setup.exe` | `https://github.com/gackstone/Institutional-EA/releases/latest/download/InstitutionalEA-Setup.exe` |
| macOS | `InstitutionalEA.dmg` | `https://github.com/gackstone/Institutional-EA/releases/latest/download/InstitutionalEA.dmg` |
| Android (Direct) | `InstitutionalEA.apk` | `https://github.com/gackstone/Institutional-EA/releases/latest/download/InstitutionalEA.apk` |
| Android (Play Store) | `InstitutionalEA.aab` | `https://github.com/gackstone/Institutional-EA/releases/latest/download/InstitutionalEA.aab` |
| Checksums | `SHA256SUMS.txt` | `https://github.com/gackstone/Institutional-EA/releases/latest/download/SHA256SUMS.txt` |
| iOS | TestFlight Public Link | Configured in `apps/web/src/config/downloads.config.ts` |

---

## 2. GitHub Actions Secrets (Names Only)

Configure these in **GitHub → Settings → Secrets and variables → Actions**. Any missing signing secret causes that job to emit a warning and produce an **unsigned** build rather than failing.

| Secret Name | Platform | Purpose |
|---|---|---|
| `WIN_CSC_LINK` | Windows | Base64-encoded `.pfx`/`.p12` Authenticode certificate |
| `WIN_CSC_KEY_PASSWORD` | Windows | Password for `WIN_CSC_LINK` |
| `MAC_CSC_LINK` | macOS | Base64-encoded Developer ID Application `.p12` certificate |
| `MAC_CSC_KEY_PASSWORD` | macOS | Password for `MAC_CSC_LINK` |
| `APPLE_ID` | macOS | Apple ID email for notarization |
| `APPLE_APP_SPECIFIC_PASSWORD` | macOS | App-specific password generated at appleid.apple.com |
| `APPLE_TEAM_ID` | macOS | 10-character Apple Developer Team ID |
| `ANDROID_KEYSTORE_BASE64` | Android | Base64-encoded release `.keystore` / `.jks` file |
| `ANDROID_KEYSTORE_PASSWORD` | Android | Keystore store password |
| `ANDROID_KEY_ALIAS` | Android | Key alias inside the keystore |
| `ANDROID_KEY_PASSWORD` | Android | Key password for the alias |
| `EXPO_TOKEN` | iOS (optional) | Expo Access Token for EAS Build / TestFlight submission |

---

## 3. Generating the Android Release Keystore (One-Time)

Run this **locally on a secure machine** (never inside the repo):

```bash
keytool -genkeypair -v -storetype PKCS12 \
  -keystore institutional-ea-release.keystore \
  -alias institutional-ea \
  -keyalg RSA -keysize 2048 -validity 10000
```

Encode it to Base64 for `ANDROID_KEYSTORE_BASE64`:

- **Windows PowerShell:**
  ```powershell
  [Convert]::ToBase64String([IO.File]::ReadAllBytes("institutional-ea-release.keystore")) | Set-Clipboard
  ```
- **macOS / Linux:**
  ```bash
  base64 -i institutional-ea-release.keystore | tr -d '\n'
  ```

Store the `.keystore` file in an encrypted password manager / offline backup. Losing it prevents updating an existing Play Store listing.

---

## 4. iOS Setup: Apple Developer, EAS & TestFlight Public Link

iOS distribution outside Expo Go requires a paid **Apple Developer Program** membership (\$99/year). Until configured, the CI `ios` job automatically skips without failing the release.

### One-Time Setup
1. **Enroll** in the Apple Developer Program at https://developer.apple.com/programs/.
2. **Register Bundle ID** `com.institutionalea.monitor` in Apple Developer Portal → Identifiers.
3. **Create App Record** in App Store Connect (https://appstoreconnect.apple.com) named **Institutional EA** bound to `com.institutionalea.monitor`.
4. **Add `EXPO_TOKEN`** (from https://expo.dev/settings/access-tokens) to GitHub Secrets.
5. **Configure EAS Credentials** once from `apps/mobile`:
   ```bash
   npx eas-cli login
   npx eas-cli credentials -p ios
   ```
6. **Build & Submit to TestFlight:**
   ```bash
   npx eas-cli build --platform ios --profile production
   npx eas-cli submit --platform ios --latest
   ```
7. **Create a TestFlight Public Link:**
   - Open App Store Connect → **TestFlight** → **External Testing** → create a group (e.g. `Public Beta`).
   - Add your build, complete Beta App Review, and click **Enable Public Link**.
   - Copy the `https://testflight.apple.com/join/...` URL into `DOWNLOAD_PLATFORMS.ios.downloadUrl` in `apps/web/src/config/downloads.config.ts`.

### Free Alternative for iOS Testers (Expo Go)
Before Apple Developer enrollment, testers can install **Expo Go** from the App Store and preview the read-only mobile app by scanning the QR code from:
```bash
cd apps/mobile && npx expo start
```

---

## 5. Cutting a Release

### Step A — Dry-Run (Draft Release)
1. Go to **GitHub → Actions → Release Multi-Platform Builds → Run workflow**.
2. Leave `draft: true` and set `release_tag` (e.g. `v1.3.0-draft`).
3. Verify all jobs succeed, inspect the draft release assets and `SHA256SUMS.txt`, and test the installers.

### Step B — Official Release
1. Ensure version matches in:
   - `package.json` (`1.3.0`)
   - `companion/package.json` (`1.3.0`)
   - `apps/mobile/package.json` (`1.3.0`)
   - `apps/mobile/app.json` (`version`, `android.versionCode`, `ios.buildNumber`)
   - `apps/web/src/config/downloads.config.ts` (`DEFAULT_APP_VERSION`)
2. Commit and push to `origin main`.
3. Create and push the version tag (only after confirming):
   ```bash
   git tag v1.3.0
   git push origin v1.3.0
   ```
4. The workflow builds Windows, macOS, and Android (plus iOS if `EXPO_TOKEN` is set) and publishes the GitHub Release with auto-generated notes and checksums.

---

## 6. Deploying the Download Landing Page (Vercel)

The landing page lives in `apps/web/` and is configured with `apps/web/vercel.json`:
1. Import `gackstone/Institutional-EA` in Vercel.
2. Set **Root Directory** to `apps/web`.
3. Framework preset: **Vite** (`npm run build`, output `dist`).
4. Deploy — all download links and checksums are managed from `apps/web/src/config/downloads.config.ts` and dynamically hydrated from the latest GitHub Release.

---

## 7. End-User Install Guides

### Windows (`.exe`)
1. Download `InstitutionalEA-Setup.exe`.
2. Double-click to run the per-user NSIS installer (no admin elevation required).
3. **Unsigned build prompt (SmartScreen):** If Windows Defender SmartScreen displays *"Windows protected your PC"*, click **More info** → **Run anyway**.
4. Verify SHA-256 (optional): `certutil -hashfile InstitutionalEA-Setup.exe SHA256`.

### macOS (`.dmg`)
1. Download `InstitutionalEA.dmg` (Universal: Apple Silicon & Intel).
2. Open the `.dmg` and drag **Institutional EA** into **Applications**.
3. **Unsigned build prompt (Gatekeeper):** Do not double-click on first launch. Instead, **Right-click (or Control-click) → Open → Open**. Subsequent launches open normally.
4. Verify SHA-256 (optional): `shasum -a 256 InstitutionalEA.dmg`.

### Android (`.apk`)
1. Download `InstitutionalEA.apk` on your Android 7.0+ (API 24+) device.
2. Tap the downloaded file. If prompted, enable **Allow from this source** (*Install unknown apps*) for your browser.
3. Tap **Install** and open **Institutional EA** (strictly read-only).

### iOS (TestFlight / Expo Go)
1. Install Apple **TestFlight** from the App Store.
2. Open the Institutional EA TestFlight public link from the download page and tap **Accept → Install**.
