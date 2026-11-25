#!/usr/bin/env python3
"""
Generate all cross-platform Institutional EA brand assets from the single canonical source image:
    assets/brand/institutional-ea-logo-source.jpg

Platforms covered:
  - Centralized Brand Master (assets/brand/)
  - Web Application & PWA (apps/web/public/)
  - Desktop Companion: Windows & macOS Electron + NSIS + DMG + Tauri (companion/)
  - Mobile Application: Android & iOS Expo (apps/mobile/assets/)
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import struct
from pathlib import Path
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_PATH = REPO_ROOT / "assets" / "brand" / "institutional-ea-logo-source.jpg"
BG_BLACK = (0, 0, 0)
BG_BLACK_RGBA = (0, 0, 0, 255)


def load_canonical_source() -> Image.Image:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(f"Canonical logo source not found: {SOURCE_PATH}")
    return Image.open(SOURCE_PATH).convert("RGB")


def fit_on_square(
    src: Image.Image,
    size: int,
    fill_ratio: float = 0.88,
    bg_color: tuple[int, int, int] = BG_BLACK,
    rgba: bool = True,
) -> Image.Image:
    """
    Place `src` centered on a square canvas of `size x size` preserving exact aspect ratio.
    `fill_ratio` controls the maximum dimension of the artwork relative to `size`.
    """
    max_dim = max(1, int(round(size * fill_ratio)))
    w, h = src.size
    scale = min(max_dim / w, max_dim / h)
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))

    resized = src.resize((new_w, new_h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), bg_color)
    offset_x = (size - new_w) // 2
    offset_y = (size - new_h) // 2
    canvas.paste(resized, (offset_x, offset_y))
    return canvas.convert("RGBA") if rgba else canvas


def apply_rounded_squircle_mask(img_rgba: Image.Image, radius_ratio: float = 0.22) -> Image.Image:
    """Apply a crisp antialiased rounded-rectangle alpha mask (used for macOS/desktop icon aesthetic)."""
    size = img_rgba.size[0]
    scale = 4
    hi = size * scale
    radius = int(round(hi * radius_ratio))
    mask = Image.new("L", (hi, hi), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), (hi - 1, hi - 1)], radius=radius, fill=255)
    mask = mask.resize((size, size), Image.Resampling.LANCZOS)
    out = img_rgba.copy()
    out.putalpha(mask)
    return out


def save_icns(src: Image.Image, out_path: Path) -> None:
    """
    Write a standards-compliant Apple ICNS container with PNG-encoded icon chunks.
    macOS 10.7+ natively supports PNG chunks for all modern Retina and standard sizes.
    """
    # Standard macOS icon chunk types -> pixel sizes
    chunks_spec = [
        (b"icp4", 16),
        (b"icp5", 32),
        (b"icp6", 64),
        (b"ic07", 128),
        (b"ic08", 256),
        (b"ic09", 512),
        (b"ic10", 1024),
    ]

    entries: list[bytes] = []
    for ostype, px in chunks_spec:
        # macOS Big Sur+ icons sit cleanly inside a subtle ~82% squircle canvas
        inner = fit_on_square(src, px, fill_ratio=0.86, rgba=True)
        rounded = apply_rounded_squircle_mask(inner, radius_ratio=0.22)
        buf = io.BytesIO()
        rounded.save(buf, format="PNG", optimize=True)
        png_bytes = buf.getvalue()
        entries.append(ostype + struct.pack(">I", 8 + len(png_bytes)) + png_bytes)

    body = b"".join(entries)
    total_len = 8 + len(body)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(b"icns" + struct.pack(">I", total_len) + body)


def save_ico(src: Image.Image, out_path: Path, sizes: list[int] | None = None) -> None:
    """Write a multi-resolution Windows ICO file."""
    if sizes is None:
        sizes = [16, 24, 32, 48, 64, 128, 256]
    base = fit_on_square(src, 256, fill_ratio=0.90, rgba=True)
    rounded = apply_rounded_squircle_mask(base, radius_ratio=0.18)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rounded.save(out_path, format="ICO", sizes=[(s, s) for s in sizes])


def save_svg_wrapper(png_img: Image.Image, out_path: Path) -> None:
    """Write a clean 64x64 SVG embedding the official raster logo so legacy SVG references show the official brand."""
    buf = io.BytesIO()
    png_img.save(buf, format="PNG", optimize=True)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">\n'
        '  <rect width="64" height="64" rx="14" fill="#000000"/>\n'
        f'  <image href="data:image/png;base64,{b64}" x="4" y="4" width="56" height="56" preserveAspectRatio="xMidYMid meet"/>\n'
        '</svg>\n'
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg, encoding="utf-8")


def save_nsis_header_bmp(src: Image.Image, out_path: Path) -> None:
    """NSIS MUI header bitmap: 150x57 RGB 24-bit BMP with logo cleanly positioned on the right."""
    canvas = Image.new("RGB", (150, 57), BG_BLACK)
    logo = fit_on_square(src, 47, fill_ratio=0.94, rgba=False)
    canvas.paste(logo, (150 - 47 - 6, (57 - 47) // 2))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="BMP")


def save_nsis_sidebar_bmp(src: Image.Image, out_path: Path) -> None:
    """NSIS MUI welcome/finish sidebar bitmap: 164x314 RGB 24-bit BMP with logo centered cleanly."""
    canvas = Image.new("RGB", (164, 314), BG_BLACK)
    logo = fit_on_square(src, 128, fill_ratio=0.92, rgba=False)
    canvas.paste(logo, ((164 - 128) // 2, 42))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="BMP")


def save_mobile_splash(src: Image.Image, out_path: Path) -> None:
    """Mobile splash screen: 1284x2778 RGBA PNG on pure black with centered official logo."""
    canvas = Image.new("RGBA", (1284, 2778), BG_BLACK_RGBA)
    logo = fit_on_square(src, 560, fill_ratio=0.92, rgba=True)
    canvas.paste(logo, ((1284 - 560) // 2, (2778 - 560) // 2))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, format="PNG", optimize=True)


def main() -> None:
    src = load_canonical_source()
    print(f"Loaded canonical logo source: {SOURCE_PATH} ({src.size[0]}x{src.size[1]} {src.mode})")

    # 1. Centralized Brand Master
    master_png = fit_on_square(src, 1024, fill_ratio=0.90, rgba=True)
    master_path = REPO_ROOT / "assets" / "brand" / "institutional-ea-logo.png"
    master_png.save(master_path, format="PNG", optimize=True)
    print(f"  [OK] {master_path.relative_to(REPO_ROOT)}")

    # 2. Web App & PWA (apps/web/public/)
    web_pub = REPO_ROOT / "apps" / "web" / "public"
    web_pub.mkdir(parents=True, exist_ok=True)

    fit_on_square(src, 512, fill_ratio=0.90, rgba=True).save(web_pub / "logo.png", format="PNG", optimize=True)
    fit_on_square(src, 32, fill_ratio=0.92, rgba=True).save(web_pub / "favicon-32x32.png", format="PNG", optimize=True)
    fit_on_square(src, 180, fill_ratio=0.88, rgba=False).save(web_pub / "apple-touch-icon.png", format="PNG", optimize=True)
    fit_on_square(src, 192, fill_ratio=0.88, rgba=True).save(web_pub / "icon-192.png", format="PNG", optimize=True)
    fit_on_square(src, 512, fill_ratio=0.88, rgba=True).save(web_pub / "icon-512.png", format="PNG", optimize=True)
    save_ico(src, web_pub / "favicon.ico", sizes=[16, 24, 32, 48, 64])
    print("  [OK] apps/web/public/{logo.png,favicon.ico,favicon-32x32.png,apple-touch-icon.png,icon-192.png,icon-512.png}")

    # 3. Desktop Companion (Windows & macOS Electron + NSIS + DMG + Tauri)
    comp_pub = REPO_ROOT / "companion" / "public"
    comp_elec = REPO_ROOT / "companion" / "electron"
    comp_res = REPO_ROOT / "companion" / "resources"
    comp_tauri_icons = REPO_ROOT / "companion" / "src-tauri" / "icons"

    fit_on_square(src, 512, fill_ratio=0.90, rgba=True).save(comp_pub / "institutional-ea-logo.png", format="PNG", optimize=True)
    save_ico(src, comp_pub / "favicon.ico", sizes=[16, 24, 32, 48])
    save_svg_wrapper(fit_on_square(src, 128, fill_ratio=0.92, rgba=True), comp_pub / "institutional-ea-logo.svg")

    # Electron BrowserWindow & System Tray icon (rounded square PNG)
    elec_icon = apply_rounded_squircle_mask(fit_on_square(src, 256, fill_ratio=0.90, rgba=True), radius_ratio=0.18)
    elec_icon.save(comp_elec / "icon.png", format="PNG", optimize=True)

    # Electron-builder resources
    res_icon = apply_rounded_squircle_mask(fit_on_square(src, 512, fill_ratio=0.90, rgba=True), radius_ratio=0.18)
    res_icon.save(comp_res / "icon.png", format="PNG", optimize=True)
    save_ico(src, comp_res / "icon.ico")
    save_icns(src, comp_res / "icon.icns")
    save_nsis_header_bmp(src, comp_res / "installerHeader.bmp")
    save_nsis_sidebar_bmp(src, comp_res / "installerSidebar.bmp")

    # Tauri icon bundle (keeps src-tauri/tauri.conf.json fully valid and consistent)
    comp_tauri_icons.mkdir(parents=True, exist_ok=True)
    res_icon.save(comp_tauri_icons / "icon.png", format="PNG", optimize=True)
    apply_rounded_squircle_mask(fit_on_square(src, 32, fill_ratio=0.90, rgba=True), radius_ratio=0.18).save(
        comp_tauri_icons / "32x32.png", format="PNG", optimize=True
    )
    apply_rounded_squircle_mask(fit_on_square(src, 128, fill_ratio=0.90, rgba=True), radius_ratio=0.18).save(
        comp_tauri_icons / "128x128.png", format="PNG", optimize=True
    )
    apply_rounded_squircle_mask(fit_on_square(src, 256, fill_ratio=0.90, rgba=True), radius_ratio=0.18).save(
        comp_tauri_icons / "128x128@2x.png", format="PNG", optimize=True
    )
    shutil.copy2(comp_res / "icon.ico", comp_tauri_icons / "icon.ico")
    shutil.copy2(comp_res / "icon.icns", comp_tauri_icons / "icon.icns")
    print("  [OK] companion/{public,electron,resources,src-tauri/icons} assets generated")

    # 4. Mobile App (Android & iOS Expo)
    mob_assets = REPO_ROOT / "apps" / "mobile" / "assets"
    mob_assets.mkdir(parents=True, exist_ok=True)

    # iOS App Store requires opaque RGB PNG (no alpha channel)
    fit_on_square(src, 1024, fill_ratio=0.84, rgba=False).save(mob_assets / "icon.png", format="PNG", optimize=True)
    # Android adaptive icon foreground: inner ~64% safe zone so circular/squircle masks never crop
    fit_on_square(src, 1024, fill_ratio=0.64, rgba=True).save(mob_assets / "adaptive-icon.png", format="PNG", optimize=True)
    # Splash screen (1284x2778)
    save_mobile_splash(src, mob_assets / "splash.png")
    # In-app UI header logo
    fit_on_square(src, 256, fill_ratio=0.90, rgba=True).save(mob_assets / "logo.png", format="PNG", optimize=True)
    print("  [OK] apps/mobile/assets/{icon.png,adaptive-icon.png,splash.png,logo.png} generated")

    print("All Institutional EA cross-platform brand assets generated successfully.")


if __name__ == "__main__":
    main()
