#!/usr/bin/env python3
"""Video Review: watch a cut, see its beats, and leave timestamped notes for Claude.

    .venv/bin/python review/review.py                  # every video in the content folder (studio.json)
    .venv/bin/python review/review.py <folder>         # use a different folder as the library
    .venv/bin/python review/review.py <video.mp4>      # open one video straight away
    options: --port N (default: review_port in studio.json, 8765)  --no-browser

Notes are saved next to each video as "<video file>.notes.json" (see README.md).
A video with a sound map ("<video file>.sound.json", written by ../sound/soundmap.py) gets one timeline row per track.
A video with an effects map ("<video file>.effects.json", written by ../effects/effectsmap.py) gets a row naming what's on screen.
Beats come from "<video file>.words.txt" (the Footage Log's transcript format), a matching .srt,
or, with no transcript, the shot changes. Standard library only; needs ffmpeg and ffprobe,
plus whisper-cli for the Transcribe button. Also serves the Studio page (/studio, studio.py),
the Footage Log pages (/library) and the Asset Library (/assets, ../assets/browser/serve.py).
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from array import array
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "lib"))
import studio_config as sc  # noqa: E402

CACHE = Path.home() / ".cache" / "video-review"
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
SKIP_DIRS = {"node_modules", HERE.name}
LONG_CLIP = 600  # seconds; raw takes this long are one shot, so skip shot detection


def content_root():
    """The content folder named in studio.json (content_root)."""
    return sc.content_root().expanduser().resolve()


def default_port():
    try:
        return int(sc.get("review_port") or 8765)
    except (TypeError, ValueError):
        return 8765


ROOT = content_root()
PORT = default_port()
APP_VERSION = 6  # bump when the pages or API change, so an older copy still running isn't reused (5: sound tracks, 6: effects row)

JOBS, JOBS_LOCK, NOTES_LOCK = {}, threading.Lock(), threading.Lock()

ABOUT = (
    "Notes left in Video Review. t is seconds into this video file. Claude: fix only what each "
    'open note asks, then set its status to "done", say what changed in "reply" and put the new '
    'file name in "done_in".'
)


def now():
    return datetime.now().isoformat(timespec="seconds")


def fmt_tc(t):
    cs = int(round(t * 100))
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{m}:{s:02d}.{cs:02d}"


def run(cmd, timeout=None):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace").strip().splitlines()
        raise RuntimeError(err[-1] if err else f"{cmd[0]} failed")
    return r


def ffmpeg_video(head, p, tail, keyframes_only=False, timeout=1800):
    """Run ffmpeg on a video, trying hardware decoding first."""
    skip = ["-skip_frame", "nokey"] if keyframes_only else []
    tries = [["-hwaccel", "videotoolbox"], []] if sys.platform == "darwin" else [[]]
    for i, hw in enumerate(tries):
        try:
            return run(head + hw + skip + ["-i", str(p)] + tail, timeout=timeout)
        except RuntimeError:
            if i == len(tries) - 1:
                raise


def resolve(rel):
    if not rel:
        raise ValueError("missing path")
    p = (ROOT / rel).resolve()
    if ROOT not in p.parents:
        raise PermissionError("outside the library folder")
    if not p.is_file():
        raise FileNotFoundError(rel)
    return p


def rel_of(p):
    return p.relative_to(ROOT).as_posix()


def folder_of(rel):
    f = Path(rel).parent.as_posix()
    return "" if f == "." else f


# ---------- cached analysis ----------

def cache_file(p, kind):
    st = p.stat()
    h = hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]
    return CACHE / f"{h}.{kind}"


def cached_json(p, kind, build):
    f = cache_file(p, kind)
    if f.exists():
        try:
            return json.loads(f.read_text())
        except ValueError:
            pass
    data = build()
    f.write_text(json.dumps(data))
    return data


def rate(s):
    try:
        a, b = (s or "0/0").split("/")
        return float(a) / float(b) if float(b) else 0.0
    except ValueError:
        return 0.0


def probe(p):
    def build():
        r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)], timeout=120)
        d = json.loads(r.stdout or b"{}")
        streams = d.get("streams", [])
        v = next((s for s in streams if s.get("codec_type") == "video"), {})
        w, h = v.get("width") or 0, v.get("height") or 0
        rot = 0
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot = rot or int((v.get("tags") or {}).get("rotate", 0) or 0)
        if abs(rot) % 180 == 90:
            w, h = h, w
        return {
            "duration": float(d.get("format", {}).get("duration") or v.get("duration") or 0),
            "fps": round(rate(v.get("avg_frame_rate")) or rate(v.get("r_frame_rate")) or 30, 3),
            "width": w,
            "height": h,
            "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        }

    return cached_json(p, "probe.json", build)


def waveform(p, info):
    def build():
        dur = info["duration"] or 1
        if not info["has_audio"]:
            return {"bucket": dur, "peaks": []}
        sr = 4000 if dur <= LONG_CLIP else 1000
        r = run(["ffmpeg", "-v", "error", "-i", str(p), "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"], timeout=900)
        pcm = array("h")
        pcm.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
        if sys.byteorder == "big":
            pcm.byteswap()
        step = max(1, int(sr * max(0.01, dur / 12000)))
        peaks = []
        for i in range(0, len(pcm), step):
            chunk = pcm[i : i + step]
            peaks.append(max(max(chunk), -min(chunk)))
        top = max(peaks) if peaks and max(peaks) > 0 else 1
        # square root so quiet speech still shows next to loud music
        return {"bucket": step / sr, "peaks": [round(100 * math.sqrt(v / top)) for v in peaks]}

    return cached_json(p, "wave.json", build)


def shots(p, info):
    def build():
        dur = info["duration"]
        if dur > LONG_CLIP:
            return {"cuts": [], "skipped": "long clip"}
        r = ffmpeg_video(
            ["ffmpeg", "-hide_banner", "-nostats"], p,
            ["-an", "-vf", "scale=192:-2,select='gt(scene,0.32)',showinfo", "-f", "null", "-"],
            timeout=900,
        )
        cuts = []
        for m in re.findall(rb"pts_time:\s*([\d.]+)", r.stderr):
            t = float(m)
            if 0.3 < t < dur - 0.3 and (not cuts or t - cuts[-1] > 0.4):
                cuts.append(round(t, 3))
        return {"cuts": cuts}

    return cached_json(p, "shots.json", build)


def filmstrip(p, info):
    meta, img = cache_file(p, "strip.json"), cache_file(p, "strip.jpg")
    if meta.exists() and img.exists():
        try:
            return json.loads(meta.read_text())
        except ValueError:
            pass
    dur = max(info["duration"], 0.1)
    interval = max(0.5, dur / 240)
    count = int(dur // interval) + 1
    th = 96
    w, h = info["width"] or 1080, info["height"] or 1920
    tw = max(2, int(round(th * w / h / 2)) * 2)
    cols = max(1, min(count, 4096 // tw))
    rows = math.ceil(count / cols)
    vf = f"fps={1 / interval:.6f},scale={tw}:{th},tile={cols}x{rows}"
    ffmpeg_video(
        ["ffmpeg", "-v", "error", "-y"], p,
        ["-an", "-vf", vf, "-frames:v", "1", "-q:v", "5", str(img)],
        keyframes_only=dur > 180,
    )
    data = {"interval": interval, "count": count, "cols": cols, "rows": rows, "tw": tw, "th": th, "key": img.stem}
    meta.write_text(json.dumps(data))
    return data


# ---------- transcripts ----------

WORD_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s+(.+?)\s*$")
SRT_TIME = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def group_words(words):
    """Split words into spoken lines: at sentence ends, pauses, or about 4 s / 9 words."""
    lines, start = [], 0
    for i in range(1, len(words) + 1):
        if i < len(words):
            prev, cur = words[i - 1], words[i]
            n = i - start
            pause = cur["s"] - prev["e"] > 0.35 or prev["e"] - prev["s"] > 1.1
            sentence_end = prev["w"][-1:] in ".?!"
            comma = prev["w"][-1:] in ",;:" and n >= 4
            too_long = n >= 9 or cur["e"] - words[start]["s"] > 4.0
            if not (pause or sentence_end or comma or too_long):
                continue
        seg = words[start:i]
        lines.append({"s": seg[0]["s"], "e": seg[-1]["e"], "text": " ".join(w["w"] for w in seg), "w0": start, "w1": i})
        start = i
    return lines


def srt_candidates(p):
    base = re.sub(r"\s*\([^)]*\)\s*$", "", p.stem)  # "Reel 1 (clean).mp4" -> "Reel 1.srt"
    out = []
    for name in (p.name + ".srt", p.stem + ".srt", base + ".srt"):
        c = p.parent / name
        if c not in out:
            out.append(c)
    return out


def parse_srt(f):
    out = []
    for block in re.split(r"\n\s*\n", f.read_text(errors="replace").replace("\r", "").strip()):
        rows = block.split("\n")
        for i, row in enumerate(rows):
            m = SRT_TIME.search(row)
            if m:
                g = [int(x) for x in m.groups()]
                s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                text = re.sub(r"<[^>]+>", "", " ".join(rows[i + 1 :])).strip()
                if text:
                    out.append({"s": round(s, 3), "e": round(e, 3), "text": text})
                break
    return out


def load_transcript(p):
    wf = Path(str(p) + ".words.txt")
    if wf.exists():
        words = []
        for row in wf.read_text(errors="replace").splitlines():
            m = WORD_LINE.match(row)
            if m:
                words.append({"s": float(m[1]), "e": float(m[2]), "w": m[3]})
        if words:
            return {"source": wf.name, "kind": "words", "words": words, "lines": group_words(words)}
    for f in srt_candidates(p):
        if f.exists():
            lines = parse_srt(f)
            if lines:
                return {"source": f.name, "kind": "srt", "words": None, "lines": lines}
    return None


_FOOTAGE = None


def footage_mod():
    """library/footage.py, loaded on first use (transcripts and the tracker CSV)."""
    global _FOOTAGE
    if _FOOTAGE is None:
        lib = str(KIT / "library")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import footage
        _FOOTAGE = footage
    return _FOOTAGE


def can_transcribe():
    try:
        return footage_mod().can_transcribe()
    except Exception:
        return False


def transcribe(p):
    """whisper.cpp with word timing, the same as the Footage Log (library/footage.py), into <video>.words.txt."""
    f = footage_mod()
    if not f.can_transcribe():
        raise RuntimeError(f"Needs whisper-cli and the model at {f.whisper_model()} (setup/INSTALL.md)")
    words = f.whisper_words(p)
    f.write_words(p, words)
    return {"words": len(words)}


# ---------- background jobs ----------

def job(key, fn):
    with JOBS_LOCK:
        j = JOBS.get(key)
        if j and (j["status"] != "error" or time.time() - j["at"] < 60):
            return j
        j = JOBS[key] = {"status": "running", "at": time.time()}

    def work():
        try:
            j["result"] = fn()
            j["status"] = "ready"
        except Exception as e:  # reported to the page
            j["error"] = str(e) or e.__class__.__name__
            j["status"] = "error"
        j["at"] = time.time()

    threading.Thread(target=work, daemon=True).start()
    return j


def job_tag(p):
    return f"{p}:{p.stat().st_mtime_ns}"


def analysis(p):
    info = probe(p)
    tag = job_tag(p)
    out, errors, pending = {}, {}, False
    for kind, fn in (("waveform", waveform), ("filmstrip", filmstrip), ("shots", shots)):
        j = job(f"{kind}:{tag}", lambda fn=fn: fn(p, info))
        out[kind] = j.get("result") if j["status"] == "ready" else None
        if j["status"] == "running":
            pending = True
        elif j["status"] == "error":
            errors[kind] = j["error"]
    t = JOBS.get(f"transcribe:{tag}")
    if t:
        out["transcribe"] = {"status": t["status"], "error": t.get("error")}
        pending = pending or t["status"] == "running"
    out["errors"], out["pending"] = errors, pending
    return out


# ---------- sound map: separate sound tracks (see ../sound/soundmap.py) ----------

SOUND_MAX_BYTES = 2_000_000
SOUND_KINDS = ("voice", "voice_nat", "mix", "music", "nat", "sfx")


def sound_file(p):
    return Path(str(p) + ".sound.json")


def _num(v, lo, hi):
    v = float(v)
    if not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError("out of range")
    return v


def read_sound(p):
    """The video's sound map, checked, for the timeline. No tracks (and why) when there is none, or when the map
    doesn't fit this file (another video, or an earlier render saved under the same name). Read-only."""
    f = sound_file(p)

    def none(why):
        return {"tracks": [], "why": why}

    if not f.is_file():
        return none("none")
    if f.stat().st_size > SOUND_MAX_BYTES:
        return none("too big")
    try:
        d = json.loads(f.read_text())
    except (ValueError, OSError):
        return none("unreadable")
    if not isinstance(d, dict) or d.get("version") != 1 or not isinstance(d.get("tracks"), list):
        return none("unreadable")
    if d.get("video") != p.name:
        return none("other video")
    if "video_size" in d and d["video_size"] != p.stat().st_size:
        return none("stale")
    try:
        if abs(float(d.get("duration") or 0) - probe(p)["duration"]) > 0.15:
            return none("stale")
    except (RuntimeError, ValueError, TypeError):
        return none("unreadable")
    tracks = []
    for t in d["tracks"][:8]:
        try:
            if not isinstance(t, dict) or t.get("kind") not in SOUND_KINDS or not isinstance(t.get("peaks"), list):
                continue
            tr = {"id": str(t.get("id") or t["kind"])[:20], "kind": t["kind"], "name": str(t.get("name") or "")[:80],
                  "title": str(t.get("title") or "")[:120], "bucket": _num(t.get("bucket"), 0.001, 10),
                  "peaks": [max(0, min(100, int(v))) for v in t["peaks"][:400000]]}
            if t["kind"] == "sfx":
                cues = []
                for c in (t.get("cues") or [])[:3000]:
                    if not isinstance(c, dict):
                        continue
                    try:
                        cue = {"t": _num(c.get("t"), 0, 86400), "len": _num(c.get("len") or 0.05, 0, 600),
                               "at": _num(c.get("at", c.get("t")), 0, 86400), "name": str(c.get("name") or "")[:120],
                               "what": str(c.get("what") or "")[:60], "file": str(c.get("file") or "")[:200],
                               "from": str(c.get("from") or "")[:60]}
                        if c.get("level_db") is not None:
                            cue["level_db"] = _num(c["level_db"], -200, 50)
                    except (TypeError, ValueError):
                        continue
                    cues.append(cue)
                tr["cues"] = cues
            tracks.append(tr)
        except (TypeError, ValueError):
            continue
    tracks.sort(key=lambda t: SOUND_KINDS.index(t["kind"]))
    return {"tracks": tracks, "why": "" if tracks else "unreadable", "made": str(d.get("made") or "")[:40],
            "cues_from": str(d.get("cues_from") or "")[:300]}


EFFECTS_MAX_BYTES = 1_000_000


def effects_file(p):
    return Path(str(p) + ".effects.json")


def read_effects(p):
    """The video's effects map, checked, for the row above the frames: which layout, library effect or graphic is on
    screen over each stretch. No blocks (and why) when there is none or it doesn't fit this file. Read-only."""
    f = effects_file(p)

    def none(why):
        return {"blocks": [], "why": why}

    if not f.is_file():
        return none("none")
    if f.stat().st_size > EFFECTS_MAX_BYTES:
        return none("too big")
    try:
        d = json.loads(f.read_text())
    except (ValueError, OSError):
        return none("unreadable")
    if not isinstance(d, dict) or d.get("version") != 1 or not isinstance(d.get("blocks"), list):
        return none("unreadable")
    if d.get("video") != p.name:
        return none("other video")
    if "video_size" in d and d["video_size"] != p.stat().st_size:
        return none("stale")
    try:
        dur = probe(p)["duration"]
        if abs(float(d.get("duration") or 0) - dur) > 0.15:
            return none("stale")
    except (RuntimeError, ValueError, TypeError):
        return none("unreadable")
    blocks = []
    for b in d["blocks"][:2000]:
        if not isinstance(b, dict):
            continue
        try:
            blocks.append({"t": _num(b.get("t"), 0, dur + 1), "len": _num(b.get("len"), 0.001, dur + 1),
                           "lane": int(_num(b.get("lane") or 0, 0, 5)), "label": str(b.get("label") or "")[:60],
                           "entry": str(b.get("entry") or "")[:80], "detail": str(b.get("detail") or "")[:160],
                           "about": str(b.get("about") or "")[:400], "key": str(b.get("key") or "")[:40],
                           "group": str(b.get("group") or "")[:20]})
        except (TypeError, ValueError):
            continue
    return {"blocks": blocks, "why": "" if blocks else "unreadable", "made": str(d.get("made") or "")[:40]}


def note_on_screen(v):
    """The visual effects a new note is on (from the page's effects row), kept small; [] when there are none."""
    out = []
    for c in (v if isinstance(v, list) else [])[:6]:
        if not isinstance(c, dict):
            continue
        try:
            out.append({"i": int(c.get("i")), "label": str(c.get("label") or "")[:60],
                        "entry": str(c.get("entry") or "")[:80], "detail": str(c.get("detail") or "")[:160],
                        "t": round(_num(c.get("t"), 0, 86400), 3), "len": round(_num(c.get("len") or 0, 0, 86400), 3)})
        except (TypeError, ValueError):
            continue
    return out


def note_sfx(v):
    """The sound effects a new note is on (from the page), kept small and plain; [] when there are none."""
    out = []
    for c in (v if isinstance(v, list) else [])[:6]:
        if not isinstance(c, dict):
            continue
        try:
            out.append({"i": int(c.get("i")), "name": str(c.get("name") or "")[:120],
                        "what": str(c.get("what") or "")[:60], "file": str(c.get("file") or "")[:200],
                        "t": round(_num(c.get("t"), 0, 86400), 3), "len": round(_num(c.get("len") or 0, 0, 600), 3),
                        "at": round(_num(c.get("at", c.get("t")), 0, 86400), 3)})
        except (TypeError, ValueError):
            continue
    return out


# ---------- notes ----------

def notes_file(p):
    return Path(str(p) + ".notes.json")


def read_notes(p):
    f = notes_file(p)
    if f.exists():
        try:
            d = json.loads(f.read_text())
            if isinstance(d, dict) and isinstance(d.get("notes"), list):
                return d
        except ValueError:
            pass
    return {"video": p.name, "about": ABOUT, "notes": []}


def write_notes(p, d):
    d["video"], d["about"], d["updated"] = p.name, ABOUT, now()
    d["notes"].sort(key=lambda n: float(n.get("t") or 0))
    f = notes_file(p)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, f)


def change_notes(p, body):
    op = body.get("op")
    with NOTES_LOCK:
        d = read_notes(p)
        notes = d["notes"]
        if op == "add":
            text = str(body.get("text", "")).strip()
            if not text:
                raise ValueError("empty note")
            t = round(float(body.get("t", 0)), 2)
            note = {
                "id": "n" + uuid.uuid4().hex[:6],
                "t": t,
                "timecode": fmt_tc(t),
                "beat": str(body.get("beat") or ""),
                "beat_text": str(body.get("beat_text") or ""),
            }
            sfx = note_sfx(body.get("sfx"))
            if sfx:  # optional: the sound effect(s) the playhead was on (only for videos with a sound map)
                note["sfx"] = sfx
            seen = note_on_screen(body.get("on_screen"))
            if seen:  # optional: the visual effect(s) on screen there (only for videos with an effects map)
                note["on_screen"] = seen
            note.update({
                "text": text,
                "status": "open",
                "created": now(),
                "reply": "",
                "done_in": "",
            })
            notes.append(note)
        elif op in ("update", "delete"):
            n = next((x for x in notes if x.get("id") == body.get("id")), None)
            if n is None:
                raise FileNotFoundError("note")
            if op == "delete":
                notes.remove(n)
            else:
                if "text" in body:
                    text = str(body["text"]).strip()
                    if not text:
                        raise ValueError("empty note")
                    n["text"] = text
                if body.get("status") in ("open", "done"):
                    n["status"] = body["status"]
                n["edited"] = now()
        else:
            raise ValueError("unknown op")
        write_notes(p, d)
        return d


# ---------- library ----------

def library():
    vids = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS)
        for f in filenames:
            if f.startswith(".") or Path(f).suffix.lower() not in VIDEO_EXT:
                continue
            p = Path(dirpath) / f
            try:
                st = p.stat()
            except OSError:
                continue
            n_open = n_done = 0
            if notes_file(p).exists():
                for n in read_notes(p)["notes"]:
                    if n.get("status") == "done":
                        n_done += 1
                    else:
                        n_open += 1
            rel = rel_of(p)
            vids.append({"path": rel, "name": f, "folder": folder_of(rel), "size": st.st_size,
                         "mtime": st.st_mtime, "open": n_open, "done": n_done})
    return {"root": str(ROOT), "root_name": ROOT.name, "videos": vids}


def file_stamp(p):
    st = p.stat()
    return {"size": st.st_size, "mtime": st.st_mtime}


def info_for(p):
    try:
        i = dict(probe(p))
    except RuntimeError as e:
        # a render writes the MP4's index last, so a file being written can't be read yet
        busy = time.time() - p.stat().st_mtime < 120
        raise RuntimeError(("This video is still being written (a render is probably running). "
                            "Try again in a minute." if busy else "This file can't be read: ") + ("" if busy else str(e)))
    rel = rel_of(p)
    i.update(
        path=rel, name=p.name, folder=folder_of(rel),
        transcript=load_transcript(p),
        notes=read_notes(p), notes_file=notes_file(p).name,
        can_transcribe=i["has_audio"] and can_transcribe(),
        file=file_stamp(p),
    )
    return i


# ---------- server ----------

# ---------- footage log + video tracker (see ../library/README.md) ----------

LOG_DIR = ROOT / "Footage Log"
TRACK_LOCK = threading.Lock()
STILL_SEM = threading.Semaphore(4)
TRACK_EDITABLE = ("status", "posted_on", "post_url", "notes", "title", "platform", "style", "brand")
STATUSES = ("in review", "ready to post", "scheduled", "posted", "shelved", "superseded")


def footage_log():
    f = LOG_DIR / "footage-log.json"
    return json.loads(f.read_text()) if f.exists() else {"clips": [], "missing": True}


def tracker_read():
    f = LOG_DIR / "video-tracker.json"
    return json.loads(f.read_text()) if f.exists() else {"videos": [], "missing": True}


def tracker_change(body):
    """Set status / posted_on / post_url / notes / title on one tracked video, then refresh Video Tracker.csv."""
    with TRACK_LOCK:
        d = tracker_read()
        v = next((x for x in d["videos"] if x["file"] == body.get("file")), None)
        if v is None:
            raise FileNotFoundError(body.get("file") or "file")
        for k in TRACK_EDITABLE:
            if k in body:
                val = str(body[k] or "")[:2000]
                if k == "status" and val not in STATUSES:
                    raise ValueError(f"unknown status: {val}")
                v[k] = val
        if v.get("status") == "posted" and not v.get("posted_on"):
            v["posted_on"] = datetime.now().strftime("%Y-%m-%d")
        d["updated"] = datetime.now().isoformat(timespec="seconds")
        f = LOG_DIR / "video-tracker.json"
        tmp = f.with_name(f".{f.name}.{uuid.uuid4().hex[:6]}")
        tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False))
        os.replace(tmp, f)
        try:
            footage_mod().write_tracker_csv(d["videos"])
        except Exception as e:
            print("Video Tracker.csv not refreshed:", e, file=sys.stderr)
    return v


def still(p, t, w):
    """One frame of a clip as a small JPEG (cached), for the footage log's moment thumbnails."""
    t, w = max(0.0, float(t)), max(80, min(640, int(float(w))))
    st = p.stat()
    key = hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}|{t:.2f}|{w}".encode()).hexdigest()[:20]
    f = CACHE / "stills" / f"{key}.jpg"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_name(f"{key}.{uuid.uuid4().hex[:6]}.jpg")
        with STILL_SEM:
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(p), "-frames:v", "1",
                 "-vf", f"scale={w}:-2", "-q:v", "5", str(tmp)], timeout=90)
        os.replace(tmp, f)
    return f.read_bytes()


# ---------- Studio home, project cards, glossary, classroom, guides (see studio.py) ----------

_STUDIO = None


def studio_route(h, method, u):
    """Hand /studio pages and /api/studio/ calls to studio.py, loaded on first use so nothing above depends on it."""
    global _STUDIO
    if _STUDIO is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("video_review_studio", HERE / "studio.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _STUDIO = mod
    return _STUDIO.handle(h, method, u, root=ROOT, library=library, tracker=tracker_read, statuses=STATUSES)


# ---------- Asset Library browser (see ../assets/browser/serve.py) ----------

_ASSETS = None


def assets_route(h, method, u):
    """Hand /assets, /assets/data and /assets/thumb/<name> to assets/browser/serve.py, loaded on first use."""
    global _ASSETS
    if _ASSETS is None:
        import importlib.util
        f = KIT / "assets" / "browser" / "serve.py"
        if not f.is_file():
            raise FileNotFoundError("the Asset Library isn't set up yet (assets/README.md)")
        spec = importlib.util.spec_from_file_location("video_review_assets", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _ASSETS = mod
    return _ASSETS.handle(h, method, u)


class Handler(BaseHTTPRequestHandler):
    server_version = "VideoReview/1"

    def log_message(self, *args):
        pass

    def send_bytes(self, b, ctype, code=200, cache=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
        self.end_headers()
        self.wfile.write(b)

    def send_json(self, obj, code=200):
        self.send_bytes(json.dumps(obj).encode(), "application/json; charset=utf-8", code)

    def send_media(self, p):
        size = p.stat().st_size
        start, end, code = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m and (m[1] or m[2]):
            if m[1]:
                start = int(m[1])
                end = min(int(m[2]), size - 1) if m[2] else size - 1
            else:
                start = max(0, size - int(m[2]))
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", "video/mp4")  # Chrome plays .mov (H.264/HEVC) fine under this type
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(p, "rb") as fh:
            fh.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        self.route("GET")

    def do_POST(self):
        self.route("POST")

    def route(self, method):
        u = urlparse(self.path)
        rel = (parse_qs(u.query).get("path") or [""])[0]
        try:
            host = (self.headers.get("Host") or "").split(":")[0]
            if host not in ("127.0.0.1", "localhost"):
                raise PermissionError("local use only")
            if method == "POST" and self.headers.get("X-Video-Review") != "1":
                raise PermissionError("missing header")
            if u.path in ("/", "/index.html"):
                return self.send_bytes((HERE / "editor.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/ping":
                return self.send_json({"app": "video-review", "root": str(ROOT), "version": APP_VERSION})
            if u.path == "/api/videos":
                return self.send_json(library())
            if u.path in ("/library", "/library.html"):
                return self.send_bytes((HERE / "library.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/footage":
                return self.send_json(footage_log())
            if u.path == "/api/tracker":
                if method == "POST":
                    return self.send_json(tracker_change(self.read_body()))
                return self.send_json(tracker_read())
            if u.path == "/studio" or u.path.startswith(("/studio/", "/api/studio/")):
                return studio_route(self, method, u)
            if u.path == "/assets" or u.path.startswith("/assets/"):
                return assets_route(self, method, u)
            p = resolve(rel)
            if u.path == "/api/still.jpg":
                q = parse_qs(u.query)
                return self.send_bytes(still(p, (q.get("t") or ["0"])[0], (q.get("w") or ["240"])[0]), "image/jpeg", cache=True)
            if u.path == "/media":
                return self.send_media(p)
            if u.path == "/api/info":
                return self.send_json(info_for(p))
            if u.path == "/api/analysis":
                return self.send_json(analysis(p))
            if u.path == "/api/sound" and method == "GET":
                return self.send_json(read_sound(p))
            if u.path == "/api/effects" and method == "GET":
                return self.send_json(read_effects(p))
            if u.path == "/api/filmstrip.jpg":
                f = cache_file(p, "strip.jpg")
                if not f.exists():
                    raise FileNotFoundError("filmstrip")
                return self.send_bytes(f.read_bytes(), "image/jpeg", cache=True)
            if u.path == "/api/notes":
                if method == "POST":
                    return self.send_json(change_notes(p, self.read_body()))
                return self.send_json(dict(read_notes(p), file=file_stamp(p)))
            if u.path == "/api/transcribe" and method == "POST":
                j = job(f"transcribe:{job_tag(p)}", lambda: transcribe(p))
                return self.send_json({"status": j["status"], "error": j.get("error")})
            self.send_json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except FileNotFoundError as e:
            self.send_json({"error": f"not found: {e}"}, 404)
        except PermissionError as e:
            self.send_json({"error": str(e)}, 403)
        except ValueError as e:
            self.send_json({"error": str(e)}, 400)
        except Exception as e:
            self.send_json({"error": str(e) or e.__class__.__name__}, 500)


def ping(port):
    try:
        with urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=0.6) as r:
            return json.loads(r.read())
    except Exception:
        return None


def main():
    global ROOT, PORT
    ap = argparse.ArgumentParser(description="Watch a cut, see its beats, leave timestamped notes.")
    ap.add_argument("target", nargs="?", help="library folder, or one video to open")
    ap.add_argument("--port", type=int, default=default_port())
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    open_rel = None
    ROOT = content_root()
    if a.target:
        t = Path(a.target).expanduser().resolve()
        if t.is_file():
            if ROOT not in t.parents:
                ROOT = t.parent
            open_rel = t.relative_to(ROOT).as_posix()
        elif t.is_dir():
            ROOT = t
        else:
            sys.exit(f"Not found: {t}")
    CACHE.mkdir(parents=True, exist_ok=True)
    if not ROOT.is_dir():
        print(f"Note: the content folder {ROOT} isn't there yet, so the library is empty. Make it, or set "
              "content_root in studio.json (START-HERE.md).", flush=True)

    srv = None
    for port in range(a.port, a.port + 20):
        running = ping(port)
        if running and running.get("app") == "video-review" and running.get("root") == str(ROOT) and running.get("version") == APP_VERSION:
            PORT = port
            break
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            PORT = port
            break
        except OSError:
            continue
    else:
        sys.exit("No free port found")

    url = f"http://127.0.0.1:{PORT}/" + (f"#/v/{quote(open_rel, safe='')}" if open_rel else "")
    if srv is None:
        print(f"Video Review is already running: {url}", flush=True)
        if not a.no_browser:
            webbrowser.open(url)
        return
    print(f"Video Review: {url}\nLibrary: {ROOT}\nPress Ctrl+C to stop.", flush=True)
    if not a.no_browser:
        threading.Timer(0.4, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
