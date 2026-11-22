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
  const [institutionalEaStatus, setInstitutionalEaStatus] = useState<PairingStatus>({
    isPaired: false,
    instanceId: null,
    deviceTokenMasked: null,
    pairedAt: null,
    apiUrl: "https://arcadefx.live/api/v1"
  });
  const [institutionalEaCode, setInstitutionalEaCode] = useState<string>("");
  const [institutionalEaError, setInstitutionalEaError] = useState<string | null>(null);
  const [institutionalEaLoading, setInstitutionalEaLoading] = useState<boolean>(false);

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
      setInstitutionalEaStatus(pStatus);
      setTelegramStatus(tStatus);
      setTerminals(tList);
      if (tList.length > 0) setSelectedTerminal(tList[0]);
    } catch (e) {
      console.error(e);
    }
  };

  const handleInstitutionalEaPair = async () => {
    if (!institutionalEaCode || institutionalEaCode.length !== 6) {
      setInstitutionalEaError("Pairing code must be exactly 6 characters.");
      return;
    }
    setInstitutionalEaLoading(true);
    setInstitutionalEaError(null);
    try {
      const res = await IPC.submitPairingCode(institutionalEaCode);
      if (res.success) {
        const s = await IPC.getPairingStatus();
        setInstitutionalEaStatus(s);
        setCurrentStep(3);
      } else {
        setInstitutionalEaError(res.message);
      }
    } catch (e: any) {
      setInstitutionalEaError(e.message || "Pairing failed.");
    } finally {
      setInstitutionalEaLoading(false);
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
      <div className="relative w-full max-w-2xl bg-institutional-ea-card border border-institutional-ea-border rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh] text-institutional-ea-text">
        {/* Progress Bar & Header */}
        <div className="bg-institutional-ea-surface border-b border-institutional-ea-border p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-[var(--institutional-ea-primary-soft)] border border-institutional-ea-primary/30 flex items-center justify-center">
                <Wand2 className="w-4 h-4 text-institutional-ea-primary" />
              </div>
              <div>
                <h2 className="text-base font-bold text-institutional-ea-text">Institutional EA Setup Wizard</h2>
                <p className="text-xs text-institutional-ea-textMuted">Guided onboarding and system alignment</p>
              </div>
            </div>
            <div className="text-xs font-mono font-semibold px-2.5 py-1 rounded-md bg-institutional-ea-card border border-institutional-ea-border text-institutional-ea-primary">
              Step {currentStep} of {totalSteps}
            </div>
          </div>

          <div className="w-full bg-institutional-ea-secondary h-1.5 rounded-full overflow-hidden">
            <div
              className="bg-institutional-ea-primary h-full transition-all duration-300"
              style={{ width: `${(currentStep / totalSteps) * 100}%` }}
            />
          </div>
        </div>

        {/* Step Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-4">
          {/* STEP 1: Welcome & Overview */}
          {currentStep === 1 && (
            <div className="space-y-4 text-center py-4">
              <div className="w-14 h-14 rounded-2xl bg-institutional-ea-surface border border-institutional-ea-border p-2 mx-auto flex items-center justify-center shadow-sm">
                <img src="/institutional-ea-logo.svg" alt="Institutional EA" className="w-full h-full object-contain" />
              </div>
              <h3 className="text-xl font-extrabold text-institutional-ea-text">Welcome to Institutional EA</h3>
              <p className="text-xs text-institutional-ea-textSecondary max-w-md mx-auto leading-relaxed">
                This guided wizard establishes high-speed communication between your local MetaTrader 5 terminal,
                the Python quantitative engine, and your Institutional EA Cloud portal.
              </p>

              <div className="grid grid-cols-3 gap-3 pt-3 text-left">
                <div className="p-3 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl">
                  <div className="font-bold text-xs text-institutional-ea-text mb-1">1. Cloud Pairing</div>
                  <div className="text-[11px] text-institutional-ea-textMuted">Secure 6-char link with Institutional EA Cloud</div>
                </div>
                <div className="p-3 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl">
                  <div className="font-bold text-xs text-institutional-ea-text mb-1">2. Telegram Alerts</div>
                  <div className="text-[11px] text-institutional-ea-textMuted">Real-time telemetry and execution commands</div>
                </div>
                <div className="p-3 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl">
                  <div className="font-bold text-xs text-institutional-ea-text mb-1">3. MQL5 Bridge</div>
                  <div className="text-[11px] text-institutional-ea-textMuted">ZeroMQ/Socket EA installation into MT5</div>
                </div>
              </div>
            </div>
          )}

          {/* STEP 2: Institutional EA Cloud Pairing */}
          {currentStep === 2 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
                  <Link2 className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-institutional-ea-text">Pair with Institutional EA Cloud</h3>
                  <p className="text-xs text-institutional-ea-textMuted">Synchronize your trading session with your web dashboard</p>
                </div>
              </div>

              {institutionalEaStatus.isPaired ? (
                <div className="p-4 rounded-xl bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-institutional-ea-profit" />
                  <div className="text-xs text-institutional-ea-profit font-semibold">
                    Device already paired with Institutional EA Cloud!
                  </div>
                </div>
              ) : (
                <div className="space-y-3 pt-2">
                  <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border text-xs text-institutional-ea-textSecondary space-y-1">
                    <div>1. Log in to <b className="text-institutional-ea-text">Institutional EA Cloud</b></div>
                    <div>2. Open <b>Settings &gt; Bot Management &gt; Pair Desktop</b></div>
                    <div>3. Generate and paste your 6-character code below:</div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-institutional-ea-text mb-1">Pairing Code</label>
                    <input
                      type="text"
                      maxLength={6}
                      value={institutionalEaCode}
                      onChange={(e) => setInstitutionalEaCode(e.target.value.toUpperCase())}
                      placeholder="e.g. 7X9K2P"
                      className="w-full px-4 py-2.5 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl text-center font-mono text-lg font-bold tracking-widest text-institutional-ea-text uppercase focus:border-institutional-ea-primary outline-none transition"
                    />
                  </div>

                  {institutionalEaError && (
                    <div className="p-3 bg-[var(--institutional-ea-loss-soft)] border border-institutional-ea-loss/30 rounded-xl text-xs text-institutional-ea-loss flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0" />
                      <span>{institutionalEaError}</span>
                    </div>
                  )}

                  <button
                    onClick={handleInstitutionalEaPair}
                    disabled={institutionalEaLoading || institutionalEaCode.length !== 6}
                    className="w-full py-2.5 rounded-xl bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                  >
                    <RefreshCw className={`w-4 h-4 ${institutionalEaLoading ? "animate-spin" : ""}`} />
                    {institutionalEaLoading ? "Pairing..." : "Verify & Link Account"}
                  </button>
                </div>
              )}
            </div>
          )}

          {/* STEP 3: Telegram Remote Control */}
          {currentStep === 3 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
                  <Send className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-institutional-ea-text">Telegram Remote Control & Alerts</h3>
                  <p className="text-xs text-institutional-ea-textMuted">Receive immediate mobile notifications and send trade controls</p>
                </div>
              </div>

              {telegramStatus.isPaired ? (
                <div className="p-4 rounded-xl bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 flex items-center gap-3">
                  <CheckCircle2 className="w-5 h-5 text-institutional-ea-profit" />
                  <div className="text-xs text-institutional-ea-profit font-semibold">
                    Telegram Bot connected: {telegramStatus.botUsername || "Configured"}
                  </div>
                </div>
              ) : (
                <div className="space-y-3 pt-2">
                  <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border text-xs text-institutional-ea-textMuted space-y-1">
                    <div>1. Message <span className="text-institutional-ea-primary font-mono">@BotFather</span> on Telegram and create a bot</div>
                    <div>2. Enter the bot token or skip if already configured in <code>.env</code></div>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-institutional-ea-text mb-1">Bot Token (Optional)</label>
                    <input
                      type="text"
                      value={telegramToken}
                      onChange={(e) => setTelegramToken(e.target.value)}
                      placeholder="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
                      className="w-full px-3 py-2 bg-institutional-ea-surface border border-institutional-ea-border rounded-xl text-institutional-ea-text font-mono text-xs focus:border-institutional-ea-primary outline-none transition"
                    />
                  </div>

                  {telegramError && (
                    <div className="p-3 bg-[var(--institutional-ea-loss-soft)] border border-institutional-ea-loss/30 rounded-xl text-xs text-institutional-ea-loss">
                      {telegramError}
                    </div>
                  )}

                  <button
                    onClick={handleTelegramPair}
                    disabled={telegramLoading}
                    className="w-full py-2.5 rounded-xl bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
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
                <div className="p-2.5 rounded-xl bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
                  <FileCode2 className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-institutional-ea-text">MetaTrader 5 Integration</h3>
                  <p className="text-xs text-institutional-ea-textMuted">Select terminal and deploy PythonBridgeEA.mq5</p>
                </div>
              </div>

              <div className="space-y-2">
                <div className="text-xs font-semibold text-institutional-ea-textSecondary">Detected MT5 Terminals:</div>
                {terminals.length === 0 ? (
                  <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border text-xs text-institutional-ea-textMuted">
                    No MT5 instances found automatically.
                  </div>
                ) : (
                  terminals.map((t) => (
                    <div
                      key={t.id}
                      onClick={() => setSelectedTerminal(t)}
                      className={`p-3 rounded-xl border cursor-pointer transition text-xs ${
                        selectedTerminal?.id === t.id
                          ? "bg-[var(--institutional-ea-primary-soft)] border-institutional-ea-primary/50 text-institutional-ea-text"
                          : "bg-institutional-ea-surface border-institutional-ea-border text-institutional-ea-textSecondary hover:border-institutional-ea-borderStrong"
                      }`}
                    >
                      <div className="font-bold flex items-center justify-between">
                        <span>{t.name}</span>
                        {t.eaInstalled && (
                          <span className="text-[10px] text-institutional-ea-profit font-semibold">EA Installed</span>
                        )}
                      </div>
                      <div className="font-mono text-[10px] text-institutional-ea-textMuted mt-0.5 truncate max-w-lg">
                        {t.executablePath}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {eaSuccess ? (
                <div className="p-3 bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 rounded-xl text-xs text-institutional-ea-profit flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>PythonBridgeEA.mq5 deployed successfully into MT5 Experts folder!</span>
                </div>
              ) : (
                <button
                  onClick={handleDeployEA}
                  disabled={eaDeploying || !selectedTerminal}
                  className="w-full py-2.5 rounded-xl bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive disabled:opacity-50 text-white font-bold text-xs flex items-center justify-center gap-2 transition"
                >
                  <RefreshCw className={`w-4 h-4 ${eaDeploying ? "animate-spin" : ""}`} />
                  {eaDeploying ? "Installing EA..." : "Deploy PythonBridgeEA to Selected Terminal"}
                </button>
              )}

              {eaError && (
                <div className="p-3 bg-[var(--institutional-ea-loss-soft)] border border-institutional-ea-loss/30 rounded-xl text-xs text-institutional-ea-loss">
                  {eaError}
                </div>
              )}
            </div>
          )}

          {/* STEP 5: MT5 Terminal Configuration Guide */}
          {currentStep === 5 && (
            <div className="space-y-4">
              <div className="flex items-center gap-3">
                <div className="p-2.5 rounded-xl bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
                  <PlayCircle className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-institutional-ea-text">Chart Attachment & AutoTrading</h3>
                  <p className="text-xs text-institutional-ea-textMuted">3 essential steps inside MetaTrader 5</p>
                </div>
              </div>

              <div className="space-y-2 text-xs">
                <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-institutional-ea-primary text-white flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    1
                  </div>
                  <div>
                    <div className="font-bold text-institutional-ea-text">Enable Algo Trading</div>
                    <div className="text-institutional-ea-textMuted text-[11px] mt-0.5">
                      Ensure the "Algo Trading" button in MT5's top toolbar is clicked and displays green.
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-institutional-ea-primary text-white flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    2
                  </div>
                  <div>
                    <div className="font-bold text-institutional-ea-text">Allow DLL Imports & WebRequests</div>
                    <div className="text-institutional-ea-textMuted text-[11px] mt-0.5">
                      Open <i>Tools &gt; Options &gt; Expert Advisors</i> and check "Allow Algo Trading" and "Allow DLL imports".
                    </div>
                  </div>
                </div>

                <div className="p-3 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border flex items-start gap-3">
                  <div className="w-5 h-5 rounded-full bg-institutional-ea-primary text-white flex items-center justify-center text-[10px] font-bold shrink-0 mt-0.5">
                    3
                  </div>
                  <div>
                    <div className="font-bold text-institutional-ea-text">Attach PythonBridgeEA to Any Chart</div>
                    <div className="text-institutional-ea-textMuted text-[11px] mt-0.5">
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
                <div className="p-2.5 rounded-xl bg-[var(--institutional-ea-primary-soft)] text-institutional-ea-primary border border-institutional-ea-primary/30">
                  <Cpu className="w-6 h-6" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-institutional-ea-text">Pre-Flight System Check</h3>
                  <p className="text-xs text-institutional-ea-textMuted">Verifying local ports, Python runtime, and bridge sockets</p>
                </div>
              </div>

              <div className="space-y-2">
                {diagnostics.length === 0 ? (
                  <div className="p-6 text-center text-xs text-institutional-ea-textMuted bg-institutional-ea-surface rounded-xl border border-institutional-ea-border">
                    Press the button below to run pre-flight diagnostics.
                  </div>
                ) : (
                  diagnostics.map((d) => (
                    <div
                      key={d.id}
                      className="p-3 rounded-xl bg-institutional-ea-surface border border-institutional-ea-border flex items-center justify-between text-xs"
                    >
                      <div>
                        <div className="font-bold text-institutional-ea-text">{d.name}</div>
                        <div className="text-[11px] text-institutional-ea-textMuted">{d.details}</div>
                      </div>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          d.status === "PASS"
                            ? "bg-[var(--institutional-ea-profit-soft)] text-institutional-ea-profit border border-institutional-ea-profit/30"
                            : "bg-[var(--institutional-ea-loss-soft)] text-institutional-ea-loss border border-institutional-ea-loss/30"
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
                className="w-full py-2.5 rounded-xl bg-institutional-ea-secondary hover:brightness-105 text-institutional-ea-text font-bold text-xs flex items-center justify-center gap-2 border border-institutional-ea-border transition"
              >
                <RefreshCw className={`w-4 h-4 ${diagLoading ? "animate-spin" : ""}`} />
                {diagLoading ? "Executing Tests..." : "Run Diagnostics Check"}
              </button>
            </div>
          )}

          {/* STEP 7: Completion & Launch */}
          {currentStep === 7 && (
            <div className="space-y-4 text-center py-6">
              <div className="w-14 h-14 rounded-full bg-[var(--institutional-ea-profit-soft)] border border-institutional-ea-profit/30 mx-auto flex items-center justify-center text-institutional-ea-profit">
                <CheckCircle2 className="w-8 h-8" />
              </div>
              <h3 className="text-xl font-extrabold text-institutional-ea-text">Setup Successfully Completed!</h3>
              <p className="text-xs text-institutional-ea-textSecondary max-w-md mx-auto leading-relaxed">
                Your Institutional EA Companion is fully configured. You can start the automated scalping engine
                directly from the top control bar at any time.
              </p>

              <div className="p-3.5 bg-institutional-ea-surface rounded-xl border border-institutional-ea-border max-w-sm mx-auto text-left text-xs text-institutional-ea-textMuted space-y-1">
                <div className="font-semibold text-institutional-ea-text flex items-center gap-1.5">
                  <ShieldAlert className="w-4 h-4 text-institutional-ea-primary" /> Safety Reminders:
                </div>
                <div>• Initial mode is locked to <b>DEMO/SIMULATION</b></div>
                <div>• Daily drawdown circuit breaker set to <b>3.0%</b></div>
                <div>• Emergency liquidation available via <b>Close All</b></div>
              </div>
            </div>
          )}
        </div>

        {/* Wizard Footer Controls */}
        <div className="p-4 bg-institutional-ea-surface border-t border-institutional-ea-border flex items-center justify-between">
          {currentStep > 1 ? (
            <button
              onClick={() => setCurrentStep((prev) => prev - 1)}
              className="px-4 py-2 rounded-xl bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-text text-xs font-semibold border border-institutional-ea-border flex items-center gap-1.5 transition"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back
            </button>
          ) : (
            <button
              onClick={onFinish}
              className="px-4 py-2 rounded-xl bg-institutional-ea-card hover:bg-institutional-ea-secondary text-institutional-ea-textMuted hover:text-institutional-ea-text text-xs font-semibold border border-institutional-ea-border transition"
            >
              Skip Setup
            </button>
          )}

          {currentStep < totalSteps ? (
            <button
              onClick={() => setCurrentStep((prev) => prev + 1)}
              className="px-5 py-2 rounded-xl bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive text-white text-xs font-bold flex items-center gap-1.5 transition"
            >
              Next <ArrowRight className="w-3.5 h-3.5" />
            </button>
          ) : (
            <button
              onClick={handleFinishOnboarding}
              className="px-6 py-2 rounded-xl bg-institutional-ea-primary hover:bg-institutional-ea-primaryHover active:bg-institutional-ea-primaryActive text-white text-xs font-bold transition"
            >
              Finish & Open Dashboard
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
