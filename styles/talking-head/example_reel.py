#!/usr/bin/env python3
"""Talking Head Classic example: a talking clip (and one B-roll clip) -> a short reel. White title box at the
start, jump cuts that alternate a 1.1x and 1.25x punch-in, B-roll over one phrase, yellow word-by-word captions,
the voice levelled to -14 LUFS.

    .venv/bin/python styles/talking-head/example_reel.py --footage "<shoot name or folder>" [options]
        --talk CLIP      the talking clip (default: the clip with the most words said)
        --broll CLIP     B-roll for the third phrase (default: the first other clip; "none" for none)
        --title "..."    the title box (default: the first words said; flag it if you wrote it)
        --seconds 15     about how much speech to use
        --name NAME      file name stem (default: <talk clip>_TalkingHead)
        --out FILE       write here (never overwrites); default <shoot>/Style Tests/<name>_vN.mp4

Then check every word survived the cuts:
    .venv/bin/python styles/talking-head/verify.py "<the video>"

For a real reel, Claude writes the recipe by hand in a copy of this file: which phrases, in what order
(rk.phrase(clip, "first words", "last words")), where the B-roll goes, the title (STYLES.md).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import reelkit as rk  # noqa: E402
from stylekit import media, paths  # noqa: E402
from stylekit import words as W_  # noqa: E402

EFFECTS = []   # the effects library, in reel time, before captions: ["spotlight@stronger"] (one or two per reel at most)


def pick(footage, talk=None, broll=None):
    folder = paths.shoot_dir(footage)
    clips = paths.raw_clips(folder)
    if talk:
        talk = paths.find_clip(talk, folder)
    else:
        if not clips:
            raise SystemExit(f"No video clips in {folder}")
        talk = max(clips[:8], key=lambda c: (len(W_.words_for(c)) if media.probe(c)["has_audio"] else 0,
                                             media.probe(c)["duration"]))
    if broll == "none":
        broll = None
    elif broll:
        broll = paths.find_clip(broll, folder)
    else:
        others = [c for c in clips if c != talk]
        broll = others[0] if others else None
    return str(talk), (str(broll) if broll else None)


def recipe(talk, broll=None, title=None, seconds=15.0):
    """(segments, overlays, placeholder) for the reel."""
    ws = W_.clean(W_.words_for(talk))
    placeholder = not ws
    if ws:
        pieces = rk.phrases(talk, seconds=seconds)
    else:   # no speech in this clip: a stretch of it, with placeholder captions (samples only)
        d = media.probe(talk)["duration"]
        step = min(3.0, (min(d, seconds) - 0.2) / 3)
        pieces = [(talk, 0.1 + k * step, 0.1 + (k + 1) * step) for k in range(3)]
    segs = rk.jump_cuts(talk, pieces)
    if broll and len(segs) >= 3:
        # B-roll over the third phrase; if the clip is shorter than the phrase, back to the talking head after it
        d = media.probe(broll)["duration"]
        seg = segs[2]
        (src, a, b), = seg["a"]
        length = b - a
        start = max(0.0, min(d * 0.3, d - length - 0.1))
        show = min(length, d - start - 0.1, 3.5)
        is_pov = any(p.lower() in ("pov", "glasses") for p in Path(broll).parts)
        seg["v"] = [(rk.pov if is_pov else rk.cam)(broll, t=start, d=show)]
        if show < length - 0.05:
            seg["v"].append(dict(k="talk", src=talk, t=a + show, zoom=1.25))   # the talking head, still in sync
    hook = title or " ".join(w["w"].strip(",.?!") for w in ws[:5]) or "Talking Head Classic"
    first_len = sum(b - a for _, a, b in segs[0]["a"])
    overlays = [rk.title(0, max(2.5, min(3.8, first_len + 0.5)), hook)]
    return segs, overlays, placeholder


def make(footage, talk=None, broll=None, title=None, seconds=15.0, name=None, out=None):
    talk, broll = pick(footage, talk, broll)
    segs, overlays, placeholder = recipe(talk, broll, title, seconds)
    if placeholder:
        print(f"  no speech in {Path(talk).name}: placeholder captions (for a sample only)")
    return rk.build(name or f"{Path(talk).stem}_TalkingHead", segs, overlays, shoot=paths.shoot_of(talk), out=out,
                    effects=EFFECTS, placeholder=placeholder)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--footage", required=True)
    ap.add_argument("--talk")
    ap.add_argument("--broll")
    ap.add_argument("--title")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--name")
    ap.add_argument("--out")
    a = ap.parse_args()
    make(a.footage, a.talk, a.broll, a.title, a.seconds, a.name, a.out)


if __name__ == "__main__":
    main()
