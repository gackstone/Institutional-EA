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
          className="iea-glass-card border-[#FF5A6E]/45 p-4 flex flex-wrap items-center justify-between gap-3 text-xs"
        >
          <div className="flex items-center space-x-2.5 min-w-0">
            <AlertTriangle className="w-4 h-4 text-[#FF5A6E] shrink-0" />
            <div className="min-w-0">
              <div className="font-semibold text-[#F4F7FF]">
                {this.props.panelName} encountered an error
              </div>
              <div className="text-[#B6C5E0] font-mono text-[11px] truncate">
                {this.state.errorMessage || "Unable to render this panel."}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={this.handleRetry}
            className="px-3 py-1.5 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] font-bold inline-flex items-center space-x-1.5 shrink-0 transition"
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
          className="min-h-screen w-screen bg-[#091426] text-[#F4F7FF] flex items-center justify-center p-6 font-sans"
        >
          <div className="max-w-md w-full rounded-2xl bg-[#0D1B36] border border-[#FF5A6E]/50 p-6 shadow-2xl space-y-4">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-[#FF5A6E]/20 border border-[#FF5A6E]/45 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-[#FF5A6E]" />
              </div>
              <div>
                <h1 className="text-base font-bold text-[#F4F7FF]">
                  Institutional EA couldn&apos;t display this view
                </h1>
                <p className="text-xs text-[#8496B8]">
                  DEMO lock remains active. Open MT5 positions are unaffected.
                </p>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-[#071020] border border-white/10 text-[11px] font-mono text-[#FFD9DF] break-words">
              {this.state.errorMessage || "Unexpected UI rendering failure."}
            </div>

            <div className="flex flex-wrap items-center gap-2 pt-1">
              <button
                type="button"
                onClick={this.handleReload}
                className="px-4 py-2 rounded-full bg-[#B0F648] hover:bg-[#C2F076] text-[#081321] text-xs font-extrabold inline-flex items-center space-x-1.5 transition"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                <span>Reload</span>
              </button>
              <button
                type="button"
                onClick={this.handleResetSettings}
                className="px-3.5 py-2 rounded-full bg-[#192E58] hover:bg-[#243F73] border border-white/15 text-[#F4F7FF] text-xs font-semibold inline-flex items-center space-x-1.5 transition"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset settings</span>
              </button>
              <button
                type="button"
                onClick={this.handleOpenLogs}
                className="px-3.5 py-2 rounded-full bg-transparent hover:bg-white/10 border border-white/15 text-[#B6C5E0] text-xs font-semibold inline-flex items-center space-x-1.5 transition"
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
