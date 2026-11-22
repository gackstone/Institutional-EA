"""
Cross-Platform Python Sidecar Packaging Script.
Bundles run_bridge_server.py, start_bot.py, and mt5_bot_agent.py into standalone frozen
sidecars for Electron and Tauri using PyInstaller.

Output sidecars:
- companion/resources/bin/mt5_bridge_server.exe
- companion/resources/bin/mt5_trading_engine.exe
- companion/resources/bin/mt5_bot_agent.exe
"""

import os
import sys
import shutil
import platform
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
COMPANION_DIR = PROJECT_ROOT / "companion"
RESOURCES_BIN_DIR = COMPANION_DIR / "resources" / "bin"
TAURI_BIN_DIR = COMPANION_DIR / "src-tauri" / "binaries"
DIST_DIR = COMPANION_DIR / "packaging" / "dist"
BUILD_DIR = COMPANION_DIR / "packaging" / "build"

RESOURCES_BIN_DIR.mkdir(parents=True, exist_ok=True)
TAURI_BIN_DIR.mkdir(parents=True, exist_ok=True)


def get_target_triple():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system == "windows":
        arch = "x86_64" if machine in ["amd64", "x86_64"] else "i686"
        return f"{arch}-pc-windows-msvc"
    elif system == "darwin":
        arch = "aarch64" if machine in ["arm64", "aarch64"] else "x86_64"
        return f"{arch}-apple-darwin"
    elif system == "linux":
        arch = "aarch64" if machine in ["arm64", "aarch64"] else "x86_64"
        return f"{arch}-unknown-linux-gnu"
    return "unknown"


def build_sidecar(script_path: Path, output_name: str, triple: str):
    ext = ".exe" if platform.system() == "Windows" else ""
    target_exe = f"{output_name}{ext}"
    res_target = RESOURCES_BIN_DIR / target_exe
    tauri_target = TAURI_BIN_DIR / f"{output_name}-{triple}{ext}"

    print(f"[*] Packaging {script_path.name} -> {target_exe}...")

    # Data separation syntax
    sep = ";" if platform.system() == "Windows" else ":"
    config_data = f"{PROJECT_ROOT / 'config'}{sep}config"
    mql5_data = f"{PROJECT_ROOT / 'mql5'}{sep}mql5"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
        "--specpath", str(COMPANION_DIR / "packaging"),
        "--paths", str(PROJECT_ROOT),
        "--add-data", config_data,
        "--add-data", mql5_data,
        "--hidden-import", "MetaTrader5",
        "--hidden-import", "dotenv",
        "--hidden-import", "numpy",
        "--hidden-import", "requests",
        "--hidden-import", "src",
        "--hidden-import", "src.core",
        "--hidden-import", "src.data",
        "--hidden-import", "src.smc",
        "--hidden-import", "src.regime",
        "--hidden-import", "src.risk",
        "--hidden-import", "src.execution",
        "--hidden-import", "src.monitoring",
        "--hidden-import", "src.notifications",
        "--hidden-import", "src.learning",
        "--hidden-import", "src.manual_mgmt",
        "--hidden-import", "src.broker_adaptation",
        "--hidden-import", "companion",
        "--hidden-import", "companion.database",
        "--hidden-import", "companion.service",
        "--name", output_name,
        str(script_path)
    ]

    try:
        subprocess.check_call(cmd, cwd=str(PROJECT_ROOT))
        built_file = DIST_DIR / target_exe
        if built_file.exists():
            shutil.copy2(built_file, res_target)
            print(f"[+] Successfully copied to {res_target}")
            unpacked_bin = COMPANION_DIR / "release" / "win-unpacked" / "resources" / "bin"
            if unpacked_bin.exists():
                shutil.copy2(built_file, unpacked_bin / target_exe)
                print(f"[+] Successfully copied to {unpacked_bin / target_exe}")
            # Also copy to tauri binaries directory with target triple
            shutil.copy2(built_file, tauri_target)
            print(f"[+] Successfully copied to {tauri_target}")
            return True
    except Exception as e:
        print(f"[-] Packaging error for {output_name}: {e}")
        return False
    return False


def main():
    triple = get_target_triple()
    print(f"Target Triple: {triple}")
    print(f"Project Root: {PROJECT_ROOT}")

    services = [
        (PROJECT_ROOT / "scripts" / "run_bridge_server.py", "mt5_bridge_server"),
        (PROJECT_ROOT / "scripts" / "start_bot.py", "mt5_trading_engine"),
        (PROJECT_ROOT / "agent" / "mt5_bot_agent.py", "mt5_bot_agent"),
        (COMPANION_DIR / "service" / "main.py", "mt5_control_service"),
    ]

    success_count = 0
    for script, name in services:
        if script.exists():
            if build_sidecar(script, name, triple):
                success_count += 1
        else:
            print(f"[-] Missing script: {script}")

    print(f"[*] Sidecar packaging complete: {success_count}/{len(services)} built successfully.")
    return 0 if success_count == len(services) else 1


if __name__ == "__main__":
    sys.exit(main())
