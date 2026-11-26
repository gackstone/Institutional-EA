import test from "node:test";
import assert from "node:assert/strict";
import {
  DARK_THEME,
  LIGHT_THEME,
  getThemeTokens,
} from "../theme/themeTokens.ts";
import {
  SecureStorage,
  setCustomSecureStorage,
} from "../services/SecureStorage.ts";
import {
  assertMobileReadOnlyAction,
  FORBIDDEN_CLIENT_ACTIONS,
  ReadOnlyViolationError,
} from "../services/ReadOnlyGuard.ts";

test("mobile theme tokens synchronize with brand palette and switch modes", () => {
  assert.equal(DARK_THEME.background, "#0B0F19");
  assert.equal(DARK_THEME.accent, "#6FF2C4");
  assert.equal(LIGHT_THEME.background, "#F4F7FA");
  assert.equal(DARK_THEME.bullCandle, "#0A997D");
  assert.equal(LIGHT_THEME.bearCandle, "#EE3749");

  const darkTokens = getThemeTokens("dark");
  const lightTokens = getThemeTokens("light");
  assert.equal(darkTokens.surface, "#111827");
  assert.equal(lightTokens.surface, "#FFFFFF");
});

test("SecureStorage stores, retrieves, and clears device token securely", async () => {
  // Test with fresh memory backend
  const testMap = new Map<string, string>();
  setCustomSecureStorage({
    async getItem(key: string) {
      return testMap.get(key) ?? null;
    },
    async setItem(key: string, value: string) {
      testMap.set(key, value);
    },
    async removeItem(key: string) {
      testMap.delete(key);
    },
  });

  assert.equal(await SecureStorage.getDeviceToken(), null);

  await SecureStorage.setDeviceToken("jwt-read-token-xyz");
  assert.equal(await SecureStorage.getDeviceToken(), "jwt-read-token-xyz");

  await SecureStorage.clearDeviceToken();
  assert.equal(await SecureStorage.getDeviceToken(), null);
});

test("SecureStorage remembers user theme selection", async () => {
  await SecureStorage.setStoredTheme("light");
  assert.equal(await SecureStorage.getStoredTheme(), "light");

  await SecureStorage.setStoredTheme("dark");
  assert.equal(await SecureStorage.getStoredTheme(), "dark");
});

test("ReadOnlyGuard strictly blocks any order execution or bot modification", () => {
  for (const action of FORBIDDEN_CLIENT_ACTIONS) {
    assert.throws(
      () => assertMobileReadOnlyAction(action),
      (err: unknown) => {
        return (
          err instanceof ReadOnlyViolationError &&
          err.message.includes("Strict Read-Only Violation")
        );
      }
    );
  }

  // Safe read-only actions do not throw
  assert.doesNotThrow(() => assertMobileReadOnlyAction("FETCH_POSITIONS"));
  assert.doesNotThrow(() => assertMobileReadOnlyAction("SUBSCRIBE_TELEMETRY"));
});
