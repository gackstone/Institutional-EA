import React from "react";
import { AlertTriangle, RefreshCw, RotateCcw, FolderOpen } from "lucide-react";
import { resetAllUiPersistedState } from "../utils/persistedState";

function sanitizeErrorMessage(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err || "Unexpected rendering error");
  // Redact any token-like strings
  const cleaned = msg.replace(/[A-Za-z0-9_\-]{28,}/g, "[REDACTED]").trim();
  return cleaned.length > 160 ? `${cleaned.slice(0, 157)}...` : cleaned;
}

interface PanelBoundaryProps {
  panelName: string;
  children: React.ReactNode;
}

interface PanelBoundaryState {
  hasError: boolean;
  errorMessage: string;
  retryKey: number;
}

export class PanelErrorBoundary extends React.Component<PanelBoundaryProps, PanelBoundaryState> {
  constructor(props: PanelBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorMessage: "", retryKey: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<PanelBoundaryState> {
    return { hasError: true, errorMessage: sanitizeErrorMessage(error) };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    const summary = sanitizeErrorMessage(error);
    console.error(`[PanelErrorBoundary:${this.props.panelName}]`, summary, info.componentStack);
    try {
      (window as any).electronAPI?.reportRendererError?.({
        source: `PanelErrorBoundary:${this.props.panelName}`,
        message: summary,
      });
    } catch {
      // ignore
    }
  }

  private handleRetry = () => {
    this.setState((prev) => ({
      hasError: false,
      errorMessage: "",
      retryKey: prev.retryKey + 1,
    }));
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          data-testid={`panel-error-${this.props.panelName.toLowerCase().replace(/\s+/g, "-")}`}
          className="iea-card border-iea-dangerBorder p-4 flex flex-wrap items-center justify-between gap-3 text-xs"
        >
          <div className="flex items-center space-x-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-iea-danger shrink-0" />
            <div className="min-w-0">
              <div className="font-semibold text-iea-textPrimary">
                {this.props.panelName} encountered an error
              </div>
              <div className="text-iea-textSecondary font-mono text-[11px] truncate">
                {this.state.errorMessage || "Unable to render this panel."}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={this.handleRetry}
            className="iea-btn-primary px-3.5 py-1.5 inline-flex items-center space-x-1.5 shrink-0"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Retry</span>
          </button>
        </div>
      );
    }

    return <React.Fragment key={this.state.retryKey}>{this.props.children}</React.Fragment>;
  }
}

interface AppBoundaryProps {
  children: React.ReactNode;
}

interface AppBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

export class AppErrorBoundary extends React.Component<AppBoundaryProps, AppBoundaryState> {
  constructor(props: AppBoundaryProps) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(error: Error): AppBoundaryState {
    return { hasError: true, errorMessage: sanitizeErrorMessage(error) };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    const summary = sanitizeErrorMessage(error);
    console.error("[AppErrorBoundary]", summary, info.componentStack);
    try {
      (window as any).electronAPI?.reportRendererError?.({
        source: "AppErrorBoundary",
        message: summary,
      });
    } catch {
      // ignore
    }
  }

  private handleReload = () => {
    if ((window as any).electronAPI?.fallbackReload) {
      (window as any).electronAPI.fallbackReload();
    } else {
      window.location.reload();
    }
  };

  private handleResetSettings = async () => {
    resetAllUiPersistedState();
    if ((window as any).electronAPI?.fallbackResetSettings) {
      await (window as any).electronAPI.fallbackResetSettings();
    } else {
      window.location.reload();
    }
  };

  private handleOpenLogs = () => {
    (window as any).electronAPI?.fallbackOpenLogs?.();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          data-testid="app-error-boundary"
          className="min-h-screen w-screen bg-iea-canvas text-iea-textPrimary flex items-center justify-center p-6 font-sans"
        >
          <div className="max-w-md w-full iea-card border-iea-dangerBorder p-7 space-y-4">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-iea-dangerSoft border border-iea-dangerBorder flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-iea-danger" />
              </div>
              <div>
                <h1 className="text-base font-semibold text-iea-textPrimary">
                  Institutional EA couldn&apos;t display this view
                </h1>
                <p className="text-xs text-iea-textMuted">
                  DEMO lock remains active. Open MT5 positions are unaffected.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-iea-inset border border-iea-borderSubtle text-[11px] font-mono text-iea-danger break-words">
              {this.state.errorMessage || "Unexpected UI rendering failure."}
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={this.handleReload}
                className="iea-btn-primary px-4 py-2 text-xs inline-flex items-center space-x-1.5"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reload</span>
              </button>
              <button
                type="button"
                onClick={this.handleResetSettings}
                className="iea-btn-neutral px-3.5 py-2 text-xs inline-flex items-center space-x-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset settings</span>
              </button>
              <button
                type="button"
                onClick={this.handleOpenLogs}
                className="px-3.5 py-2 rounded-full bg-transparent hover:bg-iea-elevated border border-iea-borderDefault text-iea-textSecondary hover:text-iea-textPrimary text-xs font-medium inline-flex items-center space-x-1.5 transition"
              >
                <FolderOpen className="w-3.5 h-3.5" />
                <span>Open logs</span>
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
