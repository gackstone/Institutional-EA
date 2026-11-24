/**
 * Strict Read-Only Security Guardrails.
 *
 * Enforces that no mobile client can ever invoke trading actions, mutate parameters,
 * or obtain non-read-only tokens.
 */

export const READONLY_SCOPES = ["telemetry:read"] as const;
export type ReadOnlyScope = (typeof READONLY_SCOPES)[number];

export const FORBIDDEN_OPERATIONS = [
  "start_bot",
  "stop_bot",
  "pause_bot",
  "resume_bot",
  "place_order",
  "modify_order",
  "close_order",
  "close_all_positions",
  "update_risk",
  "change_account",
  "update_settings",
] as const;

export type ForbiddenOperation = (typeof FORBIDDEN_OPERATIONS)[number];

/**
 * Validates that an array of scopes is strictly read-only.
 * Returns true if valid; throws error if any unauthorized scope is present.
 */
export function assertReadOnlyScope(scopes: string[]): boolean {
  if (!Array.isArray(scopes) || scopes.length === 0) {
    throw new Error("Security Error: Scopes array cannot be empty");
  }
  for (const s of scopes) {
    if (!READONLY_SCOPES.includes(s as ReadOnlyScope)) {
      throw new Error(`Security Violation: Scope '${s}' exceeds read-only permissions`);
    }
  }
  return true;
}

/**
 * Throws a SecurityError if an operation is forbidden.
 */
export function assertOperationPermitted(operation: string): void {
  if (FORBIDDEN_OPERATIONS.includes(operation as ForbiddenOperation)) {
    throw new Error(
      `Strict Read-Only Enforcement: Operation '${operation}' is strictly prohibited on the mobile client.`
    );
  }
}
