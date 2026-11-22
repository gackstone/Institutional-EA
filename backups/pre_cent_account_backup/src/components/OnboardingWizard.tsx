import React, { useState, useEffect } from "react";
import {
  Wand2,
  Link2,
  Send,
  Cpu,
  FileCode2,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  PlayCircle,
  HelpCircle,
  ShieldAlert
} from "lucide-react";
import { IPC } from "../services/ipc";
import { PairingStatus, TelegramStatus, MT5TerminalInfo, DiagnosticResult } from "../types";

interface OnboardingWizardProps {
  isOpen: boolean;
  onFinish: () => void;
}

export const OnboardingWizard: React.FC<OnboardingWizardProps> = ({ isOpen, onFinish }) => {
  const [currentStep, setCurrentStep] = useState<number>(1);
  const totalSteps = 7;

  // Step States
  const [arcadefxStatus, setArcadefxStatus] = useState<PairingStatus>({
    isPaired: false,
    instanceId: null,
    deviceTokenMasked: null,
    pairedAt: null,
    apiUrl: "https://arcadefx.live/api/v1"
  });
  const [arcadefxCode, setArcadefxCode] = useState<string>("");
  const [arcadefxError, setArcadefxError] = useState<string | null>(null);
  const [arcadefxLoading, setArcadefxLoading] = useState<boolean>(false);

  const [telegramStatus, setTelegramStatus] = useState<TelegramStatus>({
    isPaired: false,
    botTokenMasked: null,
    chatIdMasked: null,
    botUsername: null,
    enabled: false
  });
  const [telegramToken, setTelegramToken] = useState<string>("");
  const [telegramLoading, setTelegramLoading] = useState<boolean>(false);
  const [telegramError, setTelegramError] = useState<string | null>(null);

  const [terminals, setTerminals] = useState<MT5TerminalInfo[]>([]);
  const [selectedTerminal, setSelectedTerminal] = useState<MT5TerminalInfo | null>(null);
  const [eaDeploying, setEaDeploying] = useState<boolean>(false);
  const [eaSuccess, setEaSuccess] = useState<boolean>(false);
  const [eaError, setEaError] = useState<string | null>(null);

  const [diagnostics, setDiagnostics] = useState<DiagnosticResult[]>([]);
  const [diagLoading, setDiagLoading] = useState<boolean>(false);

  useEffect(() => {
    if (isOpen) {
      loadInitialData();
    }
  }, [isOpen]);

  const loadInitialData = async () => {
    try {
      const [pStatus, tStatus, tList] = await Promise.all([
        IPC.getPairingStatus(),
        IPC.getTelegramStatus(),
        IPC.scanMT5Terminals()
      ]);
      setArcadefxStatus(pStatus);
      setTelegramStatus(tStatus);
      setTerminals(tList);
      if (tList.length > 0) setSelectedTerminal(tList[0]);
    } catch (e) {
      console.error(e);
    }
  };

  const handleArcadePair = async () => {
    if (!arcadefxCode || arcadefxCode.length !== 6) {
      setArcadefxError("Pairing code must be exactly 6 characters.");
      return;
    }
    setArcadefxLoading(true);
    setArcadefxError(null);
    try {
      const res = await IPC.submitPairingCode(arcadefxCode);
      if (res.success) {
        const s = await IPC.getPairingStatus();
        setArcadefxStatus(s);
        setCurrentStep(3);
      } else {
        setArcadefxError(res.message);
      }
    } catch (e: any) {
      setArcadefxError(e.message || "Pairing failed.");
    } finally {
      setArcadefxLoading(false);
    }
  };

  const handleTelegramPair = async () => {
    setTelegramLoading(true);
    setTelegramError(null);
    try {
      const res = await IPC.startTelegramPairing(telegramToken);
      if (res.success) {
        const s = await IPC.getTelegramStatus();
        setTelegramStatus(s);
        setCurrentStep(4);
      } else {
        setTelegramError(res.message);
      }
    } catch (e: any) {
      setTelegramError(e.message || "Pairing failed.");
    } finally {
      setTelegramLoading(false);
    }
  };

  const handleDeployEA = async () => {
    if (!selectedTerminal || !selectedTerminal.expertsFolder) {
      setEaError("Selected MT5 terminal lacks valid MQL5 Experts folder.");
      return;
    }
    setEaDeploying(true);
    setEaError(null);
    try {
      const res = await IPC.deployEA(selectedTerminal.expertsFolder);
      if (res.success) {
        setEaSuccess(true);
      } else {
        setEaError(res.message);
      }
    } catch (e: any) {
      setEaError(e.message || "EA deployment failed.");
    } finally {
      setEaDeploying(false);
    }
  };

  const runDiag = async () => {
    setDiagLoading(true);
    try {
      const results = await IPC.runDiagnostics();
      setDiagnostics(results);
    } catch (e) {
      console.error(e);
    } finally {
      setDiagLoading(false);
    }
  };

  const handleFinishOnboarding = async () => {
    try {
      await IPC.completeOnboarding();
      onFinish();
    } catch (e) {
      console.error(e);
      onFinish();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay-bg)] backdrop-blur-sm p-4 select-none animate-fadeIn">
      <div className="relative w-full max-w-2xl bg-arcade-card border border-arcade-border rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh] text-arcade-text">
        {/* Progress Bar & Header */}
        <div className="bg-arcade-surface border-b border-arcade-border p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-[var(--arcade-primary-soft)] border border-arcade-primary/30 flex items-center justify-center">
                <Wand2 className="w-4 h-4 text-arcade-primary" />
              </div>
              <div>
                <h2 className="text-base font-bold text-arcade-text">ArcadeFX MT5-001 Setup Wizard</h2>
                <p className="text-xs text-arcade-textMuted">Guided onboarding and system alignment</p>
              </div>
            </div>
            <div className="text-xs font-mono font-semibold px-2.5 py-1 rounded-md bg-arcade-card border border-arcade-border text-arcade-primary">
              Step {currentStep} of {totalSteps}
            </div>
          </div>

          <div className="w-full bg-arcade-secondary h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-arcade-primary h-full transition-all duration-300"
              style={{ width: `${(currentStep / totalSteps) * 100}%` }}
            />
          </div>
        </div>

        {/* Step Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {/* STEP 1: Welcome & Overview */}
          {currentStep === 1 && (
            <div className="space-y-4 text-center py-4">
              <div className="w-14 h-14 rounded-2xl bg-arcade-surface border border-arcade-border p-2 mx-auto flex items-center justify-center shadow-sm">
                <img src="/arcadefx-logo.svg" alt="ArcadeFX" className="w-full h-full object-contain" />
              </div>
              <h3 className="text-xl font-extrabold text-arcade-text">Welcome to ArcadeFX MT5-001</h3>
              <p className="text-xs text-arcade-textSecondary max-w-md mx-auto leading-relaxed">
                This guided wizard establishes high-speed communication between your local MetaTrader 5 terminal,
                the Python quantitative engine, and your ArcadeFX.live cloud portal.
              </p>

              <div className="grid grid-cols-3 gap-3 pt-3 text-left">
                <div className="p-3 bg-arcade-surface border border-arcade-border rounded-xl">
                  <div className="font-bold text-xs text-arcade-text mb-1">1. Cloud Pairing</div>
                  <div className="text-[11px] text-arcade-textMuted">Secure 6-char link with arcadefx.live</div>
                </div>
                <div className="p-3 bg-arcade-surface border border-arcade-border rounded-xl">
                  <div className="font-bold text-xs text-arcade-text mb-1">2. Telegram Alerts</div>
                  <div className="text-[11px] text-arcade-textMuted">Real-time telemetry and execution commands</div>
                </div>
                <div className="p-3 bg-arcade-surface border border-arcade-border rounded-xl">
                  <div className="font-bold text-xs text-arcade-text mb-1">3. MQL5 Bridge</div>
                  <div className="text-[11px] text-arcade-textMuted">ZeroMQ/Socket EA installation into MT5</div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: ArcadeFX Cloud Pairing */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--arcade-primary-soft)] text-arcade-primary border border-arcade-primary/30">
                  <Link2 className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-arcade-text">Pair with ArcadeFX.live</h3>
                  <p className="text-xs text-arcade-textMuted">Synchronize your trading session with your web dashboard</p>
                </div>
              </div>

              {arcadefxStatus.isPaired ? (
                <div className="p-4 rounded-xl bg-[var(--arcade-profit-soft)] border border-arcade-profit/30 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-arcade-profit" />
                  <div className="text-xs text-arcade-profit font-semibold">
                    Device already paired with ArcadeFX Cloud!
                  </div>
                </div>
              ) : (
                <div className="space-y-3 pt-2">
                  <div className="p-3 bg-arcade-surface rounded-xl border border-arcade-border text-xs text-arcade-textSecondary space-y-1">
                    <div>1. Log in to <b className="text-arcade-text">arcadefx.live</b></div>
                    <div>2. Open <b>Settings &gt; Bot Management &gt; Pair Desktop</b></div>
                    <div>3. Generate and paste your 6-character code below:</div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-arcade-text mb-1">Pairing Code</label>
                    <input
                      type="text"
                      maxLength={6}
                      value={arcadefxCode}
                      onChange={(e) => setArcadefxCode(e.target.value.toUpperCase())}
                      placeholder="e.g. 7X9K2P"
                      className="w-full px-4 py-2.5 bg-arcade-surface border border-arcade-border rounded-xl text-center font-mono text-lg font-bold tracking-widest text-arcade-text uppercase focus:border-arcade-primary outline-none transition"
                    />
                  </div>

                  {arcadefxError && (
                    <div className="p-3 bg-[var(--arcade-loss-soft)] border border-arcade-loss/30 rounded-xl text-xs text-arcade-loss flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      <span>{arcadefxError}</span>
                    </div>
                  )}

                  <button
                    onClick={handleArcadePair}
                    disabled={arcadefxLoading || arcadefxCode.length !== 6}
                    className="w-full py-2.5 rounded-xl bg-arcade-primary hover:bg-arcade-primaryHover active:bg-arcade-primaryActive disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                  >
                    <RefreshCw className={`w-4 h-4 ${arcadefxLoading ? "animate-spin" : ""}`} />
                    {arcadefxLoading ? "Pairing..." : "Verify & Link Account"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* STEP 3: Telegram Remote Control */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--arcade-primary-soft)] text-arcade-primary border border-arcade-primary/30">
                  <Send className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-arcade-text">Telegram Remote Control & Alerts</h3>
                  <p className="text-xs text-arcade-textMuted">Receive immediate mobile notifications and send trade controls</p>
                </div>
              </div>

              {telegramStatus.isPaired ? (
                <div className="p-4 rounded-xl bg-[var(--arcade-profit-soft)] border border-arcade-profit/30 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-arcade-profit" />
                  <div className="text-xs text-arcade-profit font-semibold">
                    Telegram Bot connected: {telegramStatus.botUsername || "Configured"}
                  </div>
                </div>
              ) : (
                <div className="space-y-3 pt-2">
                  <div className="p-3 bg-arcade-surface rounded-xl border border-arcade-border text-xs text-arcade-textMuted space-y-1">
                    <div>1. Message <span className="text-arcade-primary font-mono">@BotFather</span> on Telegram and create a bot</div>
                    <div>2. Enter the bot token or skip if already configured in <code>.env</code></div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-arcade-text mb-1">Bot Token (Optional)</label>
                    <input
                      type="text"
                      value={telegramToken}
                      onChange={(e) => setTelegramToken(e.target.value)}
                      placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                      className="w-full px-3 py-2 bg-arcade-surface border border-arcade-border rounded-xl text-arcade-text font-mono text-xs focus:border-arcade-primary outline-none transition"
                    />
                  </div>

                  {telegramError && (
                    <div className="p-3 bg-[var(--arcade-loss-soft)] border border-arcade-loss/30 rounded-xl text-xs text-arcade-loss">
                      {telegramError}
                    </div>
                  )}

                  <button
                    onClick={handleTelegramPair}
                    disabled={telegramLoading}
                    className="w-full py-2.5 rounded-xl bg-arcade-primary hover:bg-arcade-primaryHover active:bg-arcade-primaryActive disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                  >
                    <RefreshCw className={`w-4 h-4 ${telegramLoading ? "animate-spin" : ""}`} />
                    {telegramLoading ? "Connecting..." : "Connect Telegram Bot"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* STEP 4: Terminal Selection & EA Install */}
          {currentStep === 4 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--arcade-primary-soft)] text-arcade-primary border border-arcade-primary/30">
                  <FileCode2 className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-arcade-text">MetaTrader 5 Integration</h3>
                  <p className="text-xs text-arcade-textMuted">Select terminal and deploy PythonBridgeEA.mq5</p>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-arcade-textSecondary">Detected MT5 Terminals:</div>
                {terminals.length === 0 ? (
                  <div className="p-3 bg-arcade-surface rounded-xl border border-arcade-border text-xs text-arcade-textMuted">
                    No MT5 instances found automatically.
                  </div>
                ) : (
                  terminals.map((t) => (
                    <div
                      key={t.id}
                      onClick={() => setSelectedTerminal(t)}
                      className={`p-3 rounded-xl border cursor-pointer transition text-xs ${
                        selectedTerminal?.id === t.id
                          ? "bg-[var(--arcade-primary-soft)] border-arcade-primary/50 text-arcade-text"
                          : "bg-arcade-surface border-arcade-border text-arcade-textSecondary hover:border-arcade-borderStrong"
                      }`}
                    >
                      <div className="font-bold flex items-center justify-between">
                        <span>{t.name}</span>
                        {t.eaInstalled && (
                          <span className="text-[10px] text-arcade-profit font-semibold">EA Installed</span>
                        )}
                      </div>
                      <div className="font-mono text-[10px] text-arcade-textMuted mt-0.5 truncate max-w-lg">
                        {t.executablePath}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {eaSuccess ? (
                <div className="p-3 bg-[var(--arcade-profit-soft)] border border-arcade-profit/30 rounded-xl text-xs text-arcade-profit flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>PythonBridgeEA.mq5 deployed successfully into MT5 Experts folder!</span>
                </div>
              ) : (
                <button
                  onClick={handleDeployEA}
                  disabled={eaDeploying || !selectedTerminal}
                  className="w-full py-2.5 rounded-xl bg-arcade-primary hover:bg-arcade-primaryHover active:bg-arcade-primaryActive disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                >
                  <RefreshCw className={`w-4 h-4 ${eaDeploying ? "animate-spin" : ""}`} />
                  {eaDeploying ? "Installing EA..." : "Deploy PythonBridgeEA to Selected Terminal"}
                </button>
              )}

              {eaError && (
                <div className="p-3 bg-[var(--arcade-loss-soft)] border border-arcade-loss/30 rounded-xl text-xs text-arcade-loss">
                  {eaError}
                </div>
              )}
            </div>
          )}

          {/* STEP 5: MT5 Terminal Configuration Guide */}
          {currentStep === 5 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--arcade-primary-soft)] text-arcade-primary border border-arcade-primary/30">
                  <PlayCircle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-arcade-text">Chart Attachment & AutoTrading</h3>
                  <p className="text-xs text-arcade-textMuted">3 essential steps inside MetaTrader 5</p>
                </div>
              </div>

              <div className="space-y-2 text-xs">
                <div className="p-3 bg-arcade-surface rounded-xl border border-arcade-border flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-arcade-primary text-white flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <div className="font-bold text-arcade-text">Enable Algo Trading</div>
                    <div className="text-arcade-textMuted text-[11px] mt-0.5">
                      Ensure the "Algo Trading" button in MT5's top toolbar is clicked and displays green.
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-arcade-surface rounded-xl border border-arcade-border flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-arcade-primary text-white flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <div className="font-bold text-arcade-text">Allow DLL Imports & WebRequests</div>
                    <div className="text-arcade-textMuted text-[11px] mt-0.5">
                      Open <i>Tools &gt; Options &gt; Expert Advisors</i> and check "Allow Algo Trading" and "Allow DLL imports".
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-arcade-surface rounded-xl border border-arcade-border flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-arcade-primary text-white flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    3
                  </div>
                  <div>
                    <div className="font-bold text-arcade-text">Attach PythonBridgeEA to Any Chart</div>
                    <div className="text-arcade-textMuted text-[11px] mt-0.5">
                      Open the Navigator window (Ctrl+N), expand Expert Advisors, and drag <code>PythonBridgeEA</code> onto any open chart window (e.g. EURUSD).
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 6: Pre-Flight Diagnostics Check */}
          {currentStep === 6 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--arcade-primary-soft)] text-arcade-primary border border-arcade-primary/30">
                  <Cpu className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-arcade-text">Pre-Flight System Check</h3>
                  <p className="text-xs text-arcade-textMuted">Verifying local ports, Python runtime, and bridge sockets</p>
                </div>
              </div>

              <div className="space-y-2">
                {diagnostics.length === 0 ? (
                  <div className="p-6 text-center text-xs text-arcade-textMuted bg-arcade-surface rounded-xl border border-arcade-border">
                    Press the button below to run pre-flight diagnostics.
                  </div>
                ) : (
                  diagnostics.map((d) => (
                    <div
                      key={d.id}
                      className="p-3 rounded-xl bg-arcade-surface border border-arcade-border flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="font-bold text-arcade-text">{d.name}</div>
                        <div className="text-[11px] text-arcade-textMuted">{d.details}</div>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          d.status === "PASS"
                            ? "bg-[var(--arcade-profit-soft)] text-arcade-profit border border-arcade-profit/30"
                            : "bg-[var(--arcade-loss-soft)] text-arcade-loss border border-arcade-loss/30"
                        }`}
                      >
                        {d.status}
                      </span>
                    </div>
                  ))
                )}
              </div>

              <button
                onClick={runDiag}
                disabled={diagLoading}
                className="w-full py-2.5 rounded-xl bg-arcade-secondary hover:brightness-105 text-arcade-text font-bold text-xs flex items-center justify-center gap-2 border border-arcade-border transition"
              >
                <RefreshCw className={`w-4 h-4 ${diagLoading ? "animate-spin" : ""}`} />
                {diagLoading ? "Executing Tests..." : "Run Diagnostics Check"}
              </button>
            </div>
          )}

          {/* STEP 7: Completion & Launch */}
          {currentStep === 7 && (
            <div className="space-y-4 text-center py-6">
              <div className="w-14 h-14 rounded-full bg-[var(--arcade-profit-soft)] border border-arcade-profit/30 mx-auto flex items-center justify-center text-arcade-profit">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-extrabold text-arcade-text">Setup Successfully Completed!</h3>
              <p className="text-xs text-arcade-textSecondary max-w-md mx-auto leading-relaxed">
                Your MT5-001 Companion is fully configured. You can start the automated scalping engine
                directly from the top control bar at any time.
              </p>

              <div className="p-3.5 bg-arcade-surface rounded-xl border border-arcade-border max-w-sm mx-auto text-left text-xs text-arcade-textMuted space-y-1">
                <div className="font-semibold text-arcade-text flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-arcade-primary" /> Safety Reminders:
                </div>
                <div>• Initial mode is locked to <b>DEMO/SIMULATION</b></div>
                <div>• Daily drawdown circuit breaker set to <b>3.0%</b></div>
                <div>• Emergency liquidation available via <b>Close All</b></div>
              </div>
            </div>
          )}
        </div>

        {/* Wizard Footer Controls */}
        <div className="p-4 bg-arcade-surface border-t border-arcade-border flex items-center justify-between">
          {currentStep > 1 ? (
            <button
              onClick={() => setCurrentStep((prev) => prev - 1)}
              className="px-4 py-2 rounded-xl bg-arcade-card hover:bg-arcade-secondary text-arcade-text text-xs font-semibold border border-arcade-border flex items-center gap-1.5 transition"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back
            </button>
          ) : (
            <button
              onClick={onFinish}
              className="px-4 py-2 rounded-xl bg-arcade-card hover:bg-arcade-secondary text-arcade-textMuted hover:text-arcade-text text-xs font-semibold border border-arcade-border transition"
            >
              Skip Setup
            </button>
          )}

          {currentStep < totalSteps ? (
            <button
              onClick={() => setCurrentStep((prev) => prev + 1)}
              className="px-5 py-2 rounded-xl bg-arcade-primary hover:bg-arcade-primaryHover active:bg-arcade-primaryActive text-white text-xs font-bold flex items-center gap-1.5 transition"
            >
              Next <ArrowRight className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              onClick={handleFinishOnboarding}
              className="px-6 py-2 rounded-xl bg-arcade-primary hover:bg-arcade-primaryHover active:bg-arcade-primaryActive text-white text-xs font-bold transition"
            >
              Finish & Open Dashboard
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
