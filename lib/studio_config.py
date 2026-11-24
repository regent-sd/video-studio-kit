"""Settings and brands for every studio tool.

Every script in the kit reads its paths, brand colours and fonts from here, so nothing
about one person or one brand is written into the code.

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "lib"))  # depth to the kit root
    import studio_config as sc

    sc.content_root()            # Path to the shoots folder
    b = sc.brand()               # the default brand (or sc.brand("my-brand"))
    sc.color(b, "accent")        # (r, g, b)
    sc.hex_color(b, "accent")    # "#C8642D"
    sc.font(b, "caption")        # (path, index) for PIL.ImageFont.truetype(path, size, index=index)
    sc.voice()                   # VoiceStudio settings

Settings come from `studio.json` at the kit root, laid over `studio.example.json`, so a
missing key falls back to the example's value. Keys starting with "_" are notes for people.
Set STUDIO_CONFIG=/path/to/other.json to use a different settings file (tests do this).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

KIT_ROOT = Path(__file__).resolve().parents[1]
BRANDS_DIR = KIT_ROOT / "brands"
RULES_DIR = KIT_ROOT / "rules"

_PATH_KEYS = {"content_root", "sound_library", "music_library", "asset_library_dir"}

# Fonts every Mac has. A brand can name one of these instead of shipping a font file.
# Each is (file, index inside a .ttc collection).
SYSTEM_FONTS: dict[str, tuple[str, int]] = {
    "SF Pro": ("/System/Library/Fonts/SFNS.ttf", 0),
    "SF Pro Rounded": ("/System/Library/Fonts/SFNSRounded.ttf", 0),
    "SF Mono": ("/System/Library/Fonts/SFNSMono.ttf", 0),
    "New York": ("/System/Library/Fonts/NewYork.ttf", 0),
    "New York Italic": ("/System/Library/Fonts/NewYorkItalic.ttf", 0),
    "Avenir Next Bold": ("/System/Library/Fonts/Avenir Next.ttc", 0),
    "Avenir Next Demi Bold": ("/System/Library/Fonts/Avenir Next.ttc", 2),
    "Avenir Next Medium": ("/System/Library/Fonts/Avenir Next.ttc", 5),
    "Avenir Next Heavy": ("/System/Library/Fonts/Avenir Next.ttc", 8),
    "Avenir Next Condensed Heavy": ("/System/Library/Fonts/Avenir Next Condensed.ttc", 8),
    "Avenir Next Condensed Bold": ("/System/Library/Fonts/Avenir Next Condensed.ttc", 0),
    "Georgia": ("/System/Library/Fonts/Supplemental/Georgia.ttf", 0),
    "Georgia Bold": ("/System/Library/Fonts/Supplemental/Georgia Bold.ttf", 0),
    "Didot": ("/System/Library/Fonts/Supplemental/Didot.ttc", 0),
    "Baskerville": ("/System/Library/Fonts/Supplemental/Baskerville.ttc", 0),
    "Hoefler Text": ("/System/Library/Fonts/Supplemental/Hoefler Text.ttc", 0),
    "American Typewriter": ("/System/Library/Fonts/Supplemental/AmericanTypewriter.ttc", 0),
    "Menlo": ("/System/Library/Fonts/Menlo.ttc", 0),
}

# Used when a brand leaves a colour or font out.
DEFAULT_COLORS = {
    "background": "#F6F3EE",
    "surface": "#FFFFFF",
    "text": "#1E1E1E",
    "muted": "#8A8A8A",
    "accent": "#FFD60A",
    "highlight": "#FFE88A",
    "good": "#28BE69",
    "bad": "#FF3B30",
    "dark": "#0B0C0F",
    "dark_surface": "#1E2026",
    "on_dark": "#FFFFFF",
}
DEFAULT_FONTS = {
    "title": "SF Pro",
    "heading": "SF Pro",
    "caption": "Avenir Next Condensed Heavy",
    "number": "SF Pro",
    "body": "Avenir Next Medium",
}


def _expand(p: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(p)))


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def settings_file() -> Path:
    """studio.json at the kit root, or the file named by $STUDIO_CONFIG (handy for tests)."""
    env = os.environ.get("STUDIO_CONFIG")
    return _expand(env) if env else KIT_ROOT / "studio.json"


def has_settings() -> bool:
    """True once studio.json exists (setup has run)."""
    return settings_file().exists()


def load() -> dict:
    """The settings, studio.json over studio.example.json, with paths expanded."""
    cfg = json.loads((KIT_ROOT / "studio.example.json").read_text())
    own = settings_file()
    if own.exists():
        cfg = _merge(cfg, json.loads(own.read_text()))
    for k in _PATH_KEYS:
        if cfg.get(k):
            cfg[k] = str(_expand(cfg[k]))
    cfg["asset_roots"] = [str(_expand(p)) for p in cfg.get("asset_roots") or []]
    return cfg


def get(key: str, default=None):
    return load().get(key, default)


def path(key: str) -> Path:
    """A path setting (content_root, sound_library, music_library, asset_library_dir)."""
    v = load().get(key)
    if not v:
        raise KeyError(f"studio.json has no '{key}'. Run the setup (START-HERE.md) or add it.")
    return Path(v)


def content_root() -> Path:
    return path("content_root")


def owner(default: str = "you") -> str:
    return (load().get("owner") or "").strip() or default


def voice() -> dict:
    return dict(load().get("voice") or {})


# ---------- brands ----------

def list_brands() -> list[str]:
    return sorted(p.name for p in BRANDS_DIR.iterdir() if (p / "brand.json").exists())


def brand(slug: str | None = None) -> dict:
    """A brand's settings with 'dir' (its folder) added. None = the default brand."""
    slug = slug or load().get("default_brand") or "example-brand"
    d = BRANDS_DIR / slug
    f = d / "brand.json"
    if not f.exists():
        raise FileNotFoundError(f"No brand '{slug}' (looked for {f}). Brands: {', '.join(list_brands()) or 'none'}")
    b = json.loads(f.read_text())
    b["dir"] = str(d)
    b.setdefault("slug", slug)
    b["colors"] = {**DEFAULT_COLORS, **(b.get("colors") or {})}
    b["fonts"] = {**DEFAULT_FONTS, **(b.get("fonts") or {})}
    return b


def hex_color(b: dict, role: str) -> str:
    c = (b.get("colors") or {}).get(role) or DEFAULT_COLORS.get(role) or "#FF00FF"
    return c if c.startswith("#") else "#" + c


def color(b: dict, role: str, alpha: int | None = None) -> tuple:
    h = hex_color(b, role).lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb + (alpha,) if alpha is not None else rgb


def font(b: dict, role: str) -> tuple[str, int]:
    """(file, index) for a font role: title, heading, caption, number, body.

    A brand's font may be a system font name (see SYSTEM_FONTS), a file in the brand's
    fonts/ folder ("fonts/MyFont-Bold.otf"), or {"file": "...", "index": 0}.
    Falls back to the default for that role if the file is missing.
    """
    spec = (b.get("fonts") or {}).get(role) or DEFAULT_FONTS.get(role, "SF Pro")
    for candidate in (spec, DEFAULT_FONTS.get(role, "SF Pro"), "SF Pro"):
        r = _resolve_font(b, candidate)
        if r:
            return r
    return SYSTEM_FONTS["SF Pro"]


def _resolve_font(b: dict, spec) -> tuple[str, int] | None:
    index = 0
    if isinstance(spec, dict):
        index = int(spec.get("index", 0))
        spec = spec.get("file") or spec.get("name") or ""
    if not spec:
        return None
    if spec in SYSTEM_FONTS:
        f, i = SYSTEM_FONTS[spec]
        return (f, i) if Path(f).exists() else None
    for base in (Path(b.get("dir", BRANDS_DIR)), KIT_ROOT):
        p = (base / spec).expanduser()
        if p.exists():
            return str(p), index
    p = _expand(spec)
    return (str(p), index) if p.exists() else None


def logo(b: dict) -> Path | None:
    f = b.get("logo")
    if not f:
        return None
    p = Path(b["dir"]) / f
    return p if p.exists() else None


# ---------- house rules ----------

def rules_path() -> Path:
    """The house rules Claude follows (rules/house-rules.md, made at setup)."""
    return RULES_DIR / "house-rules.md"


if __name__ == "__main__":
    import pprint
    print("kit:", KIT_ROOT)
    print("settings file:", "studio.json" if has_settings() else "studio.example.json only (run setup)")
    pprint.pprint({k: v for k, v in load().items() if not k.startswith("_")})
    print("brands:", list_brands())
    b = brand()
    print("default brand:", b["name"], {r: font(b, r) for r in DEFAULT_FONTS})
