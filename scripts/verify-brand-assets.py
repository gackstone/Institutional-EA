#!/usr/bin/env python3
"""
Institutional EA — Cross-Platform Branding & Version Consistency Validator

Verifies:
  1. Canonical master logo source & generated PNG exist and are valid.
  2. All platform-specific icons, splash screens, and installer bitmaps exist
     with exact required dimensions, formats, and modes (Web, Windows, macOS,
     Android, iOS, Tauri).
  3. Active platform configurations reference the official logo assets.
  4. Active UI entrypoints contain no obsolete placeholder/legacy logo markup.
  5. Application version numbers are synchronized across all packages/platforms.
  6. (--check-builds) Production dist outputs include the expected branding assets.

Exit code 0 on pass; non-zero with clear diagnostics on any failure.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent


class ValidationReport:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.errors: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed.append(msg)

    def fail(self, msg: str) -> None:
        self.errors.append(msg)


def check_image(
    report: ValidationReport,
    rel_path: str,
    expected_size: tuple[int, int] | None = None,
    expected_format: str | None = None,
    expected_modes: tuple[str, ...] | None = None,
    required_ico_sizes: set[int] | None = None,
    required_icns_min_px: int | None = None,
) -> None:
    p = REPO_ROOT / rel_path
    if not p.exists():
        report.fail(f"Missing required branding asset: {rel_path}")
        return
    if p.stat().st_size == 0:
        report.fail(f"Branding asset is empty (0 bytes): {rel_path}")
        return

    try:
        with Image.open(p) as im:
            im.load()
            size = im.size
            fmt = im.format
            mode = im.mode
            info_sizes = im.info.get("sizes", set())
    except Exception as exc:
        report.fail(f"Unreadable image {rel_path}: {exc}")
        return

    if expected_size and size != expected_size:
        report.fail(f"{rel_path}: expected dimensions {expected_size}, got {size}")
        return
    if expected_format and fmt != expected_format:
        report.fail(f"{rel_path}: expected format {expected_format}, got {fmt}")
        return
    if expected_modes and mode not in expected_modes:
        report.fail(f"{rel_path}: expected mode in {expected_modes}, got {mode}")
        return
    if required_ico_sizes:
        present = {s[0] for s in info_sizes}
        missing = required_ico_sizes - present
        if missing:
            report.fail(f"{rel_path}: missing ICO sizes {sorted(missing)} (found {sorted(present)})")
            return
    if required_icns_min_px:
        max_px = max((s[0] * (s[2] if len(s) > 2 else 1) for s in info_sizes), default=0)
        if max_px < required_icns_min_px:
            report.fail(f"{rel_path}: max ICNS resolution {max_px}px < required {required_icns_min_px}px")
            return

    report.ok(f"{rel_path} ({size[0]}x{size[1]} {mode} {fmt})")


def check_required_assets(report: ValidationReport) -> None:
    # Canonical master
    check_image(report, "assets/brand/institutional-ea-logo-source.jpg", expected_format="JPEG", expected_modes=("RGB",))
    check_image(report, "assets/brand/institutional-ea-logo.png", expected_size=(1024, 1024), expected_format="PNG", expected_modes=("RGBA", "RGB"))

    # Web & PWA
    check_image(report, "apps/web/public/logo.png", expected_size=(512, 512), expected_format="PNG")
    check_image(report, "apps/web/public/favicon.ico", expected_format="ICO", required_ico_sizes={16, 32, 48})
    check_image(report, "apps/web/public/favicon-32x32.png", expected_size=(32, 32), expected_format="PNG")
    check_image(report, "apps/web/public/apple-touch-icon.png", expected_size=(180, 180), expected_format="PNG")
    check_image(report, "apps/web/public/icon-192.png", expected_size=(192, 192), expected_format="PNG")
    check_image(report, "apps/web/public/icon-512.png", expected_size=(512, 512), expected_format="PNG")

    # Desktop Companion (Electron + NSIS + DMG)
    check_image(report, "companion/public/institutional-ea-logo.png", expected_size=(512, 512), expected_format="PNG")
    check_image(report, "companion/public/favicon.ico", expected_format="ICO", required_ico_sizes={16, 32, 48})
    check_image(report, "companion/electron/icon.png", expected_size=(256, 256), expected_format="PNG")
    check_image(report, "companion/resources/icon.png", expected_size=(512, 512), expected_format="PNG")
    check_image(report, "companion/resources/icon.ico", expected_format="ICO", required_ico_sizes={16, 32, 48, 128, 256})
    check_image(report, "companion/resources/icon.icns", expected_format="ICNS", required_icns_min_px=1024)
    check_image(report, "companion/resources/installerHeader.bmp", expected_size=(150, 57), expected_format="BMP", expected_modes=("RGB",))
    check_image(report, "companion/resources/installerSidebar.bmp", expected_size=(164, 314), expected_format="BMP", expected_modes=("RGB",))

    # Tauri bundle icons
    check_image(report, "companion/src-tauri/icons/icon.png", expected_size=(512, 512), expected_format="PNG")
    check_image(report, "companion/src-tauri/icons/32x32.png", expected_size=(32, 32), expected_format="PNG")
    check_image(report, "companion/src-tauri/icons/128x128.png", expected_size=(128, 128), expected_format="PNG")
    check_image(report, "companion/src-tauri/icons/128x128@2x.png", expected_size=(256, 256), expected_format="PNG")
    check_image(report, "companion/src-tauri/icons/icon.ico", expected_format="ICO", required_ico_sizes={16, 32, 48, 256})
    check_image(report, "companion/src-tauri/icons/icon.icns", expected_format="ICNS", required_icns_min_px=1024)

    # Mobile (Android & iOS Expo)
    # iOS App Store requires opaque RGB icon (no alpha channel)
    check_image(report, "apps/mobile/assets/icon.png", expected_size=(1024, 1024), expected_format="PNG", expected_modes=("RGB",))
    check_image(report, "apps/mobile/assets/adaptive-icon.png", expected_size=(1024, 1024), expected_format="PNG")
    check_image(report, "apps/mobile/assets/splash.png", expected_size=(1284, 2778), expected_format="PNG")
    check_image(report, "apps/mobile/assets/logo.png", expected_size=(256, 256), expected_format="PNG")


def check_configurations(report: ValidationReport) -> None:
    # 1. Web index.html & manifest
    web_html = (REPO_ROOT / "apps/web/index.html").read_text(encoding="utf-8")
    for needle in ('href="/favicon.ico"', 'href="/favicon-32x32.png"', 'href="/apple-touch-icon.png"', 'href="/manifest.webmanifest"'):
        if needle not in web_html:
            report.fail(f"apps/web/index.html missing expected link: {needle}")
    manifest = json.loads((REPO_ROOT / "apps/web/public/manifest.webmanifest").read_text(encoding="utf-8"))
    icon_srcs = {i.get("src") for i in manifest.get("icons", [])}
    if not {"/icon-192.png", "/icon-512.png"}.issubset(icon_srcs):
        report.fail(f"apps/web/public/manifest.webmanifest missing required icons (found {icon_srcs})")
    else:
        report.ok("apps/web/index.html & manifest.webmanifest references valid")

    # 2. Web App.tsx — must use /logo.png and no legacy IEA text badge
    web_app = (REPO_ROOT / "apps/web/src/App.tsx").read_text(encoding="utf-8")
    if 'src="/logo.png"' not in web_app:
        report.fail("apps/web/src/App.tsx does not reference /logo.png")
    if re.search(r">\s*IEA\s*</span>", web_app):
        report.fail("apps/web/src/App.tsx still contains legacy 'IEA' text badge placeholder")
    else:
        report.ok("apps/web/src/App.tsx uses official /logo.png without legacy placeholders")

    # 3. Companion index.html, fallback.html, App.tsx, SVG wrapper
    comp_html = (REPO_ROOT / "companion/index.html").read_text(encoding="utf-8")
    if "./institutional-ea-logo.png" not in comp_html or "./favicon.ico" not in comp_html:
        report.fail("companion/index.html missing official logo/favicon references")
    if re.search(r">\s*IEA\s*</div>", comp_html):
        report.fail("companion/index.html boot splash still contains legacy 'IEA' text placeholder")
    else:
        report.ok("companion/index.html boot splash & favicon valid")

    comp_svg = (REPO_ROOT / "companion/public/institutional-ea-logo.svg").read_text(encoding="utf-8")
    if "data:image/png;base64," not in comp_svg:
        report.fail("companion/public/institutional-ea-logo.svg does not embed official raster artwork")
    else:
        report.ok("companion/public/institutional-ea-logo.svg embeds official artwork")

    comp_app = (REPO_ROOT / "companion/src/App.tsx").read_text(encoding="utf-8")
    if comp_app.count("./institutional-ea-logo.png") < 2:
        report.fail("companion/src/App.tsx must reference ./institutional-ea-logo.png in both titlebar and sidebar")
    else:
        report.ok("companion/src/App.tsx references official logo in titlebar and sidebar")

    fallback_html = (REPO_ROOT / "companion/electron/fallback.html").read_text(encoding="utf-8")
    if "./icon.png" not in fallback_html:
        report.fail("companion/electron/fallback.html missing ./icon.png branding")
    else:
        report.ok("companion/electron/fallback.html references ./icon.png")

    # 4. Companion package.json electron-builder config
    comp_pkg = json.loads((REPO_ROOT / "companion/package.json").read_text(encoding="utf-8"))
    build_cfg = comp_pkg.get("build", {})
    expected_build_refs = [
        ("win.icon", build_cfg.get("win", {}).get("icon"), "resources/icon.ico"),
        ("mac.icon", build_cfg.get("mac", {}).get("icon"), "resources/icon.icns"),
        ("dmg.icon", build_cfg.get("dmg", {}).get("icon"), "resources/icon.icns"),
        ("nsis.installerIcon", build_cfg.get("nsis", {}).get("installerIcon"), "resources/icon.ico"),
        ("nsis.uninstallerIcon", build_cfg.get("nsis", {}).get("uninstallerIcon"), "resources/icon.ico"),
        ("nsis.installerHeader", build_cfg.get("nsis", {}).get("installerHeader"), "resources/installerHeader.bmp"),
        ("nsis.installerSidebar", build_cfg.get("nsis", {}).get("installerSidebar"), "resources/installerSidebar.bmp"),
    ]
    for label, actual, expected in expected_build_refs:
        if actual != expected:
            report.fail(f"companion/package.json build.{label} = {actual!r}, expected {expected!r}")
    report.ok("companion/package.json electron-builder icon bindings valid")

    # 5. Mobile app.json & RootNavigator.tsx
    mob_cfg = json.loads((REPO_ROOT / "apps/mobile/app.json").read_text(encoding="utf-8")).get("expo", {})
    if mob_cfg.get("icon") != "./assets/icon.png":
        report.fail(f"apps/mobile/app.json expo.icon = {mob_cfg.get('icon')!r}")
    if mob_cfg.get("splash", {}).get("image") != "./assets/splash.png":
        report.fail(f"apps/mobile/app.json expo.splash.image = {mob_cfg.get('splash', {}).get('image')!r}")
    if mob_cfg.get("android", {}).get("adaptiveIcon", {}).get("foregroundImage") != "./assets/adaptive-icon.png":
        report.fail("apps/mobile/app.json expo.android.adaptiveIcon.foregroundImage mismatch")
    mob_nav = (REPO_ROOT / "apps/mobile/src/navigation/RootNavigator.tsx").read_text(encoding="utf-8")
    if "../../assets/logo.png" not in mob_nav:
        report.fail("apps/mobile/src/navigation/RootNavigator.tsx missing official brand logo import")
    else:
        report.ok("apps/mobile/app.json & RootNavigator.tsx branding references valid")


def check_version_consistency(report: ValidationReport) -> None:
    versions: dict[str, str | None] = {
        "package.json": json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8")).get("version"),
        "companion/package.json": json.loads((REPO_ROOT / "companion/package.json").read_text(encoding="utf-8")).get("version"),
        "apps/web/package.json": json.loads((REPO_ROOT / "apps/web/package.json").read_text(encoding="utf-8")).get("version"),
        "apps/mobile/package.json": json.loads((REPO_ROOT / "apps/mobile/package.json").read_text(encoding="utf-8")).get("version"),
        "apps/mobile/app.json (expo.version)": json.loads((REPO_ROOT / "apps/mobile/app.json").read_text(encoding="utf-8")).get("expo", {}).get("version"),
        "apps/mobile/app.json (ios.buildNumber)": json.loads((REPO_ROOT / "apps/mobile/app.json").read_text(encoding="utf-8")).get("expo", {}).get("ios", {}).get("buildNumber"),
        "companion/src-tauri/tauri.conf.json": json.loads((REPO_ROOT / "companion/src-tauri/tauri.conf.json").read_text(encoding="utf-8")).get("version"),
    }
    unique = set(versions.values())
    if len(unique) != 1 or None in unique:
        details = ", ".join(f"{k}={v}" for k, v in versions.items())
        report.fail(f"Version mismatch across platforms: {details}")
    else:
        ver = next(iter(unique))
        report.ok(f"All 7 platform manifests synchronized at version {ver}")


def check_production_builds(report: ValidationReport) -> None:
    web_dist = [
        "apps/web/dist/index.html",
        "apps/web/dist/logo.png",
        "apps/web/dist/favicon.ico",
        "apps/web/dist/favicon-32x32.png",
        "apps/web/dist/apple-touch-icon.png",
        "apps/web/dist/icon-192.png",
        "apps/web/dist/icon-512.png",
        "apps/web/dist/manifest.webmanifest",
    ]
    for rel in web_dist:
        if not (REPO_ROOT / rel).exists():
            report.fail(f"Built web output missing branding asset: {rel}")
    comp_dist = [
        "companion/dist/index.html",
        "companion/dist/institutional-ea-logo.png",
        "companion/dist/institutional-ea-logo.svg",
        "companion/dist/favicon.ico",
    ]
    for rel in comp_dist:
        if not (REPO_ROOT / rel).exists():
            report.fail(f"Built companion output missing branding asset: {rel}")
    if not any("Built " in e for e in report.errors):
        report.ok("Production dist outputs (apps/web/dist & companion/dist) include all branding assets")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Institutional EA cross-platform branding assets & versions.")
    parser.add_argument("--check-builds", action="store_true", help="Also verify built dist/ directories contain branding assets.")
    args = parser.parse_args()

    report = ValidationReport()
    check_required_assets(report)
    check_configurations(report)
    check_version_consistency(report)
    if args.check_builds:
        check_production_builds(report)

    print("=== INSTITUTIONAL EA BRAND ASSET VALIDATION ===")
    print(f"Checks passed: {len(report.passed)}")
    if report.errors:
        print(f"Checks FAILED: {len(report.errors)}")
        for err in report.errors:
            print(f"  [FAIL] {err}")
        return 1

    print("SUCCESS: All cross-platform branding assets, configurations, and versions are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
