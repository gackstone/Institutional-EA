import React, { useState, useRef, useEffect } from "react";
import {
  Terminal,
  Search,
  Trash2,
  Download,
  ArrowDownCircle,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Maximize2,
  Minimize2,
  SlidersHorizontal
} from "lucide-react";
import { LogMessage } from "../types";

interface LiveConsoleProps {
  logs: LogMessage[];
  onClearLogs: () => void;
}

export const LiveConsole: React.FC<LiveConsoleProps> = ({ logs, onClearLogs }) => {
  const [filterService, setFilterService] = useState<string>("ALL");
  const [filterLevel, setFilterLevel] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [autoScroll, setAutoScroll] = useState<boolean>(true);
  const [copied, setCopied] = useState<boolean>(false);
  const [isCollapsed, setIsCollapsed] = useState<boolean>(false);
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (autoScroll && scrollRef.current && !isCollapsed) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll, isCollapsed]);

  const filteredLogs = logs.filter((log) => {
    if (filterService !== "ALL" && log.service.toUpperCase() !== filterService) {
      return false;
    }
    if (filterLevel !== "ALL" && log.level.toUpperCase() !== filterLevel) {
      return false;
    }
    if (searchQuery.trim() !== "") {
      const q = searchQuery.toLowerCase();
      return (
        log.message.toLowerCase().includes(q) ||
        log.service.toLowerCase().includes(q) ||
        log.level.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const getLevelBadge = (level: string) => {
    const l = (level || "").toUpperCase();
    switch (l) {
      case "CRITICAL":
        return "bg-rose-600 text-white font-extrabold border-rose-700";
      case "ERROR":
        return "bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/25";
      case "WARNING":
      case "WARN":
        return "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25";
      case "SUCCESS":
        return "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25";
      case "INFO":
      default:
        return "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/25";
    }
  };

  const copyToClipboard = () => {
    const text = filteredLogs
      .map((l) => `[${l.timestamp}] [${l.level}] [${l.service}] ${l.message}`)
      .join("\n");
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const exportToFile = () => {
    const text = filteredLogs
      .map((l) => `[${l.timestamp}] [${l.level}] [${l.service}] ${l.message}`)
      .join("\n");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `mt5-companion-logs-${new Date().toISOString().slice(0, 10)}.log`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const latestLog = logs.length > 0 ? logs[logs.length - 1] : null;

  // Height determination
  const containerHeightClass = isCollapsed
    ? "h-11"
    : isExpanded
    ? "h-[480px]"
    : "h-[300px]";

  return (
    <div
      id="live-console"
      className={`p-3 sm:px-4 sm:py-3 bg-arcade-bg border-t border-arcade-border flex flex-col ${containerHeightClass} transition-all duration-200 ease-in-out`}
    >
      {/* Console Header & Control Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-2 select-none mb-2">
        {/* Left: Title & Event Count */}
        <div className="flex items-center gap-2 min-w-0">
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-arcade-text hover:text-arcade-primary transition cursor-pointer"
            title={isCollapsed ? "Expand Console" : "Collapse Console"}
          >
            <div className="w-6 h-6 rounded-md bg-arcade-primary/10 border border-arcade-primary/20 flex items-center justify-center text-arcade-primary shrink-0">
              <Terminal className="w-3.5 h-3.5" />
            </div>
            <span className="font-sans font-bold">Live Activity Console</span>
          </button>

          <span className="text-[10px] text-arcade-textMuted font-mono px-2 py-0.5 rounded-full bg-arcade-card border border-arcade-border shrink-0">
            {filteredLogs.length} events
          </span>

          {/* Collapsed preview text */}
          {isCollapsed && latestLog && (
            <div className="hidden md:flex items-center gap-2 text-xs font-mono text-arcade-textSecondary truncate max-w-xl pl-2">
              <span className="text-arcade-textMuted text-[10px]">
                {latestLog.timestamp.slice(11, 19)}
              </span>
              <span className="text-arcade-primary font-bold text-[11px]">
                [{latestLog.service}]
              </span>
              <span className="truncate text-[11px] text-arcade-text">
                {latestLog.message}
              </span>
            </div>
          )}
        </div>

        {/* Right Toolbar Controls */}
        <div className="flex items-center gap-1.5 flex-wrap text-xs">
          {!isCollapsed && (
            <>
              {/* Search Filter */}
              <div className="relative">
                <Search className="w-3.5 h-3.5 text-arcade-textMuted absolute left-2.5 top-2" />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Filter logs..."
                  className="pl-7 pr-2.5 py-1 bg-arcade-card border border-arcade-border rounded-lg text-arcade-text text-xs w-32 focus:w-44 focus:border-arcade-primary transition-all outline-none font-sans"
                />
              </div>

              {/* Service Filter */}
              <select
                value={filterService}
                onChange={(e) => setFilterService(e.target.value)}
                className="bg-arcade-card border border-arcade-border rounded-lg px-2 py-1 text-arcade-text text-xs outline-none font-sans cursor-pointer"
                title="Filter by background service"
              >
                <option value="ALL">All Services</option>
                <option value="ENGINE">Trading Engine</option>
                <option value="BRIDGE">Bridge Server</option>
                <option value="ARCADEFX">ArcadeFX Cloud</option>
                <option value="TELEGRAM">Telegram</option>
                <option value="SYSTEM">System</option>
              </select>

              {/* Severity Level Filter */}
              <select
                value={filterLevel}
                onChange={(e) => setFilterLevel(e.target.value)}
                className="bg-arcade-card border border-arcade-border rounded-lg px-2 py-1 text-arcade-text text-xs outline-none font-sans cursor-pointer"
                title="Filter by severity level"
              >
                <option value="ALL">All Levels</option>
                <option value="INFO">INFO</option>
                <option value="SUCCESS">SUCCESS</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>

              {/* Auto-scroll Toggle */}
              <button
                type="button"
                onClick={() => setAutoScroll(!autoScroll)}
                className={`p-1.5 rounded-lg border text-xs flex items-center justify-center transition cursor-pointer ${
                  autoScroll
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30"
                    : "bg-arcade-card text-arcade-textMuted border-arcade-border hover:text-arcade-text"
                }`}
                title={autoScroll ? "Auto-scroll ON (click to pause)" : "Auto-scroll OFF (click to follow)"}
                aria-label="Auto-scroll"
              >
                <ArrowDownCircle className="w-3.5 h-3.5" />
              </button>

              {/* Copy to Clipboard */}
              <button
                type="button"
                onClick={copyToClipboard}
                className="p-1.5 rounded-lg bg-arcade-card hover:bg-arcade-secondary text-arcade-textSecondary hover:text-arcade-text border border-arcade-border transition cursor-pointer shadow-xs"
                title="Copy filtered logs to clipboard"
                aria-label="Copy logs"
              >
                {copied ? (
                  <Check className="w-3.5 h-3.5 text-emerald-500" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
              </button>

              {/* Export to File */}
              <button
                type="button"
                onClick={exportToFile}
                className="p-1.5 rounded-lg bg-arcade-card hover:bg-arcade-secondary text-arcade-textSecondary hover:text-arcade-text border border-arcade-border transition cursor-pointer shadow-xs"
                title="Export logs to .log file"
                aria-label="Export logs"
              >
                <Download className="w-3.5 h-3.5" />
              </button>

              {/* Clear Console */}
              <button
                type="button"
                onClick={onClearLogs}
                className="p-1.5 rounded-lg bg-arcade-card hover:bg-rose-500/10 text-arcade-textSecondary hover:text-rose-600 border border-arcade-border transition cursor-pointer shadow-xs"
                title="Clear console events"
                aria-label="Clear logs"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>

              {/* Maximize / Normal Height Toggle */}
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="p-1.5 rounded-lg bg-arcade-card hover:bg-arcade-secondary text-arcade-textSecondary hover:text-arcade-text border border-arcade-border transition cursor-pointer shadow-xs"
                title={isExpanded ? "Restore default height" : "Expand console height"}
                aria-label="Toggle Expand"
              >
                {isExpanded ? (
                  <Minimize2 className="w-3.5 h-3.5" />
                ) : (
                  <Maximize2 className="w-3.5 h-3.5" />
                )}
              </button>
            </>
          )}

          {/* Collapse / Restore Button */}
          <button
            type="button"
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="p-1.5 rounded-lg bg-arcade-card hover:bg-arcade-secondary text-arcade-textSecondary hover:text-arcade-text border border-arcade-border transition cursor-pointer shadow-xs"
            title={isCollapsed ? "Expand Activity Console" : "Collapse Activity Console"}
            aria-label="Toggle Collapse"
          >
            {isCollapsed ? (
              <ChevronUp className="w-3.5 h-3.5" />
            ) : (
              <ChevronDown className="w-3.5 h-3.5" />
            )}
          </button>
        </div>
      </div>

      {/* Terminal Output Window */}
      {!isCollapsed && (
        <div
          ref={scrollRef}
          className="flex-1 bg-arcade-card border border-arcade-border rounded-xl p-3 font-mono text-xs overflow-y-auto space-y-1 select-text shadow-inner"
        >
          {filteredLogs.length === 0 ? (
            <div className="text-center text-arcade-textMuted py-16 font-sans select-none space-y-1">
              <Terminal className="w-8 h-8 mx-auto text-arcade-textMuted/40" />
              <p className="text-xs font-medium">No activity log entries match the selected filter criteria.</p>
              <p className="text-[11px] text-arcade-textMuted">Events from MT5 bridge, trading engine, and ArcadeFX sync will stream here in real time.</p>
            </div>
          ) : (
            filteredLogs.map((log) => (
              <div
                key={log.id}
                className="flex items-start gap-2.5 leading-relaxed hover:bg-arcade-surface/60 px-2 py-0.5 rounded-md transition-colors"
              >
                {/* Timestamp */}
                <span className="text-arcade-textMuted shrink-0 select-none text-[11px]">
                  {log.timestamp.slice(11, 19)}
                </span>

                {/* Severity Badge */}
                <span
                  className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase border shrink-0 ${getLevelBadge(
                    log.level
                  )}`}
                >
                  {log.level}
                </span>

                {/* Service Label */}
                <span className="text-arcade-primary shrink-0 font-bold select-none text-[11px]">
                  [{log.service.toUpperCase()}]
                </span>

                {/* Message Body */}
                <span className="text-arcade-text break-all text-[11px] font-normal flex-1">
                  {log.message}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
