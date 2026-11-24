#!/usr/bin/env python3
"""Talking Head Classic builder: shots -> cached clips, sound pieces, a PNG overlay track (title box, labels,
word-by-word captions), effects, the final mix and the build record.

    import reelkit as rk
    shoot = "2026-03-14 Kitchen Remodel"
    talk = rk.clip(shoot, "talk.mp4")                      # found in any Raw/<camera>/ folder of the shoot
    hands = rk.clip(shoot, "POV/hands.mp4")
    segs = [
        dict(a=[rk.phrase(talk, "so here's the thing", "nobody tells you")], v=[rk.talk(talk)]),
        dict(a=[rk.phrase(talk, "first", "twice")], v=[rk.talk(talk, zoom=1.25)]),            # jump cut: punch in
        dict(a=[rk.phrase(talk, "and then", "done")], v=[rk.pov(hands, t=3.0)]),             # B-roll over the voice
    ]
    rk.build("Kitchen_Tips", segs, overlays=[rk.title(0, 3.5, "Three kitchen tips")], shoot=shoot)

A segment is dict(a=[sound pieces], v=[shots], gain=1.0, cap=True):
  sound piece  (clip, start, end) in source seconds, or ("gap", seconds) of silence
  shot         talk(clip): plays in sync with the sound, one sub-shot per sound piece (the classic jump cut)
               cam(clip, t=, d=) / pov(clip, t=, d=): other footage from t for d seconds (None: the rest)
               split(top_clip, bottom_clip, top_off=): two cameras, one above the other, in sync
               any shot takes zoom, cx/cy (source px) or cxf/cyf (0..1), speed (2.5 = time-lapse)
Overlays are (start, end, fn(img)) in reel seconds: title(), label(), stats_card(), counter().

Captions come from the clips' transcripts (<clip>.words.txt): 1-3 words, the word being said in the accent colour.
Cut points from phrase() come from the sound level, so words aren't clipped. Check every build with verify.py.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit import fxhook, media, paths, record  # noqa: E402
from stylekit import words as W_  # noqa: E402

W, H, FPS, SR = 1080, 1920, 30, 48000
STYLE = "talking-head"
COND = "/System/Library/Fonts/Avenir Next Condensed.ttc"
HEAVY, BOLD, DEMI = 8, 0, 2

# The classic look. build(look=...) changes any of it (e.g. a brand's caption font and accent).
LOOK = dict(font=(COND, HEAVY), label_font=(COND, DEMI), active=(255, 222, 60), text=(255, 255, 255),
            stroke=(0, 0, 0), title_fg=(15, 15, 15), title_bg=(255, 255, 255, 245), grade="punchy")


def F(size, spec=None):
    path, idx = spec or LOOK["font"]
    return ImageFont.truetype(path, size, index=idx)


def ff(args):
    media.ff(args)


def even(x): return media.even(x)
def clamp(v, a, b): return max(a, min(b, v))


# ---------------------------------------------------------------- clips and shots
def clip(shoot, name) -> str:
    """A clip of a shoot by file name or Raw-relative path ("POV/hands.mp4"), from any Raw/ subfolder."""
    return str(paths.find_clip(name, shoot))


def talk(src, zoom=1.1, **kw):
    """The talking head, in sync with the sound pieces of its segment."""
    return dict(k="talk", src=str(src), zoom=zoom, sync=True, **kw)


def cam(src, t=0.0, d=None, zoom=1.0, **kw):
    """Footage from any camera, from t seconds for d seconds (None: to the end of the segment)."""
    return dict(k="cam", src=str(src), t=t, d=d, zoom=zoom, **kw)


def pov(src, t=0.0, d=None, zoom=1.0, **kw):
    """Footage from a head-mounted or glasses camera (gentler sharpening)."""
    return dict(k="pov", src=str(src), t=t, d=d, zoom=zoom, **kw)


def split(top, bottom, top_off=0.0, sync=True, **kw):
    """Two cameras at once, top above bottom, in sync: top time = bottom time + top_off."""
    return dict(k="split", src=str(bottom), top=str(top), top_off=top_off, sync=sync, **kw)


def _box(sp, size):
    """Crop box for a shot: by hand (cx/cy px or cxf/cyf fractions), else following the person, else centred."""
    src = sp["src"]
    sw, sh = media.probe_wh(src)
    aspect = size[0] / size[1]
    if any(k in sp for k in ("cx", "cy", "cxf", "cyf")):
        cx = sp.get("cx", sw * sp.get("cxf", 0.5))
        cy = sp.get("cy", sh * sp.get("cyf", 0.5))
        return media.crop_box(src, cx, cy, aspect, sp.get("zoom", 1.0))
    kind = "half" if size[1] == 960 else "full"
    # the talking head sits lower than in Fast Cut, leaving the top of the frame for the title box
    room = 0.10 if kind == "half" else (0.22 if sp["k"] == "talk" else None)
    return media.frame_for(src, kind, sp.get("zoom", 1.0), room=room)[0]


def render_shot(sp, t, n, out):
    """One shot as n frames from source time t."""
    k = sp["k"]
    speed = sp.get("speed", 1.0)
    dur = n / FPS
    look = sp.get("grade", LOOK["grade"])
    if k in ("talk", "cam", "pov"):
        bx = _box(sp, (W, H))
        vf = (f"crop={bx[2]}:{bx[3]}:{bx[0]}:{bx[1]},scale={W}:{H}:flags=lanczos,{media.grade(look, k == 'pov')},"
              f"setpts=(PTS-STARTPTS)/{speed},fps={FPS},format=yuv420p")
        ff(["-ss", f"{max(0.0, t):.3f}", "-t", f"{dur * speed + 1:.3f}", "-i", sp["src"], "-map", "0:v:0", "-vf", vf,
            "-frames:v", n] + media.ENC + [out])
    elif k == "split":
        top = dict(sp, src=sp["top"])
        tb, bb = _box(top, (W, 960)), _box(sp, (W, 960))
        tt = t + sp.get("top_off", 0.0)
        fc = (f"[0:v]crop={tb[2]}:{tb[3]}:{tb[0]}:{tb[1]},scale={W}:960:flags=lanczos,{media.grade(look, True)},"
              f"setpts=PTS-STARTPTS,fps={FPS}[a];"
              f"[1:v]crop={bb[2]}:{bb[3]}:{bb[0]}:{bb[1]},scale={W}:960:flags=lanczos,{media.grade(look)},"
              f"setpts=PTS-STARTPTS,fps={FPS}[b];[a][b]vstack=inputs=2,format=yuv420p[v]")
        ff(["-ss", f"{max(0.0, tt):.3f}", "-t", f"{dur + 1:.3f}", "-i", sp["top"], "-ss", f"{max(0.0, t):.3f}",
            "-t", f"{dur + 1:.3f}", "-i", sp["src"], "-filter_complex", fc, "-map", "[v]", "-frames:v", n] + media.ENC + [out])
    else:
        raise ValueError(f"unknown shot kind {k}")
    # a source that ran out early: hold its last frame so the shot is still n frames
    got = int(os.popen(f"ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames "
                       f"-of csv=p=0 '{out}'").read().strip() or 0)
    if got < n:
        ff(["-i", out, "-vf", f"tpad=stop_mode=clone:stop={n - got}", "-frames:v", n] + media.ENC + [out + ".pad.mp4"])
        os.replace(out + ".pad.mp4", out)


# ---------------------------------------------------------------- sound pieces from what's said
def phrase(src, first, last=None, after=0.0):
    """The sound piece (src, start, end) from the word(s) `first` through the word(s) `last` (text, or the
    seconds a word starts at), cut in the pauses around them as the sound level shows, never inside a word."""
    ws = W_.words_for(src)
    if not ws:
        raise SystemExit(f"{Path(src).name} has no words to cut by (no speech, or no transcript).")
    def idx(x, after_t):
        if isinstance(x, (int, float)):
            return min(range(len(ws)), key=lambda i: abs(ws[i]["s"] - x))
        return W_.find(ws, x, after_t)
    i0 = idx(first, after)
    i1 = i0 if last is None else idx(last, ws[i0]["s"])
    if isinstance(last, str) and len(last.split()) > 1:
        i1 += len(last.split()) - 1
    a, b = W_.cut_points(src, ws, i0, i1)
    return (str(src), a, b)


def phrases(src, start=0.0, seconds=20.0, max_gap=0.55):
    """Whole phrases from `start` until about `seconds` of speech: [(src, a, b)], each cut in a pause."""
    ws = W_.clean(W_.words_for(src))
    out, total = [], 0.0
    for i0, i1 in W_.sentences(ws, max_gap):
        if ws[i0]["s"] < start:
            continue
        a, b = W_.cut_points(src, ws, i0, i1)
        out.append((str(src), a, b))
        total += b - a
        if total >= seconds:
            break
    return out


def jump_cuts(src, pieces, zooms=(1.1, 1.25)):
    """One segment per piece, the talking head alternating between two punch-ins: the classic jump cut."""
    return [dict(a=[p], v=[talk(src, zoom=zooms[k % len(zooms)])]) for k, p in enumerate(pieces)]


def words_in(path, a, b):
    out = []
    for w in W_.words_for(path):   # by where each word starts (Whisper often stretches a word's end into a pause)
        if a - 0.08 <= w["s"] < b - 0.05:
            out.append(dict(w, e=min(w["e"], b)))
    return out


# ---------------------------------------------------------------- drawing
def text_size(d, txt, fnt, stroke=0):
    b = d.textbbox((0, 0), txt, font=fnt, stroke_width=stroke)
    return b[2] - b[0], b[3] - b[1], b


def wrap(d, txt, fnt, maxw):
    lines = []
    for para in txt.split("\n"):
        cur = ""
        for word in para.split(" "):
            t = (cur + " " + word).strip()
            if text_size(d, t, fnt)[0] <= maxw or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    return lines


def draw_box_title(img, txt, y, size=80, maxw=900, pad=(34, 18), center_y=False, look=None):
    lk = look or LOOK
    d = ImageDraw.Draw(img)
    fnt = F(size, lk["font"])
    lines = wrap(d, txt, fnt, maxw - 2 * pad[0])
    lh = int(size * 1.12)
    bw = max(text_size(d, l, fnt)[0] for l in lines) + 2 * pad[0]
    bh = lh * len(lines) + 2 * pad[1] + int(size * 0.12)
    if center_y:
        y = y - bh // 2
    x = (W - bw) // 2
    d.rounded_rectangle([x, y, x + bw, y + bh], radius=26, fill=lk["title_bg"])
    for i, l in enumerate(lines):
        tw, th, b = text_size(d, l, fnt)
        d.text(((W - tw) // 2 - b[0], y + pad[1] + i * lh - b[1] + int(size * 0.08)), l, font=fnt, fill=lk["title_fg"])
    return y + bh


def draw_pill(img, txt, x, y, size=46, fg=(255, 255, 255), bg=(0, 0, 0, 175), anchor="l", look=None):
    lk = look or LOOK
    d = ImageDraw.Draw(img)
    fnt = F(size, lk["label_font"])
    tw, th, b = text_size(d, txt, fnt)
    pw, ph = tw + 44, int(size * 1.45)
    if anchor == "c":
        x = (W - pw) // 2
    d.rounded_rectangle([x, y, x + pw, y + ph], radius=ph // 2, fill=bg)
    d.text((x + 22 - b[0], y + (ph - th) // 2 - b[1]), txt, font=fnt, fill=fg)


def draw_caption(img, chunk, active, y, size=96, look=None):
    """1-3 words, white with a black outline, the word being said in the accent colour; wraps under 940 px."""
    lk = look or LOOK
    d = ImageDraw.Draw(img)
    fnt = F(size, lk["font"])
    stroke = 10
    space = text_size(d, " ", fnt)[0] + 6
    toks = [w["w"] for w in chunk]
    lines, cur, curw = [], [], 0
    for i, t in enumerate(toks):
        tw = text_size(d, t, fnt, stroke)[0]
        if cur and curw + space + tw > 940:
            lines.append(cur)
            cur, curw = [], 0
        cur.append((i, t, tw))
        curw += (space if len(cur) > 1 else 0) + tw
    if cur:
        lines.append(cur)
    lh = int(size * 1.08)
    y0 = y - (lh * len(lines)) // 2
    for li, line in enumerate(lines):
        total = sum(tw for _, _, tw in line) + space * (len(line) - 1)
        x = (W - total) // 2
        for i, t, tw in line:
            col = lk["active"] if i == active else lk["text"]
            b = d.textbbox((0, 0), t, font=fnt, stroke_width=stroke)
            d.text((x - b[0] + stroke, y0 + li * lh), t, font=fnt, fill=col, stroke_width=stroke, stroke_fill=lk["stroke"])
            x += tw + space


def draw_card(img, lines, dim=165, look=None):
    """The footage dims and big lines sit over it. lines: [(text, size, colour)]."""
    lk = look or LOOK
    img.alpha_composite(Image.new("RGBA", (W, H), (0, 0, 0, dim)))
    d = ImageDraw.Draw(img)
    hs = [int(sz * 1.2) for _, sz, _ in lines]
    y = (H - sum(hs)) // 2 - 60
    for (t, sz, col), hh in zip(lines, hs):
        fnt = F(sz, lk["font"])
        tw, th, b = text_size(d, t, fnt, 6)
        d.text(((W - tw) // 2 - b[0], y), t, font=fnt, fill=col, stroke_width=6, stroke_fill=lk["stroke"])
        y += hh


def draw_counter(img, n, y, word="", hot=False, look=None):
    """A count, one number at a time (reps, steps): the word above the number."""
    lk = look or LOOK
    d = ImageDraw.Draw(img)
    col = lk["active"] if hot else lk["text"]
    if word:
        f1 = F(64, lk["font"])
        tw, th, b = text_size(d, word, f1, 8)
        d.text(((W - tw) // 2 - b[0], y), word, font=f1, fill=col, stroke_width=8, stroke_fill=lk["stroke"])
    f2 = F(260, lk["font"])
    tw, th, b = text_size(d, str(n), f2, 12)
    d.text(((W - tw) // 2 - b[0], y + 70 - b[1]), str(n), font=f2, fill=col, stroke_width=12, stroke_fill=lk["stroke"])


def draw_seam(img):
    ImageDraw.Draw(img).rectangle([0, 957, W, 963], fill=(255, 255, 255, 255))


# Overlay makers: (start, end, fn). The kind and words are kept on fn for the build record.
def _ov(t0, t1, fn, kind, text):
    fn.kind, fn.text = kind, text
    return (t0, t1, fn)


def title(t0, t1, txt, y=250, size=80, maxw=900):
    """The white title box (the hook at the start, a closing line at the end)."""
    return _ov(t0, t1, lambda img, look=None: draw_box_title(img, txt, y, size, maxw, look=look), "Title box", txt)


def label(t0, t1, txt, x=40, y=236, anchor="l", size=46, fg=(255, 255, 255), bg=(0, 0, 0, 175)):
    """A small rounded label over the footage (what a camera shows, a weight, a place)."""
    return _ov(t0, t1, lambda img, look=None: draw_pill(img, txt, x, y, size, fg, bg, anchor, look=look), "Label", txt)


def stats_card(t0, t1, lines, dim=165):
    """The footage dims and big lines sit over it. Only real numbers."""
    return _ov(t0, t1, lambda img, look=None: draw_card(img, lines, dim, look=look), "Stats card",
               " · ".join(str(l[0]) for l in lines))


def counter(t0, t1, n, word="", y=260, hot=False):
    return _ov(t0, t1, lambda img, look=None: draw_counter(img, n, y, word, hot, look=look), "Counter", str(n))


def seam(t0, t1):
    return _ov(t0, t1, lambda img, look=None: draw_seam(img), None, "")


# ---------------------------------------------------------------- assembly
def build(name, segs, overlays=(), shoot=None, out=None, cap_y=1330, cap=True, audio_mode="speech", drop_words=(),
          effects=(), look=None, placeholder=False):
    """Render the reel. Returns (path, seconds, caption words). Writes <shoot>/Style Tests/<name>_vN.mp4 (or out;
    never overwrites), <video>.words.txt (every word said, for verify.py), the build record and the sound-effect
    moments (work/<name>/sfx_events.json). audio_mode "speech" levels the voice to -14 LUFS; "nat" keeps footage
    sound (light noise clean-up). placeholder: made-up caption words for footage with no speech (samples only)."""
    lk = dict(LOOK, **(look or {}))
    work = paths.work_dir(STYLE, name)
    cache = paths.cache_dir(STYLE)
    audio, shots, capw, allw = [], [], [], []
    tl = 0.0
    first_src = None
    for sg in segs:
        seg_t0, pieces = tl, []
        for pc in sg["a"]:
            if pc[0] == "gap":
                x = np.zeros(int(round(pc[1] * SR)), np.float32)
                pieces.append(("gap", tl, tl + pc[1], None, None))
            else:
                p, a, b = pc[:3]
                first_src = first_src or p
                x = media.read_audio(p, a, b) * sg.get("gain", 1.0)
                pieces.append((p, tl, tl + (b - a), a, b))
                said = words_in(p, a, b)
                allw += [dict(w=w["w"], s=tl + (w["s"] - a), e=tl + (w["e"] - a)) for w in said]
                if sg.get("cap", cap):
                    for w in W_.clean(said):
                        if any(abs(w["s"] - d) < 0.03 for d in drop_words):
                            continue
                        capw.append(dict(w=w["w"].rstrip(",.;:"), s=tl + (w["s"] - a), e=tl + (w["e"] - a), brk=w.get("brk", False)))
                    if capw:
                        capw[-1]["brk"] = True
            audio.append(x)
            tl += len(x) / SR
        seg_t1, cursor = tl, seg_t0
        for sh in sg["v"]:
            if sh.get("sync"):
                for (p, o0, o1, a, b) in pieces:
                    if p == "gap":
                        continue
                    shots.append((sh, a + sh.get("off", 0.0), o0, o1, p))
                cursor = seg_t1
            else:
                d = sh.get("d") or (seg_t1 - cursor)
                shots.append((sh, sh.get("t", 0.0), cursor, min(seg_t1, cursor + d), None))
                cursor += d
    total = tl
    if placeholder and not capw:
        capw = [dict(w, brk=False) for w in W_.placeholder_words(0.0, total)]
    # --- video: each shot a whole number of frames, the timeline advanced by exactly that
    parts, placed, frames = [], [], 0
    for sh, t, o0, o1, sound_src in shots:
        n = int(round(o1 * FPS)) - int(round(o0 * FPS))
        if n <= 0:
            continue
        first_src = first_src or sh["src"]
        cp = cache / (media.key("th1", sh, t, n, lk["grade"]) + ".mp4")
        if not cp.exists():
            render_shot(dict(sh, grade=sh.get("grade", lk["grade"])), t, n, str(cp) + ".tmp.mp4")
            os.replace(str(cp) + ".tmp.mp4", cp)
        parts.append(str(cp))
        placed.append((sh, t, frames / FPS, (frames + n) / FPS, sound_src))
        frames += n
    total = frames / FPS   # the picture's own length: the sound is padded or trimmed to it, so both end together
    lst = work / "v.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    vpath = work / "video.mp4"
    ff(["-f", "concat", "-safe", 0, "-i", lst, "-c", "copy", vpath])
    au = np.concatenate(audio).astype(np.float32) if audio else np.zeros(1, np.float32)
    n_au = int(round(total * SR))
    au = np.pad(au, (0, max(0, n_au - len(au))))[:n_au]
    apath = work / "audio.f32"
    au.tofile(apath)
    # --- effects on the picture, before captions and overlays
    fx0 = len(fxhook.applied())
    if effects:
        wav = work / "audio_for_fx.wav"
        ff(["-f", "f32le", "-ar", SR, "-ac", 1, "-i", apath, "-c:a", "pcm_s16le", wav])
        vpath = Path(fxhook.effects_pass(vpath, list(effects), words=allw, audio=wav, skin="dark", out=work / "video_fx.mp4"))
    # --- overlays and captions, as a PNG track that changes only when something on it does
    chunks = W_.chunk(capw, maxw=3, maxc=17, gap=0.45, max_word=10.0) if cap else []
    events = {0.0, total}
    for (a, b, fn) in overlays:
        events |= {max(0, a), min(total, b)}
    cap_spans = []
    for ci, ch in enumerate(chunks):
        end = ch[-1]["e"] + 0.25
        if ci + 1 < len(chunks):
            end = min(end, chunks[ci + 1][0]["s"])
        for wi, w in enumerate(ch):
            ws_ = ch[0]["s"] if wi == 0 else w["s"]
            we = ch[wi + 1]["s"] if wi + 1 < len(ch) else end
            if we > ws_:
                cap_spans.append((ws_, we, ci, wi))
                events |= {ws_, we}
    ev = sorted(e for e in events if 0 <= e <= total)
    ovdir = work / "ov"
    ovdir.mkdir(exist_ok=True)
    cl, cache_png, k = ["ffconcat version 1.0"], {}, None
    for a, b in zip(ev[:-1], ev[1:]):
        if b - a < 1e-4:
            continue
        mid = (a + b) / 2
        act = tuple(i for i, (x, y, fn) in enumerate(overlays) if x <= mid < y)
        cs = next(((ci, wi) for (x, y, ci, wi) in cap_spans if x <= mid < y), None)
        k = (act, cs)
        if k not in cache_png:
            img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for i in act:
                _draw_overlay(overlays[i][2], img, lk)
            if cs:
                draw_caption(img, chunks[cs[0]], cs[1], cap_y, look=lk)
            pth = ovdir / f"o{len(cache_png):04d}.png"
            img.save(pth, compress_level=1)
            cache_png[k] = pth
        cl.append(f"file '{cache_png[k]}'\nduration {b - a:.4f}")
    if k is not None:
        cl.append(f"file '{cache_png[k]}'")
    olist = work / "ov.txt"
    olist.write_text("\n".join(cl) + "\n")
    # --- final
    dest = paths.output_for(name, shoot, out, near=first_src)
    af = ("highpass=f=70,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" if audio_mode == "speech"
          else "highpass=f=70,afftdn=nf=-30,volume=4dB,alimiter=limit=0.7:level=false,aresample=48000")
    ff(["-i", vpath, "-f", "concat", "-safe", 0, "-i", olist, "-f", "f32le", "-ar", SR, "-ac", 1, "-i", apath,
        "-filter_complex", f"[1:v]fps={FPS},format=rgba[o];[0:v][o]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v];"
                           f"[2:a]{af},pan=stereo|c0=c0|c1=c0[a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", 18, "-profile:v", "high", "-level", "4.2",
        "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ar", SR, "-t", f"{total:.3f}", "-movflags", "+faststart", dest])
    W_.write_words(str(dest) + ".words.txt", allw or capw)
    cuts = [round(pc[1], 3) for pc in _pieces(segs) if pc[1] > 0.01]   # where one sound piece meets the next
    (work / "cuts.json").write_text(json.dumps({"video": str(dest), "cuts": cuts}, indent=1))
    sfx = []
    for (a, b, fn) in overlays:
        kind = getattr(fn, "kind", None)
        if kind == "Title box":
            sfx.append(dict(t=round(max(0.0, a), 3), type="whoosh", len=0.35))
        elif kind in ("Label", "Counter"):
            sfx.append(dict(t=round(max(0.0, a), 3), type="pop"))
    (work / "sfx_events.json").write_text(json.dumps(sorted(sfx, key=lambda e: e["t"]), indent=1))
    print(f"{dest}  {total:.2f} s")
    print(f"  check the words: .venv/bin/python styles/talking-head/verify.py \"{dest}\"")
    keep_record(placed, overlays, total, audio_mode, dest, apath, af, work, fx0, _pieces(segs))
    return str(dest), total, capw


def _draw_overlay(fn, img, lk):
    try:
        fn(img, look=lk)
    except TypeError:   # an overlay written as fn(img)
        fn(img)


def _pieces(segs):
    """Every sound piece with its reel time: [(src, t0, t1, a, b)] (gaps included)."""
    out, tl = [], 0.0
    for sg in segs:
        for pc in sg["a"]:
            if pc[0] == "gap":
                n = int(round(pc[1] * SR))
                out.append(("gap", tl, tl + n / SR, None, None))
            else:
                p, a, b = pc[:3]
                n = int(round((b - a) * SR))
                out.append((p, tl, tl + n / SR, a, b))
            tl += n / SR
    return out


# ---------------------------------------------------------------- build record
def _clip_name(p):
    return Path(str(p)).name


def keep_record(placed, overlays, total, audio_mode, out, apath, af, work, fx0=0, pieces=()):
    """What the reel shows over each stretch (punch-ins, B-roll, two camera views, sped-up footage, the title box,
    labels, stats cards, counters, library effects) and its one sound track. Captions are not blocks; a talking
    shot or footage playing its own sound is plain footage (no block). Kept in the work folder; the maps go beside
    the video."""
    rec = record.new("styles/talking-head/reelkit.py",
                     [os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0].endswith(".py") else None, __file__])
    if rec is None:
        return
    talks = [sh.get("zoom", 1.0) for sh, *_ in placed if sh["k"] == "talk"]
    base = min(talks) if talks else 1.0
    for sh, t, p0, p1, sound_src in placed:
        k, speed = sh["k"], sh.get("speed", 1.0)
        own = sound_src is not None and sound_src == sh["src"]
        if k == "split":
            key, detail = "split", ""
        elif speed != 1:
            key, detail = "speed", f"{speed:g}x speed"
        elif sh.get("sync") and own and k == "talk" and sh.get("zoom", 1.0) > base + 1e-6:
            key, detail = "punch", f"{sh.get('zoom', 1.0):g}x crop; the wider shots are {base:g}x"
        elif sh.get("sync") and own:
            key, detail = "talk", ""
        else:
            key, detail = "broll", f"{_clip_name(sh['src'])}, from {int(t // 60)}:{int(t % 60):02d}"
        record.layout(rec, "talking-head", key, p0, min(p1, total), detail)
    for a, b, fn in overlays:
        kind = getattr(fn, "kind", None)
        if kind:
            rec.block(max(0.0, a), min(total, b), kind, None, getattr(fn, "text", ""), kind.lower().replace(" ", "_"), "graphic")
    for name, a, b in fxhook.applied()[fx0:]:
        rec.effect(name, a, b)
    for sh, t, p0, p1, sound_src in placed:   # the raw seconds used: every shot's picture...
        span = (p1 - p0) * sh.get("speed", 1.0)
        record.used(rec, sh["src"], t, min(t + span, media.probe(sh["src"])["duration"] or t + span))
        if sh["k"] == "split":
            record.used(rec, sh["top"], t + sh.get("top_off", 0.0), t + sh.get("top_off", 0.0) + span)
    for src, o0, o1, a, b in pieces:          # ...and every piece of sound
        if src != "gap":
            record.used(rec, src, a, b)
    rec.track_cmd("voice_nat" if audio_mode == "speech" else "nat",
                  ["-f", "f32le", "-ar", SR, "-ac", 1, "-i", str(apath), "-filter_complex", f"[0:a]{af}[out]"])
    record.save(rec, out, keep_in=work)
