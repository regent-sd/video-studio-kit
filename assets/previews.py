#!/usr/bin/env python3
"""Asset Library: a small preview of every file, and contact sheets for the tagging agents.

  .venv/bin/python assets/previews.py run [--kinds photo,graphic,...] [--limit N] [--top "<folder>"] [--retry-errors]
        [--no-scan] [--floor 8] [--wait 20]
        make the missing previews: photos and graphics first, then PDFs, design files, video, audio; smallest first
        within each. Resumable. On a synced drive, reading a file downloads it: the run keeps free disk space above
        --floor GB, waits up to --wait minutes for macOS to free space, and stops cleanly if it doesn't.
  .venv/bin/python assets/previews.py status        coverage by kind and folder, failures by reason, the last run
  .venv/bin/python assets/previews.py sheets [--all] [--no-scan]
        3x3 contact sheets of the files not yet described (--all: every file), batched by folder, for tagging
  .venv/bin/python assets/previews.py reference <name> <folder or file> [...]
        one sheet of the previews under those catalog paths, e.g. your current logos ("current") and retired
        ones ("retired"), for the tagging agents to compare against

One preview per content: <cache>/thumbs/<md5>.jpg (the file's id when it has no md5), 640 px on the long edge, sRGB,
orientation applied, transparency on light grey. Video gets a 2x2 tile of four frames; audio gets its length only.
Facts go to media.json in the library folder (width, height, duration, taken, pages, thumb, preview_error), which
catalog.py scan merges. The renderer is render.swift (compiled once into <cache>/bin/render when swiftc is there);
without it, Pillow and macOS's sips do what they can.
"""
import base64
import datetime as dt
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assetlib as al  # noqa: E402

from PIL import Image, ImageDraw, ImageOps  # noqa: E402

Image.MAX_IMAGE_PIXELS = None
LONG, QUALITY, GREY = 640, 80, (224, 224, 224)
MEDIA_FIELDS = ("width", "height", "duration", "taken", "pages", "thumb", "preview_error")
PRIORITY = {"photo": 1, "graphic": 1, "pdf": 2, "design-source": 3, "video": 4, "audio": 5}
PILLOW_EXT = {"jpg", "jpeg", "jpe", "png", "gif", "webp", "bmp", "tif", "tiff", "ico"}
SIPS_EXT = {"pdf", "heic", "heif", "psd", "psb", "tif", "tiff", "dng", "cr2", "cr3", "nef", "arw", "raf", "orf", "rw2"}
PDF_EXT = {"pdf", "ai", "ait"}
CANT = {"dxf": "DXF (CAD drawing); macOS has no renderer", "idml": "IDML (InDesign markup); no renderer",
        "sketch": "Sketch file; no renderer", "fig": "Figma file; no renderer", "xd": "Adobe XD file; no renderer"}


def log(msg):
    line = f"{dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  {msg}"
    print(line, flush=True)
    al.CACHE.mkdir(parents=True, exist_ok=True)
    with open(al.LOG, "a") as fh:
        fh.write(line + "\n")


def free_bytes():
    return shutil.disk_usage(Path.home()).free


def allocated(p):
    """Bytes of the file actually on this Mac (0 for an online-only file)."""
    try:
        return os.stat(p).st_blocks * 512
    except OSError:
        return 0


def skip_reason(a):
    if al.in_to_delete(a["folder"]):
        return "_To Delete"
    if a.get("package"):
        return "macOS package"
    if a["kind"] not in PRIORITY:
        return f"{a['kind']}: no preview for this kind"
    return None


def load_media():
    m = al.load_json(al.MEDIA_FILE, {})
    return m if isinstance(m, dict) else {}


def save_media(media):
    cur = load_media()
    cur.update(media)
    al.atomic_write(al.MEDIA_FILE, json.dumps(cur, indent=1, ensure_ascii=False, sort_keys=True))
    media.clear()
    media.update(cur)


def entry_done(e, kind, retry_errors=False):
    if not isinstance(e, dict):
        return False
    if e.get("preview_error"):
        return not retry_errors
    if kind == "audio":
        return e.get("duration") is not None
    return bool(e.get("thumb")) and (al.THUMBS / e["thumb"]).exists()


def build_renderer():
    """True when the Swift renderer is ready (compiled once; rebuilt when render.swift changes)."""
    src = HERE / "render.swift"
    if al.BIN.exists() and al.BIN.stat().st_mtime >= src.stat().st_mtime:
        return True
    if not shutil.which("swiftc"):
        log("swiftc not found (Xcode Command Line Tools); using Pillow and sips. SVG files get no preview.")
        return False
    al.BIN.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["swiftc", "-O", "-o", str(al.BIN), str(src)], capture_output=True, text=True)
    if r.returncode:
        log(f"render.swift didn't compile; using Pillow and sips. {r.stderr.strip()[:200]}")
        return False
    return True


HAVE_BIN = False


# ---------------------------------------------------------------- making one preview

class Fail(Exception):
    """A lasting reason this file has no preview (recorded as preview_error)."""


def render(path, out, mode):
    if not HAVE_BIN:
        return fallback(path, out, mode)
    try:
        r = subprocess.run([str(al.BIN), str(path), str(out), str(LONG), mode], capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        raise Fail("timeout: renderer took over 5 minutes")
    try:
        info = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Fail(f"renderer crashed ({(r.stderr or '').strip()[:80] or r.returncode})")
    if "error" in info:
        raise Fail(info["error"])
    return info


def fallback(path, out, mode):
    """No Swift renderer: Pillow for common images, sips (built into macOS) for PDF, HEIC, PSD and camera raw."""
    ext = Path(path).suffix.lower().lstrip(".")
    if mode == "image" and ext in PILLOW_EXT:
        try:
            return pillow_still(path, out)
        except Exception as e:
            if ext not in SIPS_EXT:
                raise Fail(f"Pillow cannot read it ({e.__class__.__name__})")
    if mode == "nsimage":
        raise Fail("SVG needs the Swift renderer (install the Xcode Command Line Tools)")
    if ext in SIPS_EXT or mode == "pdf":
        r = subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "80", "-Z", str(LONG), str(path),
                            "--out", str(out)], capture_output=True, text=True, timeout=300)
        if r.returncode or not Path(out).exists():
            raise Fail("sips cannot read it")
        if mode == "pdf":
            return {"width": None, "height": None}
        q = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)], capture_output=True, text=True, timeout=60)
        dims = dict(re.findall(r"pixel(Width|Height):\s*(\d+)", q.stdout))
        return {"width": int(dims["Width"]) if "Width" in dims else None, "height": int(dims["Height"]) if "Height" in dims else None}
    raise Fail("no renderer for this file without the Swift renderer")


def exif_date(s):
    m = re.match(r"(\d{4})[:\-](\d\d)[:\-](\d\d)[ T](\d\d):(\d\d):(\d\d)", s or "")
    if not m or m.group(1) in ("0000", "1970"):
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}T{m.group(4)}:{m.group(5)}:{m.group(6)}"


def pillow_still(path, out):
    with Image.open(path) as im:
        w, h = im.size
        exif = im.getexif()
        taken = exif.get_ifd(0x8769).get(0x9003) if exif else None
        im.draft("RGB", (LONG, LONG))
        if exif and exif.get(0x0112, 1) in (5, 6, 7, 8):
            w, h = h, w
        im = ImageOps.exif_transpose(im)
        icc = im.info.get("icc_profile")
        if icc and im.mode in ("RGB", "RGBA", "CMYK"):
            try:
                from PIL import ImageCms
                im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)), ImageCms.createProfile("sRGB"),
                                               outputMode="RGBA" if im.mode == "RGBA" else "RGB")
            except Exception:
                pass
        finish(im, out)
    return {"width": w, "height": h, "taken": taken}


def finish(im, out):
    """Any Pillow image -> flattened sRGB JPEG, 640 px long edge."""
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, GREY)
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    im = im.convert("RGB")
    im.thumbnail((LONG, LONG), Image.LANCZOS)
    im.save(out, "JPEG", quality=QUALITY, optimize=True)


def read_capped(path, cap=400 * 1024 * 1024):
    with open(path, "rb") as fh:
        return fh.read(cap)


def xmp_thumb(data):
    """The largest JPEG thumbnail Adobe apps embed in XMP (xmpGImg:image), as bytes."""
    best = b""
    for m in re.finditer(rb"xmpGImg:image(?:>|=\")([A-Za-z0-9+/=\s&#;xXaAdD]{200,}?)(?:<|\")", data):
        raw = re.sub(rb"&#x?[0-9A-Fa-f]+;|\s", b"", m.group(1))
        try:
            jpg = base64.b64decode(raw + b"=" * (-len(raw) % 4))
        except ValueError:
            continue
        if jpg[:3] == b"\xff\xd8\xff" and len(jpg) > len(best):
            best = jpg
    return best


def embedded_preview(path, ext, tmp):
    """Design files macOS can't draw: use the preview the app saved inside the file."""
    data = read_capped(path)
    blob, what = b"", ""
    if ext == "eps" and data[:4] == b"\xc5\xd0\xd3\xc6":
        off, n = int.from_bytes(data[20:24], "little"), int.from_bytes(data[24:28], "little")
        if off and n:
            blob, what = data[off:off + n], "tif"
    if not blob and ext == "cdr" and data[:2] == b"PK":
        try:
            z = zipfile.ZipFile(io.BytesIO(data))
            names = [n for n in z.namelist() if n.lower().startswith("metadata/thumbnails/") and n.lower().endswith(".bmp")]
            names.sort(key=lambda n: (not n.lower().endswith("page1.bmp"), -z.getinfo(n).file_size))
            if names:
                blob, what = z.read(names[0]), "bmp"
        except zipfile.BadZipFile:
            pass
    if not blob and ext == "studio3":
        i = data.find(b"\x89PNG\r\n\x1a\n")
        j = data.find(b"IEND", i)
        if i >= 0 and j > i:
            blob, what = data[i:j + 8], "png"
    if not blob:
        blob, what = xmp_thumb(data), "jpg"
    if not blob:
        reasons = {"eps": "EPS with no embedded preview (needs Ghostscript)", "indd": "InDesign file with no embedded preview",
                   "cdr": "CorelDRAW file with no embedded preview", "studio3": "Silhouette file with no embedded preview"}
        raise Fail(reasons.get(ext, f"{ext} file with no embedded preview"))
    src = tmp / f"embedded.{what}"
    src.write_bytes(blob)
    return src


def probe(path):
    ffprobe = al.tool("ffprobe")
    if not ffprobe:
        raise Fail("ffprobe not installed (brew install ffmpeg-full)")
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                        "format=duration:format_tags=creation_time:stream=codec_type,width,height:stream_tags=rotate:stream_side_data=rotation",
                        "-of", "json", str(path)], capture_output=True, text=True, timeout=180)
    try:
        return json.loads(r.stdout)
    except ValueError:
        raise Fail("ffprobe could not read it")


def video(path, out, tmp, check_space):
    j = probe(path)
    dur = float(j.get("format", {}).get("duration") or 0)
    vs = [s for s in j.get("streams", []) if s.get("codec_type") == "video" and s.get("width")]
    if not vs:
        raise Fail("no video stream")
    s = vs[0]
    w, h = s["width"], s["height"]
    rot = s.get("tags", {}).get("rotate") or next((d.get("rotation") for d in s.get("side_data_list", []) if "rotation" in d), 0)
    if abs(int(float(rot or 0))) % 180 == 90:
        w, h = h, w
    frames = []
    for i, f in enumerate((0.125, 0.375, 0.625, 0.875)):
        check_space()
        fp = tmp / f"f{i}.jpg"
        t = max(0.0, dur * f) if dur else 0
        try:
            subprocess.run([al.tool("ffmpeg") or "ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(path), "-frames:v", "1",
                            "-an", "-vf", "scale='if(gt(iw,ih),320,-2)':'if(gt(iw,ih),-2,320)'", "-y", str(fp)],
                           capture_output=True, timeout=300)
        except subprocess.TimeoutExpired:
            continue
        if fp.exists() and fp.stat().st_size:
            frames.append(Image.open(fp).convert("RGB"))
    if not frames:
        raise Fail("ffmpeg could not decode any frame")
    while len(frames) < 4:
        frames.append(Image.new("RGB", frames[0].size, GREY))
    fw, fh = frames[0].size
    tile = Image.new("RGB", (fw * 2 + 2, fh * 2 + 2), GREY)
    for i, fr in enumerate(frames):
        tile.paste(fr.resize((fw, fh)), ((i % 2) * (fw + 2), (i // 2) * (fh + 2)))
    finish(tile, out)
    taken = j.get("format", {}).get("tags", {}).get("creation_time")
    return {"width": w, "height": h, "duration": round(dur, 2) if dur else None, "taken": taken[:19] if taken else None}


def make(a, path, check_space):
    """Make the preview for one file. Returns the media facts (thumb set), or raises Fail."""
    ext, kind = a["ext"], a["kind"]
    out = al.THUMBS / f"{al.key_of(a)}.jpg"
    part = out.with_suffix(".part.jpg")
    tmp = al.TMP / al.key_of(a)
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        if kind == "audio":
            d = probe(path).get("format", {}).get("duration")
            if d is None:
                raise Fail("ffprobe found no duration")
            return {"duration": round(float(d), 2), "thumb": None}
        if kind == "video":
            info = video(path, part, tmp, check_space)
        elif ext in PDF_EXT:
            try:
                info = render(path, part, "pdf")
            except Fail as e:
                if ext == "pdf":
                    raise
                try:
                    info = render(embedded_preview(path, ext, tmp), part, "image")
                    info["width"] = info["height"] = None      # that is the thumbnail's size, not the artwork's
                except Fail:
                    raise Fail(f"Illustrator file is not PDF-compatible and has no embedded preview ({e})")
            info.pop("units", None)
        elif ext == "svg":
            info = render(path, part, "nsimage")
        elif ext in CANT:
            raise Fail(CANT[ext])
        elif ext in ("eps", "indd", "indt", "cdr", "studio3"):
            info = render(embedded_preview(path, ext, tmp), part, "image")
            info["width"] = info["height"] = None
            info.pop("taken", None)
        else:
            try:
                info = render(path, part, "image")
            except Fail as e:
                if ext not in PILLOW_EXT:
                    if not HAVE_BIN:
                        raise
                    try:
                        info = render(path, part, "nsimage")
                    except Fail:
                        raise e
                else:
                    try:
                        info = pillow_still(path, part)
                    except Exception:
                        raise e
        info.pop("frames", None)
        if not part.exists() or part.stat().st_size == 0:
            raise Fail("no image came out")
        os.replace(part, out)
        info["taken"] = exif_date(info.get("taken")) or (info.get("taken") if kind == "video" else None)
        info["thumb"] = out.name
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        if part.exists():
            part.unlink()


# ---------------------------------------------------------------- run

def scan_catalog():
    r = subprocess.run([sys.executable, str(HERE / "catalog.py"), "scan"], capture_output=True, text=True, timeout=3600)
    if r.returncode:
        log(f"catalog scan failed: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.returncode == 0


def take_lock():
    al.CACHE.mkdir(parents=True, exist_ok=True)
    if al.LOCK.exists():
        try:
            pid = int(al.LOCK.read_text().strip())
            os.kill(pid, 0)
            sys.exit(f"previews.py is already running (pid {pid}); remove {al.LOCK} if it isn't")
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    al.LOCK.write_text(str(os.getpid()))


def run(args):
    global HAVE_BIN
    al.need_roots()
    kinds = set((al.opt(args, "--kinds", "") or "").split(",")) - {""}
    limit = int(al.opt(args, "--limit", "0"))
    top = (al.opt(args, "--top") or "").lower()
    floor = float(al.opt(args, "--floor", "8")) * 1e9
    wait_min = float(al.opt(args, "--wait", "20"))
    retry, no_scan = al.flag(args, "--retry-errors"), al.flag(args, "--no-scan")
    take_lock()
    stop = {"why": None}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(why="stopped by SIGTERM"))
    signal.signal(signal.SIGINT, lambda *_: stop.update(why="stopped by Ctrl-C"))
    for d in (al.THUMBS, al.TMP):
        d.mkdir(parents=True, exist_ok=True)
    w = al.icloud_warning(al.CACHE)
    if w:
        log("WARNING: " + w)
    HAVE_BIN = build_renderer()
    t0 = time.time()
    st = {"started": dt.datetime.now().isoformat(timespec="seconds"), "made": 0, "reused": 0, "failed": {}, "vanished": 0,
          "deferred_big": [], "skipped_rule": {}, "downloaded_bytes": 0, "source_bytes": 0, "free_start": free_bytes(),
          "free_min": free_bytes(), "waits": [], "stalled": None, "finished": False, "rescans": 0}
    log(f"run start: kinds={sorted(kinds) or 'all'} top={top or 'all'} limit={limit or 'none'} floor={floor / 1e9:.0f} GB "
        f"free={st['free_start'] / 1e9:.2f} GB renderer={'swift' if HAVE_BIN else 'pillow+sips'}")
    media = load_media()
    if not no_scan:
        scan_catalog()

    def plan():
        groups, skipped = {}, {}
        for a in al.load_catalog()["assets"]:
            why = skip_reason(a)
            if why:
                skipped[why.split(":")[0]] = skipped.get(why.split(":")[0], 0) + 1
                continue
            if kinds and a["kind"] not in kinds or top and top not in (a["top"].lower(), f"{a['root']}/{a['top']}".lower()):
                continue
            groups.setdefault(al.key_of(a), []).append(a)
        return groups, skipped

    groups, st["skipped_rule"] = plan()
    queue = sorted(groups, key=lambda k: (PRIORITY[groups[k][0]["kind"]], groups[k][0]["bytes"], k))
    todo = [k for k in queue if not entry_done(media.get(k), groups[k][0]["kind"], retry)]
    log(f"{len(groups)} unique contents in scope, {len(todo)} still to do")
    dirty, last_save, last_scan, vanished_since = 0, time.time(), time.time(), 0

    def note_free():
        f = free_bytes()
        st["free_min"] = min(st["free_min"], f)
        return f

    def wait_for_space(need):
        f = note_free()
        if f - need >= floor:
            return True
        save_media(media)
        start = time.time()
        log(f"free {f / 1e9:.2f} GB is under the floor (+{need / 1e9:.2f} GB for this file); waiting up to {wait_min:.0f} min")
        while time.time() - start < wait_min * 60 and not stop["why"]:
            time.sleep(30)
            f = note_free()
            if f - need >= floor:
                st["waits"].append({"minutes": round((time.time() - start) / 60, 1), "recovered_to_gb": round(f / 1e9, 2)})
                log(f"space recovered to {f / 1e9:.2f} GB after {(time.time() - start) / 60:.1f} min")
                return True
        st["waits"].append({"minutes": round((time.time() - start) / 60, 1), "recovered_to_gb": None})
        return False

    class Stall(Exception):
        pass

    def check_space():
        if note_free() < floor and not wait_for_space(0):
            raise Stall()

    i = 0
    for n, k in enumerate(todo):
        if stop["why"] or (limit and i >= limit):
            break
        members = groups[k]
        kind = members[0]["kind"]
        i += 1
        existing = [a for a in members if os.path.exists(al.to_disk(a["path"]))]
        if not existing:
            st["vanished"] += 1
            vanished_since += 1
            log(f"gone (moved?): {members[0]['path']}")
            if vanished_since >= 3 and time.time() - last_scan > 300:
                save_media(media)
                dirty = 0
                if scan_catalog():
                    st["rescans"] += 1
                    groups.update(plan()[0])
                    log("re-scanned the catalog after files moved; carrying on with fresh paths")
                last_scan, vanished_since = time.time(), 0
            continue
        a = sorted(existing, key=lambda x: (not x["local"], x["locked"], x["path"]))[0]
        path = al.to_disk(a["path"])
        need = 0 if a["local"] else (min(a["bytes"], 64e6) if kind in ("video", "audio") else a["bytes"])
        f = note_free()
        if f >= floor and f - need < floor and need > 1e9:
            st["deferred_big"].append({"path": a["path"], "gb": round(a["bytes"] / 1e9, 2)})
            log(f"deferred (too big for the space left now): {a['path']} {a['bytes'] / 1e9:.2f} GB")
            continue
        if not wait_for_space(need):
            st["stalled"] = {"at_path": a["path"], "position": n, "of": len(todo), "free_gb": round(free_bytes() / 1e9, 2)}
            log(f"STALLED: free space did not recover above the floor; stopping at {a['path']}")
            break
        before = allocated(path)
        try:
            info = make(a, path, check_space)
            info["preview_error"] = None
            st["made"] += 1
        except Stall:
            st["stalled"] = {"at_path": a["path"], "position": n, "of": len(todo), "free_gb": round(free_bytes() / 1e9, 2)}
            log(f"STALLED mid-file: {a['path']}")
            break
        except Fail as e:
            info = {"thumb": None, "preview_error": str(e)}
            reason = str(e).split(":")[0].split("(")[0].strip()
            st["failed"][reason] = st["failed"].get(reason, 0) + 1
            log(f"no preview: {a['path']}: {e}")
        except FileNotFoundError:
            st["vanished"] += 1
            vanished_since += 1
            log(f"gone mid-read (moved?): {a['path']}")
            continue
        except (OSError, subprocess.SubprocessError) as e:     # passing trouble: not recorded, tried again next run
            st["failed"]["transient (retried next run)"] = st["failed"].get("transient (retried next run)", 0) + 1
            log(f"error (will retry next run): {a['path']}: {e}")
            continue
        st["downloaded_bytes"] += max(0, allocated(path) - before)
        st["source_bytes"] += a["bytes"]
        media[k] = {f: info.get(f) for f in MEDIA_FIELDS}
        dirty += 1
        if i % 25 == 0:
            log(f"[{kind}] {n + 1}/{len(todo)}  made {st['made']} failed {sum(st['failed'].values())}  "
                f"downloaded {st['downloaded_bytes'] / 1e9:.2f} GB  free {note_free() / 1e9:.2f} GB  {(time.time() - t0) / 60:.0f} min")
        if dirty >= 200 or time.time() - last_save > 120:
            save_media(media)
            dirty, last_save = 0, time.time()
            write_state(st, t0)
    else:
        st["finished"] = True
    if limit and i >= limit and not st["stalled"]:
        st["finished"] = i >= len(todo)
    save_media(media)
    if stop["why"]:
        log(stop["why"])
        st["stopped"] = stop["why"]
    write_state(st, t0)
    scan_catalog()
    shutil.rmtree(al.TMP, ignore_errors=True)
    al.LOCK.unlink(missing_ok=True)
    log(f"made {st['made']}, failed {sum(st['failed'].values())} {st['failed']}, vanished {st['vanished']}, "
        f"deferred {len(st['deferred_big'])}; skipped by rule {st['skipped_rule']}; downloaded "
        f"{st['downloaded_bytes'] / 1e9:.2f} GB; {(time.time() - t0) / 60:.1f} min; "
        + ("finished" if st["finished"] else f"NOT finished: {st.get('stalled') or st.get('stopped') or 'limit reached'}"))


def write_state(st, t0):
    st["minutes"] = round((time.time() - t0) / 60, 1)
    st["free_now"] = free_bytes()
    al.atomic_write(al.STATE, json.dumps(st, indent=1))


# ---------------------------------------------------------------- status

def status(args):
    assets = al.load_catalog()["assets"]
    media = load_media()
    rows, tops, fails = {}, {}, {}
    for a in assets:
        e = media.get(al.key_of(a)) or media.get(a["id"]) or {}
        why = skip_reason(a)
        r = rows.setdefault(a["kind"], {"files": 0, "preview": 0, "facts": 0, "failed": 0, "skipped": 0, "todo": 0})
        t = tops.setdefault(f"{a['root']}/{a['top']}" if a["top"] else a["root"],
                            {"files": 0, "preview": 0, "failed": 0, "skipped": 0, "todo": 0})
        r["files"] += 1
        t["files"] += 1
        if why:
            r["skipped"] += 1
            t["skipped"] += 1
        elif e.get("preview_error"):
            r["failed"] += 1
            t["failed"] += 1
            fails[f"{a['ext']}: {e['preview_error']}"] = fails.get(f"{a['ext']}: {e['preview_error']}", 0) + 1
        elif e.get("thumb") and (al.THUMBS / e["thumb"]).exists():
            r["preview"] += 1
            t["preview"] += 1
        elif a["kind"] == "audio" and e.get("duration") is not None:
            r["facts"] += 1
            t["preview"] += 1
        else:
            r["todo"] += 1
            t["todo"] += 1
    print(f"{'kind':<14}{'files':>7}{'preview':>9}{'facts':>7}{'failed':>8}{'skipped':>9}{'to do':>7}")
    for k, r in sorted(rows.items(), key=lambda kv: -kv[1]["files"]):
        print(f"{k:<14}{r['files']:>7}{r['preview']:>9}{r['facts']:>7}{r['failed']:>8}{r['skipped']:>9}{r['todo']:>7}")
    print(f"\n{'folder':<42}{'files':>7}{'done':>7}{'failed':>8}{'skipped':>9}{'to do':>7}")
    for k, t in sorted(tops.items(), key=lambda kv: -kv[1]["files"]):
        print(f"{k[:41]:<42}{t['files']:>7}{t['preview']:>7}{t['failed']:>8}{t['skipped']:>9}{t['todo']:>7}")
    if fails:
        print("\nFailures by reason:")
        for k, v in sorted(fails.items(), key=lambda kv: -kv[1]):
            print(f"  {v:>5}  {k}")
    print(f"\n{len(list(al.THUMBS.glob('*.jpg'))) if al.THUMBS.exists() else 0} preview files in {al.THUMBS}")
    if al.STATE.exists():
        s = json.loads(al.STATE.read_text())
        print(f"Last run {s['started']}: {s.get('minutes')} min, made {s['made']}, downloaded "
              f"{s['downloaded_bytes'] / 1e9:.2f} GB, lowest free {s['free_min'] / 1e9:.2f} GB, "
              + ("finished" if s.get("finished") else f"not finished ({s.get('stalled') or s.get('stopped') or 'limit'})"))


# ---------------------------------------------------------------- contact sheets

CELL, GAP, CAP = 500, 15, 34
BATCH = 500


def slug(s, n=22):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower().replace("&", "and")).strip("-")
    return s[:n].rstrip("-")


def sheet_image(cells, out):
    W = 3 * CELL + 4 * GAP
    H = 3 * (CELL + CAP) + 4 * GAP
    img = Image.new("RGB", (W, H), (40, 40, 40))
    d = ImageDraw.Draw(img)
    big, small = al.ui_font(46, bold=True), al.ui_font(19)
    for i, c in enumerate(cells):
        r, col = divmod(i, 3)
        x, y = GAP + col * (CELL + GAP), GAP + r * (CELL + CAP + GAP)
        d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=(255, 255, 255))
        with Image.open(al.THUMBS / c["thumb"]) as t:
            t = t.convert("RGB")
            t.thumbnail((CELL, CELL), Image.LANCZOS)
            if max(t.size) < CELL:       # small originals stay crisp but fill the cell
                s = CELL / max(t.size)
                t = t.resize((max(1, round(t.width * s)), max(1, round(t.height * s))), Image.LANCZOS)
            img.paste(t, (x + (CELL - t.width) // 2, y + (CELL - t.height) // 2))
        d.rectangle([x, y, x + 92, y + 60], fill=(0, 0, 0))
        d.text((x + 46, y + 30), c["cell"], font=big, fill=(255, 220, 0), anchor="mm")
        d.rectangle([x, y + CELL, x + CELL - 1, y + CELL + CAP - 1], fill=(20, 20, 20))
        name = c["name"]
        while d.textlength(name, font=small) > CELL - 12 and len(name) > 4:
            name = name[:-2]
        if name != c["name"]:
            name = name[:-1] + "…"
        d.text((x + 6, y + CELL + CAP // 2), name, font=small, fill=(235, 235, 235), anchor="lm")
    img.save(out, "JPEG", quality=88)


def unique_items(assets, media, untagged_only):
    groups = {}
    for a in assets:
        if not al.in_to_delete(a["folder"]):
            groups.setdefault(al.key_of(a), []).append(a)
    items = []
    for k, ms in groups.items():
        if untagged_only and any(m.get("description") for m in ms):
            continue
        rep = sorted(ms, key=lambda m: (m["locked"], m["top"].lower() in ("archive", "archives"), len(m["path"]), m["path"]))[0]
        e = media.get(k) or media.get(rep["id"]) or {}
        thumb = e.get("thumb") if e.get("thumb") and (al.THUMBS / e["thumb"]).exists() else None
        item = {"md5": rep["md5"], "ids": [m["id"] for m in ms], "paths": sorted(m["path"] for m in ms), "name": rep["name"],
                "kind": rep["kind"], "bytes": rep["bytes"], "width": e.get("width"), "height": e.get("height"),
                "taken": e.get("taken"), "duration": e.get("duration"), "pages": e.get("pages"), "thumb": thumb,
                "_folder": rep["folder"], "_top": f"{rep['root']}/{rep['top']}" if rep["top"] else rep["root"]}
        if not thumb:
            item["no_preview_reason"] = e.get("preview_error") or skip_reason(rep) or "not previewed yet"
        items.append(item)
    return items


def sheets(args):
    every, no_scan = al.flag(args, "--all"), al.flag(args, "--no-scan")
    if not no_scan:
        scan_catalog()
    items = unique_items(al.load_catalog()["assets"], load_media(), untagged_only=not every)
    by_top = {}
    for it in items:
        by_top.setdefault(it["_top"], {}).setdefault(it["_folder"], []).append(it)
    batches = []              # whole folders, in tree order, within one top folder; about BATCH files each
    for topname in sorted(by_top):
        folders = by_top[topname]
        cur, cur_f = [], []
        for f in sorted(folders):
            fi = sorted(folders[f], key=lambda x: x["name"].lower())
            if len(fi) > BATCH:
                if cur:
                    batches.append((topname, cur_f, cur))
                    cur, cur_f = [], []
                for s in range(0, len(fi), BATCH):
                    batches.append((topname, [f], fi[s:s + BATCH]))
                continue
            if cur and len(cur) + len(fi) > BATCH:
                batches.append((topname, cur_f, cur))
                cur, cur_f = [], []
            cur += fi
            cur_f.append(f)
        if cur:
            batches.append((topname, cur_f, cur))
    multi = len(al.ROOTS) > 1
    tmp_dir = al.SHEETS.with_name("sheets.new")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True)
    used, index = {}, []
    for topname, flist, its in batches:
        common = os.path.commonpath(flist)
        rest = common[len(topname):].strip("/") if common.startswith(topname) else ""
        tail = "-".join(slug(p, 14) for p in rest.split("/")[-2:] if p) if rest else ""
        parts = topname.split("/")
        head = slug(parts[-1] if len(parts) > 1 else parts[0], 18) or "loose"
        if multi or len(parts) == 1:
            head = slug(parts[0], 16) + ("-" + head if len(parts) > 1 else "-loose")
        name = (head + (f"-{tail}" if tail else ""))[:44].rstrip("-") or "batch"
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:
            name = f"{name}-{used[name]}"
        bdir = tmp_dir / name
        bdir.mkdir()
        withp = [x for x in its if x["thumb"]]
        nop = [x for x in its if not x["thumb"]]
        sheet_list = []
        for s in range(0, len(withp), 9):
            cells = [dict(x, cell="ABC"[j // 3] + str(j % 3 + 1)) for j, x in enumerate(withp[s:s + 9])]
            fn = f"sheet-{s // 9 + 1:03d}.jpg"
            sheet_image(cells, bdir / fn)
            sheet_list.append({"file": fn, "cells": [{k: v for k, v in c.items() if not k.startswith("_")} for c in cells]})
        doc = {"batch": name, "top": topname, "folders": flist, "assets": len(its), "with_preview": len(withp),
               "grid": "3x3; cells A1 A2 A3 / B1 B2 B3 / C1 C2 C3 (row letter, column number)",
               "sheets": sheet_list, "no_preview": [{k: v for k, v in x.items() if not k.startswith("_")} for x in nop]}
        (bdir / "batch.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        index.append({"batch": name, "assets": len(its), "with_preview": len(withp), "no_preview": len(nop),
                      "sheets": len(sheet_list), "folders": len(flist)})
    (tmp_dir / "index.json").write_text(json.dumps(index, indent=1, ensure_ascii=False))
    shutil.rmtree(al.SHEETS, ignore_errors=True)
    os.replace(tmp_dir, al.SHEETS)
    print(f"{'batch':<46}{'files':>7}{'preview':>8}{'none':>6}{'sheets':>7}")
    for b in index:
        print(f"{b['batch']:<46}{b['assets']:>7}{b['with_preview']:>8}{b['no_preview']:>6}{b['sheets']:>7}")
    what = "files" if every else "files not yet described"
    print(f"\n{len(index)} batches, {sum(b['assets'] for b in index)} unique {what}, "
          f"{sum(b['sheets'] for b in index)} sheets in {al.SHEETS}")


def reference(args):
    """One labelled sheet (up to 9 previews) per name: what the tagging agents compare logos against."""
    if len(args) < 2:
        sys.exit('usage: previews.py reference <name> "<catalog folder or file>" [...]   e.g. reference current "Brand/Logos/Now"')
    name, places = slug(args[0], 30) or "reference", args[1:]
    media = load_media()
    picks = []
    for a in al.load_catalog()["assets"]:
        if any(al.under(a["path"], p.rstrip("/")) for p in places):
            e = media.get(al.key_of(a)) or {}
            if e.get("thumb") and (al.THUMBS / e["thumb"]).exists() and all(p["thumb"] != e["thumb"] for p in picks):
                picks.append({"name": a["name"], "thumb": e["thumb"], "path": a["path"]})
    if not picks:
        sys.exit("No previews under those paths. Check the paths (catalog.py find) and run previews.py run first.")
    al.REFERENCE.mkdir(parents=True, exist_ok=True)
    out = []
    for s in range(0, min(len(picks), 27), 9):
        cells = [dict(x, cell="ABC"[j // 3] + str(j % 3 + 1)) for j, x in enumerate(picks[s:s + 9])]
        fn = al.REFERENCE / f"{name}{'' if s == 0 else f'-{s // 9 + 1}'}.jpg"
        sheet_image(cells, fn)
        out.append(fn)
    for fn in out:
        print(f"Wrote {fn}")
    if len(picks) > 27:
        print(f"({len(picks) - 27} more previews left out; three sheets is plenty to compare against)")


def main():
    args = sys.argv[1:]
    cmd = args.pop(0) if args else ""
    {"run": run, "status": status, "sheets": sheets, "reference": reference}.get(cmd, lambda _: print(__doc__))(args)


if __name__ == "__main__":
    main()
