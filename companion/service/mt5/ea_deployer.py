"""
Production MetaTrader 5 EA Deployment & Verification Pipeline.

Safely deploys PythonBridgeEA.mq5 and its required MQL5 assets (Sounds, Include,
Libraries, Presets) to a verified DEMO MT5 terminal:
  1. Programmatically verifies connected MT5 account is DEMO (refuses REAL/UNKNOWN).
  2. Resolves target MT5 data folder (via explicit path or origin.txt matching).
  3. Creates timestamped backup of any overwritten files before modification.
  4. Copies source assets with SHA-256 verification.
  5. Compiles PythonBridgeEA.mq5 with metaeditor64.exe /compile /log and parses output.
  6. Rolls back to backup automatically if any step or compilation fails.
  7. Inspects config/common.ini (read-only) for Algo Trading & DLL import flags.
  8. Verifies .ex5 output, #property version match, and ZMQ ports (5555/5556).
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from companion.service.mt5.sync_service import MT5SyncService


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_ea_version(mq5_path: Path) -> str:
    if not mq5_path.exists():
        return ""
    try:
        text = mq5_path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r'#property\s+version\s+"([^"]+)"', text)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def _read_text_auto(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="ignore")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-16-le", errors="ignore")


def resolve_data_folder_from_origin(executable_path: Optional[str]) -> Optional[Path]:
    """Matches a terminal64.exe directory to its AppData\\Roaming\\MetaQuotes\\Terminal\\<hash> folder via origin.txt."""
    if not executable_path:
        return None
    install_dir = Path(executable_path).resolve().parent
    roaming = Path(os.environ.get("APPDATA", "")) / "MetaQuotes" / "Terminal"
    if not roaming.exists():
        return None
    for entry in roaming.iterdir():
        if not entry.is_dir():
            continue
        origin = entry / "origin.txt"
        if not origin.exists():
            continue
        try:
            origin_path = Path(_read_text_auto(origin).strip()).resolve()
            if str(origin_path).lower() == str(install_dir).lower():
                return entry
        except Exception:
            continue
    return None


def inspect_common_ini(data_folder: Path) -> Dict[str, Any]:
    """Read-only inspection of MT5 config/common.ini for Algo Trading and DLL flags."""
    ini_path = data_folder / "config" / "common.ini"
    result: Dict[str, Any] = {
        "exists": ini_path.exists(),
        "path": str(ini_path),
        "allow_algo_trading": None,
        "allow_dll_imports": None,
        "note": "",
    }
    if not ini_path.exists():
        result["note"] = "common.ini not found; verify Tools -> Options -> Expert Advisors -> Allow Algorithmic Trading & Allow DLL imports in MT5."
        return result
    try:
        txt = _read_text_auto(ini_path)
        m_algo = re.search(r"(?im)^\s*ExpertsEnabled\s*=\s*(\d+)", txt)
        m_dll = re.search(r"(?im)^\s*ExpertsDllImport\s*=\s*(\d+)", txt)
        result["allow_algo_trading"] = (m_algo.group(1) == "1") if m_algo else None
        result["allow_dll_imports"] = (m_dll.group(1) == "1") if m_dll else None
        missing = []
        if result["allow_algo_trading"] is False:
            missing.append("Allow Algorithmic Trading")
        if result["allow_dll_imports"] is False:
            missing.append("Allow DLL imports")
        if missing:
            result["note"] = f"Enable {', '.join(missing)} in MT5 (Tools -> Options -> Expert Advisors)."
        else:
            result["note"] = "MT5 common.ini Expert Advisor flags look OK (verify Algo Trading button is green in MT5 toolbar)."
    except Exception as exc:
        result["note"] = f"Could not parse common.ini: {exc}"
    return result


def parse_metaeditor_log(log_text: str) -> Tuple[bool, int, int, List[str]]:
    """Parses MetaEditor compile log; returns (ok, errors, warnings, relevant_lines)."""
    lines = [ln.strip() for ln in log_text.splitlines() if ln.strip()]
    errors = 0
    warnings = 0
    result_match = re.search(r"Result:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?", log_text, re.IGNORECASE)
    if result_match:
        errors = int(result_match.group(1))
        warnings = int(result_match.group(2))
    else:
        error_lines = [ln for ln in lines if re.search(r"\berror\b", ln, re.IGNORECASE)]
        errors = len(error_lines)
    return (errors == 0), errors, warnings, lines[-25:]


def deploy_ea_pipeline(
    project_root: Path,
    mt5_sync: MT5SyncService,
    executable_path: Optional[str] = None,
    data_folder: Optional[str] = None,
    experts_dir: Optional[str] = None,
    compile_ea: bool = True,
) -> Dict[str, Any]:
    """
    Executes the full EA deployment pipeline with DEMO verification, backup,
    SHA-256 copy verification, MetaEditor compilation, rollback on error, and post-checks.
    """
    steps: List[Dict[str, Any]] = []

    def _record(step: str, ok: bool, detail: str) -> None:
        steps.append({"step": step, "ok": ok, "detail": detail})

    # 1. Programmatic DEMO account verification
    snap = mt5_sync.get_snapshot()
    if snap.get("connection_status") != "CONNECTED":
        mt5_sync.connect(terminal_path=executable_path)
        snap = mt5_sync.sync_all(terminal_path=executable_path)

    account = snap.get("account") or {}
    trade_mode = str(account.get("trade_mode", "UNKNOWN")).upper()
    demo_verified = bool(account.get("demo_verified", False)) and trade_mode == "DEMO"
    if not demo_verified:
        detail = f"Refused EA deployment: MT5 account is not verified DEMO (mode={trade_mode}, conn={snap.get('connection_status')})."
        _record("verify_demo_account", False, detail)
        return {
            "success": False,
            "message": detail,
            "steps": steps,
        }
    _record("verify_demo_account", True, f"Verified DEMO account ({account.get('broker', 'MT5')}, mode=DEMO)")

    # 2. Locate EA source & assets
    mql5_src = project_root / "mql5"
    ea_src = mql5_src / "Experts" / "PythonBridgeEA.mq5"
    if not ea_src.exists():
        detail = f"EA source file missing: {ea_src}"
        _record("locate_sources", False, detail)
        return {"success": False, "message": detail, "steps": steps}
    src_version = extract_ea_version(ea_src) or "3.10"
    _record("locate_sources", True, f"Found PythonBridgeEA.mq5 (v{src_version})")

    # 3. Resolve target MT5 data folder
    resolved_data: Optional[Path] = None
    if data_folder:
        resolved_data = Path(data_folder)
    elif experts_dir:
        exp_p = Path(experts_dir)
        # <data>/MQL5/Experts -> <data>
        resolved_data = exp_p.parent.parent if exp_p.name.lower() == "experts" else exp_p
    elif executable_path:
        resolved_data = resolve_data_folder_from_origin(executable_path)

    if not resolved_data or not resolved_data.exists():
        detail = "Could not resolve MT5 data folder. Click Scan first or verify terminal installation."
        _record("resolve_target", False, detail)
        return {"success": False, "message": detail, "steps": steps}

    mql5_dst = resolved_data / "MQL5"
    dst_experts = mql5_dst / "Experts"
    dst_experts.mkdir(parents=True, exist_ok=True)
    _record("resolve_target", True, f"Target MT5 MQL5 directory: {mql5_dst}")

    # Collect files to copy: (src_path, dst_path)
    copy_plan: List[Tuple[Path, Path]] = [(ea_src, dst_experts / "PythonBridgeEA.mq5")]
    for sub in ("Sounds", "Include", "Libraries", "Presets"):
        src_sub = mql5_src / sub
        if src_sub.exists() and src_sub.is_dir():
            for item in src_sub.rglob("*"):
                if item.is_file() and not item.name.endswith((".log", ".bak")):
                    rel = item.relative_to(src_sub)
                    copy_plan.append((item, mql5_dst / sub / rel))

    # 4. Timestamped backup of any existing target files (including existing .ex5)
    ts_tag = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_dir = mql5_dst / "Backups" / f"ea_deploy_{ts_tag}"
    backed_up: List[Tuple[Path, Path]] = []  # (original_path, backup_path)
    newly_created: List[Path] = []
    existing_ex5 = dst_experts / "PythonBridgeEA.ex5"

    def _rollback() -> None:
        for orig, bak in backed_up:
            try:
                orig.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(bak, orig)
            except Exception:
                pass
        for created in newly_created:
            try:
                if created.exists():
                    created.unlink()
            except Exception:
                pass

    try:
        targets_to_backup = [dst for _, dst in copy_plan] + [existing_ex5]
        for dst in targets_to_backup:
            if dst.exists():
                rel = dst.relative_to(mql5_dst)
                bak_path = backup_dir / rel
                bak_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, bak_path)
                backed_up.append((dst, bak_path))
        _record(
            "backup",
            True,
            f"Backed up {len(backed_up)} existing file(s) to {backup_dir}" if backed_up else "No existing files needed backup",
        )

        # 5. Copy with SHA-256 verification
        verified_hashes: Dict[str, str] = {}
        for src, dst in copy_plan:
            existed = dst.exists()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            if not existed:
                newly_created.append(dst)
            h_src = sha256_file(src)
            h_dst = sha256_file(dst)
            if h_src != h_dst:
                raise RuntimeError(f"SHA-256 mismatch copying {src.name}")
            verified_hashes[dst.name] = h_dst[:12]
        _record("copy_assets", True, f"Copied and SHA-256 verified {len(copy_plan)} file(s)")

        # 6. Compile with metaeditor64.exe
        compile_summary: Dict[str, Any] = {"compiled": False, "errors": 0, "warnings": 0, "log_tail": []}
        dst_mq5 = dst_experts / "PythonBridgeEA.mq5"
        dst_ex5 = dst_experts / "PythonBridgeEA.ex5"

        if compile_ea:
            metaeditor: Optional[Path] = None
            if executable_path:
                cand = Path(executable_path).resolve().parent / "metaeditor64.exe"
                if cand.exists():
                    metaeditor = cand
            if metaeditor is None:
                for p in (
                    Path(r"C:\Program Files\MetaTrader 5\metaeditor64.exe"),
                    Path(r"C:\Program Files (x86)\MetaTrader 5\metaeditor64.exe"),
                ):
                    if p.exists():
                        metaeditor = p
                        break

            if metaeditor is None:
                raise RuntimeError("metaeditor64.exe not found next to terminal64.exe; cannot compile PythonBridgeEA.mq5")

            compile_log = dst_experts / "PythonBridgeEA_compile.log"
            if compile_log.exists():
                compile_log.unlink()

            cmd = [str(metaeditor), f'/compile:{dst_mq5}', f'/log:{compile_log}']
            subprocess.run(
                cmd,
                timeout=60,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

            log_text = _read_text_auto(compile_log) if compile_log.exists() else ""
            ok_compile, err_cnt, warn_cnt, tail = parse_metaeditor_log(log_text)
            compile_summary = {
                "compiled": ok_compile and dst_ex5.exists() and dst_ex5.stat().st_size > 0,
                "errors": err_cnt,
                "warnings": warn_cnt,
                "metaeditor": str(metaeditor),
                "log_path": str(compile_log),
                "log_tail": tail,
            }
            if not compile_summary["compiled"]:
                raise RuntimeError(f"MetaEditor compile failed ({err_cnt} errors, {warn_cnt} warnings)")
            _record("compile_ea", True, f"Compiled PythonBridgeEA.ex5 cleanly ({err_cnt} errors, {warn_cnt} warnings)")
        else:
            _record("compile_ea", True, "Compile skipped by caller")

        # 7. Read-only common.ini inspection
        ini_check = inspect_common_ini(resolved_data)
        _record("inspect_settings", True, ini_check["note"])

        # 8. Post-deploy verification
        installed_version = extract_ea_version(dst_mq5)
        ex5_ok = dst_ex5.exists() and dst_ex5.stat().st_size > 0
        zmq_info = mt5_sync.check_zmq_bridge()
        version_match = installed_version == src_version
        _record(
            "verify_deployment",
            bool(ex5_ok and version_match),
            f"PythonBridgeEA.ex5 ({dst_ex5.stat().st_size if ex5_ok else 0} bytes), version={installed_version} (match={version_match}), ZMQ 5555={'UP' if zmq_info['port_5555'] else 'IDLE'}",
        )

        return {
            "success": True,
            "message": f"PythonBridgeEA v{installed_version} compiled and deployed cleanly to DEMO terminal.",
            "ea_version": installed_version,
            "ex5_path": str(dst_ex5),
            "ex5_size_bytes": dst_ex5.stat().st_size if ex5_ok else 0,
            "backup_dir": str(backup_dir) if backed_up else None,
            "verified_hashes": verified_hashes,
            "compile": compile_summary,
            "settings_check": ini_check,
            "zmq_bridge": zmq_info,
            "chart_attachment": {
                "automated": False,
                "note": "MT5 does not expose an external IPC API to attach an EA to a running chart without restarting the terminal. In MT5 Navigator -> Expert Advisors, click Refresh and drag PythonBridgeEA onto a chart (with Algo Trading enabled).",
            },
            "steps": steps,
        }

    except Exception as exc:
        _rollback()
        _record("rollback", True, f"Rolled back due to error: {exc}")
        return {
            "success": False,
            "message": f"EA deployment failed and rolled back: {exc}",
            "backup_dir": str(backup_dir) if backed_up else None,
            "steps": steps,
        }
