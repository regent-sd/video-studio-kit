#!/usr/bin/env python3
"""Footage Log: what is in every raw clip, and what every finished video used.

  .venv/bin/python library/footage.py scan               every raw clip, and whether it has a transcript and a log card
  .venv/bin/python library/footage.py prep [name ...]    transcript + frame sheets + brief for clips with no log card (or the named ones)
  .venv/bin/python library/footage.py index              rebuild the log index, the video tracker and both CSVs in "<content>/Footage Log"
  .venv/bin/python library/footage.py check              list cards that are missing, broken, or leave gaps in a clip

A raw clip is any video inside a shoot's Raw/ folder, in any subfolder (Raw/Camera, Raw/POV, Raw/Phone, Raw/Screen or
one of your own); the subfolder's name is the clip's camera. A clip's log card is "<clip>.log.json" next to the clip,
and its transcript is "<clip>.words.txt" (the format Video Review reads). Frame sheets and briefs go to
~/.cache/footage-log and can be deleted. See README.md in this folder for the card format and the routine.

Settings (studio.json): content_root; whisper_model (default ~/.cache/whisper.cpp/ggml-base.en.bin);
whisper_language (default "en"); timezone (e.g. "America/New_York"; default: this Mac's); people (names of people
who often appear and have agreed to be filmed).
"""
import csv, datetime as dt, json, os, re, shutil, subprocess, sys, tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "lib"))
import studio_config as sc  # noqa: E402

ROOT = sc.content_root()
LOG_DIR = ROOT / "Footage Log"
WORK = Path.home() / ".cache" / "footage-log"
RAW_EXT = {".mp4", ".mov", ".m4v"}
OUT_EXT = {".mp4", ".mov", ".m4v"}
SKIP_TOP = {"_To Delete", "Footage Log", ".claude"}
OUTPUT_DIRS = {"Finished": "finished", "Style Tests": "style test", "Older Versions": "older version"}
STATUSES = ("in review", "ready to post", "scheduled", "posted", "shelved", "superseded")
ROLES = {"owner", "staff", "customer", "guest", "child"}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, check=True, **kw)


def local_tz():
    name = (sc.get("timezone") or "").strip()
    if name:
        try:
            from zoneinfo import ZoneInfo
            return ZoneInfo(name)
        except Exception:
            print(f"timezone '{name}' in studio.json isn't known; using this Mac's", file=sys.stderr)
    return dt.datetime.now().astimezone().tzinfo


# ---------------------------------------------------------------- finding clips

def is_raw(rel: Path):
    parts = rel.parts
    return (len(parts) > 2 and parts[0] not in SKIP_TOP and "Raw" in parts[1:-1]
            and rel.suffix.lower() in RAW_EXT and not rel.name.startswith("."))


def raw_clips():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_TOP)
        for f in sorted(filenames):
            p = Path(dirpath) / f
            if is_raw(p.relative_to(ROOT)):
                out.append(p)
    return out


def outputs():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_TOP)
        rel_dir = Path(dirpath).relative_to(ROOT)
        if len(rel_dir.parts) < 2 or rel_dir.parts[1] not in OUTPUT_DIRS:
            continue
        for f in sorted(filenames):
            if Path(f).suffix.lower() in OUT_EXT and not f.startswith("."):
                out.append(Path(dirpath) / f)
    return out


def find_clip(name):
    hits = [p for p in raw_clips() if p.name == name or p.stem == name or name in p.name]
    if len(hits) != 1:
        raise SystemExit(f"{name}: {len(hits)} matches")
    return hits[0]


def card_path(p): return Path(str(p) + ".log.json")
def words_path(p): return Path(str(p) + ".words.txt")
def rel(p): return str(Path(p).relative_to(ROOT))


def work_dir(p):
    d = WORK / (re.sub(r"[^A-Za-z0-9._-]+", "_", rel(p).split("/")[0]) + "__" + p.stem)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- facts about a clip

def camera_of(p, tags):
    """The Raw subfolder the clip is in (Camera, POV, Phone, Screen or your own name); for a clip straight in Raw/,
    the camera model the file names, else "Other"."""
    parts = Path(rel(p)).parts
    i = parts.index("Raw") if "Raw" in parts else -1
    if 0 <= i < len(parts) - 2:
        return parts[i + 1]
    for k in ("com.apple.quicktime.model", "model", "com.android.model", "make", "com.apple.quicktime.make"):
        if tags.get(k):
            return str(tags[k]).strip()[:40]
    return "Other"


def probe(p):
    j = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration:format_tags:stream=codec_type,codec_name,width,height,r_frame_rate,color_transfer:stream_side_data=rotation",
                        "-of", "json", str(p)]).stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    w, h = v.get("width", 0), v.get("height", 0)
    rot = 0
    for sd in v.get("side_data_list", []) or []:
        rot = int(sd.get("rotation", 0) or 0)
    if abs(rot) in (90, 270):
        w, h = h, w
    num, _, den = (v.get("r_frame_rate") or "0/1").partition("/")
    fps = round(float(num) / float(den or 1), 2) if float(den or 1) else 0
    tags = j["format"].get("tags", {})
    return {
        "duration": round(float(j["format"].get("duration", 0)), 2),
        "width": w, "height": h,
        "orientation": "vertical" if h > w else ("horizontal" if w > h else "square"),
        "fps": fps,
        "hdr": v.get("color_transfer") in ("arib-std-b67", "smpte2084"),
        "has_audio": any(s["codec_type"] == "audio" for s in j["streams"]),
        "camera": camera_of(p, tags),
        "recorded": recorded_at(p, tags),
    }


def recorded_at(p, tags):
    """When the clip was filmed, in local time: the file's own creation date (with its time zone), else a date and
    time written into the file name (many cameras do: 20260314_101112), else the container's UTC time."""
    s = tags.get("com.apple.quicktime.creationdate")
    if s:
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(local_tz()).replace(tzinfo=None).isoformat(timespec="seconds")
        except ValueError:
            pass
    m = re.search(r"(20\d{2})(\d{2})(\d{2})[_-]?(\d{2})(\d{2})(\d{2})", p.name)
    if m:
        try:
            return dt.datetime(*map(int, m.groups())).isoformat()
        except ValueError:
            pass
    s = tags.get("creation_time")
    if s:
        try:
            return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(local_tz()).replace(tzinfo=None).isoformat(timespec="seconds")
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------- transcripts

def whisper_model():
    return Path(os.path.expanduser(sc.get("whisper_model") or "~/.cache/whisper.cpp/ggml-base.en.bin"))


def can_transcribe():
    return bool(shutil.which("whisper-cli")) and whisper_model().is_file()


def read_words(f):
    words = []
    for line in Path(f).read_text(errors="replace").splitlines():
        m = re.match(r"\s*([\d.]+)-([\d.]+)\s+(.*)", line)
        if m:
            words.append((float(m.group(1)), float(m.group(2)), m.group(3)))
    return words


def write_words(p, words):
    words_path(p).write_text("".join(f"{a:.2f}-{b:.2f} {w}\n" for a, b, w in words))


def drop_sound_tags(words):
    """whisper.cpp writes non-speech as "(crowd murmuring)" or "[music]"; keep only spoken words."""
    out, depth = [], 0
    for w in words:
        t = w[2]
        opens, closes = t.count("(") + t.count("["), t.count(")") + t.count("]")
        if depth == 0 and opens == 0:
            out.append(w)
        depth = max(0, depth + opens - closes)
    return out


def whisper_words(p):
    """The clip's words with their times, [(start, end, word)], from whisper.cpp with DTW word timing."""
    model = whisper_model()
    if not can_transcribe():
        raise RuntimeError(f"needs whisper-cli and the model at {model} (setup/INSTALL.md)")
    lang = (sc.get("whisper_language") or "en").strip()
    m = re.match(r"ggml-(.+?)\.bin$", model.name)
    dtw = ["-dtw", m.group(1)] if m and m.group(1) in ("tiny", "tiny.en", "base", "base.en", "small", "small.en",
                                                       "medium", "medium.en", "large.v1", "large.v2", "large.v3",
                                                       "large.v3.turbo") else []
    with tempfile.TemporaryDirectory() as tmp:
        wav, out = Path(tmp) / "a.wav", Path(tmp) / "out"
        run(["ffmpeg", "-v", "error", "-y", "-i", str(p), "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
        run(["whisper-cli", "-m", str(model), "-f", str(wav), "-l", lang, *dtw, "-nfa", "-ojf", "-of", str(out), "-np"])
        d = json.loads(Path(str(out) + ".json").read_text(errors="replace"))
    words = []
    for seg in d.get("transcription", []):
        seg_end = seg["offsets"]["to"] / 1000
        for tok in seg.get("tokens", []):
            text = tok["text"]
            if text.startswith("[") or not text.strip():
                continue
            t = tok.get("t_dtw", -1) / 100
            if t < 0:
                t = tok["offsets"]["from"] / 1000
            if text.startswith(" ") or not words:
                words.append([t, seg_end, text.strip()])
            else:
                words[-1][2] += text
    for i in range(len(words) - 1):  # a word ends where the next begins (capped at its segment's end)
        if words[i + 1][0] > words[i][0]:
            words[i][1] = min(words[i][1], words[i + 1][0])
    return drop_sound_tags([tuple(w) for w in words])


def transcript(p, info):
    """Make <clip>.words.txt if it's missing."""
    wp = words_path(p)
    if wp.exists():
        return "existing"
    if not info["has_audio"]:
        wp.write_text("")
        return "no audio"
    if not can_transcribe():
        return f"none (needs whisper-cli and {whisper_model()})"
    write_words(p, whisper_words(p))
    return f"whisper.cpp {whisper_model().stem.replace('ggml-', '')}"


def lines_of(words, gap=0.7, longest=14.0):
    """Group words into spoken lines: [(start, end, text)]."""
    out, cur = [], []
    for w in words:
        if cur and (w[0] - cur[-1][1] > gap or w[1] - cur[0][0] > longest or re.search(r"[.?!]$", cur[-1][2])):
            out.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
            cur = []
        cur.append(w)
    if cur:
        out.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
    return out


# ---------------------------------------------------------------- frame sheets

COLS, ROWS = 5, 4


def frame_interval(d):
    base = 2 if d <= 60 else 4 if d <= 300 else 6 if d <= 900 else 10
    return max(base, d / 240)  # at most ~240 frames (12 sheets) per clip


def fmt(t):
    t = max(0, t)
    return f"{int(t // 60)}:{t % 60:04.1f}"


def sheets(p, info, wd):
    from PIL import Image, ImageDraw, ImageFont
    fdir = wd / "frames"
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir()
    step = frame_interval(info["duration"])
    vert = info["orientation"] == "vertical"
    tw, th = (216, 384) if vert else (384, 216)
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-skip_frame", "nokey", "-i", str(p), "-an",
                        "-vf", f"select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,{step:.2f})',scale={tw}:{th}:force_original_aspect_ratio=decrease,showinfo",
                        "-fps_mode", "vfr", "-q:v", "4", str(fdir / "f%05d.jpg")], capture_output=True)
    times = [float(x) for x in re.findall(rb"pts_time:\s*([\d.]+)", r.stderr)]
    files = sorted(fdir.glob("f*.jpg"))
    times = times[:len(files)]
    font = None
    for f, i in (("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0), sc.SYSTEM_FONTS["SF Pro"]):
        try:
            font = ImageFont.truetype(f, 20, index=i)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default()
    for old in wd.glob("sheet_*.jpg"):
        old.unlink()
    out, per = [], COLS * ROWS
    for k in range(0, len(files), per):
        chunk = list(zip(files[k:k + per], times[k:k + per]))
        sheet = Image.new("RGB", (COLS * tw, -(-len(chunk) // COLS) * th), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)
        for i, (f, t) in enumerate(chunk):
            im = Image.open(f)
            x, y = (i % COLS) * tw, (i // COLS) * th
            sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            label = fmt(t)
            bw = draw.textlength(label, font=font) + 10
            draw.rectangle([x, y, x + bw, y + 26], fill=(0, 0, 0))
            draw.text((x + 5, y + 2), label, fill=(255, 220, 0), font=font)
        sp = wd / f"sheet_{k // per + 1:02d}.jpg"
        sheet.save(sp, quality=82)
        out.append((sp, chunk[0][1], chunk[-1][1]))
    shutil.rmtree(fdir)
    return out, step


def prep(p):
    wd = work_dir(p)
    info = probe(p)
    how = transcript(p, info)
    shs, step = sheets(p, info, wd)
    words = read_words(words_path(p)) if words_path(p).exists() else []
    lines = lines_of(words)
    b = [f"# {p.name}", "",
         f"- File: {rel(p)}",
         f"- Shoot: {rel(p).split('/')[0]}",
         f"- Camera: {info['camera']}   Recorded: {info['recorded']}",
         f"- Length: {fmt(info['duration'])} ({info['duration']} s), {info['width']}x{info['height']} {info['orientation']}, {info['fps']} fps"
         + (", HDR (HLG: frames look flat/grey, that's normal)" if info["hdr"] else ""),
         f"- Transcript: {how}; {len(words)} words. Word times can be off by about half a second.",
         f"- Frame sheets: one frame every {step:.1f} s (yellow label = time in the clip, m:ss.s)", ""]
    for sp, a, z in shs:
        b.append(f"  - {sp}  ({fmt(a)} to {fmt(z)})")
    b += ["", "## What's said", ""]
    b += [f"[{fmt(a)}-{fmt(z)}] {t}" for a, z, t in lines] or ["(no speech found)"]
    b += ["", "## Card", "",
          f"Write {card_path(p).name} next to the clip, in the format in library/README.md (\"Log card format\").",
          f"Use camera {json.dumps(info['camera'])}, recorded {json.dumps(info['recorded'])}, duration {info['duration']}, "
          f"orientation {json.dumps(info['orientation'])}."]
    (wd / "brief.md").write_text("\n".join(b) + "\n")
    (wd / "probe.json").write_text(json.dumps(info, indent=1))
    return p, how, len(shs)


# ---------------------------------------------------------------- index + tracker

def load_cards():
    cards = []
    for p in raw_clips():
        cp = card_path(p)
        if cp.exists():
            try:
                c = json.load(open(cp))
            except json.JSONDecodeError as e:
                print(f"BAD CARD {cp}: {e}", file=sys.stderr)
                continue
            c["path"] = rel(p)
            cards.append(c)
    return cards


def usage_file():
    return LOG_DIR / "usage.json"


def load_usage():
    """Which seconds of which raw clip each output used: Footage Log/usage.json, written by usage.py."""
    f = usage_file()
    try:
        return json.load(open(f)) if f.exists() else {}
    except (OSError, ValueError):
        return {}


TRACK_FIELDS_KEEP = ("title", "status", "posted_on", "post_url", "platform", "notes", "brand", "style")


def guess_platform(p):
    parts = rel(p).split("/")
    if "YouTube" in parts:
        return "YouTube"
    if "TikTok" in parts:
        return "TikTok"
    return "Instagram Reel"


def shoot_brands(cards):
    """The brand most of a shoot's log cards name, per shoot."""
    by = {}
    for c in cards:
        if c.get("brand"):
            by.setdefault(c.get("shoot") or c["path"].split("/")[0], Counter())[c["brand"]] += 1
    return {s: n.most_common(1)[0][0] for s, n in by.items()}


def tracker(usage, cards=None):
    tf = LOG_DIR / "video-tracker.json"
    old = json.load(open(tf))["videos"] if tf.exists() else []
    by_file = {v["file"]: v for v in old}
    by_name = {Path(v["file"]).name: v for v in old}
    brands = shoot_brands(cards if cards is not None else load_cards())
    default_brand = sc.load().get("default_brand") or ""
    vids = []
    for p in outputs():
        r = rel(p)
        prev = by_file.get(r) or by_name.get(p.name) or {}
        kind = OUTPUT_DIRS[r.split("/")[1]]
        try:
            info = probe(p)
        except Exception:
            info = {"duration": 0, "orientation": "?"}
        stem = p.name
        side = lambda suffix_re: sorted(x.name for x in p.parent.iterdir()
                                        if re.search(suffix_re, x.name, re.I) and _same_video(x.name, stem))
        v = {
            "file": r,
            "title": prev.get("title") or re.sub(r"[_-]+", " ", p.stem),
            "shoot": r.split("/")[0],
            "kind": kind,
            "brand": prev.get("brand") or brands.get(r.split("/")[0]) or default_brand,
            "platform": prev.get("platform") or guess_platform(p),
            "style": prev.get("style", ""),
            "status": prev.get("status") or {"finished": "ready to post", "style test": "in review", "older version": "superseded"}[kind],
            "posted_on": prev.get("posted_on", ""),
            "post_url": prev.get("post_url", ""),
            "length": round(info["duration"], 1),
            "caption_file": next(iter(side(r"(caption|description).*\.txt$")), ""),
            "cover_files": side(r"(cover|thumbnail).*\.(jpe?g|png)$"),
            "clips_used": usage.get(p.name, {}).get("clips", []),
            "built_by": usage.get(p.name, {}).get("built_by", ""),
            "notes": prev.get("notes", ""),
        }
        if kind == "older version":
            v["status"] = prev.get("status") if prev.get("status") in ("superseded", "posted") else "superseded"
        vids.append(v)
    order = {s: i for i, s in enumerate(STATUSES)}
    vids.sort(key=lambda v: (v["shoot"], order.get(v["status"], 9), v["file"]))
    doc = {"about": "Every finished video, style test and older version in the content folder. footage.py index keeps the "
                    "file list, lengths, covers and clips_used up to date; status, posted_on, post_url, title, brand, style "
                    "and notes are kept as you set them. Statuses: " + ", ".join(STATUSES) + ".",
           "updated": dt.datetime.now().isoformat(timespec="seconds"), "videos": vids}
    tf.write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    write_tracker_csv(vids)
    return vids


def write_tracker_csv(vids):
    """Video Tracker.csv in Footage Log: the tracker as a sheet (opens in Numbers, Excel or Google Sheets)."""
    with open(LOG_DIR / "Video Tracker.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Shoot", "Title", "Status", "Kind", "Brand", "Platform", "Style", "Length (s)", "Posted on", "Post URL",
                    "Caption file", "Cover", "Clips used", "Notes", "File"])
        for v in vids:
            w.writerow([v["shoot"], v["title"], v["status"], v["kind"], v["brand"], v["platform"], v["style"], v["length"],
                        v["posted_on"], v["post_url"], v["caption_file"], "; ".join(v["cover_files"]),
                        "; ".join(f"{c['clip']} {fmt(c['from'])}-{fmt(c['to'])}" for c in v["clips_used"]), v["notes"], v["file"]])


def _same_video(side_name, video_name):
    """A cover / thumbnail / caption / description belongs to a video when the video's name (minus extension,
    "(captioned)"-style suffixes and version) starts the side file's name and a marker word follows."""
    if Path(side_name).suffix.lower() in OUT_EXT or side_name.lower().endswith(".srt"):
        return False
    if side_name.lower().startswith("instagram captions") and re.search(r"reel", video_name, re.I):
        return True  # one captions file for all the reels in the folder
    base = re.sub(r"\.(mp4|mov|m4v)$", "", video_name, flags=re.I)
    base = re.sub(r"\s*\((captioned|clean|text|camera cuts|side by side)\)$", "", base)
    base = re.sub(r"[-_ ]v\d+$", "", base)
    base = re.sub(r"-YouTube-Cut$", "-YouTube", base)
    if not side_name.startswith(base):
        return False
    return bool(re.match(r"^[\s_-]*(v\d+[\s_-]*)?(cover|thumbnail|caption|description)", side_name[len(base):], re.I))


def index():
    if not ROOT.is_dir():
        sys.exit(f"The content folder {ROOT} isn't there. Make it, or set content_root in studio.json.")
    LOG_DIR.mkdir(exist_ok=True)
    usage = load_usage()
    cards = load_cards()
    vids = tracker(usage, cards)
    used_in = {}
    for v in vids:
        for c in v["clips_used"]:
            used_in.setdefault(c["clip"], []).append({"video": Path(v["file"]).name, "file": v["file"], "status": v["status"],
                                                      "from": c["from"], "to": c["to"]})
    for c in cards:
        dur = c.get("duration") or 0
        uses = []
        for u in used_in.get(c.get("clip"), []):
            a, z = max(0.0, u["from"]), min(dur, u["to"]) if dur else u["to"]
            if z - a > 0.05:  # a builder can point a little past the end of a clip
                uses.append(dict(u, **{"from": round(a, 2), "to": round(z, 2)}))
        c["used_in"] = uses
        spans = sorted((u["from"], u["to"]) for u in uses if u["status"] != "superseded")
        total, end = 0.0, 0.0
        for a, z in spans:  # each second counts once, however many videos used it
            if z > end:
                total += z - max(a, end)
                end = z
        c["used_seconds"] = round(total, 1)
    doc = {"about": "Generated by library/footage.py index from the <clip>.log.json cards. Edit the cards, not this.",
           "updated": dt.datetime.now().isoformat(timespec="seconds"), "clips": cards}
    (LOG_DIR / "footage-log.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
    with open(LOG_DIR / "Footage Log.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Shoot", "Clip", "Camera", "Recorded", "Start", "End", "What happens", "Said", "People", "Tags",
                    "Good for", "Flags", "Best still", "Used in", "File"])
        for c in cards:
            ui = "; ".join(sorted({u["video"] for u in c["used_in"]}))
            for m in c.get("moments", []):
                w.writerow([c.get("shoot"), c.get("clip"), c.get("camera"), c.get("recorded"), fmt(m.get("start", 0)),
                            fmt(m.get("end", 0)), m.get("what", ""), m.get("said", ""), ", ".join(m.get("people", c.get("people", []))),
                            ", ".join(m.get("tags", [])), ", ".join(m.get("use_for", [])), ", ".join(m.get("flags", [])),
                            fmt(m["best_still"]) if m.get("best_still") is not None else "", ui, c["path"]])
    print(f"{len(cards)} clips logged, {sum(len(c.get('moments', [])) for c in cards)} moments; {len(vids)} videos tracked")
    try:   # the safety net: any tracked video without its sound or effects map gets them from its build record
        sys.path.insert(0, str(HERE))
        import buildrecord
        for line in buildrecord.check_maps(ROOT, [v["file"] for v in vids]):
            print(line)
    except Exception as e:
        print(f"Maps: not checked ({e})")


CARD_KEYS = ("clip", "shoot", "brand", "camera", "recorded", "duration", "summary", "people", "tags", "moments")


def known_people():
    """Who a card may name: you (owner in studio.json), the people listed in studio.json, and the roles."""
    names = set(ROLES)
    if sc.owner(""):
        names.add(sc.owner(""))
    names.update(str(x) for x in (sc.get("people") or []) if str(x).strip())
    return names


def check():
    """Problems in the log cards: missing fields, moments outside the clip, gaps, overlaps, unknown people."""
    bad = 0
    people = known_people()
    for p in raw_clips():
        cp = card_path(p)
        if not cp.exists():
            print(f"NO CARD   {rel(p)}")
            bad += 1
            continue
        try:
            c = json.load(open(cp))
        except json.JSONDecodeError as e:
            print(f"BAD JSON  {rel(p)}: {e}")
            bad += 1
            continue
        probs = [f"missing {k}" for k in CARD_KEYS if k not in c]
        if c.get("clip") != p.name:
            probs.append(f"clip is {c.get('clip')!r}")
        dur = c.get("duration") or 0
        ms = sorted(c.get("moments", []), key=lambda m: m.get("start", 0))
        if not ms:
            probs.append("no moments")
        last = 0.0
        for m in ms:
            a, b = m.get("start"), m.get("end")
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)) or b <= a:
                probs.append(f"bad times {a}-{b}")
                continue
            if b > dur + 1.0:
                probs.append(f"moment {fmt(a)}-{fmt(b)} runs past the end ({fmt(dur)})")
            if a > last + 3.0:
                probs.append(f"gap {fmt(last)}-{fmt(a)}")
            if a < last - 1.0:
                probs.append(f"overlap at {fmt(a)}")
            last = max(last, b)
            for who in m.get("people", []):
                if who not in people:
                    probs.append(f"unknown person {who!r} (a regular? add them to people in studio.json)")
            if not m.get("what"):
                probs.append(f"moment {fmt(a)} has no 'what'")
        if ms and dur - last > 3.0:
            probs.append(f"last moment ends at {fmt(last)} of {fmt(dur)}")
        if probs:
            bad += 1
            print(f"PROBLEMS  {rel(p)}: " + "; ".join(sorted(set(probs))[:8]))
    print(f"{bad} clip(s) need attention" if bad else "all cards look right")
    return 1 if bad else 0


# ---------------------------------------------------------------- main

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"
    if cmd in ("scan", "prep", "index", "check") and not ROOT.is_dir():
        sys.exit(f"The content folder {ROOT} isn't there. Make it, or set content_root in studio.json (START-HERE.md).")
    if cmd == "scan":
        clips = raw_clips()
        for p in clips:
            print(f"{'card' if card_path(p).exists() else '----'} {'words' if words_path(p).exists() else '-----'}  {rel(p)}")
        print(f"{len(clips)} raw clips, {sum(card_path(p).exists() for p in clips)} logged")
    elif cmd == "prep":
        names = sys.argv[2:]
        clips = [find_clip(n) for n in names] if names else [p for p in raw_clips() if not card_path(p).exists()]
        if not clips:
            print("Every raw clip has a log card. Name clips to prep them again.")
        # whisper.cpp uses the GPU, so transcription is the slow part; frame sheets run alongside
        with ThreadPoolExecutor(3) as ex:
            for p, how, n in ex.map(prep, clips):
                print(f"{p.name}: transcript {how}; {n} sheets -> {work_dir(p) / 'brief.md'}", flush=True)
    elif cmd == "index":
        index()
    elif cmd == "check":
        sys.exit(check())
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
