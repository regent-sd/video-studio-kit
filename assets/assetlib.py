"""Settings and small helpers shared by every Asset Library tool (catalog, previews, chunks, tags, moves, browser).

Everything comes from studio.json through lib/studio_config.py:

  asset_roots        the folders to catalog: one or many, local or a synced drive
  asset_library_dir  where the catalog, tags, media facts, move log and snapshots live
  asset_cache_dir    previews, contact sheets and work files (default <asset_library_dir>/cache.nosync)
  asset_never_move   folders or files moves.py must never move or rename (default none)
  asset_exclude      folders left out of the catalog entirely (default none)

Inside the catalog every path is "<root name>/<path inside that root>", where the root name is the root folder's
own name, so files from several roots never clash. Your shoots folder (content_root), the library folder and the
cache are always left out.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "lib"))
import studio_config as sc  # noqa: E402

TO_DELETE = "_To Delete"
CFG = sc.load()


def expand(p) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(p))))


def _norm(p: Path) -> str:
    return os.path.normpath(str(p))


# ---------------------------------------------------------------- roots

def _roots():
    out, seen = [], set()
    for raw in CFG.get("asset_roots") or []:
        p = Path(_norm(expand(raw)))
        label = p.name or "root"
        if label in seen:                       # two roots with the same folder name: add the parent's name
            label = f"{label} ({p.parent.name or 'root'})"
            n = 2
            while label in seen:
                label, n = f"{p.name} ({n})", n + 1
        seen.add(label)
        out.append((label, p))
    return out


ROOTS: list[tuple[str, Path]] = _roots()
ROOT_BY_LABEL = dict(ROOTS)

LIB = expand(CFG.get("asset_library_dir") or "~/Movies/Video Studio/_Asset Library")
CACHE = expand(CFG["asset_cache_dir"]) if CFG.get("asset_cache_dir") else LIB / "cache.nosync"

CATALOG, CSV_FILE = LIB / "asset-catalog.json", LIB / "asset-catalog.csv"
TAGS_DIR, MEDIA_FILE = LIB / "tags", LIB / "media.json"
MOVE_LOG, SNAPS, PLANS = LIB / "move-log.csv", LIB / "snapshots", LIB / "plans"

THUMBS, SHEETS, CHUNKS = CACHE / "thumbs", CACHE / "sheets", CACHE / "chunks"
WORK, REVIEW, REFERENCE = CACHE / "tags-work", CACHE / "tags-review", CACHE / "reference"
HASHES, BIN, TMP = CACHE / "hashes.json", CACHE / "bin" / "render", CACHE / "tmp"
LOG, STATE, LOCK = CACHE / "previews.log", CACHE / "run-state.json", CACHE / "previews.lock"
BUNDLE, LAYOUT = CACHE / "bundle", CACHE / "sprite-layout.json"


def need_roots():
    if not ROOTS:
        sys.exit("No asset_roots in studio.json yet. Add the folders you want catalogued, e.g.\n"
                 '  "asset_roots": ["~/Pictures/Brand Photos", "~/Documents/Marketing"]\n'
                 "then run the scan again (assets/README.md, 'Set it up for your folders').")


def to_disk(cpath: str) -> Path:
    """Catalog path -> the file or folder on disk."""
    label, _, rest = cpath.partition("/")
    if label not in ROOT_BY_LABEL:
        raise KeyError(f"{cpath!r} doesn't start with a root name ({', '.join(ROOT_BY_LABEL) or 'no roots'})")
    return ROOT_BY_LABEL[label] / rest if rest else ROOT_BY_LABEL[label]


def to_catalog(p) -> str | None:
    """A path on disk -> its catalog path, or None when it isn't inside any root."""
    p = Path(_norm(expand(p)))
    for label, root in ROOTS:
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        return label if str(rel) == "." else f"{label}/{rel.as_posix()}"
    return None


def under(p: str, top: str) -> bool:
    return p == top or p.startswith(top + "/")


def _place(s) -> str | None:
    """A never-move or exclude entry -> a catalog path. Accepts an absolute path, '<root name>/sub', or, when there
    is only one root, a path inside it."""
    s = str(s).strip().rstrip("/")
    if not s:
        return None
    if s.startswith(("/", "~", "$")):
        return to_catalog(s)
    if s.split("/", 1)[0] in ROOT_BY_LABEL:
        return s
    if len(ROOTS) == 1:
        return f"{ROOTS[0][0]}/{s}"
    return s


NEVER_MOVE = [p for p in (_place(x) for x in CFG.get("asset_never_move") or []) if p]


def _excluded():
    """Absolute folders the walk skips, and their catalog paths (for moves.py to protect)."""
    disk = set()
    for x in CFG.get("asset_exclude") or []:
        s = str(x).strip()
        if not s:
            continue
        if s.startswith(("/", "~", "$")):
            disk.add(_norm(expand(s)))
        else:
            c = _place(s)
            try:
                disk.add(_norm(to_disk(c)))
            except KeyError:
                pass
    for p in (LIB, CACHE):
        disk.add(_norm(p))
    if CFG.get("content_root"):
        disk.add(_norm(expand(CFG["content_root"])))
    return disk


EXCLUDED_DISK = _excluded()
EXCLUDED = sorted(c for c in (to_catalog(p) for p in EXCLUDED_DISK) if c and "/" in c)


def locked(cpath: str) -> bool:
    return any(under(cpath, x) for x in NEVER_MOVE)


def in_to_delete(cpath: str) -> bool:
    """True for a '_To Delete' folder and anything inside one, anywhere below a root."""
    return TO_DELETE in cpath.split("/")[1:]


def short_hash(s: str, n: int = 4) -> str:
    return hashlib.sha1(s.encode()).hexdigest()[:n]


def icloud_warning(p: Path) -> str | None:
    """iCloud's 'Optimize Mac Storage' pushes files in Documents and Desktop online; a folder ending in .nosync is skipped."""
    home = Path.home()
    for synced in (home / "Documents", home / "Desktop", home / "Library" / "Mobile Documents"):
        try:
            Path(_norm(p)).relative_to(synced)
        except ValueError:
            continue
        if not any(part.endswith(".nosync") for part in Path(_norm(p)).parts):
            return (f"The cache {p} is inside {synced.name}, which iCloud may sync and push online. "
                    "Set asset_cache_dir to a folder ending in .nosync, or outside Documents and Desktop.")
    return None


# ---------------------------------------------------------------- files

def atomic_write(path: Path, text: str, encoding="utf-8"):
    """Temp file in the same folder, then rename: safe on synced drives and if the script is stopped."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def load_json(p, default):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def load_catalog() -> dict:
    if not CATALOG.exists():
        sys.exit(f"No catalog yet at {CATALOG}. Run: .venv/bin/python assets/catalog.py scan")
    return json.loads(CATALOG.read_text())


def key_of(a: dict) -> str:
    """Previews, media facts and tags belong to the content: the md5, or the file's id when it has none."""
    return a.get("md5") or a["id"]


# ---------------------------------------------------------------- command lines

def opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        val = args[i + 1] if i + 1 < len(args) else default
        del args[i:i + 2]
        return val
    return default


def flag(args, name) -> bool:
    if name in args:
        args.remove(name)
        return True
    return False


def gb(n) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e8 else f"{n / 1e6:.1f} MB"


# ---------------------------------------------------------------- tools and fonts

def tool(name: str) -> str | None:
    """ffmpeg / ffprobe: the one on PATH, else Homebrew's ffmpeg-full."""
    for p in (shutil.which(name), f"/opt/homebrew/opt/ffmpeg-full/bin/{name}", f"/opt/homebrew/bin/{name}",
              f"/usr/local/bin/{name}"):
        if p and os.path.exists(p):
            return p
    return None


def ui_font(size: int, bold: bool = False):
    """A plain system font for contact sheets (not a brand font: these are working sheets, never published)."""
    from PIL import ImageFont
    for name in (("Avenir Next Bold", "SF Pro") if bold else ("Avenir Next Medium", "SF Pro")):
        f, i = sc.SYSTEM_FONTS[name]
        try:
            return ImageFont.truetype(f, size, index=i)
        except OSError:
            continue
    return ImageFont.load_default()


def brand_name() -> str:
    try:
        return sc.brand().get("name") or ""
    except (FileNotFoundError, ValueError):
        return ""
