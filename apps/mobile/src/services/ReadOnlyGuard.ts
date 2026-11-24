/**
 * Mobile Read-Only Runtime Guard.
 *
 * Guarantees that the mobile application cannot invoke order execution,
 * parameter mutation, or risk overrides.
 */

export const FORBIDDEN_CLIENT_ACTIONS = [
  "EXECUTE_BUY",
  "EXECUTE_SELL",
  "CLOSE_POSITION",
  "CLOSE_ALL",
  "MODIFY_STOP_LOSS",
  "MODIFY_TAKE_PROFIT",
  "START_BOT",
  "STOP_BOT",
  "PAUSE_BOT",
  "CHANGE_RISK_SETTINGS",
  "UPDATE_BROKER_LOGIN",
] as const;

export type ForbiddenClientAction = (typeof FORBIDDEN_CLIENT_ACTIONS)[number];

export class ReadOnlyViolationError extends Error {
  constructor(action: string) {
    super(
      `Strict Read-Only Violation: Action '${action}' is not permitted in the mobile monitoring companion.`
    );
    this.name = "ReadOnlyViolationError";
  }
}

export function assertMobileReadOnlyAction(actionName: string): void {
  if (FORBIDDEN_CLIENT_ACTIONS.includes(actionName as ForbiddenClientAction)) {
    throw new ReadOnlyViolationError(actionName);
  }
}
