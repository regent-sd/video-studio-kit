"""Where things are: the kit, its settings, shoots and their Raw clips, work and cache folders, and output names
that never overwrite a file.

Shoots live in the content folder (settings: content_root), one folder per shoot named by the first day filmed:
    <content_root>/<YYYY-MM-DD Title>/Raw/<camera>/<clip>      camera originals, never edited
    <content_root>/<YYYY-MM-DD Title>/Style Tests/              where the builders write new videos
Any subfolder of Raw/ works as a camera folder (Camera, POV, Phone, Screen...).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

KIT = Path(__file__).resolve().parents[2]
STYLES = KIT / "styles"
if str(KIT / "lib") not in sys.path:
    sys.path.insert(0, str(KIT / "lib"))
import studio_config as sc  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def is_video(p) -> bool:
    p = Path(p)
    return p.suffix.lower() in VIDEO_EXT and not p.name.startswith(".")


def _base(style: str, kind: str) -> Path:
    """work/ or cache/ for a style: <settings work_dir>/<style>/<kind>, or styles/<style>/<kind> in the kit
    (both are kept out of git)."""
    root = sc.get("work_dir")
    d = (Path(os.path.expanduser(root)) / style / kind) if root else (STYLES / style / kind)
    d.mkdir(parents=True, exist_ok=True)
    return d


def work_dir(style: str, name: str | None = None) -> Path:
    d = _base(style, "work")
    if name:
        d = d / safe_name(name)
        d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir(style: str = "shared") -> Path:
    return _base(style, "cache")


def safe_name(s: str) -> str:
    keep = "".join(c if c.isalnum() or c in "-_. " else "_" for c in str(s)).strip()
    return keep.replace(" ", "_") or "reel"


def content_root() -> Path:
    return sc.content_root()


def shoot_dir(shoot) -> Path:
    """A shoot folder from its name ("2026-03-14 Kitchen Remodel") or a path."""
    p = Path(os.path.expanduser(str(shoot)))
    if p.is_absolute() or p.exists():
        return p.resolve()
    return content_root() / str(shoot)


def raw_clips(folder) -> list[Path]:
    """Every video under a folder (a shoot's Raw/ when given a shoot), sorted by name."""
    folder = Path(folder)
    if (folder / "Raw").is_dir():
        folder = folder / "Raw"
    return sorted((p for p in folder.rglob("*") if p.is_file() and is_video(p)), key=lambda p: str(p).lower())


def find_clip(name, shoot=None) -> Path:
    """A clip by path, or by file name (or Raw-relative path like "POV/clip.mp4") inside the shoot's Raw/ folders."""
    p = Path(os.path.expanduser(str(name)))
    if p.is_absolute() and p.exists():
        return p
    if shoot is not None:
        sd = shoot_dir(shoot)
        for base in (sd, sd / "Raw"):
            if (base / p).exists():
                return (base / p).resolve()
        hits = [c for c in raw_clips(sd) if c.name == p.name]
        if hits:
            return hits[0]
    if p.exists():
        return p.resolve()
    where = f" in {shoot_dir(shoot)}/Raw" if shoot is not None else ""
    raise FileNotFoundError(f"No clip '{name}'{where}.")


def shoot_of(path) -> Path | None:
    """The shoot folder a file sits in (the folder holding its Raw/), if any."""
    p = Path(path).resolve()
    for parent in p.parents:
        if parent.name == "Raw":
            return parent.parent
    return None


def next_version(folder, stem: str, ext: str = ".mp4") -> Path:
    """<folder>/<stem>_v1.mp4, or the first _vN that doesn't exist yet."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    v = 1
    while (folder / f"{stem}_v{v}{ext}").exists():
        v += 1
    return folder / f"{stem}_v{v}{ext}"


def output_for(name: str, shoot=None, out=None, near=None, folder: str = "Style Tests") -> Path:
    """Where a builder writes its video. --out is used as given but never overwrites; otherwise the shoot's
    Style Tests/<name>_vN.mp4 (the shoot from `shoot`, or the shoot the clip `near` sits in), or the work folder."""
    if out:
        o = Path(os.path.expanduser(str(out))).resolve()
        if o.exists():
            raise SystemExit(f"{o} already exists. Builders never overwrite a file: pick a new name (v2, v3...).")
        o.parent.mkdir(parents=True, exist_ok=True)
        return o
    sd = shoot_dir(shoot) if shoot is not None else (shoot_of(near) if near else None)
    if sd is None:
        return next_version(work_dir("renders"), safe_name(name))
    return next_version(sd / folder, safe_name(name))
