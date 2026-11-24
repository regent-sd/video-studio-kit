#!/usr/bin/env python3
"""Sound map: a finished video's separate sound tracks, saved beside it for Video Review's timeline.

Video Review normally shows one "Sound" row: the finished video's mixed sound. A sound map lets it show one row per
track instead (voice, music, footage sound, sound effects), with the song's name and every sound effect at its time.
The map is a small file next to the video, "<video file>.sound.json". It holds the waveform of each track, worked out
here once, so no audio is copied into the shoot and the timeline never needs the work folder.

    .venv/bin/python -I sound/soundmap.py VIDEO [--auto]        from the build record (the usual way)
    .venv/bin/python -I sound/soundmap.py VIDEO --work FOLDER [--music-title "Song (Artist)"]
    .venv/bin/python -I sound/soundmap.py VIDEO --cues RESOLVED_CUES.json [track files] [--music-title "Song (Artist)"]
    .venv/bin/python -I sound/soundmap.py VIDEO --show

--work FOLDER   the builder's work folder. The tool finds the Real SFX run whose finished sound is exactly this
                video's sound, then the separate files that run was made from (see "What it reads" below).
--cues FILE     a Real SFX "*_resolved_cues.json" for this video, with the track files named by hand:
  --voice F         the voice alone
  --nat F           the footage's own sound alone (no voice)
  --voice-nat F     voice and footage sound together in one file
  --music F         the music as it plays in the mix (with --music-minus: the mix the music is in)
  --music-minus F   take this file away from --music, for builders that save the mix before and after the music
  --mix F           everything except the effects in one file (default: the cue file's original_audio)
  --mix-name NAME   what that one file holds, in plain words (default "Everything except the effects")
  --sfx-track F     the sound effects alone (default: the cue file's sfx_ducked, else its sfx_track)
--music-title T  the song's name as you know it, shown on the music row
--dry-run        check everything and report, write nothing
--replace        overwrite a map that is already there
--show           print what the map beside VIDEO holds

--auto (the default when no --work or --cues is given): the builder's own record. The kit's builders keep one at
render time (library/buildrecord.py): "<render>.build.json" with small copies of each sound track at its level in the
mix, and the song's name. The tool finds the record whose render has this video's picture (the build registry,
"<content>/Footage Log/builds.jsonl"), then the Real SFX run made from that render whose finished file has this
video's exact sound (or none, when the video kept the render's own sound). With --work, a record beside the run's
render is preferred too.

What it reads (--work, without a record):
  - a Real SFX run mixed from separate files named voice.wav, nat.wav and music.wav (its base_audio): those three
    are the tracks;
  - else nat_n.wav and mix_raw.wav beside the version without effects: nat_n.wav is the voice and footage sound
    together, and the music is mix_raw.wav minus nat_n.wav;
  - else the run's original_audio (the render without effects) as one row, plus the effects.
  The effects row is always the run's sfx_ducked.wav (the effects as they went into the mix) and its cue list.

Checks, and it refuses (writes nothing) when one fails:
  - every track, and the cue file, is as long as the video (within 0.15 s);
  - the tracks add up to the video's own sound: the tool finds each track's level in the finished mix and the result
    must account for at least 97% of the video's sound energy. Files from another version fail here.
  - with --work, the run's finished file must have exactly the same sound as the video (bit for bit).

It only ever writes "<video file>.sound.json". It never changes a video, a notes file or a work folder, and it
refuses videos in a Raw folder. Standard library only; needs ffmpeg and ffprobe.
"""
import argparse
import json
import math
import operator
import os
import re
import subprocess
import sys
from array import array
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDIO = HERE.parent                    # the kit
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
LEN_TOL = 0.15          # seconds a track may differ from the video
MIN_FIT = 0.97          # share of the video's sound energy the tracks must account for
GAIN_RANGE = 20.0       # dB: a fitted level outside +-this means the file doesn't belong to the mix
MAX_LOCAL = 0.5         # in any quarter second, the unexplained sound must stay under half of what plays there
FORMAT_VERSION = 1
ABOUT = ("Sound map for Video Review: the separate sound tracks of this video, as waveform peaks (0-100, square root, "
         "one shared scale for all the tracks of this video, each track at its level in the finished mix), plus "
         "every sound effect. Made by sound/soundmap.py; safe to delete (the timeline then shows one "
         "mixed sound row).")

KINDS = ("voice", "voice_nat", "mix", "music", "nat", "sfx")      # the timeline's row order
NAMES = {"voice": "Voice", "voice_nat": "Voice and footage sound", "mix": "Everything except the effects",
         "music": "Music", "nat": "Footage sound", "sfx": "Sound effects"}
LIBRARIES = {"starter_cc0": "Starter CC0", "uisfx": "uisfx (interface sounds)",
             "earshot_bank": "Earshot Bank (made in code)"}   # other Real SFX library ids show tidied


class Refuse(Exception):
    """A check failed: nothing is written, and the message says why in plain words."""


def run(cmd, timeout=900):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace").strip().splitlines()
        raise RuntimeError(f"{cmd[0]} failed: {err[-1] if err else 'no message'}")
    return r


def rel_studio(p):
    p = Path(p).resolve()
    try:
        return p.relative_to(STUDIO).as_posix()
    except ValueError:
        return str(p)


def probe(p):
    """Length of the file and of its first sound stream, in seconds (None when it has no sound)."""
    r = run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(p)], timeout=120)
    d = json.loads(r.stdout or b"{}")
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    total = float(d.get("format", {}).get("duration") or 0)
    alen = float(a.get("duration") or total) if a else None
    return total, alen


def audio_md5(p):
    """Checksum of the first sound stream as stored (not decoded): equal only when the sound is the same bits."""
    r = run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(p), "-map", "0:a:0", "-c", "copy", "-f", "md5", "-"])
    return r.stdout.decode().strip()


def decode(p, sr, n):
    """The file's sound as mono floats at sr, cut or padded to n samples."""
    r = run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(p), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(sr),
             "-f", "f32le", "-"])
    x = array("f")
    x.frombytes(r.stdout[: len(r.stdout) // 4 * 4])
    if sys.byteorder == "big":
        x.byteswap()
    if len(x) < n:
        x.extend([0.0] * (n - len(x)))
    return x[:n]


def dot(x, y):
    return math.fsum(map(operator.mul, x, y))


def solve(a, b):
    """Gaussian elimination with partial pivoting for a small square system."""
    k = len(b)
    m = [list(a[i]) + [b[i]] for i in range(k)]
    for c in range(k):
        piv = max(range(c, k), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-12:
            raise Refuse("two of the track files hold the same sound, so their levels can't be told apart")
        m[c], m[piv] = m[piv], m[c]
        for r in range(k):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [m[r][j] - f * m[c][j] for j in range(k + 1)]
    return [m[i][k] / m[i][i] for i in range(k)]


def fit_levels(tracks, target):
    """Each track's gain in the finished mix (least squares), and the share of the video's sound energy explained."""
    e_t = dot(target, target)
    if e_t <= 0:
        raise Refuse("the video is silent")
    live = [i for i, x in enumerate(tracks) if dot(x, x) > e_t * 1e-7]
    gains = [None] * len(tracks)
    if live:
        xs = [tracks[i] for i in live]
        a = [[dot(xs[i], xs[j]) for j in range(len(xs))] for i in range(len(xs))]
        b = [dot(x, target) for x in xs]
        g = solve(a, b)
        resid = e_t - 2 * sum(gi * bi for gi, bi in zip(g, b)) + sum(
            g[i] * g[j] * a[i][j] for i in range(len(g)) for j in range(len(g)))
        explained = 1 - max(0.0, resid) / e_t
        for i, gi in zip(live, g):
            gains[i] = gi
    else:
        explained = 0.0
    known = [g for g in gains if g is not None]
    for i in range(len(gains)):             # a silent track: no level to find; give it the others' typical level
        if gains[i] is None:
            gains[i] = sorted(known)[len(known) // 2] if known else 1.0
    return gains, explained


def local_check(xs, gains, target, sr, win=0.25):
    """The worst quarter second: the sound the tracks don't account for, against what plays there (in the video or
    in the tracks, whichever is louder). A sound in one and not the other gives about 1 or more; a true match stays
    well under MAX_LOCAL. Quarters quieter than -60 dB are skipped."""
    n, w = len(target), max(1, int(win * sr))
    model = array("f", [0.0] * n)
    for x, g in zip(xs, gains):
        model = array("f", map(lambda m, v, g=g: m + g * v, model, x))
    worst, at = 0.0, 0.0
    for i in range(0, n, w):
        tv, mv = target[i:i + w], model[i:i + w]
        ev, em = dot(tv, tv), dot(mv, mv)
        er = math.fsum((a - b) ** 2 for a, b in zip(tv, mv))
        floor = max(ev, em)
        if floor > len(tv) * 1e-6 and er / floor > worst:
            worst, at = er / floor, i / sr
    return worst, at


def bucket_step(sr, dur):
    return max(1, int(sr * max(0.01, dur / 12000)))   # the same bucket as Video Review's mixed sound row


def peaks_of(x, g, step):
    ag = abs(g)
    return [ag * max(max(x[i:i + step]), -min(x[i:i + step])) for i in range(0, len(x), step)]


def nice_song(path):
    s = Path(path).stem
    s = re.sub(r"_(main|full|preview)\b", "", s, flags=re.I)
    s = re.sub(r"[_]+", " ", s).replace("-", " ")
    return re.sub(r"\s+", " ", s).strip()


def cue_entries(cues):
    out = []
    for c in cues:
        src = c.get("slice_of") or c.get("file") or ""
        stem = Path(src).stem
        label = str(c.get("label") or "")
        if " - " in stem:
            name = stem.split(" - ", 1)[1]
        elif label and not re.fullmatch(r"[a-z]+( x[\d.]+)?", label):
            name = label
        else:
            name = stem
        name = re.sub(r"_\d+_\d+$", "", name).replace("_", " ").strip()
        name = name[:1].upper() + name[1:]
        start = float(c.get("start", c.get("t", 0)))
        e = {"t": round(start, 3), "len": round(float(c.get("seg") or 0.1), 3), "at": round(float(c.get("t", start)), 3),
             "name": name, "what": re.sub(r"\s+x[\d.]+$", "", label) or (c.get("role") or ""),
             "file": Path(src).name}
        if c.get("peak_after_db") is not None:
            e["level_db"] = round(float(c["peak_after_db"]), 1)
        lid = str(c.get("library") or c.get("source") or "")
        lib = LIBRARIES.get(lid) or (lid.replace("_", " ").replace("-", " ").strip().capitalize() if lid else "")
        if lib:
            e["from"] = lib
        out.append(e)
    out.sort(key=lambda e: (e["t"], e["at"]))
    return out


def find_run(work, video_md5):
    """The Real SFX run in the work folder (or one level down) whose finished file has this video's exact sound."""
    work = Path(work)
    found = sorted(set(work.glob("*_resolved_cues.json")) | set(work.glob("*/*_resolved_cues.json")))
    if not found:
        raise Refuse(f"there is no Real SFX run (*_resolved_cues.json) in {work} or the folders just inside it")
    hits = []
    for f in found:
        try:
            d = json.loads(f.read_text())
        except ValueError:
            continue
        out = d.get("output")
        if out and Path(out).is_file() and audio_md5(out) == video_md5:
            hits.append((f, d))
    if not hits:
        raise Refuse(f"none of the {len(found)} Real SFX runs in {work} made this video's sound (no finished file "
                     "of theirs has exactly the same sound). If the video was mixed another way, name the files with "
                     "--cues and the track options.")
    if len(hits) > 1:
        raise Refuse("more than one Real SFX run made this exact sound: " + ", ".join(str(h[0]) for h in hits)
                     + ". Pick one with --cues.")
    return hits[0]


def plan_from_run(cue_path, d, mix_name):
    """The track files a Real SFX run was made from (see 'What it reads' at the top)."""
    tracks = []
    base = d.get("base_audio") or []
    if base:
        for f in base:
            kind = {"voice.wav": "voice", "nat.wav": "nat", "music.wav": "music"}.get(Path(f).name)
            if not kind:
                raise Refuse(f"the run was mixed from {f}, and the tool doesn't know what that file holds")
            tracks.append({"kind": kind, "file": f})
    else:
        nofx = Path(d.get("video") or "")
        nat_n, mix_raw = nofx.parent / "nat_n.wav", nofx.parent / "mix_raw.wav"
        if nat_n.is_file() and mix_raw.is_file():
            tracks.append({"kind": "voice_nat", "file": str(nat_n)})
            tracks.append({"kind": "music", "file": str(mix_raw), "minus": str(nat_n)})
        else:
            orig = d.get("original_audio") or d.get("video")
            if not orig or not Path(orig).is_file():
                raise Refuse(f"the run's sound without effects ({orig}) is missing")
            tracks.append({"kind": "mix", "file": orig, "name": mix_name})
    tracks.append({"kind": "sfx", "file": sfx_file(d, cue_path)})
    return tracks


def sfx_file(d, cue_path):
    for f in (d.get("sfx_ducked"), str(cue_path).replace("_resolved_cues.json", "_sfx_ducked.wav"),
              str(cue_path).replace("_resolved_cues.json", "_sfx_track.wav")):
        if f and Path(f).is_file():
            return f
    raise Refuse(f"the effects track of {cue_path} is missing")


def best_lag(xs, target, sr, most=0.02):
    """The small delay (in samples, up to `most` seconds either way) that lines the tracks up best with the video's
    sound: a limiter's look-ahead in the final step can delay the whole mix by a few milliseconds."""
    n = min(len(target), int(30 * sr))
    mix = [math.fsum(v) for v in zip(*(x[:n] for x in xs))] if len(xs) > 1 else list(xs[0][:n])
    t = target[:n]
    best, best_c = 0, -2.0
    em = dot(mix, mix)
    for lag in range(-int(most * sr), int(most * sr) + 1):
        a, b = (t[lag:], mix[:n - lag]) if lag >= 0 else (t[:n + lag], mix[-lag:])
        c = dot(a, b) / math.sqrt(max(1e-12, dot(a, a) * em))
        if c > best_c:
            best, best_c = lag, c
    return best


def build(video, plan, cue_path, cues_doc, music_title, music_file, made_from=None, align=False):
    total, alen = probe(video)
    if alen is None:
        raise Refuse("the video has no sound")
    lens = [x for x in (total, alen) if x]

    def close(t):
        return any(abs(t - x) <= LEN_TOL for x in lens)

    if cues_doc is not None and not close(float(cues_doc.get("duration") or 0)):
        raise Refuse(f"the cue file is for a {float(cues_doc.get('duration') or 0):.2f} s video, and this one is "
                     f"{total:.2f} s long, so they don't belong together")
    for t in plan:
        for f in [t["file"]] + ([t["minus"]] if t.get("minus") else []):
            if not Path(f).is_file():
                raise Refuse(f"missing file: {f}")
            ft, fa = probe(f)
            if fa is None:
                raise Refuse(f"{Path(f).name} has no sound in it")
            full = Path(str(f)[: -len("_ducked.wav")] + "_track.wav") if str(f).endswith("_sfx_ducked.wav") else None
            if full and full.is_file():
                # Real SFX's ducked copy of the effects stops when its last sound has played (up to about half a
                # second early); the effects track it was made from is the full length, so that one is checked
                st, sa = probe(full)
                if not close(sa or st) or fa > (sa or st) + 0.01 or fa < (sa or st) - 0.5:
                    raise Refuse(f"{full.name} is {sa or st:.2f} s long and the video is {total:.2f} s, so it "
                                 "belongs to another version")
                continue
            if not close(fa) and not close(ft):
                raise Refuse(f"{Path(f).name} is {fa:.2f} s long and the video is {total:.2f} s, so it belongs to "
                             "another version")
    sr = 4000 if total <= 600 else 1000
    n = int(round(total * sr))
    target = decode(video, sr, n)
    xs = []
    for t in plan:
        x = decode(t["file"], sr, n)
        if t.get("minus"):
            y = decode(t["minus"], sr, n)
            x = array("f", map(operator.sub, x, y))
        xs.append(x)
    lag = 0
    if align:       # tracks from a build record: line them up with the video's sound first (the effects track,
        own = [i for i, t in enumerate(plan) if t["kind"] != "sfx"]     # from the effects run, already is)
        lag = best_lag([xs[i] for i in own], target, sr) if own else 0
        if lag:
            for i in own:
                x = xs[i]
                xs[i] = (array("f", [0.0] * lag) + x[:n - lag]) if lag > 0 else (x[-lag:] + array("f", [0.0] * -lag))
    gains, explained = fit_levels(xs, target)
    bad = [(t, g) for t, g in zip(plan, gains) if g <= 0 or abs(20 * math.log10(g)) > GAIN_RANGE]
    if explained < MIN_FIT or bad:
        why = (f"together they account for only {100 * explained:.1f}% of the video's sound (it must be "
               f"{100 * MIN_FIT:.0f}% or more)") if explained < MIN_FIT else \
              f"{Path(bad[0][0]['file']).name} would need a level that makes no sense ({bad[0][1]:.3g}x)"
        raise Refuse("these files don't add up to this video's sound: " + why + ". They belong to another version.")
    worst, at = local_check(xs, gains, target, sr)
    if worst > MAX_LOCAL:
        m, s = divmod(at, 60)
        raise Refuse(f"at {int(m)}:{s:05.2f} the files and the video don't sound the same (one has a sound the "
                     "other hasn't, for example an effect added or taken out). They belong to another version.")
    step = bucket_step(sr, total)
    pk = [peaks_of(x, g, step) for x, g in zip(xs, gains)]
    top = max((max(p) for p in pk if p), default=0) or 1.0
    tracks = []
    for t, g, p in zip(plan, gains, pk):
        tr = {"id": t["kind"], "kind": t["kind"], "name": t.get("name") or NAMES[t["kind"]]}
        if t["kind"] in ("music", "mix") and music_title:
            tr["title"] = music_title
        if t["kind"] in ("music", "mix") and music_file:
            tr["song_file"] = Path(music_file).name
        tr["file"] = rel_studio(t["file"]) + (f" minus {Path(t['minus']).name}" if t.get("minus") else "")
        tr["gain_db"] = round(20 * math.log10(g), 2)
        tr["bucket"] = round(step / sr, 4)
        tr["peaks"] = [round(100 * math.sqrt(v / top)) for v in p]
        if t["kind"] == "sfx" and cues_doc is not None:
            tr["cues"] = cue_entries(cues_doc.get("cues") or [])
        tracks.append(tr)
    tracks.sort(key=lambda tr: KINDS.index(tr["kind"]))
    st = Path(video).stat()
    doc = {"about": ABOUT, "version": FORMAT_VERSION, "video": Path(video).name, "video_size": st.st_size,
           "duration": round(total, 3), "made": datetime.now().isoformat(timespec="seconds"),
           "made_from": made_from or (rel_studio(Path(cue_path).parent) if cue_path else rel_studio(Path(plan[0]["file"]).parent)),
           "cues_from": rel_studio(cue_path) if cue_path else None,
           "checks": {"fit": round(explained, 4), "worst_quarter_second": round(worst, 3), "lengths": "match",
                      **({"tracks_moved_ms": round(1000 * lag / sr, 1)} if lag else {})},
           "scale": {"top_db": round(20 * math.log10(top), 1),
                     "note": "a peak of 100 stands for this level (dB against full scale, before the mix's limiter); "
                             "a peak p stands for (p/100)^2 of it"},
           "tracks": tracks}
    return doc


def buildrecord():
    lib = str(STUDIO / "library")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    import buildrecord as BR
    return BR


def record_plan(rec_file, doc):
    """The sound tracks a build record keeps (small copies, at their level in the mix)."""
    base = Path(rec_file).parent
    return [{"kind": t["kind"], "file": str(base / t["file"]), "name": t.get("name")} for t in doc.get("tracks") or []
            if t.get("kind") in KINDS and t["kind"] != "sfx"]


def runs_from_render(render, video_audio):
    """Real SFX runs made from this render (their "video" is it) whose finished file has the video's exact sound."""
    render = Path(render).resolve()
    cands = set()
    for pat in ("*_resolved_cues.json", "*/*_resolved_cues.json", "*/*/*_resolved_cues.json"):
        cands |= set(render.parent.glob(pat))
    for pat in ("styles/*/work*/**/*_resolved_cues.json", "walkthrough/work*/**/*_resolved_cues.json"):
        cands |= set(STUDIO.glob(pat))
    hits = []
    for f in sorted(cands):
        try:
            d = json.loads(f.read_text())
        except (ValueError, OSError):
            continue
        if not d.get("video") or Path(d["video"]).resolve() != render:
            continue
        out = d.get("output")
        if out and Path(out).is_file() and audio_md5(out) == video_audio:
            hits.append((f.resolve(), d))
    return hits


def auto_plan(video):
    """Plan, cue file, cue doc, song title, song file, made_from and how the sound was matched, from the build record."""
    BR = buildrecord()
    recs = BR.find_records(BR.stream_md5(video, "v"))
    if not recs:
        raise Refuse("no build record has this video's picture (it was made before builds kept records, or by a "
                     "builder that doesn't keep one); give --work FOLDER or --cues FILE instead")
    why = ""
    vam = audio_md5(video)
    total, _ = probe(video)
    recs = sorted(recs, key=lambda x: abs(float(x.get("duration") or 0) - total) > LEN_TOL)   # right length first
    for r in recs:
        doc = json.loads(Path(r["record"]).read_text())
        plan = record_plan(r["record"], doc)
        if not plan:
            why = f"{Path(r['record']).name} keeps no sound tracks"
            continue
        song = doc.get("song") or {}
        made = rel_studio(r["record"])
        if BR.stream_md5(video, "a") == doc.get("audio_md5"):
            return plan, None, None, song.get("title", ""), song.get("file", ""), made, "the render's own sound, bit for bit"
        hits = runs_from_render(doc["render_path"], vam)
        if len(hits) == 1:
            cue_path, cues_doc = hits[0]
            plan.append({"kind": "sfx", "file": sfx_file(cues_doc, cue_path)})
            return (plan, cue_path, cues_doc, song.get("title", ""), song.get("file", ""), made,
                    "bit-for-bit the same sound as the effects run's own file")
        why = ("no Real SFX run made from " + Path(doc["render_path"]).name + " has this video's exact sound") if not hits \
            else "more than one Real SFX run has this video's exact sound"
    raise Refuse(why)


def dumps(doc):
    """Readable JSON with each peaks list on one line, so the file stays small."""
    keep = {}
    for i, tr in enumerate(doc["tracks"]):
        keep[f"@@P{i}@@"] = json.dumps(tr["peaks"], separators=(",", ":"))
        tr["peaks"] = f"@@P{i}@@"
    s = json.dumps(doc, indent=1, ensure_ascii=False)
    for k, v in keep.items():
        s = s.replace(json.dumps(k), v)
    for i, tr in enumerate(doc["tracks"]):
        tr["peaks"] = json.loads(keep[f"@@P{i}@@"])
    return s + "\n"


def map_path(video):
    return Path(str(video) + ".sound.json")


def show(video):
    f = map_path(video)
    if not f.exists():
        print(f"No sound map beside {Path(video).name}.")
        return
    d = json.loads(f.read_text())
    print(f"{f.name}  ({f.stat().st_size // 1024} KB, made {d.get('made')}, from {d.get('made_from')})")
    print(f"  checks: {d.get('checks')}")
    for tr in d.get("tracks", []):
        extra = f" · {tr['title']}" if tr.get("title") else ""
        cues = f", {len(tr['cues'])} effects" if tr.get("cues") else ""
        print(f"  {tr['name']}{extra}: {len(tr['peaks'])} peaks every {tr['bucket']} s, level {tr['gain_db']:+.1f} dB "
              f"in the mix{cues}  [{tr['file']}]")
        for c in tr.get("cues", [])[:200]:
            print(f"      {c['t']:7.3f} s  {c['len']:5.2f} s  {c['name']}  ({c['what']}, {c.get('level_db', '?')} dB)")


def main():
    ap = argparse.ArgumentParser(description="Write a video's sound map (<video>.sound.json) for Video Review.")
    ap.add_argument("video")
    ap.add_argument("--work")
    ap.add_argument("--cues")
    for k in ("voice", "nat", "voice-nat", "music", "music-minus", "mix", "sfx-track"):
        ap.add_argument("--" + k)
    ap.add_argument("--mix-name", default=NAMES["mix"])
    ap.add_argument("--music-title", default="")
    ap.add_argument("--music-file", default="", help="the song's file, to name it when --music-title isn't given")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--auto", action="store_true", help="from the build record (the default with no --work or --cues)")
    a = ap.parse_args()

    video = Path(a.video).expanduser().resolve()
    try:
        if not video.is_file() or video.suffix.lower() not in VIDEO_EXT:
            raise Refuse(f"not a video file: {video}")
        if a.show:
            return show(video)
        if any(part.lower() == "raw" for part in video.parent.parts):
            raise Refuse("this is a raw camera clip (it's in a Raw folder); sound maps are for finished videos")
        if map_path(video).exists() and not a.replace and not a.dry_run:
            raise Refuse(f"{map_path(video).name} is already there (add --replace to make it again)")
        cue_path, cues_doc, made_from, rec_title, rec_file = None, None, None, "", ""
        if a.auto or not (a.work or a.cues):
            plan, cue_path, cues_doc, rec_title, rec_file, made_from, same = auto_plan(video)
        elif a.work:
            cue_path, cues_doc = find_run(Path(a.work).expanduser().resolve(), audio_md5(video))
            rec = Path(str(cues_doc.get("video") or "") + ".build.json")
            rdoc = json.loads(rec.read_text()) if rec.is_file() else {}
            if record_plan(rec, rdoc):     # the builder's own record, when it kept one
                plan = record_plan(rec, rdoc) + [{"kind": "sfx", "file": sfx_file(cues_doc, cue_path)}]
                rec_title, rec_file = (rdoc.get("song") or {}).get("title", ""), (rdoc.get("song") or {}).get("file", "")
                made_from = rel_studio(rec)
            else:
                plan = plan_from_run(cue_path, cues_doc, a.mix_name)
            same = True
        else:
            cue_path = Path(a.cues).expanduser().resolve()
            cues_doc = json.loads(cue_path.read_text())
            plan = []
            for opt, kind in (("voice", "voice"), ("voice_nat", "voice_nat"), ("mix", "mix"), ("music", "music"),
                              ("nat", "nat")):
                f = getattr(a, opt)
                if f:
                    t = {"kind": kind, "file": str(Path(f).expanduser().resolve())}
                    if kind == "music" and a.music_minus:
                        t["minus"] = str(Path(a.music_minus).expanduser().resolve())
                    if kind == "mix":
                        t["name"] = a.mix_name
                    plan.append(t)
            if not plan:
                orig = cues_doc.get("original_audio") or cues_doc.get("video")
                plan.append({"kind": "mix", "file": orig, "name": a.mix_name})
            plan.append({"kind": "sfx", "file": str(Path(a.sfx_track).expanduser().resolve()) if a.sfx_track
                         else sfx_file(cues_doc, cue_path)})
            out = cues_doc.get("output")
            same = bool(out and Path(out).is_file() and audio_md5(out) == audio_md5(video))
        title = a.music_title or rec_title or (nice_song(a.music_file) if a.music_file else "")
        doc = build(video, plan, cue_path, cues_doc, title, a.music_file or rec_file, made_from,
                    align=bool(made_from and made_from.endswith(".build.json")))
        doc["checks"]["same_sound_as_run_output"] = same
        text = dumps(doc)
    except Refuse as e:
        sys.exit(f"Refused, nothing written: {e}")
    except RuntimeError as e:
        sys.exit(f"Stopped, nothing written: {e}")

    print(f"{video.name}: {doc['duration']:.2f} s, the tracks account for {100 * doc['checks']['fit']:.2f}% of its sound"
          f" (worst quarter second {doc['checks']['worst_quarter_second']:.2f}, limit {MAX_LOCAL})"
          + ((", " + same if isinstance(same, str) else ", bit-for-bit the same sound as the effects run's own file") if same else ""))
    for tr in doc["tracks"]:
        print(f"  {tr['name']}{' · ' + tr['title'] if tr.get('title') else ''}: level {tr['gain_db']:+.1f} dB in the mix"
              + (f", {len(tr['cues'])} effects" if tr.get("cues") else "") + f"  [{tr['file']}]")
    if a.dry_run:
        print(f"Dry run: would write {map_path(video).name} ({len(text) // 1024} KB).")
        return
    f = map_path(video)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, f)
    print(f"Wrote {f} ({len(text) // 1024} KB).")


if __name__ == "__main__":
    main()
