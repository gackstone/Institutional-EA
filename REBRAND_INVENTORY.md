# Institutional EA — Complete Rebrand Inventory & Audit Log

This document records the Phase 1 deep inspection inventory of all legacy brand, product, design-system, and repository names across the entire codebase, along with the Phase 2–3 execution summary, file renames, intentionally preserved identifiers, and artwork audit.

## 1. Identified Legacy Brand & Product Name Families

| Legacy Brand Family | Observed Variations & Casings | Target Replacement (`Institutional EA`) |
| :--- | :--- | :--- |
| **MT5-001 / MT5-OO1** | `MT5-001`, `MT5-OO1`, `MT5_001`, `mt5-oo1`, `mt5_oo1`, `mt5oo1`, `mt5-001`, `Mt5001_bot`, `mt5-oo1-companion`, `mt5_oo1_companion`, `MT5-OO1 Companion`, `MT5-001 Companion` | Display: `Institutional EA` / `Institutional EA Companion`<br>kebab-case: `institutional-ea` / `institutional-ea-companion`<br>snake_case: `institutional_ea` / `institutional_ea_companion`<br>PascalCase: `InstitutionalEa`<br>UPPER_SNAKE: `INSTITUTIONAL_EA` |
| **ArcadeFX / Arcade FX** | `ArcadeFX`, `Arcade FX`, `ArcadeFx`, `ARCADEFX`, `arcadefx`, `arcade-fx`, `arcade_fx`, `arcade`, `live.arcadefx.mt5oo1`, `live.arcadefx.mt5companion`, `bg-arcade-*`, `--arcade-*` | Display: `Institutional EA`<br>Bundle/App ID: `com.institutionalea.app`<br>kebab-case: `institutional-ea`<br>snake_case: `institutional_ea`<br>PascalCase: `InstitutionalEa`<br>UPPER_SNAKE: `INSTITUTIONAL_EA` |
| **AlgoVistra** | `AlgoVistra`, `AlgoVistraEnginePipeline`, `AlgoVistraPipeline`, `AlgoVistraSkills`, `algovistra_backtest`, `algovistra_skills` | `Institutional EA`, `InstitutionalEaEnginePipeline`, `InstitutionalEaPipeline`, `InstitutionalEaSkills`, `institutional_ea_backtest`, `institutional_ea_skills` |
| **JBCyberLogics / Trading-Bot / Quant Systems** | `JBCyberLogics`, `Trading-Bot`, `trading-bot`, `trading_bot`, `Quant Systems`, `gackstonew-lgtm/MT5-OO1`, `gackstone/MT5-001-Bot` | `Institutional EA`, `https://github.com/gackstone/Institutional-EA`, `institutional-ea`, `institutional_ea` |
| **Alpha Coach** | `alpha_coach_theme` (localStorage theme key) | `institutional_ea_theme` |
| **Yardly / Yardly Automotive** | `Yardly`, `Yardly Automotive`, `Yardly Design System`, `yardly-glass`, `yardly-card`, `animate-yardly-fade`, `animate-yardly-slide` | `Institutional EA`, `Institutional EA Design System`, `institutional-ea-glass`, `institutional-ea-card`, `animate-institutional-ea-fade`, `animate-institutional-ea-slide` |

## 2. Full Codebase Occurrence Inventory (Phase 1 Audit)

Total file-level pattern groups discovered before rebrand: **242**

| Old Brand / Term Family | File Path | Type of Occurrence | Match Count | Matched Tokens |
| :--- | :--- | :--- | :---: | :--- |
| ArcadeFX / Arcade FX / arcadefx / arcade | `.env.example` | CI/CD Workflow, Deployment & Environment Config | 4 | `ARCADEFX_API_URL`, `ArcadeFx`, `arcadefx` |
| JBCyberLogics / Trading-Bot / trading-bot | `.env.example` | CI/CD Workflow, Deployment & Environment Config | 1 | `Trading-Bot` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `.gitignore` | CI/CD Workflow, Deployment & Environment Config | 1 | `MT5-001-Companion-Setup` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `CHANGELOG.md` | Documentation, Release Notes & Audit Reports | 5 | `ArcadeFX`, `ArcadeFx`, `arcadefx`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `CHANGELOG.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_ACCOUNT_SIZING_REMEDIATION_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_CENT_ACCOUNT_COMPATIBILITY_REPORT.md` | Documentation, Release Notes & Audit Reports | 8 | `MT5-001`, `MT5-001-CENT-COMPAT-20261116`, `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_CRITICAL_REMEDIATION_REPORT.md` | Documentation, Release Notes & Audit Reports | 2 | `MT5-001`, `MT5-001-Bot` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_DYNAMIC_POSITION_LAYERING_REPORT.md` | Documentation, Release Notes & Audit Reports | 2 | `MT5-001`, `MT5-001-Bot` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_FINAL_EXECUTION_PIPELINE_AUDIT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_FINAL_TEST_RESULTS.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `MT5-001_FORENSIC_REMEDIATION_AND_RUNTIME_VERIFICATION_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `arcadefx-companion` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_FORENSIC_REMEDIATION_AND_RUNTIME_VERIFICATION_REPORT.md` | Documentation, Release Notes & Audit Reports | 12 | `MT5-001`, `MT5-001-Bot`, `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_FULL_CODEBASE_AUDIT_REPORT.md` | Documentation, Release Notes & Audit Reports | 2 | `MT5-001`, `MT5-001-Bot` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_POST_IMPLEMENTATION_AUDIT_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_SECOND_INDEPENDENT_AUDIT_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_STEP_BY_STEP_RUN_AND_TEST_GUIDE.md` | Documentation, Release Notes & Audit Reports | 2 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_SYMBOL_WHITELIST_ENFORCEMENT_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5-001_US30_ROOT_CAUSE_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5_001_UNIFIED_RISK_EXECUTION_RECONCILIATION_REPORT.md` | Documentation, Release Notes & Audit Reports | 4 | `MT5-001`, `MT5-001-ENG-REPORT-2026-11-17-006`, `MT5_001_BACKUP_UNIFIED_RISK_20261117_193500` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `MT5_001_UNIVERSAL_ACCOUNT_EXECUTION_FINAL_REPORT.md` | Documentation, Release Notes & Audit Reports | 3 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `README.md` | Documentation, Release Notes & Audit Reports | 7 | `ArcadeFX`, `ArcadeFX_MT5_Supervisor_Mutex`, `ArcadeFx`, `arcadefx`, `arcadefx_ea_heartbeat` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `README.md` | Documentation, Release Notes & Audit Reports | 2 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `agent/mt5_bot_agent.py` | Python Engine, Agent, Supervisor & Operational Scripts | 53 | `ARCADEFX_API_URL`, `ARCADEFx`, `ArcadeFX`, `ArcadeFx`, `ArcadeFx-MT5BotAgent`, `ArcadeFxAgent` (+3 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `agent/mt5_bot_agent.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `agent/requirements.txt` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `Arcade` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `agent/run_agent.bat` | Python Engine, Agent, Supervisor & Operational Scripts | 2 | `ARCADEFx`, `ArcadeFx` |
| AlgoVistra / algovistra | `backups/obsolete_scalper_arch_backup/config/strategy.yaml` | Archived Backup Snapshot | 1 | `AlgoVistra` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/obsolete_scalper_arch_backup/docs/ARCHITECTURE_AFTER.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/obsolete_scalper_arch_backup/docs/PULL_REQUEST.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/config/backups/pre_upgrade_backup/manual_management.yaml` | Archived Backup Snapshot | 1 | `ARCADEFX` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/config/backups/pre_upgrade_backup/settings.json` | Documentation, Release Notes & Audit Reports | 2 | `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/config/manual_management.yaml` | Archived Backup Snapshot | 1 | `ARCADEFX` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/config/settings.json` | Documentation, Release Notes & Audit Reports | 2 | `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/electron/main.cjs` | Archived Backup Snapshot | 68 | `ARCADEFX`, `ARCADEFX_API_URL`, `ARCADEFX_APP_DATA_DIR`, `ARCADEFX_DATA_DIR`, `ARCADEFX_DIR`, `Arcade` (+4 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_cent_account_backup/electron/main.cjs` | Archived Backup Snapshot | 9 | `MT5-OO1`, `MT5-OO1-Companion`, `mt5-oo1-companion` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/electron/preload.cjs` | Archived Backup Snapshot | 1 | `ArcadeFX` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/App.tsx` | Archived Backup Snapshot | 3 | `arcade-bg`, `arcade-text`, `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/ControlsBar.tsx` | Archived Backup Snapshot | 55 | `ArcadeFX`, `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-primary`, `arcade-primaryHover` (+6 more) |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/components/ControlsBar.tsx` | Archived Backup Snapshot | 4 | `yardly-fade`, `yardly-glass`, `yardly-slide` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/DiagnosticsModal.tsx` | Archived Backup Snapshot | 32 | `arcade-border`, `arcade-card`, `arcade-info`, `arcade-loss`, `arcade-primary`, `arcade-primaryHover` (+8 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/Header.tsx` | Archived Backup Snapshot | 75 | `ArcadeFX`, `arcade-border`, `arcade-card`, `arcade-primary`, `arcade-primaryHover`, `arcade-profit` (+4 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_cent_account_backup/src/components/Header.tsx` | Archived Backup Snapshot | 1 | `MT5-001` |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/components/Header.tsx` | Archived Backup Snapshot | 2 | `yardly-fade`, `yardly-glass` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/LiveConsole.tsx` | Archived Backup Snapshot | 64 | `ARCADEFX`, `ArcadeFX`, `arcade-bg`, `arcade-border`, `arcade-card`, `arcade-primary` (+5 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/MT5SetupWizard.tsx` | Archived Backup Snapshot | 80 | `arcade-border`, `arcade-borderStrong`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary` (+10 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/MetricsGrid.tsx` | Archived Backup Snapshot | 41 | `arcade-bg`, `arcade-border`, `arcade-borderStrong`, `arcade-primary`, `arcade-secondary`, `arcade-text` (+2 more) |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/components/MetricsGrid.tsx` | Archived Backup Snapshot | 6 | `yardly-card` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/OnboardingWizard.tsx` | Archived Backup Snapshot | 215 | `ArcadeFX`, `ArcadePair`, `ArcadefxCode`, `ArcadefxError`, `ArcadefxLoading`, `ArcadefxStatus` (+22 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_cent_account_backup/src/components/OnboardingWizard.tsx` | Archived Backup Snapshot | 3 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/PairingModal.tsx` | Archived Backup Snapshot | 63 | `ArcadeFX`, `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary` (+11 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/PositionsTable.tsx` | Archived Backup Snapshot | 185 | `arcade-bg`, `arcade-border`, `arcade-card`, `arcade-primary`, `arcade-primaryHover`, `arcade-secondary` (+5 more) |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/components/PositionsTable.tsx` | Archived Backup Snapshot | 6 | `yardly-card`, `yardly-fade`, `yardly-slide` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/SettingsModal.tsx` | Archived Backup Snapshot | 90 | `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary`, `arcade-primaryActive` (+7 more) |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/components/SettingsModal.tsx` | Archived Backup Snapshot | 2 | `Yardly` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/StatusBadge.tsx` | Archived Backup Snapshot | 17 | `ArcadeFX`, `arcade-border`, `arcade-primary`, `arcade-secondary`, `arcade-textMuted`, `arcade-textSecondary` |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/components/StatusBadge.tsx` | Archived Backup Snapshot | 1 | `Yardly` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/TelegramPairingModal.tsx` | Archived Backup Snapshot | 57 | `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary`, `arcade-primary-soft` (+10 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/components/screens/MonitoringSettingsScreens.tsx` | Archived Backup Snapshot | 4 | `ArcadeFX` |
| Alpha Coach (alpha_coach_theme) | `backups/pre_cent_account_backup/src/context/ThemeContext.tsx` | Archived Backup Snapshot | 1 | `alpha_coach_theme` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/core/app_paths.py` | Archived Backup Snapshot | 10 | `ARCADEFX_APP_DATA_DIR`, `ArcadeFX`, `ArcadeFX_MT5Companion`, `arcadefx`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_cent_account_backup/src/core/app_paths.py` | Archived Backup Snapshot | 6 | `MT5-OO1`, `mt5-oo1-companion` |
| AlgoVistra / algovistra | `backups/pre_cent_account_backup/src/engine/pipeline.py` | Archived Backup Snapshot | 3 | `AlgoVistra`, `AlgoVistraEnginePipeline`, `AlgoVistraPipeline` |
| AlgoVistra / algovistra | `backups/pre_cent_account_backup/src/engine/skills/__init__.py` | Archived Backup Snapshot | 2 | `AlgoVistra` |
| AlgoVistra / algovistra | `backups/pre_cent_account_backup/src/engine/skills/stop_management_policy.py` | Archived Backup Snapshot | 1 | `AlgoVistra` |
| AlgoVistra / algovistra | `backups/pre_cent_account_backup/src/engine/types.py` | Archived Backup Snapshot | 2 | `AlgoVistra` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/index.css` | Archived Backup Snapshot | 60 | `arcade-bg`, `arcade-border`, `arcade-border-strong`, `arcade-border-subtle`, `arcade-card`, `arcade-error` (+20 more) |
| Yardly / yardly-* | `backups/pre_cent_account_backup/src/index.css` | Archived Backup Snapshot | 14 | `Yardly`, `yardly-card`, `yardly-fade`, `yardly-fade-in`, `yardly-glass`, `yardly-slide` (+1 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_cent_account_backup/src/notifications/notification_policy.py` | Archived Backup Snapshot | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/services/ipc.ts` | Archived Backup Snapshot | 7 | `ARCADEFX`, `ArcadeFX`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_cent_account_backup/src/services/ipc.ts` | Archived Backup Snapshot | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_cent_account_backup/src/types/index.ts` | Archived Backup Snapshot | 1 | `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_consolidation_modified_files_backup/README.md` | Documentation, Release Notes & Audit Reports | 8 | `ArcadeFX`, `ArcadeFX_MT5_Supervisor_Mutex`, `ArcadeFx`, `arcadefx`, `arcadefx_ea_heartbeat` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_consolidation_modified_files_backup/README.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_consolidation_modified_files_backup/config/settings.json` | Documentation, Release Notes & Audit Reports | 2 | `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_remediation_backup/agent/mt5_bot_agent.py` | Archived Backup Snapshot | 53 | `ARCADEFX_API_URL`, `ARCADEFx`, `ArcadeFX`, `ArcadeFx`, `ArcadeFx-MT5BotAgent`, `ArcadeFxAgent` (+3 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_remediation_backup/agent/mt5_bot_agent.py` | Archived Backup Snapshot | 1 | `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_remediation_backup/companion/service/configuration/config_service.py` | Archived Backup Snapshot | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_remediation_backup/companion/service/orchestration/engine_controller.py` | Archived Backup Snapshot | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_remediation_backup/companion/src/components/SettingsModal.tsx` | Archived Backup Snapshot | 91 | `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary`, `arcade-primaryActive` (+7 more) |
| Yardly / yardly-* | `backups/pre_remediation_backup/companion/src/components/SettingsModal.tsx` | Archived Backup Snapshot | 2 | `Yardly` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_remediation_backup/companion/src/services/ipc.ts` | Archived Backup Snapshot | 7 | `ARCADEFX`, `ArcadeFX`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `backups/pre_remediation_backup/companion/src/services/ipc.ts` | Archived Backup Snapshot | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `backups/pre_remediation_backup/config/settings.json` | Documentation, Release Notes & Audit Reports | 2 | `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/.github/workflows/desktop-companion-build.yml` | CI/CD Workflow, Deployment & Environment Config | 5 | `MT5-OO1`, `MT5-OO1-Companion`, `MT5-OO1-Companion-`, `MT5-OO1-Companion-Setup` |
| AlgoVistra / algovistra | `companion/.github/workflows/desktop-companion-build.yml` | CI/CD Workflow, Deployment & Environment Config | 1 | `algovistra_skills` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/database/__init__.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/database/migrations.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/database/repository.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/electron/main.cjs` | Companion Desktop Shell / App Metadata & Config | 68 | `ARCADEFX`, `ARCADEFX_API_URL`, `ARCADEFX_APP_DATA_DIR`, `ARCADEFX_DATA_DIR`, `ARCADEFX_DIR`, `Arcade` (+4 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/electron/main.cjs` | Companion Desktop Shell / App Metadata & Config | 9 | `MT5-OO1`, `MT5-OO1-Companion`, `mt5-oo1-companion` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/electron/preload.cjs` | Companion Desktop Shell / App Metadata & Config | 1 | `ArcadeFX` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/index.html` | Companion UI / Frontend Source & Styling | 4 | `Arcade`, `arcade-bg`, `arcade-text`, `arcadefx-logo` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/index.html` | Companion UI / Frontend Source & Styling | 1 | `MT5-OO1` |
| Alpha Coach (alpha_coach_theme) | `companion/index.html` | Companion UI / Frontend Source & Styling | 1 | `alpha_coach_theme` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/package.json` | Companion Desktop Shell / App Metadata & Config | 2 | `Arcade`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/package.json` | Companion Desktop Shell / App Metadata & Config | 6 | `MT5-OO1`, `MT5-OO1-Companion-Setup`, `mt5-oo1-companion`, `mt5oo1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/public/arcadefx-logo.svg` | Companion Brand Asset / SVG / Icon | 2 | `arcadefx-candles`, `arcadefx-wordmark` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/__init__.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/api/server.py` | Companion Local Control Service & Database | 3 | `MT5-001`, `mt5-001-control-service` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/configuration/config_service.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/main.py` | Companion Local Control Service & Database | 3 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/orchestration/engine_controller.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/service/security/auth.py` | Companion Local Control Service & Database | 1 | `ARCADEFX_DEVICE_TOKEN` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/security/auth.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/trading/__init__.py` | Companion Local Control Service & Database | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/service/trading/btcusd_sample_service.py` | Companion Local Control Service & Database | 5 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src-tauri/Cargo.toml` | Companion Desktop Shell / App Metadata & Config | 2 | `Arcade`, `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/src-tauri/Cargo.toml` | Companion Desktop Shell / App Metadata & Config | 2 | `MT5-OO1`, `mt5_oo1_companion` |
| Quant Systems | `companion/src-tauri/Cargo.toml` | Companion Desktop Shell / App Metadata & Config | 1 | `Quant Systems` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src-tauri/tauri.conf.json` | Companion Desktop Shell / App Metadata & Config | 3 | `Arcade`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/src-tauri/tauri.conf.json` | Companion Desktop Shell / App Metadata & Config | 3 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/App.tsx` | Companion UI / Frontend Source & Styling | 3 | `arcade-bg`, `arcade-text`, `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/ControlsBar.tsx` | Companion UI / Frontend Source & Styling | 55 | `ArcadeFX`, `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-primary`, `arcade-primaryHover` (+6 more) |
| Yardly / yardly-* | `companion/src/components/ControlsBar.tsx` | Companion UI / Frontend Source & Styling | 4 | `yardly-fade`, `yardly-glass`, `yardly-slide` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/DiagnosticsModal.tsx` | Companion UI / Frontend Source & Styling | 32 | `arcade-border`, `arcade-card`, `arcade-info`, `arcade-loss`, `arcade-primary`, `arcade-primaryHover` (+8 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/Header.tsx` | Companion UI / Frontend Source & Styling | 75 | `ArcadeFX`, `arcade-border`, `arcade-card`, `arcade-primary`, `arcade-primaryHover`, `arcade-profit` (+4 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/src/components/Header.tsx` | Companion UI / Frontend Source & Styling | 1 | `MT5-001` |
| Yardly / yardly-* | `companion/src/components/Header.tsx` | Companion UI / Frontend Source & Styling | 2 | `yardly-fade`, `yardly-glass` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/LiveConsole.tsx` | Companion UI / Frontend Source & Styling | 64 | `ARCADEFX`, `ArcadeFX`, `arcade-bg`, `arcade-border`, `arcade-card`, `arcade-primary` (+5 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/MT5SetupWizard.tsx` | Companion UI / Frontend Source & Styling | 80 | `arcade-border`, `arcade-borderStrong`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary` (+10 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/MetricsGrid.tsx` | Companion UI / Frontend Source & Styling | 41 | `arcade-bg`, `arcade-border`, `arcade-borderStrong`, `arcade-primary`, `arcade-secondary`, `arcade-text` (+2 more) |
| Yardly / yardly-* | `companion/src/components/MetricsGrid.tsx` | Companion UI / Frontend Source & Styling | 6 | `yardly-card` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/OnboardingWizard.tsx` | Companion UI / Frontend Source & Styling | 215 | `ArcadeFX`, `ArcadePair`, `ArcadefxCode`, `ArcadefxError`, `ArcadefxLoading`, `ArcadefxStatus` (+22 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/src/components/OnboardingWizard.tsx` | Companion UI / Frontend Source & Styling | 3 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/PairingModal.tsx` | Companion UI / Frontend Source & Styling | 63 | `ArcadeFX`, `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary` (+11 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/PositionsTable.tsx` | Companion UI / Frontend Source & Styling | 186 | `arcade-bg`, `arcade-border`, `arcade-card`, `arcade-primary`, `arcade-primaryHover`, `arcade-secondary` (+5 more) |
| Yardly / yardly-* | `companion/src/components/PositionsTable.tsx` | Companion UI / Frontend Source & Styling | 6 | `yardly-card`, `yardly-fade`, `yardly-slide` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/SettingsModal.tsx` | Companion UI / Frontend Source & Styling | 106 | `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary`, `arcade-primaryActive` (+7 more) |
| Yardly / yardly-* | `companion/src/components/SettingsModal.tsx` | Companion UI / Frontend Source & Styling | 2 | `Yardly` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/StatusBadge.tsx` | Companion UI / Frontend Source & Styling | 17 | `ArcadeFX`, `arcade-border`, `arcade-primary`, `arcade-secondary`, `arcade-textMuted`, `arcade-textSecondary` |
| Yardly / yardly-* | `companion/src/components/StatusBadge.tsx` | Companion UI / Frontend Source & Styling | 1 | `Yardly` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/TelegramPairingModal.tsx` | Companion UI / Frontend Source & Styling | 57 | `arcade-border`, `arcade-card`, `arcade-loss`, `arcade-loss-soft`, `arcade-primary`, `arcade-primary-soft` (+10 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/components/screens/MonitoringSettingsScreens.tsx` | Companion UI / Frontend Source & Styling | 4 | `ArcadeFX` |
| Alpha Coach (alpha_coach_theme) | `companion/src/context/ThemeContext.tsx` | Companion UI / Frontend Source & Styling | 1 | `alpha_coach_theme` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/index.css` | Companion UI / Frontend Source & Styling | 60 | `arcade-bg`, `arcade-border`, `arcade-border-strong`, `arcade-border-subtle`, `arcade-card`, `arcade-error` (+20 more) |
| Yardly / yardly-* | `companion/src/index.css` | Companion UI / Frontend Source & Styling | 14 | `Yardly`, `yardly-card`, `yardly-fade`, `yardly-fade-in`, `yardly-glass`, `yardly-slide` (+1 more) |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/services/ipc.ts` | Companion UI / Frontend Source & Styling | 7 | `ARCADEFX`, `ArcadeFX`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `companion/src/services/ipc.ts` | Companion UI / Frontend Source & Styling | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/src/types/index.ts` | Companion UI / Frontend Source & Styling | 1 | `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `companion/tailwind.config.js` | Companion UI / Frontend Source & Styling | 22 | `arcade`, `arcade-bg`, `arcade-border`, `arcade-border-strong`, `arcade-border-subtle`, `arcade-card` (+15 more) |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `config/broker_registry.json` | Application & Strategy Configuration | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `config/manual_management.yaml` | Application & Strategy Configuration | 1 | `ARCADEFX` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `config/settings.json` | Application & Strategy Configuration | 2 | `arcadefx` |
| JBCyberLogics / Trading-Bot / trading-bot | `deploy/docker-compose.yml` | CI/CD Workflow, Deployment & Environment Config | 2 | `trading-bot`, `trading_bot` |
| JBCyberLogics / Trading-Bot / trading-bot | `deploy/trading_bot.service` | CI/CD Workflow, Deployment & Environment Config | 2 | `trading-bot` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/ATI_ARCHITECTURE_AND_OPERATIONS_MANUAL.md` | Documentation, Release Notes & Audit Reports | 3 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/ATI_INDEPENDENT_SECURITY_AND_SAFETY_AUDIT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/ATI_WINDOWS_POWERSHELL_DEPLOYMENT_GUIDE.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/MT5_001_ARCHITECTURE_AND_DEPENDENCY_MAP.md` | Documentation, Release Notes & Audit Reports | 8 | `ArcadeFX`, `ArcadeFX_MT5_Supervisor_Mutex` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/MT5_001_ARCHITECTURE_AND_DEPENDENCY_MAP.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/MT5_001_COMPLETE_TRADING_SYSTEM_FORENSIC_AUDIT.md` | Documentation, Release Notes & Audit Reports | 6 | `ArcadeFX`, `ArcadeFX_MT5_Supervisor_Mutex` |
| AlgoVistra / algovistra | `docs/MT5_001_COMPLETE_TRADING_SYSTEM_FORENSIC_AUDIT.md` | Documentation, Release Notes & Audit Reports | 6 | `AlgoVistra` |
| AlgoVistra / algovistra | `docs/MT5_001_GAP_ANALYSIS_AND_RECOMMENDATIONS.md` | Documentation, Release Notes & Audit Reports | 3 | `AlgoVistra` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/MT5_001_MULTI_PAIR_SCALPING_ENGINE_UPGRADE_REPORT.md` | Documentation, Release Notes & Audit Reports | 2 | `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/MT5_001_MULTI_PAIR_SCALPING_ENGINE_UPGRADE_REPORT.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001-ENG-UPGRADE-2026-11` |
| AlgoVistra / algovistra | `docs/MT5_001_STRATEGY_INVENTORY.md` | Documentation, Release Notes & Audit Reports | 5 | `AlgoVistra`, `AlgoVistraPipeline`, `algovistra_backtest`, `algovistra_skills` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/MT5_001_TECHNICAL_CAPABILITIES.md` | Documentation, Release Notes & Audit Reports | 2 | `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/NOTIFICATIONS.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/SMC_RULEBOOK.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/arcadefx_coach_prompt.md` | Documentation, Release Notes & Audit Reports | 1 | `ArcadeFx` |
| AlgoVistra / algovistra | `docs/arcadefx_coach_prompt.md` | Documentation, Release Notes & Audit Reports | 16 | `AlgoVistra` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/arcadefx_pairing_guide.md` | Documentation, Release Notes & Audit Reports | 13 | `ARCADEFX`, `ArcadeFX`, `arcadefx`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/arcadefx_pairing_guide.md` | Documentation, Release Notes & Audit Reports | 2 | `MT5-OO1` |
| AlgoVistra / algovistra | `docs/arcadefx_pairing_guide.md` | Documentation, Release Notes & Audit Reports | 1 | `AlgoVistra` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/audit_report.md` | Documentation, Release Notes & Audit Reports | 7 | `arcadefx`, `arcadefx_coach_prompt` |
| AlgoVistra / algovistra | `docs/audit_report.md` | Documentation, Release Notes & Audit Reports | 10 | `AlgoVistra`, `AlgoVistraEnginePipeline`, `algovistra_backtest`, `algovistra_backtest_report`, `algovistra_skills` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/changelog_knowledge.md` | Documentation, Release Notes & Audit Reports | 1 | `arcadefx` |
| AlgoVistra / algovistra | `docs/changelog_knowledge.md` | Documentation, Release Notes & Audit Reports | 4 | `AlgoVistra`, `AlgoVistraEnginePipeline` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/companion_troubleshooting.md` | Documentation, Release Notes & Audit Reports | 2 | `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/companion_troubleshooting.md` | Documentation, Release Notes & Audit Reports | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/desktop_companion_audit.md` | Documentation, Release Notes & Audit Reports | 10 | `Arcade`, `ArcadeFX`, `ArcadeFX_MT5_Supervisor_Mutex`, `arcadefx`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/desktop_companion_audit.md` | Documentation, Release Notes & Audit Reports | 5 | `MT5-OO1` |
| Legacy Repo URL (gackstonew-lgtm) | `docs/desktop_companion_audit.md` | Documentation, Release Notes & Audit Reports | 1 | `gackstonew-lgtm` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/desktop_companion_guide.md` | Documentation, Release Notes & Audit Reports | 6 | `ARCADEFX`, `Arcade`, `ArcadeFX`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/desktop_companion_guide.md` | Documentation, Release Notes & Audit Reports | 6 | `MT5-OO1` |
| AlgoVistra / algovistra | `docs/desktop_companion_guide.md` | Documentation, Release Notes & Audit Reports | 1 | `AlgoVistra` |
| Legacy Repo URL (gackstonew-lgtm) | `docs/desktop_companion_guide.md` | Documentation, Release Notes & Audit Reports | 1 | `gackstonew-lgtm` |
| AlgoVistra / algovistra | `docs/manual_mgmt_audit.md` | Documentation, Release Notes & Audit Reports | 2 | `AlgoVistra`, `algovistra_skills` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/mt5_integration_guide.md` | Documentation, Release Notes & Audit Reports | 1 | `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/mt5_integration_guide.md` | Documentation, Release Notes & Audit Reports | 3 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `docs/single_installer_runbook.md` | Documentation, Release Notes & Audit Reports | 7 | `ArcadeFX`, `arcadefx`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `docs/single_installer_runbook.md` | Documentation, Release Notes & Audit Reports | 9 | `MT5-OO1`, `MT5-OO1-Companion-Setup` |
| AlgoVistra / algovistra | `docs/single_installer_runbook.md` | Documentation, Release Notes & Audit Reports | 1 | `AlgoVistra` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `knowledge/coach_context.md` | Documentation, Release Notes & Audit Reports | 1 | `ArcadeFx` |
| AlgoVistra / algovistra | `knowledge/coach_context.md` | Documentation, Release Notes & Audit Reports | 16 | `AlgoVistra` |
| AlgoVistra / algovistra | `knowledge/forex_kb.json` | Documentation, Release Notes & Audit Reports | 17 | `AlgoVistra` |
| JBCyberLogics / Trading-Bot / trading-bot | `legacy/mql5/Experts/PythonBridgeEA.mq5` | MQL5 Expert Advisor Source (#property / headers) | 2 | `JBCyberLogics`, `Trading-Bot` |
| Quant Systems | `legacy/mql5/Experts/PythonBridgeEA.mq5` | MQL5 Expert Advisor Source (#property / headers) | 2 | `Quant Systems` |
| JBCyberLogics / Trading-Bot / trading-bot | `legacy/v2_baseline/mql5/PythonBridgeEA.mq5` | MQL5 Expert Advisor Source (#property / headers) | 2 | `JBCyberLogics`, `Trading-Bot` |
| Quant Systems | `legacy/v2_baseline/mql5/PythonBridgeEA.mq5` | MQL5 Expert Advisor Source (#property / headers) | 2 | `Quant Systems` |
| JBCyberLogics / Trading-Bot / trading-bot | `mql5/Experts/PythonBridgeEA.mq5` | MQL5 Expert Advisor Source (#property / headers) | 2 | `JBCyberLogics`, `Trading-Bot` |
| Quant Systems | `mql5/Experts/PythonBridgeEA.mq5` | MQL5 Expert Advisor Source (#property / headers) | 2 | `Quant Systems` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `release/RELEASE-NOTES.md` | Documentation, Release Notes & Audit Reports | 6 | `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `release/RELEASE-NOTES.md` | Documentation, Release Notes & Audit Reports | 6 | `MT5-001`, `MT5-001-Companion-Setup`, `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `release/SHA256SUMS.txt` | Documentation, Release Notes & Audit Reports | 1 | `MT5-001-Companion-Setup` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `release/release-manifest.json` | Documentation, Release Notes & Audit Reports | 2 | `ArcadeFX`, `arcadefx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `release/release-manifest.json` | Documentation, Release Notes & Audit Reports | 3 | `MT5-001`, `MT5-001-Companion-Setup`, `mt5oo1` |
| AlgoVistra / algovistra | `reports/algovistra_backtest_report.md` | Documentation, Release Notes & Audit Reports | 2 | `AlgoVistra` |
| JBCyberLogics / Trading-Bot / trading-bot | `scripts/backup.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `trading_bot` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/generate_coach_prompt.py` | Python Engine, Agent, Supervisor & Operational Scripts | 3 | `ArcadeFx`, `arcadefx`, `arcadefx_coach_prompt` |
| AlgoVistra / algovistra | `scripts/generate_coach_prompt.py` | Python Engine, Agent, Supervisor & Operational Scripts | 3 | `AlgoVistra` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/install_autostart.ps1` | Python Engine, Agent, Supervisor & Operational Scripts | 8 | `ARCADE`, `Arcade`, `ArcadeFX_MT5_Supervisor` |
| AlgoVistra / algovistra | `scripts/run_algovistra_backtest.py` | Python Engine, Agent, Supervisor & Operational Scripts | 8 | `AlgoVistra`, `AlgoVistraEnginePipeline`, `algovistra_backtest_report` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/run_bridge_server.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `ArcadeFX` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `scripts/run_bridge_server.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-OO1` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/selfcheck.py` | Python Engine, Agent, Supervisor & Operational Scripts | 8 | `ArcadeFX`, `ArcadeFx`, `arcadefx_agent`, `arcadefx_cloud_agent` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/start_supervisor.bat` | Python Engine, Agent, Supervisor & Operational Scripts | 3 | `ARCADE`, `Arcade` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/status.ps1` | Python Engine, Agent, Supervisor & Operational Scripts | 4 | `ARCADE`, `Arcade`, `ArcadeFX_MT5_Supervisor` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/supervisor.py` | Python Engine, Agent, Supervisor & Operational Scripts | 10 | `ArcadeFX_MT5_Supervisor_Mutex`, `ArcadeFx`, `ArcadeFxSupervisor`, `arcadefx_ea_heartbeat` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `scripts/uninstall_autostart.ps1` | Python Engine, Agent, Supervisor & Operational Scripts | 4 | `ARCADE`, `Arcade`, `ArcadeFX_MT5_Supervisor` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `scripts/verify_live_cent_trade_execution.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `scripts/verify_live_demo_cent_compatibility.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `scripts/verify_live_runtime_execution.py` | Python Engine, Agent, Supervisor & Operational Scripts | 2 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `scripts/verify_telegram_pipeline.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `Mt5001_bot` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `src/core/app_paths.py` | Python Engine, Agent, Supervisor & Operational Scripts | 10 | `ARCADEFX_APP_DATA_DIR`, `ArcadeFX`, `ArcadeFX_MT5Companion`, `arcadefx`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `src/core/app_paths.py` | Python Engine, Agent, Supervisor & Operational Scripts | 6 | `MT5-OO1`, `mt5-oo1-companion` |
| AlgoVistra / algovistra | `src/engine/pipeline.py` | Python Engine, Agent, Supervisor & Operational Scripts | 3 | `AlgoVistra`, `AlgoVistraEnginePipeline`, `AlgoVistraPipeline` |
| AlgoVistra / algovistra | `src/engine/skills/__init__.py` | Python Engine, Agent, Supervisor & Operational Scripts | 2 | `AlgoVistra` |
| AlgoVistra / algovistra | `src/engine/skills/stop_management_policy.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `AlgoVistra` |
| AlgoVistra / algovistra | `src/engine/types.py` | Python Engine, Agent, Supervisor & Operational Scripts | 2 | `AlgoVistra` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `src/intelligence/__init__.py` | Python Engine, Agent, Supervisor & Operational Scripts | 2 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `src/intelligence/contracts.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `src/intelligence/facade.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `src/intelligence/storage/repository.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `src/notifications/notification_policy.py` | Python Engine, Agent, Supervisor & Operational Scripts | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `start_mt5_agent.bat` | Python Engine, Agent, Supervisor & Operational Scripts | 5 | `ARCADEFx`, `ArcadeFX`, `ArcadeFx`, `arcadefx` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `start_mt5_bot.bat` | Python Engine, Agent, Supervisor & Operational Scripts | 4 | `ARCADEFx`, `ArcadeFX`, `ArcadeFx` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/conftest.py` | Unit & Integration Test Suite | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_adaptive_account_architecture.py` | Unit & Integration Test Suite | 1 | `MT5-001` |
| AlgoVistra / algovistra | `tests/test_algovistra_skills.py` | Unit & Integration Test Suite | 4 | `AlgoVistra`, `AlgoVistraEnginePipeline`, `AlgoVistraSkills` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_cent_account_compatibility.py` | Unit & Integration Test Suite | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_companion_control_service.py` | Unit & Integration Test Suite | 2 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `tests/test_companion_supervisor.py` | Unit & Integration Test Suite | 2 | `ArcadeFX`, `arcadefx_agent` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_companion_supervisor.py` | Unit & Integration Test Suite | 1 | `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_continuous_scalping_upgrade.py` | Unit & Integration Test Suite | 1 | `MT5-OO1` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_dynamic_position_layering.py` | Unit & Integration Test Suite | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `tests/test_execution_upgrade_comprehensive.py` | Unit & Integration Test Suite | 1 | `ArcadeFX` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `tests/test_mt5_bot_agent.py` | Unit & Integration Test Suite | 9 | `ArcadeFX`, `ArcadeFx`, `ArcadeFxMT5BotAgent`, `arcadefx`, `arcadefx_test_signing_secret_12345` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_remediation_compliance.py` | Unit & Integration Test Suite | 1 | `MT5-001` |
| MT5-001 / MT5-OO1 / mt5oo1 / mt5_001 | `tests/test_specialized_three_instrument_universe.py` | Unit & Integration Test Suite | 1 | `MT5-001` |
| ArcadeFX / Arcade FX / arcadefx / arcade | `tests/test_supervisor.py` | Unit & Integration Test Suite | 5 | `Arcade`, `ArcadeFX_Stale_`, `ArcadeFX_Supervisor_`, `ArcadeFxSupervisor` |

---

## 3. Final Rebrand Summary: What Changed

- **Total Files Modified / Renamed**: 213 files across the main repository and companion desktop application (`167` files modified in place + `46` files renamed via `git mv`, plus `REBRAND_INVENTORY.md` added).
- **Companion Application (`companion/`)**:
  - Updated `companion/package.json` (`name`: `institutional-ea-companion`, `productName`: `Institutional EA Companion`, `appId`: `com.institutionalea.app`, `shortcutName`: `Institutional EA Companion`, `artifactName`: `Institutional-EA-Companion-Setup.${ext}`, `repository` / `homepage` / `bugs`: `https://github.com/gackstone/Institutional-EA`).
  - Updated `companion/src-tauri/tauri.conf.json` (`productName`: `Institutional EA Companion`, `identifier`: `com.institutionalea.app`, window `title`: `Institutional EA Companion`, tray `tooltip`: `Institutional EA Companion`).
  - Updated `companion/src-tauri/Cargo.toml` (`name`: `institutional_ea_companion`, `description`, `authors`: `["Institutional EA"]`, `repository`, `homepage`).
  - Updated `companion/index.html` (`<title>Institutional EA Companion</title>`, favicon `/institutional-ea-logo.svg`, theme key `institutional_ea_theme`, body classes `bg-institutional-ea-bg text-institutional-ea-text`).
  - Updated Tailwind and CSS design tokens (`--institutional-ea-*`, `bg-institutional-ea-*`, `text-institutional-ea-*`, `border-institutional-ea-*`, `institutional-ea-glass`, `institutional-ea-card`, `animate-institutional-ea-fade`, `animate-institutional-ea-slide`) across `companion/tailwind.config.js`, `companion/src/index.css`, and all React components/modals.
  - Updated Electron main process (`companion/electron/main.cjs`), preload (`companion/electron/preload.cjs`), IPC service (`companion/src/services/ipc.ts`), and Python Local Control Service (`companion/service/`, `companion/database/`).
- **MQL5 Expert Advisor & Quantitative Engine (`mql5/`, `src/`, `agent/`, `scripts/`)**:
  - Updated `#property copyright "Institutional EA"`, `#property link "https://github.com/gackstone/Institutional-EA"`, and header comments in `mql5/Experts/PythonBridgeEA.mq5` and legacy MQL5 baselines.
  - Rebranded `InstitutionalEaEnginePipeline`, `InstitutionalEaPipeline`, `InstitutionalEaSupervisor`, `InstitutionalEaAgent`, application data paths (`src/core/app_paths.py`), and Windows Task Scheduler / launcher scripts (`scripts/supervisor.py`, `scripts/install_autostart.ps1`, `scripts/status.ps1`, `scripts/uninstall_autostart.ps1`, `start_mt5_agent.bat`, `start_mt5_bot.bat`, `agent/run_agent.bat`).
- **Documentation, License, Reports & Workflows**:
  - Updated `LICENSE`, `README.md`, `CHANGELOG.md`, `docs/`, `knowledge/`, `release/`, `deploy/`, and `companion/.github/workflows/desktop-companion-build.yml`.

### Files Renamed (46 Files via `git mv`)

| Original Path | New Path |
| :--- | :--- |
| `MT5-001_ACCOUNT_SIZING_REMEDIATION_REPORT.md` | `INSTITUTIONAL_EA_ACCOUNT_SIZING_REMEDIATION_REPORT.md` |
| `MT5-001_CENT_ACCOUNT_COMPATIBILITY_REPORT.md` | `INSTITUTIONAL_EA_CENT_ACCOUNT_COMPATIBILITY_REPORT.md` |
| `MT5-001_CRITICAL_REMEDIATION_REPORT.md` | `INSTITUTIONAL_EA_CRITICAL_REMEDIATION_REPORT.md` |
| `MT5-001_DYNAMIC_POSITION_LAYERING_REPORT.md` | `INSTITUTIONAL_EA_DYNAMIC_POSITION_LAYERING_REPORT.md` |
| `MT5-001_FINAL_EXECUTION_PIPELINE_AUDIT.md` | `INSTITUTIONAL_EA_FINAL_EXECUTION_PIPELINE_AUDIT.md` |
| `MT5-001_FINAL_TEST_RESULTS.md` | `INSTITUTIONAL_EA_FINAL_TEST_RESULTS.md` |
| `MT5-001_FORENSIC_REMEDIATION_AND_RUNTIME_VERIFICATION_REPORT.md` | `INSTITUTIONAL_EA_FORENSIC_REMEDIATION_AND_RUNTIME_VERIFICATION_REPORT.md` |
| `MT5-001_FULL_CODEBASE_AUDIT_REPORT.md` | `INSTITUTIONAL_EA_FULL_CODEBASE_AUDIT_REPORT.md` |
| `MT5-001_POST_IMPLEMENTATION_AUDIT_REPORT.md` | `INSTITUTIONAL_EA_POST_IMPLEMENTATION_AUDIT_REPORT.md` |
| `MT5-001_SECOND_INDEPENDENT_AUDIT_REPORT.md` | `INSTITUTIONAL_EA_SECOND_INDEPENDENT_AUDIT_REPORT.md` |
| `MT5-001_STEP_BY_STEP_RUN_AND_TEST_GUIDE.md` | `INSTITUTIONAL_EA_STEP_BY_STEP_RUN_AND_TEST_GUIDE.md` |
| `MT5-001_SYMBOL_WHITELIST_ENFORCEMENT_REPORT.md` | `INSTITUTIONAL_EA_SYMBOL_WHITELIST_ENFORCEMENT_REPORT.md` |
| `MT5-001_US30_ROOT_CAUSE_REPORT.md` | `INSTITUTIONAL_EA_US30_ROOT_CAUSE_REPORT.md` |
| `MT5_001_UNIFIED_RISK_EXECUTION_RECONCILIATION_REPORT.md` | `INSTITUTIONAL_EA_UNIFIED_RISK_EXECUTION_RECONCILIATION_REPORT.md` |
| `MT5_001_UNIVERSAL_ACCOUNT_EXECUTION_FINAL_REPORT.md` | `INSTITUTIONAL_EA_UNIVERSAL_ACCOUNT_EXECUTION_FINAL_REPORT.md` |
| `companion/public/arcadefx-logo.svg` | `companion/public/institutional-ea-logo.svg` |
| `companion/public/brand/arcade-fx-badge.png` | `companion/public/brand/institutional-ea-badge.png` |
| `companion/public/brand/arcade-fx-badge.webp` | `companion/public/brand/institutional-ea-badge.webp` |
| `companion/public/brand/arcade-fx-mark-128.png` | `companion/public/brand/institutional-ea-mark-128.png` |
| `companion/public/brand/arcade-fx-mark-128.webp` | `companion/public/brand/institutional-ea-mark-128.webp` |
| `companion/public/brand/arcade-fx-mark-36.png` | `companion/public/brand/institutional-ea-mark-36.png` |
| `companion/public/brand/arcade-fx-mark-36.webp` | `companion/public/brand/institutional-ea-mark-36.webp` |
| `companion/public/brand/arcade-fx-mark-64.png` | `companion/public/brand/institutional-ea-mark-64.png` |
| `companion/public/brand/arcade-fx-mark-64.webp` | `companion/public/brand/institutional-ea-mark-64.webp` |
| `companion/public/brand/arcade-fx-mark.png` | `companion/public/brand/institutional-ea-mark.png` |
| `companion/public/brand/arcade-fx-mark.webp` | `companion/public/brand/institutional-ea-mark.webp` |
| `companion/public/brand/arcade-fx-wordmark.png` | `companion/public/brand/institutional-ea-wordmark.png` |
| `companion/public/brand/arcade-fx-wordmark.webp` | `companion/public/brand/institutional-ea-wordmark.webp` |
| `companion/public/brand/arcade-fx-wordmark@2x.png` | `companion/public/brand/institutional-ea-wordmark@2x.png` |
| `companion/public/brand/arcade-fx-wordmark@2x.webp` | `companion/public/brand/institutional-ea-wordmark@2x.webp` |
| `companion/public/brand/arcade-fx-wordmark@3x.png` | `companion/public/brand/institutional-ea-wordmark@3x.png` |
| `companion/public/brand/arcade-fx-wordmark@3x.webp` | `companion/public/brand/institutional-ea-wordmark@3x.webp` |
| `deploy/trading_bot.service` | `deploy/institutional_ea.service` |
| `docs/MT5_001_ARCHITECTURE_AND_DEPENDENCY_MAP.md` | `docs/INSTITUTIONAL_EA_ARCHITECTURE_AND_DEPENDENCY_MAP.md` |
| `docs/MT5_001_COMPLETE_TRADING_SYSTEM_FORENSIC_AUDIT.md` | `docs/INSTITUTIONAL_EA_COMPLETE_TRADING_SYSTEM_FORENSIC_AUDIT.md` |
| `docs/MT5_001_GAP_ANALYSIS_AND_RECOMMENDATIONS.md` | `docs/INSTITUTIONAL_EA_GAP_ANALYSIS_AND_RECOMMENDATIONS.md` |
| `docs/MT5_001_MULTI_PAIR_SCALPING_ENGINE_UPGRADE_REPORT.md` | `docs/INSTITUTIONAL_EA_MULTI_PAIR_SCALPING_ENGINE_UPGRADE_REPORT.md` |
| `docs/MT5_001_RISK_MANAGEMENT_AUDIT.md` | `docs/INSTITUTIONAL_EA_RISK_MANAGEMENT_AUDIT.md` |
| `docs/MT5_001_STRATEGY_INVENTORY.md` | `docs/INSTITUTIONAL_EA_STRATEGY_INVENTORY.md` |
| `docs/MT5_001_TECHNICAL_CAPABILITIES.md` | `docs/INSTITUTIONAL_EA_TECHNICAL_CAPABILITIES.md` |
| `docs/MT5_001_TRADING_DECISION_ENGINE.md` | `docs/INSTITUTIONAL_EA_TRADING_DECISION_ENGINE.md` |
| `docs/arcadefx_coach_prompt.md` | `docs/institutional_ea_coach_prompt.md` |
| `docs/arcadefx_pairing_guide.md` | `docs/institutional_ea_pairing_guide.md` |
| `reports/algovistra_backtest_report.md` | `reports/institutional_ea_backtest_report.md` |
| `scripts/run_algovistra_backtest.py` | `scripts/run_institutional_ea_backtest.py` |
| `tests/test_algovistra_skills.py` | `tests/test_institutional_ea_skills.py` |

---

## 4. Intentionally Not Renamed

In accordance with the Safety Rules, the following items were intentionally left unchanged so external cloud API/webhook calls, stored broker trade attribution, and third-party platform integrations continue to work without breakage:

| Identifier / Value | Locations | Reason Not Renamed |
| :--- | :--- | :--- |
| `https://arcadefx.live/api/v1`<br>`https://www.arcadefx.live/api/v1`<br>`https://www.arcadefx.live/api/v1/bot/pairing/claim`<br>`https://arcadefx.live/api/v1/bot/pairing/claim` | `.env.example`, `agent/mt5_bot_agent.py`, `companion/electron/main.cjs`, `companion/src/App.tsx`, `companion/src/components/OnboardingWizard.tsx`, `companion/src/services/ipc.ts`, `config/settings.json`, `docs/desktop_companion_audit.md`, `docs/desktop_companion_guide.md`, `tests/test_mt5_bot_agent.py`, and backup snapshots in `backups/` | External cloud API / webhook endpoint URL not hosted in or controlled by this repository. Preserved so outbound HTTPS device pairing and telemetry requests continue to reach the live server without DNS/HTTP failure. |
| `100101` / `100001` (`InpMagicNumber` / `magic_number`) | `mql5/Experts/PythonBridgeEA.mq5`, `config/settings.json`, `companion/electron/main.cjs`, `companion/service/api/server.py` | Numeric MT5 Expert Advisor Magic Numbers used to reconcile ownership of existing open positions and historical trades on broker accounts. |
| `PythonBridgeEA.mq5` & sidecar binary names (`mt5_bridge_server`, `mt5_trading_engine`, `mt5_bot_agent`, `mt5_control_service`) | `mql5/Experts/PythonBridgeEA.mq5`, `companion/packaging/build_sidecars.py`, `companion/electron/main.cjs`, `tests/test_companion_supervisor.py` | Functional MQL5 bridge Expert Advisor filename and PyInstaller sidecar process names (`mt5` refers to the third-party MetaTrader 5 platform) expected by existing MT5 chart profiles, process watchdogs, and sidecar packaging tests. |
| Third-party packages & platform names (`MetaTrader5`, `MetaQuotes`, `lucide-react`, `react`, `electron`, `tauri`, `vite`, `tailwindcss`) | `requirements.txt`, `agent/requirements.txt`, `companion/package.json`, `companion/src-tauri/Cargo.toml` | Third-party libraries, dependencies, and external trading terminal platform names. |

---

## 5. Needs New Artwork

No replacement image assets were provided. In accordance with Phase 2 Rule 4, the image files below were renamed to match the `institutional-ea` file naming convention and all alt attributes, titles, and code references were updated to `Institutional EA`, but the binary/embedded bitmap graphics themselves still visually contain the legacy logo mark or wordmark and require new artwork from a designer:

1. `companion/public/institutional-ea-logo.svg` (SVG wrapper ids updated to `institutional-ea-candles` and `institutional-ea-wordmark`, but contains an embedded base64 PNG `<image>` layer with the legacy wordmark graphic)
2. `companion/public/brand/institutional-ea-badge.png`
3. `companion/public/brand/institutional-ea-badge.webp`
4. `companion/public/brand/institutional-ea-mark.png`
5. `companion/public/brand/institutional-ea-mark.webp`
6. `companion/public/brand/institutional-ea-mark-36.png`
7. `companion/public/brand/institutional-ea-mark-36.webp`
8. `companion/public/brand/institutional-ea-mark-64.png`
9. `companion/public/brand/institutional-ea-mark-64.webp`
10. `companion/public/brand/institutional-ea-mark-128.png`
11. `companion/public/brand/institutional-ea-mark-128.webp`
12. `companion/public/brand/institutional-ea-wordmark.png`
13. `companion/public/brand/institutional-ea-wordmark.webp`
14. `companion/public/brand/institutional-ea-wordmark@2x.png`
15. `companion/public/brand/institutional-ea-wordmark@2x.webp`
16. `companion/public/brand/institutional-ea-wordmark@3x.png`
17. `companion/public/brand/institutional-ea-wordmark@3x.webp`
18. `companion/public/brand/companion-icon.png`
19. `companion/electron/icon.png`
20. `companion/resources/icon.ico`
21. `companion/resources/icon.png`
