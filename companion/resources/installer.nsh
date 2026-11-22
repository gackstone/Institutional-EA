; Institutional EA — Minimal, Fast & Branded NSIS Installer Customizations (PART B)

; Short, clean strings (fewer words, fast flow)
!define MUI_WELCOMEPAGE_TITLE "Institutional EA"
!define MUI_WELCOMEPAGE_TEXT "Install Institutional EA (DEMO Terminal v1.3).$\r$\n$\r$\nClick Next to install."
!define MUI_FINISHPAGE_TITLE "Done"
!define MUI_FINISHPAGE_TEXT "Institutional EA is ready."
!define MUI_FINISHPAGE_RUN_TEXT "Launch Institutional EA"

!macro customInit
  ; Clean upgrade: automatically remove legacy MT5-001 / MT5-OO1 shortcuts and install directory if present
  Delete "$DESKTOP\MT5-001 Companion.lnk"
  Delete "$DESKTOP\MT5-OO1 Companion.lnk"
  Delete "$SMPROGRAMS\MT5-001 Companion.lnk"
  Delete "$SMPROGRAMS\MT5-OO1 Companion.lnk"
  IfFileExists "$LOCALAPPDATA\Programs\mt5-001-companion\Uninstall MT5-001 Companion.exe" 0 +2
    ExecWait '"$LOCALAPPDATA\Programs\mt5-001-companion\Uninstall MT5-001 Companion.exe" /S'
  IfFileExists "$LOCALAPPDATA\Programs\MT5-OO1 Companion\Uninstall MT5-OO1 Companion.exe" 0 +2
    ExecWait '"$LOCALAPPDATA\Programs\MT5-OO1 Companion\Uninstall MT5-OO1 Companion.exe" /S'
!macroend

!macro customUnInstall
  ; If running interactively (not silent), offer to keep or delete user settings & logs
  IfSilent skip_data_prompt 0
    MessageBox MB_YESNO|MB_ICONQUESTION "Keep your Institutional EA settings and logs?" IDYES skip_data_prompt
    RMDir /r "$LOCALAPPDATA\InstitutionalEA\Institutional EA Companion"
  skip_data_prompt:
!macroend
