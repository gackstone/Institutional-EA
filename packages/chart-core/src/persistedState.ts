export const PERSISTED_SCHEMA_VERSION = 2;

export interface VersionedEnvelope<T> {
  schemaVersion: number;
  updatedAt: string;
  data: T;
}

export interface StorageLike {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

export interface ReadPersistedResult<T> {
  value: T;
  migrated: boolean;
  reset: boolean;
  reason?: string;
}

function getDefaultStorage(): StorageLike | null {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      return window.localStorage;
    }
  } catch {
    // storage unavailable
  }
  return null;
}

/**
 * Reads a versioned persisted item from localStorage inside try/catch.
 * - If valid current schema: returns `data`.
 * - If older schema or legacy unversioned value: calls `migrate(raw)` and re-saves.
 * - If corrupt JSON or fails validation: resets ONLY this key to `defaultValue` and logs.
 * Never throws, so corrupt stored state can never block app startup.
 */
export function readVersionedState<T>(opts: {
  key: string;
  defaultValue: T;
  validate: (v: unknown) => v is T;
  migrate?: (legacyRaw: unknown, fromVersion: number) => T | null;
  storage?: StorageLike | null;
  logger?: (msg: string) => void;
}): ReadPersistedResult<T> {
  const storage = opts.storage === undefined ? getDefaultStorage() : opts.storage;
  const log = opts.logger || ((m) => console.warn(`[PersistedState] ${m}`));

  if (!storage) {
    return { value: opts.defaultValue, migrated: false, reset: false };
  }

  let rawStr: string | null = null;
  try {
    rawStr = storage.getItem(opts.key);
  } catch (err: any) {
    log(`Failed reading key "${opts.key}": ${err?.message || err}`);
    return { value: opts.defaultValue, migrated: false, reset: true, reason: "storage_read_error" };
  }

  if (rawStr === null || rawStr === "") {
    return { value: opts.defaultValue, migrated: false, reset: false };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawStr);
  } catch {
    // Allow plain string legacy values (e.g. "dark" for theme) to be migrated
    parsed = rawStr;
  }

  // Case 1: Current versioned envelope
  if (
    parsed &&
    typeof parsed === "object" &&
    (parsed as any).schemaVersion === PERSISTED_SCHEMA_VERSION &&
    "data" in (parsed as any)
  ) {
    const candidate = (parsed as VersionedEnvelope<unknown>).data;
    if (opts.validate(candidate)) {
      return { value: candidate, migrated: false, reset: false };
    }
    log(`Invalid data shape for key "${opts.key}" (v${PERSISTED_SCHEMA_VERSION}); resetting to defaults.`);
    writeVersionedState(opts.key, opts.defaultValue, storage);
    return { value: opts.defaultValue, migrated: false, reset: true, reason: "invalid_schema_data" };
  }

  // Case 2: Older schema version or legacy unversioned payload -> attempt migration
  const fromVersion =
    parsed && typeof parsed === "object" && typeof (parsed as any).schemaVersion === "number"
      ? (parsed as any).schemaVersion
      : 0;
  const legacyPayload =
    fromVersion > 0 && parsed && typeof parsed === "object" && "data" in (parsed as any)
      ? (parsed as any).data
      : parsed;

  if (opts.migrate) {
    try {
      const migrated = opts.migrate(legacyPayload, fromVersion);
      if (migrated !== null && opts.validate(migrated)) {
        log(`Migrated key "${opts.key}" from v${fromVersion} to v${PERSISTED_SCHEMA_VERSION}.`);
        writeVersionedState(opts.key, migrated, storage);
        return { value: migrated, migrated: true, reset: false };
      }
    } catch (err: any) {
      log(`Migration failed for key "${opts.key}": ${err?.message || err}`);
    }
  }

  // Case 3: Unrecoverable corruption -> reset ONLY this key to safe defaults
  log(`Corrupt or unrecognized persisted value for "${opts.key}"; resetting to safe defaults.`);
  writeVersionedState(opts.key, opts.defaultValue, storage);
  return { value: opts.defaultValue, migrated: false, reset: true, reason: "corrupt_or_unmigrated" };
}

export function writeVersionedState<T>(
  key: string,
  data: T,
  storageOverride?: StorageLike | null
): boolean {
  const storage = storageOverride === undefined ? getDefaultStorage() : storageOverride;
  if (!storage) return false;
  try {
    const envelope: VersionedEnvelope<T> = {
      schemaVersion: PERSISTED_SCHEMA_VERSION,
      updatedAt: new Date().toISOString(),
      data,
    };
    storage.setItem(key, JSON.stringify(envelope));
    return true;
  } catch {
    return false;
  }
}

export function resetAllUiPersistedState(storageOverride?: StorageLike | null): string[] {
  const storage = storageOverride === undefined ? getDefaultStorage() : storageOverride;
  const keys = ["iea_chart_overlay_toggles_v1", "institutional_ea_theme"];
  if (!storage) return [];
  const cleared: string[] = [];
  for (const k of keys) {
    try {
      storage.removeItem(k);
      cleared.push(k);
    } catch {
      // ignore
    }
  }
  return cleared;
}
