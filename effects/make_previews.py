#!/usr/bin/env python3
"""Preview every effect on your own footage: one short MP4 per effect, plus one contact sheet of them all.

    .venv/bin/python effects/make_previews.py --footage <folder> --out <folder> [--brand <slug>] [--only a,b]

  --footage DIR   any folder of clips (it looks in subfolders too). It picks the clips itself:
                  the one where a face is biggest and steadiest (a talking take) for most effects, and a clip
                  with no face (B-roll) for the second shot of the transitions and the green-screen card.
  --out DIR       where the previews go: FX_<effect>.mp4 for each, contact.jpg (a still of each), and
                  previews.json (which clip and seconds each used, the skin, and any wording Claude wrote).
  --brand SLUG    use the Brand skin with this brand's colours and fonts (brands/<slug>/brand.json).
                  Without it: the Dark skin (neutral dark panels, white text, yellow keywords).
  --skin dark|brand   the same choice by name (brand uses studio.json's default_brand).
  --only a,b      only these effects (names or aliases). Default: all of them.
  --grade none|camera|pov   a light colour grade for camera originals (default none).
  --sheet-only    no videos: only the contact sheet (one still per effect, quicker).
  --seconds N     how long a stretch of the talking clip to prepare (default 18).

The first run prepares the clips (a 9:16 crop around the face, a cutout of the person on every frame, the words
said). That takes about 2 s per second of footage and is cached in effects/cache/, so a second run is quick.
Each preview takes 10-60 s to render. All of them take a while: use --only to try a few first.

Previews are style tests: they stay on your Mac (never in git). Text an effect shows is your own words from the
clip unless previews.json says CLAUDE-WROTE.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core       # noqa: E402
import catalog    # noqa: E402
from PIL import Image  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}
SKIP_DIRS = {"Finished", "Older Versions", "Style Tests", "_To Delete", "Footage Log", "cache", "work"}


def say(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ the clips
def find_clips(folder):
    out = []
    for dp, dns, fns in os.walk(folder):
        dns[:] = sorted(d for d in dns if d not in SKIP_DIRS and not d.startswith("."))
        for f in sorted(fns):
            if os.path.splitext(f)[1].lower() in VIDEO_EXT and not f.startswith("."):
                out.append(os.path.join(dp, f))
    return out


def scan(path, tmp, k):
    """Length, size, sound, and how much of the time there's a face and how big (from a 1 fps look at up to 40 s)."""
    try:
        info = core.probe(path)
    except Exception as e:
        return None
    if info["dur"] < 1.5:
        return None
    a = min(info["dur"] * 0.1, 5.0)
    t = min(40.0, info["dur"] - a)
    proxy = os.path.join(tmp, f"scan{k}.mp4")
    fj = os.path.join(tmp, f"scan{k}.json")
    face_share, face_h, face_steady = 0.0, 0.0, 0.0
    try:
        core.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.2f}", "-t", f"{t:.2f}", "-i", path, "-map", "0:v:0",
                  "-vf", "fps=1,scale=-2:480", "-c:v", "libx264", "-crf", "26", "-an", proxy])
        core.run([core.ensure_helpers(), proxy, fj])
        fs = json.load(open(fj))
        hits = [f for f in fs if len(f) > 1]
        if fs:
            face_share = len(hits) / len(fs)
        if hits:
            hs = sorted(f[4] for f in hits)
            face_h = hs[len(hs) // 2]
            xs = [f[1] + f[3] / 2 for f in hits]
            face_steady = 1.0 - min(1.0, (max(xs) - min(xs)))
    except Exception as e:
        say(f"  (couldn't look for faces in {os.path.basename(path)}: {str(e).splitlines()[0]})")
    words = path + ".words.txt"
    return dict(path=path, dur=info["dur"], w=info["w"], h=info["h"], audio=info["audio"], face_share=face_share,
                face_h=face_h, steady=face_steady, words=os.path.exists(words) and os.path.getsize(words) > 0)


def pick(clips):
    """(talking clip, B-roll clip or None)."""
    def talk_score(c):
        return (c["face_share"] * (0.4 + c["face_h"]) * (0.6 + 0.4 * c["steady"]) * (1.2 if c["audio"] else 0.6)
                * (1.3 if c["words"] else 1.0) * min(1.0, c["dur"] / 8.0))
    talk = max(clips, key=talk_score)
    rest = [c for c in clips if c is not talk]
    broll = min(rest, key=lambda c: (round(c["face_share"], 1), -c["dur"])) if rest else None
    return talk, broll


def read_words(path):
    p = path + ".words.txt"
    return core._read_words_txt(p) if os.path.exists(p) else []


def stretch(c, seconds):
    """Where in the talking clip to look: the whole clip if short, else the stretch with the most words said."""
    dur = c["dur"]
    if dur <= seconds + 2:
        return 0.0, dur
    ws = read_words(c["path"])
    if ws:
        best, best_n = 0.0, -1
        for w in ws:
            a = max(0.0, w["s"] - 0.4)
            if a + seconds > dur: break
            n = sum(1 for x in ws if a <= x["s"] < a + seconds)
            if n > best_n: best, best_n = a, n
        return best, best + seconds
    a = min(dur * 0.1, dur - seconds)
    return a, a + seconds


# ------------------------------------------------------------------ where each effect goes
def moments(subj, n):
    """Start times for the effects, spread over the key words said (so the effects show different words)."""
    kws = core.key_words(subj.words)
    if not kws:
        return [0.6]
    step = max(1, len(kws) // max(1, min(n, len(kws))))
    return [max(0.0, w["s"] - 0.15) for w in kws[::step]]


def window(subj, m, sample, starts, k):
    d = max(float(m.DUR), float(sample.get("dur") or 0))
    d = min(d, max(1.0, subj.dur - 0.4))
    t0 = starts[k % len(starts)]
    t0 = min(t0, max(0.0, subj.dur - d - 0.2))
    return t0, t0 + d


def conform(src, a, b, out, grade, crop_box=None):
    """A stretch of any clip as 1080x1920 30 fps with sound (crop_box [w, h, x, y], else a center crop to 9:16),
    for the transition join."""
    info = core.probe(src)
    sw, sh = info["w"], info["h"]
    asp = core.W / core.H
    if crop_box:
        crop = "crop={}:{}:{}:{}".format(*crop_box)
    elif abs(sw / sh - asp) < 0.02:
        crop = "null"
    elif sw / sh > asp:
        crop = f"crop={int(sh * asp) // 2 * 2}:{sh // 2 * 2}"
    else:
        crop = f"crop={sw // 2 * 2}:{int(sw / asp) // 2 * 2}"
    vf = [crop, f"scale={core.W}:{core.H}:flags=lanczos", f"fps={core.FPS}"]
    if core.grade_filter(grade): vf.append(core.grade_filter(grade))
    vf += ["setpts=PTS-STARTPTS", "format=yuv420p"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src]
    if not info["audio"]:
        cmd += ["-f", "lavfi", "-t", f"{b - a:.3f}", "-i", f"anullsrc=r={core.SR}:cl=stereo"]
    cmd += ["-map", "0:v:0", "-map", "0:a:0" if info["audio"] else "1:a:0", "-vf", ",".join(vf),
            "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-c:a", "pcm_s16le", "-ar", str(core.SR), "-ac", "2",
            "-shortest", out]
    core.run(cmd)


def cut_clip(talk_subj, broll, tmp, grade):
    """A short picture with one hard cut in the middle: the talking clip, then the B-roll (or a later bit of the
    talking clip). Returns (path, the cut's time, words said before the cut)."""
    key = core._key("cut", talk_subj.dir, broll["path"] if broll else None, grade)
    d = os.path.join(core.CACHE, "previews", key)
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, "cut.mp4")
    meta_p = os.path.join(d, "cut.json")
    if os.path.exists(out) and os.path.exists(meta_p):
        m = json.load(open(meta_p))
        return out, m["cut"], m["words"]
    A = 2.6
    kws = core.key_words(talk_subj.words)
    a0 = max(0.0, (kws[0]["s"] - 0.8) if kws else 0.5)
    a0 = min(a0, max(0.0, talk_subj.dur - A))
    src = talk_subj.meta["src"]
    s0 = talk_subj.meta["start"] + a0
    p1, p2 = os.path.join(tmp, "a.mov"), os.path.join(tmp, "b.mov")
    conform(src, s0, s0 + A, p1, talk_subj.meta.get("grade", "none"), talk_subj.meta.get("crop"))
    if broll:
        b0 = min(broll["dur"] * 0.3, max(0.0, broll["dur"] - A))
        conform(broll["path"], b0, b0 + A, p2, grade)
    else:
        b0 = min(talk_subj.meta["end"] - A, s0 + A + 3.0)
        conform(src, b0, b0 + A, p2, talk_subj.meta.get("grade", "none"), talk_subj.meta.get("crop"))
    lst = os.path.join(tmp, "join.txt")
    open(lst, "w").write(f"file '{p1}'\nfile '{p2}'\n")
    core.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-crf", "14",
              "-preset", "fast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out])
    words = [dict(w=w["w"], s=round(w["s"] - a0, 3), e=round(w["e"] - a0, 3)) for w in talk_subj.words
             if a0 <= w["s"] < a0 + A]
    json.dump({"cut": A, "words": words}, open(meta_p, "w"))
    return out, A, words


def still(mp4, t, tmp, k):
    p = os.path.join(tmp, f"still{k}.png")
    core.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{max(0.0, t):.3f}", "-i", mp4, "-frames:v", "1", p])
    return Image.open(p).convert("RGB")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--footage", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--brand")
    ap.add_argument("--skin", choices=core.SKIN_NAMES)
    ap.add_argument("--only")
    ap.add_argument("--grade", default="none", choices=sorted(set(core.GRADES) | set(core.GRADE_ALIASES)))
    ap.add_argument("--sheet-only", action="store_true")
    ap.add_argument("--seconds", type=float, default=18.0)
    a = ap.parse_args()

    skin = ("brand:" + (a.brand or "")) if (a.brand or a.skin == "brand") else "dark"
    sk = core.skin(skin)
    skin_label = f"Brand skin ({sk.get('brand') or 'default brand'})" if sk.name == "brand" else "Dark skin"
    names = catalog.names()
    if a.only:
        want = [catalog.ALIASES.get(x.strip(), x.strip()) for x in a.only.split(",") if x.strip()]
        bad = [x for x in want if x not in names]
        if bad:
            sys.exit(f"no effect called {', '.join(bad)}. Effects: {', '.join(names)}")
        names = [n for n in names if n in want]
    os.makedirs(a.out, exist_ok=True)

    clips = find_clips(a.footage)
    if not clips:
        sys.exit(f"no video clips in {a.footage}")
    t_start = time.time()
    say(f"Looking at {min(len(clips), 12)} of {len(clips)} clip(s) in {a.footage} ...")
    with tempfile.TemporaryDirectory() as tmp:
        clips.sort(key=lambda p: -os.path.getsize(p))
        scanned = [c for k, p in enumerate(clips[:12]) if (c := scan(p, tmp, k))]
        if not scanned:
            sys.exit("none of the clips could be read (or all are under 1.5 s)")
        talk, broll = pick(scanned)
        say(f"  talking clip: {os.path.basename(talk['path'])} (face in {talk['face_share']:.0%} of it"
            + (", has a transcript" if talk["words"] else "") + ")")
        if talk["face_share"] < 0.3:
            say("  note: no clip shows a face most of the time, so the effects that follow your face will guess.")
        say(f"  B-roll clip:  {os.path.basename(broll['path'])}" if broll else "  B-roll clip:  none (the transitions cut "
            "to a later moment of the same clip)")
        s0, s1 = stretch(talk, a.seconds)
        say(f"Preparing {os.path.basename(talk['path'])} {s0:.1f}-{s1:.1f} s (cutout, face, words; cached) ...")
        subj = core.prep(talk["path"], s0, s1, None, 1.0, a.grade)
        say(f"  {subj.n} frames, words from {subj.meta['words_from']} ({len(subj.words)} words)")
        starts = moments(subj, len(names))

        cut_subj = None
        if any(n in catalog.TRANSITIONS for n in names):
            say("Preparing a two-shot clip with a cut, for the transitions ...")
            cut_path, cut_t, cut_words = cut_clip(subj, broll, tmp, a.grade)
            cut_subj = core.prep(cut_path, words=cut_words)

        made, stills, labels, record = [], [], [], []
        for k, n in enumerate(names):
            m = catalog.get(n)
            sample = dict(getattr(m, "SAMPLE", None) or {})
            prm = dict(m.PARAMS); prm.update(sample.get("params") or {})
            if n in catalog.TRANSITIONS:
                use = cut_subj
                d = float(m.DUR)
                t0 = max(0.0, cut_t - catalog.TRANSITIONS[n] * d); t1 = min(use.dur, t0 + d)
                if n == "zoom-through": prm["peak"] = cut_t - t0
                f0, f1 = 0, use.n
            else:
                use = subj
                t0, t1 = window(subj, m, sample, starts, k)
                f0 = max(0, int((t0 - float(sample.get("lead", 0.8))) * core.FPS))
                f1 = min(subj.n, int((t1 + float(sample.get("tail", 0.8))) * core.FPS))
            if "other_clip" in (sample.get("needs") or []):
                other = broll or talk
                prm["media"] = other["path"]
                prm["at"] = round(min(other["dur"] * 0.3, max(0.0, other["dur"] - 6)), 2)
            specs = [(m, t0, t1, prm)]
            out = os.path.join(a.out, f"FX_{n}.mp4")
            ts = time.time()
            frac = float(sample.get("still", 0.6))
            try:
                if a.sheet_only:
                    f = int(round((t0 + (t1 - t0) * frac) * core.FPS))
                    im = core.render(use, specs, None, sk, frames_only=[min(use.n - 1, f)], label=n)[min(use.n - 1, f)]
                else:
                    core.render(use, specs, out, sk, f0=f0, f1=f1, label=n)
                    im = still(out, (t0 + (t1 - t0) * frac) - f0 / core.FPS, tmp, k)
                    made.append(out)
            except Exception as e:
                say(f"  {n:15s} FAILED: {str(e).splitlines()[-1] if str(e) else type(e).__name__}")
                continue
            stills.append(im); labels.append(n)
            note = sample.get("note", "")
            record.append(dict(effect=n, file=None if a.sheet_only else os.path.basename(out),
                               clip=os.path.basename(use.meta["src"]) if use is subj else "two-shot cut (talking clip, then B-roll)",
                               window=[round(t0, 2), round(t1, 2)],
                               clip_seconds=[round(use.meta["start"] + t0, 2), round(use.meta["start"] + t1, 2)] if use is subj else None,
                               transition=n in catalog.TRANSITIONS, note=note, claude_wrote="CLAUDE-WROTE" in note))
            say(f"  {n:15s} {t0:5.2f}-{t1:5.2f} s  {time.time() - ts:5.1f} s" + ("" if a.sheet_only else f"  {out}")
                + ("  [CLAUDE-WROTE text]" if "CLAUDE-WROTE" in note else ""))

        sheet = os.path.join(a.out, "contact.jpg")
        if stills:
            core.sheet(stills, sheet, cols=min(7, len(stills)), scale=0.22, labels=labels)
        json.dump({"about": "Effect previews made by effects/make_previews.py. Style tests: they stay on this Mac.",
                   "skin": skin_label, "footage": os.path.abspath(a.footage), "talk_clip": os.path.basename(talk["path"]),
                   "talk_stretch": [round(s0, 2), round(s1, 2)],
                   "broll_clip": os.path.basename(broll["path"]) if broll else None,
                   "made": time.strftime("%Y-%m-%d %H:%M"), "previews": record},
                  open(os.path.join(a.out, "previews.json"), "w"), indent=1)
    say(f"\nMade {len(made)} preview(s) and {sheet if stills else 'no contact sheet'} with the {skin_label} "
        f"in {time.time() - t_start:.0f} s.")
    say(f"  {os.path.join(a.out, 'previews.json')} lists which clip and seconds each used. "
        "Effects marked CLAUDE-WROTE show wording Claude wrote: change it with --set before posting.")


if __name__ == "__main__":
    main()
