import React from "react";

export type Status =
  | "CONNECTED"
  | "DISCONNECTED"
  | "CONNECTING"
  | "RUNNING"
  | "PAUSED"
  | "STOPPED"
  | "ERROR"
  | "READY"
  | "STANDBY"
  | string;

export interface StatusBadgeProps {
  status: Status;
  className?: string;
  showDot?: boolean;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  className = "",
  showDot = true,
}) => {
  const key = (status || "").toUpperCase();

  // Unified Institutional EA status semantics
  let badgeClasses = "bg-institutional-ea-secondary text-institutional-ea-textMuted border-institutional-ea-border";
  let dotClass = "bg-institutional-ea-textMuted";
  let pulse = false;

  switch (key) {
    case "CONNECTED":
    case "ARMED":
    case "ONLINE":
      badgeClasses = "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25";
      dotClass = "bg-emerald-500";
      break;

    case "RUNNING":
      badgeClasses = "bg-institutional-ea-primary/10 text-institutional-ea-primary border-institutional-ea-primary/30";
      dotClass = "bg-institutional-ea-primary";
      pulse = true;
      break;

    case "PAUSED":
    case "STANDBY":
      badgeClasses = "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25";
      dotClass = "bg-amber-500";
      break;

    case "CONNECTING":
    case "STARTING":
      badgeClasses = "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/25";
      dotClass = "bg-sky-500";
      pulse = true;
      break;

    case "STOPPED":
    case "OFFLINE":
      badgeClasses = "bg-institutional-ea-secondary text-institutional-ea-textSecondary border-institutional-ea-border";
      dotClass = "bg-institutional-ea-textMuted";
      break;

    case "DISCONNECTED":
    case "ERROR":
    case "CRITICAL":
      badgeClasses = "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25";
      dotClass = "bg-rose-500";
      break;

    default:
      badgeClasses = "bg-institutional-ea-secondary text-institutional-ea-textSecondary border-institutional-ea-border";
      dotClass = "bg-institutional-ea-textMuted";
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold uppercase tracking-wider border transition-colors select-none ${badgeClasses} ${className}`}
    >
      {showDot && (
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotClass}`}
        />
      )}
      <span>{status}</span>
    </span>
  );
};
