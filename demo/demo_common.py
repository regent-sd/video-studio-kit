"""Shared bits for the demo scripts: the clip list, where the demo shoot is, small helpers.

The demo shoot is a normal shoot folder in your content folder, named by the day it was made:
    <content_root>/<YYYY-MM-DD> Demo Shoot/Raw/<camera>/<clip>.mp4
Every demo script finds the newest one by itself, so you can run them on different days.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent
KIT_ROOT = DEMO_DIR.parent
sys.path.insert(0, str(KIT_ROOT / "lib"))
import studio_config as sc  # noqa: E402

CLIPS_FILE = DEMO_DIR / "clips.json"
SCRIPT_FILE = DEMO_DIR / "narration.md"
STOCK_DIR = ".stock"          # inside the shoot: clips as downloaded, when a script replaced the Raw copy
SHOOT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} (.+)$")


def load_clips() -> dict:
    return json.loads(CLIPS_FILE.read_text())


def shoot_title() -> str:
    return load_clips().get("shoot_title") or "Demo Shoot"


def find_shoots(root: Path, title: str) -> list[Path]:
    if not root.is_dir():
        return []
    out = []
    for p in root.iterdir():
        m = SHOOT_RE.match(p.name)
        if p.is_dir() and m and m.group(1) == title:
            out.append(p)
    return sorted(out, key=lambda p: p.name)


def shoot_dir(out: str | None = None, create: bool = False) -> Path:
    """The demo shoot folder: --out if given, else the newest '<date> Demo Shoot' in the content
    folder, else a new one named for today (made only when create is True)."""
    if out:
        p = Path(out).expanduser().resolve()
    else:
        root = sc.content_root()
        title = shoot_title()
        found = find_shoots(root, title)
        p = found[-1] if found else root / f"{_dt.date.today().isoformat()} {title}"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def clip_path(shoot: Path, clip: dict) -> Path:
    return shoot / clip["camera"] / clip["file"]


def stock_path(shoot: Path, clip: dict) -> Path:
    return shoot / STOCK_DIR / clip["file"]


def have_clip(shoot: Path, clip: dict) -> Path | None:
    """The downloaded file if it's there: in .stock once make_narration has voiced it, else in Raw.
    Downloads land under their final name only when complete, so a file there is a whole one
    (or one you saved by hand, which may be a different size than listed)."""
    for p in (stock_path(shoot, clip), clip_path(shoot, clip)):
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def size_note(path: Path, clip: dict) -> str:
    want = int(clip.get("bytes") or 0)
    got = path.stat().st_size
    return "" if not want or got == want else f"{mb(got)}, not the {mb(want)} listed"


def mb(n: int | float) -> str:
    return f"{n / 1_000_000:.1f} MB"


def tool(name: str) -> str | None:
    return shutil.which(name)


def probe(path: Path) -> dict:
    """Duration, size and whether there's sound, from ffprobe. {} if ffprobe is missing or fails."""
    if not tool("ffprobe"):
        return {}
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {}
    d = json.loads(r.stdout or "{}")
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "duration": float(d.get("format", {}).get("duration") or 0),
        "width": v.get("width"),
        "height": v.get("height"),
        "has_video": bool(v),
        "has_audio": any(s.get("codec_type") == "audio" for s in d.get("streams", [])),
    }


def read_script(path: Path = SCRIPT_FILE) -> list[str]:
    """The narration lines: every non-empty line under '## Script' in narration.md, up to the next heading."""
    lines, on = [], False
    for raw in path.read_text().splitlines():
        s = raw.strip()
        if s.startswith("## "):
            on = s[3:].strip().lower() == "script"
            continue
        if on and s and not s.startswith("<!--"):
            lines.append(s)
    if not lines:
        raise SystemExit(f"No lines under '## Script' in {path}.")
    return lines


def words_path(media: Path) -> Path:
    """Transcripts sit next to the file: <file>.words.txt, one 'start-end word' per line (seconds)."""
    return media.with_name(media.name + ".words.txt")


def write_words(media: Path, words: list[tuple[float, float, str]]) -> Path:
    p = words_path(media)
    p.write_text("".join(f"{a:.2f}-{b:.2f} {w}\n" for a, b, w in words))
    return p
