#!/usr/bin/env python3
"""Fast Cut example: one talking clip and any B-roll -> a 15-25 s reel, laid out from what's said.

    .venv/bin/python styles/fastcut/example.py --footage "<shoot name or folder>" [options]
        --talk CLIP        the talking clip (default: the clip with the most words in its transcript)
        --broll CLIP ...   B-roll clips (default: every other clip)
        --skin dark|brand  Dark (default) or the brand's skin; --brand SLUG picks the brand
        --title "..."      the hook title (default: the first words said; flag it if you wrote it)
        --seconds 20       about how much speech to use
        --name NAME        file name stem (default: <talk clip>_FastCut)
        --effect SPEC      a library effect, e.g. "spotlight@4.2-7" or "todo@first" (repeatable)
        --music TRACK      a track you picked for this video ("file.wav" or "file.wav@12.5")
        --sheet [t ...]    contact sheet only: one frame per scene (fast check)
        --plan             list the scenes and notes only
        --mux              redo the sound and final file from the last render
        --out FILE         write here (never overwrites); default <shoot>/Style Tests/<name>_vN.mp4

This shows the engine working end to end on any footage. For a real video, Claude writes the scenes by hand in a
copy of this script: the story in order, each layout on the word it lands on, cards whose rows are things actually
said, and real numbers only (STYLES.md, "How to make one"). plan() below is the pattern to follow.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastcut import engine as fc, graphics as g, skins  # noqa: E402
from stylekit import media, paths  # noqa: E402
from stylekit import words as W_  # noqa: E402

NUMBER_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
                "eleven": 11, "twelve": 12, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "hundred": 100}
EFFECTS = []   # the effects library, in reel time, put on before the captions: ["spotlight@stronger", ("checklist", 4.0, 8.5)]
MUSIC = None   # a track you picked for this video, from the music library: "my-track.wav" or "my-track.wav@12.5"


# ---------------------------------------------------------------- clips
def pick_clips(footage, talk=None, broll=()):
    """(talk clip, [B-roll clips], its words). The talking clip is the one with the most words said."""
    folder = paths.shoot_dir(footage)
    clips = paths.raw_clips(folder)
    if talk:
        talk = paths.find_clip(talk, folder)
    if not clips and not talk:
        raise SystemExit(f"No video clips in {folder}")
    if not talk:
        score = lambda c: (len(W_.words_for(c)) if media.probe(c)["has_audio"] else 0, media.probe(c)["duration"])
        talk = max(clips[:8], key=score)
    broll = [paths.find_clip(b, folder) for b in broll] if broll else [c for c in clips if c != talk]
    return talk, broll, W_.clean(W_.words_for(talk))


def make_edit(talk, ws, seconds=20.0, tail=2.5):
    """The speech: whole phrases from the start of the clip until about `seconds`, each cut in a pause found in
    the sound (never inside a word). Pauses between phrases are cut out (jump cuts)."""
    if not ws:   # no speech: a stretch of the clip, with placeholder captions (samples only)
        dur = min(media.probe(talk)["duration"] - 0.2, seconds)
        return fc.Edit([fc.piece(talk, 0.1, 0.1 + dur, voice=False)], tail=tail)
    pieces, total = [], 0.0
    for i0, i1 in W_.sentences(ws, max_gap=0.55):
        a, b = W_.cut_points(talk, ws, i0, i1)
        pieces.append(fc.piece(talk, a, b))
        total += b - a
        if total >= seconds:
            break
    return fc.Edit(pieces, tail=tail)


# ---------------------------------------------------------------- the plan
def cut_times(reel, lo=1.2, hi=2.2):
    """Scene changes every 1.2-2.2 s, each on a caption start (the first sound of a word)."""
    end = reel.edit.speech_end
    starts = [s for s in reel.caption_starts() if 0.9 <= s <= end - 0.9]
    cuts, t = [0.0], 0.0
    while True:
        nxt = [s for s in starts if t + lo <= s <= t + hi]
        if not nxt:
            later = [s for s in starts if s > t + hi]
            nxt = [later[0]] if later and later[0] - t < 3.2 else ([t + 1.8] if t + 1.8 < end - 0.9 else [])
        if not nxt:
            break
        t = nxt[0]
        cuts.append(round(t, 3))
    return cuts + [end]


def said_in(reel, t0, t1, n=3, numbers=False):
    """Up to n words said between t0 and t1 worth showing: keywords first, then the longest words."""
    out = []
    for w in reel.words:
        if not (t0 + 0.05 <= w["s"] < t1 - 0.2):
            continue
        raw = w["w"].strip(",.?!;:\"'")
        low = raw.lower()
        if numbers:
            if any(c.isdigit() for c in raw) or low in NUMBER_WORDS:
                out.append((raw, w["s"]))
            continue
        if low in W_.STOP or len(low) < 4:
            continue
        out.append((raw, w["s"]))
    if numbers:
        return out[:n]
    keys = {k.lower() for k in reel.keywords}
    out.sort(key=lambda x: (x[0].lower() not in keys, -len(x[0])))
    seen, res = set(), []
    for x in out:
        if x[0].lower() not in seen:
            seen.add(x[0].lower())
            res.append(x)
    return sorted(res[:n], key=lambda x: x[1])


def first_caption(reel, t0):
    """The words of the caption that opens a scene: a card's title that is something actually said."""
    for a, b, toks in reel.caps:
        if a >= t0 - 0.1:
            return " ".join(w for w, _ in toks).capitalize()
    return ""


def title_lines(text, width=12):
    lines, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    return (lines + [cur])[:3]


def plan(reel, broll, title=None):
    """Lay out the reel: a hook, then a new layout at every cut, rotating through the Fast Cut layouts so the same
    one never runs twice in a row, about half graphics and half footage, and the end card after the speech."""
    s = reel.skin
    cuts = cut_times(reel)
    first = " ".join(w["w"].strip(",.?!") for w in reel.words[:4]) or "Fast Cut"
    hook = title or first
    lines = title_lines(hook)
    reel.split(cuts[0], cuts[1], g.Hook(s, lines, at=0.0, hot=min(1, len(lines) - 1),
                                        sub=s.brand.get("name") if s.name == "brand" else None))
    rotation = ["full", "card", "punch", "broll", "list", "full", "number", "card_split", "broll", "slam", "punch", "mosaic"]
    used_mosaic, k, last = False, 0, "split"
    for t0, t1 in zip(cuts[1:-1], cuts[2:]):
        kind = None
        for _ in range(len(rotation)):
            want = rotation[k % len(rotation)]
            k += 1
            if want == last or (want == "broll" and not broll) or (want == "mosaic" and (used_mosaic or t0 < reel.edit.speech_end * 0.6)):
                continue
            words = said_in(reel, t0, t1)
            if want in ("card", "list", "card_split") and len(words) < 3:
                continue
            if want == "number" and not said_in(reel, t0, t1, numbers=True):
                continue
            if want == "slam" and not words:
                continue
            kind = want
            break
        kind = kind or ("punch" if last != "punch" else "full")
        words = said_in(reel, t0, t1)
        if kind == "full":
            reel.full(t0, t1)
        elif kind == "punch":
            reel.punch(t0, t1)
        elif kind == "broll":
            src = broll[(k // 3) % len(broll)]
            dur = media.probe(src)["duration"]
            reel.broll(t0, t1, src, at=max(0.0, min(dur - (t1 - t0) - 0.1, dur * 0.3)))
        elif kind == "card":
            reel.card(t0, t1, g.Checklist(s, first_caption(reel, t0), words))
        elif kind == "card_split":
            reel.card_split(t0, t1, g.Checklist(s, first_caption(reel, t0), words))
        elif kind == "list":
            reel.split(t0, t1, g.ListPanel(s, first_caption(reel, t0), words, at=t0))
        elif kind == "number":
            raw, at = said_in(reel, t0, t1, numbers=True)[0]
            value = raw if any(c.isdigit() for c in raw) else str(NUMBER_WORDS[raw.lower()])
            after = [w["w"].strip(",.?!") for w in reel.words if w["s"] > at][:1]
            reel.graphic(t0, t1, g.BigNumber(s, value, at, after[0] if after else None, dark=True))
        elif kind == "slam":
            word, at = max(words, key=lambda x: len(x[0]))
            reel.graphic(t0, t1, g.Slam(s, word.upper(), at, dark=True))
        elif kind == "mosaic":
            tiles = []
            for src in (broll or []) + [reel.edit.pieces[0]["src"]]:
                d = media.probe(src)["duration"]
                for f in (0.15, 0.4, 0.65, 0.85):
                    tiles.append(media.still(src, d * f, size=(328, 450), look=reel.look, style="fastcut"))
            reel.graphic(t0, t1, g.Mosaic(s, tiles[:12], at=t0), cap="center")
            used_mosaic = True
        last = kind
    reel.end(reel.edit.speech_end, reel.edit.total, title_lines(hook, 14)[:2])
    return reel


def build(footage, talk=None, broll=(), skin="dark", brand=None, title=None, seconds=20.0, name=None,
          placeholder_ok=True, effects=None, music=None):
    """The example reel, planned and ready to render or sheet."""
    talk, broll, ws = pick_clips(footage, talk, broll)
    edit = make_edit(talk, ws, seconds)
    words = None
    if not ws:
        if not placeholder_ok:
            raise SystemExit(f"No speech in {talk.name}: Fast Cut needs someone talking.")
        print(f"  no speech in {talk.name}: placeholder captions (for a sample only)")
        words = W_.placeholder_words(0.0, edit.speech_end)
    reel = fc.Reel(name or f"{Path(talk).stem}_FastCut", edit, skins.get(skin, brand), shoot=paths.shoot_of(talk),
                   words=words, effects=effects if effects is not None else EFFECTS, music=music or MUSIC)
    return plan(reel, broll, title)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--footage", required=True)
    ap.add_argument("--talk")
    ap.add_argument("--broll", nargs="*", default=())
    ap.add_argument("--skin", default="dark", choices=["dark", "brand"])
    ap.add_argument("--brand")
    ap.add_argument("--title")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--name")
    ap.add_argument("--effect", action="append", default=None)
    ap.add_argument("--music")
    a, rest = ap.parse_known_args()
    reel = build(a.footage, a.talk, a.broll, a.skin, a.brand, a.title, a.seconds, a.name, effects=a.effect, music=a.music)
    reel.main(rest)


if __name__ == "__main__":
    main()
