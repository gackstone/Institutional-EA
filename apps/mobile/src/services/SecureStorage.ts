/**
 * Hardware-backed Secure Storage Wrapper.
 * Uses iOS Keychain / Android Keystore in production, with in-memory fallback for test harnesses.
 */

export interface ISecureStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem(key: string): Promise<void>;
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

// Global instance (configured with native SecureStore when running in Expo, or memory mock in tests)
let storageInstance: ISecureStorage = new MemorySecureStorage();

export function setCustomSecureStorage(custom: ISecureStorage): void {
  storageInstance = custom;
}

export const SecureStorage = {
  async getDeviceToken(): Promise<string | null> {
    return storageInstance.getItem("institutional_ea_device_token");
  },

  async setDeviceToken(token: string): Promise<void> {
    await storageInstance.setItem("institutional_ea_device_token", token);
  },

  async clearDeviceToken(): Promise<void> {
    await storageInstance.removeItem("institutional_ea_device_token");
  },

  async getStoredTheme(): Promise<string | null> {
    return storageInstance.getItem("institutional_ea_theme");
  },

  async setStoredTheme(theme: "dark" | "light"): Promise<void> {
    await storageInstance.setItem("institutional_ea_theme", theme);
  },
};
