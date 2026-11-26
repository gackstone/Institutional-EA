/**
 * Hardware-backed Secure Storage Wrapper.
 * Uses Android Keystore (EncryptedSharedPreferences) / iOS Keychain via expo-secure-store
 * in production, with an injectable in-memory fallback for Node unit tests.
 *
 * Security Rule 4: Pairing tokens are NEVER stored in plain AsyncStorage.
 */

export interface ISecureStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
}

export interface PairingCredentials {
  mode?: "cloud" | "lan";
  cloudUrl?: string;
  host: string;
  hosts: string[];
  port: number;
  deviceId: string;
  deviceToken: string;
  companionName: string;
  pairedAt: string;
}

class MemorySecureStorage implements ISecureStorage {
  private store: Map<string, string> = new Map();

  async getItem(key: string): Promise<string | null> {
    return this.store.get(key) ?? null;
  }

  async setItem(key: string, value: string): Promise<void> {
    if (typeof value !== "string") {
      throw new Error("SecureStorage: value must be a string");
    }
    this.store.set(key, value);
  }

  async removeItem(key: string): Promise<void> {
    this.store.delete(key);
  }

  clear(): void {
    this.store.clear();
  }
}

let storageInstance: ISecureStorage | null = null;

async function resolveStorage(): Promise<ISecureStorage> {
  if (storageInstance) return storageInstance;
  try {
    // Dynamically load expo-secure-store when running in React Native / Expo
    const mod = await import("expo-secure-store");
    if (mod && typeof mod.getItemAsync === "function") {
      storageInstance = {
        getItem: (key) => mod.getItemAsync(key),
        setItem: (key, value) => mod.setItemAsync(key, value),
        removeItem: (key) => mod.deleteItemAsync(key),
      };
      return storageInstance;
    }
  } catch {
    // Running in Node test environment without native Expo modules
  }
  storageInstance = new MemorySecureStorage();
  return storageInstance;
}

export function setCustomSecureStorage(custom: ISecureStorage): void {
  storageInstance = custom;
}

const KEYS = {
  DEVICE_TOKEN: "iea_device_token",
  PAIRING_CREDS: "iea_pairing_creds_v1",
  THEME: "iea_theme",
  BIOMETRIC_LOCK: "iea_biometric_lock",
  LOGGED_OUT: "iea_session_logged_out",
} as const;

export const SecureStorage = {
  async getDeviceToken(): Promise<string | null> {
    const s = await resolveStorage();
    return s.getItem(KEYS.DEVICE_TOKEN);
  },

  async setDeviceToken(token: string): Promise<void> {
    const s = await resolveStorage();
    await s.setItem(KEYS.DEVICE_TOKEN, token);
  },

  async clearDeviceToken(): Promise<void> {
    const s = await resolveStorage();
    await s.removeItem(KEYS.DEVICE_TOKEN);
  },

  async getPairingCredentials(): Promise<PairingCredentials | null> {
    const s = await resolveStorage();
    const raw = await s.getItem(KEYS.PAIRING_CREDS);
    if (!raw) return null;
    try {
      const parsed = JSON.parse(raw) as PairingCredentials;
      const isCloud = parsed.mode === "cloud" && Boolean(parsed.cloudUrl);
      const isLan = Boolean(parsed.host && parsed.port);
      if ((!isCloud && !isLan) || !parsed.deviceToken || !parsed.deviceId) {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  },

  async setPairingCredentials(creds: PairingCredentials): Promise<void> {
    const s = await resolveStorage();
    await s.setItem(KEYS.PAIRING_CREDS, JSON.stringify(creds));
    await s.setItem(KEYS.DEVICE_TOKEN, creds.deviceToken);
  },

  async clearPairingCredentials(): Promise<void> {
    const s = await resolveStorage();
    await s.removeItem(KEYS.PAIRING_CREDS);
    await s.removeItem(KEYS.DEVICE_TOKEN);
  },

  async getStoredTheme(): Promise<string | null> {
    const s = await resolveStorage();
    return s.getItem(KEYS.THEME);
  },

  async setStoredTheme(theme: "dark" | "light"): Promise<void> {
    const s = await resolveStorage();
    await s.setItem(KEYS.THEME, theme);
  },

  async getBiometricLockEnabled(): Promise<boolean> {
    const s = await resolveStorage();
    const raw = await s.getItem(KEYS.BIOMETRIC_LOCK);
    return raw === "true";
  },

  async setBiometricLockEnabled(enabled: boolean): Promise<void> {
    const s = await resolveStorage();
    await s.setItem(KEYS.BIOMETRIC_LOCK, enabled ? "true" : "false");
  },
};
