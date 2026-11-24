#!/usr/bin/env python3
"""Build records: what a render shows and where its separate sound tracks are, kept by the builder at render time.

Every builder calls this at the end of a render (standard library only, so any Python on the Mac can load it):

    import buildrecord as BR                     # sys.path: <kit>/library
    rec = BR.Record("my_builder.py", inputs=[spec_path])
    rec.layout(t0, t1, "fastcut", "split", detail="hook panel")   # a layout, by the builder's own name (VOCAB below)
    rec.graphic(event)                           # a graphic dict: type, start, end, text… (VOCAB["graphics"])
    rec.effect("spotlight", 6.37, 8.89)          # a library effect
    rec.block(t0, t1, "Tag", detail="“Fresh”")   # anything else, by the name the Glossary uses
    rec.tags(t0, t1, [(0.4, "Fresh"), (1.2, "Local")])   # one scene's pop-in tags as one block
    rec.used(clip_path, 12.0, 15.5)              # the raw clip seconds this render shows (for the Footage Log)
    rec.song(music_path)                         # the song: its file, and its name (music.json in the music library)
    rec.track("voice_nat", [(nat_wav, 1.0)])     # a sound track: the files that add up to it, at their mix level
    rec.track("music", [(mix_wav, 1.0), (nat_wav, -1.0)])
    rec.track_cmd("music", ffmpeg_args)          # or an ffmpeg command whose output is the track (builders that mix
                                                 # in a temporary folder: the same filters, run again, one part only)
    rec.tracks_from(other_render)                # a picture-only re-render reuses another record's sound tracks
    rec.save(render_path)                        # writes <render>.build.json and <render>.tracks/, after the render

save() writes "<render file>.build.json" beside the render and small copies of each sound track (one channel, 8 kHz,
FLAC: enough to draw and check it, not to listen to) in "<render file>.tracks/", so the next render in the same work
folder can't overwrite them. It also adds a line to the build registry ("<content>/Footage Log/builds.jsonl"), which
the map tools search by picture and usage.py reads for the raw seconds each video used. When the render already sits
in the content folder (builders that export straight into a shoot), it also writes the sound and effects maps beside
it; save(render, keep_in=work_folder) then keeps the record in the work folder, so the shoot only gets the maps.

Nothing here may stop or change a render: every step is wrapped, a problem prints one plain line, and the render's
own files are only read. VS_BUILD_REGISTRY (a file) and VS_CONTENT_ROOT (a folder) point it elsewhere for tests.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent            # <kit>/library
STUDIO = HERE.parent                              # the kit
FORMAT_VERSION = 1
TRACK_RATE = 8000
ABOUT = ("Build record: what this render shows over each stretch, the raw clip seconds it used and where its separate "
         "sound tracks are, kept by the builder at render time (library/buildrecord.py). The sound and effects maps "
         "beside the finished video are made from it. t and len are seconds in the render.")
KINDS = ("voice", "voice_nat", "mix", "music", "nat")
TRACK_NAMES = {"voice": "Voice", "voice_nat": "Voice and footage sound", "mix": "Everything except the effects",
               "music": "Music", "nat": "Footage sound"}

# What each builder's own names mean on screen: label, Glossary entry (or None), detail. A name mapped to None is
# plain footage: no block. effects/effectsmap.py reads the same table. A builder with names of its own adds a table
# with register_vocab(); a vocab this table doesn't have falls back to "fastcut", and a name it doesn't know becomes a
# block labelled with that name (and a note in the record), so a record is never lost over a name.
VOCAB = {
    "fastcut": {        # Fast Cut: its scene layouts (STYLES.md, "Layouts")
        "split": ("Split screen", "Split screen", ""), "card": ("Card", "Card", ""),
        "card_split": ("Card", "Card", ""), "qcard": ("Card", "Card", "a quote"), "quote": ("Quote card", None, ""),
        "big": ("Big number", "Big number", ""), "explainer": ("Explainer", "Explainer", ""),
        "checklist": ("Check-list card", None, ""), "end": ("End card", "End card", ""),
        "mosaic": ("Mosaic", "Mosaic", ""), "punch": ("Punch-in", "Punch-in", ""), "tag": ("Tag", None, ""),
        "stack": ("Two camera views", None, "one camera above the other"),
        "graphic": ("Full-screen graphic", None, ""), "other": ("Graphic", None, ""), "full": None,
    },
    "talking-head": {   # Talking Head Classic: its shots
        "talk": None, "footage": None, "full": None, "punch": ("Punch-in", "Punch-in", ""), "broll": ("B-roll", None, ""),
        "split": ("Two camera views", None, "one camera above the other"), "speed": ("Time-lapse", None, ""),
        "title": ("Title box", None, ""), "counter": ("Rep counter", None, ""),
    },
    "hands-on": {       # Hands-On Classic: its shots
        "full": None, "footage": None, "slow": ("Slow motion", None, ""), "fast": ("Time-lapse", None, ""),
        "push": ("Push-in", None, ""), "dissolve": ("Dissolve", None, ""), "split": ("Two camera views", None, ""),
    },
    "shots": {          # any builder: how a shot is played
        "slow": ("Slow motion", None, ""), "fast": ("Time-lapse", None, ""), "push": ("Push-in", None, ""),
        "dissolve": ("Dissolve", None, ""), "full": None,
    },
    "graphics": {       # graphics drawn over the footage (Hands-On Classic and the looks built on it)
        "hook": ("Hook title", None, ""), "endcard": ("End card", None, ""), "lower_third": ("Lower third", None, ""),
        "title": ("Title card", None, ""), "route": ("Route line", None, ""), "chip": ("Time chip", None, ""),
        "tag": ("Tag", None, ""), "counter": ("Counter", None, ""), "quote": ("Quote card", None, ""),
        "label": ("Label", None, ""), "text": ("Text line", None, ""), "lockup": ("Logo lockup", None, ""),
    },
}
PLAIN = {   # one plain line for labels that have no Glossary entry
    "Quote card": "A quote in a floating card over the footage.",
    "Two camera views": "Both cameras at once, one above the other.",
    "Tag": "A short word or two that pops in over the footage.",
    "Tags": "Short words that pop in over the footage, one after another.",
    "Check-list card": "A small card whose lines tick off as they're said.",
    "Hook title": "The opening title over the first shot.",
    "End card": "The closing card: logo, a line and what to do next.",
    "Lower third": "A name and place in the lower part of the frame.",
    "Title card": "A full-screen title between chapters.",
    "Counter": "A number that counts up on screen.",
    "Time-lapse": "The footage sped up.",
    "Time chip": "A small time-and-place chip at the start of a chapter.",
    "Route line": "A line that moves from stop to stop on a simple map.",
    "Notebook note": "A handwritten marker note that follows what it points at.",
    "Order ticket": "A ticket that prints line by line and ticks each item off.",
    "Title box": "The white title box at the top of the frame.",
    "Label": "A small rounded label over the footage.",
    "Stats card": "The footage dims and big lines of text sit over it.",
    "B-roll": "Other footage over the voice.",
    "Rep counter": "A count, one number at a time, over the footage.",
    "Slow motion": "The footage slowed down.",
    "Push-in": "A slow zoom in over the whole shot.",
    "Dissolve": "One shot fades into the next.",
    "Logo lockup": "Two logos side by side over the footage.",
    "Text line": "A small line of white text over the footage.",
    "Dimmed footage": "The footage darkens so what's on top of it reads clearly.",
    "Fade out": "The picture fades to dark at the end.",
    "Full-screen graphic": "A graphic on a plain background, in place of the footage.",
    "Graphic": "Something drawn over or in place of the footage.",
}


def register_vocab(name, table, plain=None):
    """Add (or extend) a builder's own names: {key: (label, glossary entry or None, detail) or None}."""
    VOCAB.setdefault(name, {}).update(table)
    if plain:
        PLAIN.update(plain)


def _sc():
    """lib/studio_config.py (paths and settings), or None if it can't be loaded."""
    try:
        lib = str(STUDIO / "lib")
        if lib not in sys.path:
            sys.path.insert(0, lib)
        import studio_config
        return studio_config
    except Exception:
        return None


def say(msg):
    print(f"  [build record] {msg}", flush=True)


def content_root():
    if os.environ.get("VS_CONTENT_ROOT"):
        return Path(os.environ["VS_CONTENT_ROOT"]).expanduser().resolve()
    sc = _sc()
    try:
        return sc.content_root().expanduser().resolve() if sc else None
    except Exception:
        return None


FALLBACK_REGISTRY = Path.home() / ".cache" / "video-studio" / "builds.jsonl"


def registry_path():
    """Where build lines go: $VS_BUILD_REGISTRY, else <content>/Footage Log/builds.jsonl (when the content folder is
    there), else ~/.cache/video-studio/builds.jsonl."""
    if os.environ.get("VS_BUILD_REGISTRY"):
        return Path(os.environ["VS_BUILD_REGISTRY"]).expanduser()
    root = content_root()
    if root and root.is_dir():
        return root / "Footage Log" / "builds.jsonl"
    return FALLBACK_REGISTRY


def registry_paths():
    """Every registry to read: the one in use, and the fallback (a render made while the content folder was away)."""
    out = [registry_path()]
    if not os.environ.get("VS_BUILD_REGISTRY") and FALLBACK_REGISTRY not in out:
        out.append(FALLBACK_REGISTRY)
    return out


def registry_lines():
    """Every line of every registry, as dicts, oldest first."""
    out = []
    for reg in registry_paths():
        try:
            text = reg.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
    return sorted(out, key=lambda d: d.get("made", ""))


def append_registry(entry):
    reg = registry_path()
    reg.parent.mkdir(parents=True, exist_ok=True)
    with open(reg, "a") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_path(render):
    return Path(str(render) + ".build.json")


def stream_md5(p, which):
    r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(p), "-map", f"0:{which}:0", "-c", "copy",
                        "-f", "md5", "-"], capture_output=True, timeout=600)
    return r.stdout.decode().strip().replace("MD5=", "") if r.returncode == 0 else ""


def duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, timeout=120)
    return float(r.stdout.decode().strip() or 0)


def song_title(path):
    """The song's name: from music.json ({"<file name or stem>": "Title (Artist)"}) or tracks.csv (title, artist and
    file columns; without a file column, a title whose words are all in the file name) in the song's folder or in the
    music library (studio.json music_library); otherwise the file name, tidied."""
    p = Path(str(path).split("@")[0])
    stem = p.stem
    folders = [p.parent]
    sc = _sc()
    try:
        if sc:
            folders.append(sc.path("music_library"))
    except Exception:
        pass
    words = set(re.findall(r"[a-z0-9]+", stem.lower()))
    for folder in folders:
        try:
            table = json.loads((Path(folder) / "music.json").read_text())
        except (OSError, ValueError):
            table = None
        if isinstance(table, dict):
            for k in (p.name, stem):
                if isinstance(table.get(k), str) and table[k].strip():
                    return table[k].strip()
        try:                    # tracks.csv (setup/SOUND-LIBRARY.md): title, artist, and a file column if it has one
            import csv
            with open(Path(folder) / "tracks.csv", newline="") as fh:
                rows = [{(k or "").strip().lower(): (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]
        except (OSError, ValueError):
            rows = []
        for r in rows:
            title, artist = r.get("title", ""), r.get("artist", "")
            f = r.get("file") or r.get("filename") or r.get("file name") or ""
            tw = set(re.findall(r"[a-z0-9]+", title.lower()))
            if title and ((f and f in (p.name, stem)) or (not f and tw and tw <= words)):
                return title + (f" ({artist})" if artist else "")
    s = re.sub(r"[_]+", " ", re.sub(r"_(main|full|preview)\b", "", stem, flags=re.I)).replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


class Record:
    """Collects what a render shows and how its sound is made; save() writes it. No method ever raises."""

    def __init__(self, builder, inputs=()):
        self.builder, self.inputs = builder, [str(Path(p).resolve()) for p in inputs if p]
        self.blocks, self.tracks, self.track_cmds, self.song_info, self.notes = [], [], [], None, []
        self.clips = []

    def _guard(self, fn, *a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            self.notes.append(f"{fn.__name__}: {e}")

    def block(self, t0, t1, label, entry=None, detail="", key="", group="graphic"):
        def add():
            if t1 - t0 > 0.005:
                b = {"t": round(float(t0), 3), "len": round(float(t1) - float(t0), 3), "label": str(label)}
                if entry:
                    b["entry"] = entry
                if detail:
                    b["detail"] = str(detail)
                b["key"], b["group"] = str(key or label), group
                self.blocks.append(b)
        self._guard(add)

    def layout(self, t0, t1, vocab, key, detail=""):
        def add():
            table = VOCAB.get(vocab)
            if table is None:
                self.notes.append(f"no vocab '{vocab}' (using fastcut's names; add one with register_vocab)")
                table = VOCAB["fastcut"]
            v = table.get(key, "?")
            if v == "?":
                self.notes.append(f"no name for the {vocab} layout '{key}' (labelled '{key}'; add it with register_vocab)")
                v = (str(key).replace("_", " ").replace("-", " ").capitalize(), None, "")
            if v is None:
                return
            label, entry, d0 = v
            d = detail or d0
            last = self.blocks[-1] if self.blocks else None
            if (last and last["group"] == "scene" and last["label"] == label and last.get("detail", "") == d
                    and abs(last["t"] + last["len"] - t0) < 0.02):
                last["len"] = round(float(t1) - last["t"], 3)
                return
            self.block(t0, t1, label, entry, d, key, "scene")
        self._guard(add)

    def graphic(self, ev):
        def add():
            v = VOCAB["graphics"].get(ev.get("type"))
            if not v:
                return
            label, entry, _ = v
            if ev.get("type") == "chip":
                detail = " · ".join(x for x in (ev.get("time"), ev.get("place")) if x)
            else:
                detail = next((str(ev[k]).replace("|", " ") for k in ("text", "title", "lines") if ev.get(k)), "")
            self.block(ev["start"], ev["end"], label, entry, detail, ev["type"], "graphic")
        self._guard(add)

    def effect(self, name, t0, t1):
        self.block(t0, t1, name, name, "", name, "effect")

    def used(self, clip, t0, t1, approx=False):
        """The raw clip seconds this render shows, from t0 to t1 in the clip (not in the render). usage.py reads them,
        so the Footage Log can say which moments each video used. clip: its path (or file name)."""
        def add():
            a, b = float(t0), float(t1)
            if b - a > 0.01:
                c = {"clip": Path(str(clip)).name, "from": round(a, 2), "to": round(b, 2)}
                if Path(str(clip)).is_absolute() or os.sep in str(clip):
                    c["path"] = str(Path(clip).resolve())
                if approx:
                    c["approx"] = True
                self.clips.append(c)
        self._guard(add)

    def tags(self, t0, t1, tags):
        """The tags of one scene as one block, from the first tag until the scene ends. tags: [(seconds into the
        scene, text)]."""
        def add():
            tg = sorted((float(a), str(b)) for a, b in tags)
            if tg:
                self.block(t0 + tg[0][0], t1, "Tag" if len(tg) == 1 else "Tags", None,
                           ", ".join(f"\u201c{x}\u201d" for _, x in tg), "tags", "graphic")
        self._guard(add)

    def tracks_from(self, render):
        """Reuse the sound tracks another render's record kept (a picture-only re-render that copies its sound)."""
        def add():
            f = record_path(render)
            doc = json.loads(f.read_text())
            for t in doc.get("tracks") or []:
                self.track(t["kind"], [(f.parent / t["file"], 1.0)], t.get("name"))
            if doc.get("song"):
                self.song_info = doc["song"]
        self._guard(add)

    def song(self, path, title=None):
        """The song under the video. title: its name as you know it ("Title (Artist)"); without it, music.json or
        the file name."""
        def add():
            if path:
                p = str(path).split("@")[0]
                self.song_info = {"file": Path(p).name, "path": str(Path(p).resolve()), "title": title or song_title(p)}
        self._guard(add)

    def track(self, kind, parts, name=None):
        """parts: [(file, coefficient)]: the track is their sum, at the level it has in the mix."""
        self._guard(lambda: self.tracks.append({"kind": kind, "name": name or TRACK_NAMES[kind],
                                                "parts": [(str(Path(f).resolve()), float(c)) for f, c in parts]}))

    def track_cmd(self, kind, ffmpeg_args, name=None):
        """ffmpeg_args: inputs and a filter graph whose last output label is [out]: the track, as it was in the mix."""
        self._guard(lambda: self.tracks.append({"kind": kind, "name": name or TRACK_NAMES[kind], "cmd": list(map(str, ffmpeg_args))}))

    # ---------------------------------------------------------------- writing

    def _snapshot(self, t, folder):
        out = folder / f"{t['kind']}.flac"
        tmp = folder / f".{t['kind']}.tmp.flac"
        enc = ["-ac", "1", "-ar", str(TRACK_RATE), "-c:a", "flac", "-sample_fmt", "s32", str(tmp)]
        if "cmd" in t:
            args = ["ffmpeg", "-v", "error", "-y", "-nostdin", *t["cmd"], "-map", "[out]", *enc]
        else:
            ins = [x for f, _ in t["parts"] for x in ("-i", f)]
            g = ";".join(f"[{k}:a]aformat=channel_layouts=mono,volume={c:.6f}[p{k}]" for k, (_, c) in enumerate(t["parts"]))
            g += ";" + "".join(f"[p{k}]" for k in range(len(t["parts"]))) + \
                 f"amix=inputs={len(t['parts'])}:normalize=0:duration=longest[out]"
            args = ["ffmpeg", "-v", "error", "-y", "-nostdin", *ins, "-filter_complex", g, "-map", "[out]", *enc]
        r = subprocess.run(args, capture_output=True, timeout=900)
        if r.returncode != 0:
            err = r.stderr.decode(errors="replace").strip().splitlines()
            raise RuntimeError(err[-1] if err else "ffmpeg failed")
        os.replace(tmp, out)
        return out

    def save(self, render, maps=True, keep_in=None):
        """Write the record beside the render (or in keep_in, for builders whose render is already the finished file
        in the content folder, so the shoot only gets the two maps). Returns its path, or None (after one printed
        line) if it couldn't."""
        try:
            render = Path(render).resolve()
            if not render.is_file():
                say(f"not saved: the render {render.name} isn't there")
                return None
            home = Path(keep_in).resolve() if keep_in else render.parent
            home.mkdir(parents=True, exist_ok=True)
            folder = home / (render.name + ".tracks")
            tracks = []
            if self.tracks:
                folder.mkdir(exist_ok=True)
                for t in self.tracks:
                    try:
                        f = self._snapshot(t, folder)
                        tracks.append({"kind": t["kind"], "name": t["name"], "file": f"{folder.name}/{f.name}"})
                    except Exception as e:
                        self.notes.append(f"{t['kind']} track not kept: {e}")
            dur = duration(render)
            doc = {"about": ABOUT, "version": FORMAT_VERSION, "builder": self.builder,
                   "made": datetime.now().isoformat(timespec="seconds"), "render": render.name,
                   "render_path": str(render), "render_size": render.stat().st_size, "duration": round(dur, 3),
                   "picture_md5": stream_md5(render, "v"), "audio_md5": stream_md5(render, "a"),
                   "inputs": self.inputs, "song": self.song_info, "tracks": tracks, "clips": self.clips,
                   "blocks": sorted(self.blocks, key=lambda b: (b["t"], b["group"] != "scene"))}
            if self.notes:
                doc["notes"] = self.notes
            f = home / (render.name + ".build.json")
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n")
            os.replace(tmp, f)
            append_registry({"record": str(f), "render": str(render), "picture_md5": doc["picture_md5"],
                             "audio_md5": doc["audio_md5"], "duration": doc["duration"], "made": doc["made"]})
            say(f"saved {f.name}: {len(doc['blocks'])} things on screen, {len(tracks)} sound track{'' if len(tracks) == 1 else 's'}"
                + (f" ({len(self.notes)} problem(s): {self.notes[0]})" if self.notes else ""))
            root = content_root()
            if maps and root and root in render.parents:
                make_maps(render)
            return f
        except Exception as e:
            say(f"not saved ({e}); the render itself is fine")
            return None


def find_records(picture_md5):
    """Records whose render has this picture, newest first."""
    if not picture_md5:
        return []
    out = [d for d in registry_lines() if d.get("record") and d.get("picture_md5") == picture_md5
           and Path(d.get("record", "")).is_file()]
    return sorted(out, key=lambda d: d.get("made", ""), reverse=True)


def note_placed(dest, src=None):
    """finish.py calls this when it puts a file into a shoot: a registry line saying which render it came from, so
    usage.py can give the finished file its render's raw seconds."""
    try:
        dest = Path(dest).resolve()
        append_registry({"placed": str(dest), "from": str(Path(src).resolve()) if src else "",
                         "picture_md5": stream_md5(dest, "v"), "made": datetime.now().isoformat(timespec="seconds")})
    except Exception as e:
        say(f"placement not noted ({e})")


def first_record_time():
    for d in registry_lines():
        if d.get("record"):
            try:
                return datetime.fromisoformat(d["made"]).timestamp()
            except (KeyError, ValueError):
                continue
    return None


def make_maps(video, replace=False, quiet=False, which=("sound", "effects")):
    """Write both maps (or the ones named) beside a finished video from its build record. Returns {name: message};
    a message starting "ok: " means it was written."""
    res = {}
    for name, tool in (("sound", STUDIO / "sound" / "soundmap.py"), ("effects", STUDIO / "effects" / "effectsmap.py")):
        if name not in which:
            continue
        if not tool.is_file():
            res[name] = f"not made: {tool.relative_to(STUDIO)} isn't there"
            if not quiet:
                say(f"{name} map: {res[name]}")
            continue
        try:
            r = subprocess.run([sys.executable, "-I", str(tool), str(video), "--auto"] + (["--replace"] if replace else []),
                               capture_output=True, text=True, timeout=1800, env=os.environ.copy())
            out = (r.stdout + r.stderr).strip().splitlines()
            res[name] = ("ok: " if r.returncode == 0 else "") + (out[-1] if out else "no answer")
        except Exception as e:
            res[name] = f"Stopped: {e}"
        if not quiet:
            say(f"{name} map: {res[name]}")
    return res


def check_maps(root, rel_files, cache_file=None):
    """The safety net (run by footage.py index): for each video with no sound map or no effects map, write the
    missing one(s) from its build record. Quick when nothing is missing (it only looks for the two files beside each
    video); videos older than the first build record are only counted (they can't have one); a video that failed is
    not tried again until the file changes. Returns the lines to print."""
    cache_file = Path(cache_file or (Path.home() / ".cache" / "video-review" / "automaps.json"))
    try:
        cache = json.loads(cache_file.read_text())
    except (OSError, ValueError):
        cache = {}
    first = first_record_time()
    older, made, failed = 0, [], []
    for rel in rel_files:
        p = Path(root) / rel
        need = [k for k in ("sound", "effects") if not Path(f"{p}.{k}.json").exists()]
        if not need:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if first is None or st.st_mtime < first - 300:
            older += 1
            continue
        key = f"{rel}|{st.st_size}|{int(st.st_mtime)}|{','.join(need)}"
        if key in cache:
            failed.append((rel, cache[key]))
            continue
        res = make_maps(p, quiet=True, which=need)
        bad = {k: v for k, v in res.items() if not v.startswith("ok: ")}
        if bad:
            gist = {k: re.split(r"\s*[;(]", v.replace("Refused, nothing written: ", ""), maxsplit=1)[0] for k, v in bad.items()}
            why = (next(iter(gist.values())) if len(set(gist.values())) == 1
                   else "; ".join(f"{k} map: {g}" for k, g in gist.items()))
            cache[key] = why
            failed.append((rel, why))
        else:
            made.append(rel)
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=1))
    except OSError:
        pass
    lines = []
    if made:
        lines.append(f"Maps: made the missing sound or effects map for {len(made)} video(s): " + ", ".join(Path(r).name for r in made))
    if failed:
        lines.append(f"Maps: {len(failed)} video(s) still have no sound or effects row:")
        lines += [f"  - {Path(r).name}: {why}" for r, why in failed]
    if older:
        lines.append(f"Maps: {older} older video(s) have no rows; they were made before builders kept records "
                     "(sound/README.md and effects/README.md say how to make them by hand).")
    return lines
