export type PlatformId = "windows" | "macos" | "android" | "ios";

export interface DownloadPlatformConfig {
  id: PlatformId;
  category: "desktop" | "mobile";
  name: string;
  shortLabel: string;
  ctaLabel: string;
  assetName: string;
  /** Stable GitHub Releases link or TestFlight public URL. Leave empty to display "Coming soon". */
  downloadUrl: string;
  systemRequirements: string;
  fallbackSize: string;
  architecture: string;
  installNote: string;
}

export const RELEASE_REPO = "gackstone/Institutional-EA";
export const LATEST_RELEASE_API_URL = `https://api.github.com/repos/${RELEASE_REPO}/releases/latest`;
export const LATEST_RELEASE_BASE_URL = `https://github.com/${RELEASE_REPO}/releases/latest/download`;
export const DEFAULT_APP_VERSION = "1.3.1";

/**
 * Edit links, TestFlight URL, or version defaults in this single file
 * without touching any UI component.
 */
export const DOWNLOAD_PLATFORMS: Record<PlatformId, DownloadPlatformConfig> = {
  windows: {
    id: "windows",
    category: "desktop",
    name: "Windows",
    shortLabel: "Windows (.exe)",
    ctaLabel: "Download for Windows",
    assetName: "InstitutionalEA-Setup.exe",
    downloadUrl: `${LATEST_RELEASE_BASE_URL}/InstitutionalEA-Setup.exe`,
    systemRequirements: "Windows 10 / 11 (64-bit)",
    fallbackSize: "~85 MB",
    architecture: "x64 NSIS Installer",
    installNote: "If SmartScreen appears on unsigned builds, click More info → Run anyway.",
  },
  macos: {
    id: "macos",
    category: "desktop",
    name: "macOS",
    shortLabel: "macOS (.dmg)",
    ctaLabel: "Download for macOS",
    assetName: "InstitutionalEA.dmg",
    downloadUrl: `${LATEST_RELEASE_BASE_URL}/InstitutionalEA.dmg`,
    systemRequirements: "macOS 11 Big Sur or later",
    fallbackSize: "~110 MB",
    architecture: "Universal (Apple Silicon + Intel)",
    installNote: "For unsigned builds, drag to Applications, then Right-click → Open.",
  },
  android: {
    id: "android",
    category: "mobile",
    name: "Android",
    shortLabel: "Android (.apk)",
    ctaLabel: "Download for Android",
    assetName: "InstitutionalEA.apk",
    downloadUrl: `${LATEST_RELEASE_BASE_URL}/InstitutionalEA.apk`,
    systemRequirements: "Android 7.0 (API 24) or later",
    fallbackSize: "~32 MB",
    architecture: "Universal APK (Read-Only)",
    installNote: "Allow \"Install unknown apps\" for your browser when prompted.",
  },
  ios: {
    id: "ios",
    category: "mobile",
    name: "iOS",
    shortLabel: "iOS (TestFlight)",
    ctaLabel: "Join iOS TestFlight",
    assetName: "TestFlight",
    /** Paste your Apple TestFlight public link here once enrolled (e.g. https://testflight.apple.com/join/XXXXXXXX). */
    downloadUrl: "",
    systemRequirements: "iOS 15.0 or later",
    fallbackSize: "TestFlight",
    architecture: "iPhone & iPad (Read-Only)",
    installNote: "Available via Apple TestFlight public link once published (or Expo Go for testers).",
  },
};

export const PLATFORM_ORDER: PlatformId[] = ["windows", "macos", "android", "ios"];

export const SECURITY_AND_DISCLAIMER = {
  readOnlyTitle: "Strictly Read-Only Mobile Architecture",
  readOnlyBody:
    "The Institutional EA mobile app is strictly read-only. It can never start, stop, or pause the bot, place, modify, or close orders, or change risk settings. No broker credentials, MT5 logins, or trading API keys are ever sent to or stored on your phone.",
  disclaimer:
    "Financial Disclaimer: Institutional EA is a trading automation and monitoring software tool provided for informational and operational purposes only. Trading foreign exchange, CFDs, metals, and indices carries a high level of risk and may not be suitable for all investors. Past performance is not indicative of future results. You are solely responsible for your trading decisions and risk management.",
};

export const SITE_LINKS = {
  github: `https://github.com/${RELEASE_REPO}`,
  releases: `https://github.com/${RELEASE_REPO}/releases`,
  issues: `https://github.com/${RELEASE_REPO}/issues`,
  contactEmail: "support@institutionalea.com",
};
