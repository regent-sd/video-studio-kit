"""Shared helpers for ui-world, phone-mockup, pull-back and chart-grow (light app UI, tap ripples, item lists).
(Files starting with _ are not effects.)"""
import math, re
import numpy as np
from core import W, H, FPS, key_words, norm_word, clamp, clamp01, ease_out, prog
from ._ui import spoken, clean, when, is_filler

SENT_END = ".!?"

def faces_in(c):
    """Face boxes (N x 4: cx, cy, w, h) over the effect window, cached in c.state."""
    st = c.state
    if "_faces_in" not in st:
        i0 = int(c.t0 * FPS); i1 = max(i0 + 1, int(c.t1 * FPS) + 1)
        fs = np.asarray(c.subj.faces[i0:i1], np.float32) if len(c.subj.faces) else np.zeros((0, 4), np.float32)
        if not len(fs): fs = np.asarray([c.face], np.float32)
        st["_faces_in"] = fs
    return st["_faces_in"]

def head_top_low(c, pct=10):
    """A high-ish top of the head over the window (px): the pct-th percentile, so a lean-in is allowed for."""
    fs = faces_in(c)
    return float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], pct))

def face_span(c):
    """(x0, x1, y0, y1) the face covers over the window (10th-90th percentile, so a stray frame doesn't count)."""
    fs = faces_in(c)
    x0 = float(np.percentile(fs[:, 0] - fs[:, 2] / 2, 8)); x1 = float(np.percentile(fs[:, 0] + fs[:, 2] / 2, 92))
    y0 = float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], 8)); y1 = float(np.percentile(fs[:, 1] + 0.62 * fs[:, 3], 92))
    return x0, x1, y0, y1

def sentence(c, max_words=9, a=None, b=None):
    """The first sentence said in the window (ums dropped), cut to max_words with an ellipsis. '' if nothing is said."""
    ws = [w["w"] for w in spoken(c, a, b)]
    if not ws: return ""
    out = []
    for w in ws:
        out.append(w)
        if w.rstrip()[-1:] in SENT_END and len(out) >= 3: break
    if len(out) > max_words:
        commas = [i for i, w in enumerate(out[:max_words]) if w.rstrip()[-1:] in ",;:" and i >= 3]
        if commas:                       # end on a finished clause, when there is one
            out = out[:commas[-1] + 1]
            out[-1] = out[-1].rstrip(",;:")
        else:
            out = out[:max_words]
            out[-1] = out[-1].rstrip(",;:") + "…"
    s = " ".join(out).strip().rstrip(",;:")
    return s[:1].upper() + s[1:]

def key_items(c, max_items=4):
    """[(label, seconds)] one per key word said in the window (no repeats), picked evenly if there are more."""
    seen, ws = set(), []
    for w in key_words(c.words_in()):
        n = norm_word(w["w"])
        if n not in seen: seen.add(n); ws.append(w)
    m = max(1, int(max_items or 4))
    if len(ws) > m:
        ws = [ws[int(round(i * (len(ws) - 1) / (m - 1)))] for i in range(m)] if m > 1 else ws[:1]
    return [(clean(w["w"]).capitalize(), w["s"]) for w in ws]

def given_items(c, items, lo, hi):
    """Items from a setting: strings, or {"label", "on"} (on: a word you say, or seconds into the video).
    Items without a time are spread evenly over [lo, hi]."""
    out = []
    n = len(items)
    for k, it in enumerate(items):
        if isinstance(it, str): it = {"label": it}
        fb = lo + (hi - lo) * (k + 1) / (n + 1)
        out.append((str(it.get("label", "")), when(c, it.get("on"), fb)))
    # keep them in order, a little apart
    for k in range(1, len(out)):
        if out[k][1] < out[k - 1][1] + 0.12: out[k] = (out[k][0], out[k - 1][1] + 0.12)
    return out

def ripple(s, cx, cy, r, k, col=(255, 255, 255), grow=70, a=0.5, width=3.0):
    """A tap ripple on an SS: a ring growing from radius r by grow px as k goes 0 -> 1, fading out."""
    if k <= 0 or k >= 1: return
    e = ease_out(k)
    rr = r + grow * e
    al = a * (1 - k) ** 1.4
    s.circ(cx, cy, rr, fill=tuple(col) + (int(255 * al * 0.25),))
    s.circ(cx, cy, rr, outline=tuple(col) + (int(255 * al),), width=width)

def press(t, t_tap, down=0.09, up=0.32, depth=0.14, over=0.05):
    """Scale of a pressed button around a tap at t_tap: dips to 1 - depth, springs back past 1 by over."""
    if t < t_tap - down: return 1.0
    if t < t_tap: return 1 - depth * ease_out((t - (t_tap - down)) / down)
    k = clamp01((t - t_tap) / up)
    return 1 - depth * (1 - k) + over * math.sin(math.pi * k) * (1 - k * 0.3) if k < 1 else 1.0

def blink(idle, hold=0.45, period=1.06):
    """Caret opacity: solid while typing, blinking once idle for hold seconds."""
    if idle < hold: return 1.0
    return (0.5 + 0.5 * math.cos((idle - hold) * 2 * math.pi / period)) ** 0.6

def wrap_idx(text, f, maxw):
    """Word-wrap text with font f to maxw px: [(start, end)] character spans of each line."""
    lines, cs, ce = [], None, None
    for m in re.finditer(r"\S+", text):
        if cs is None:
            cs, ce = m.start(), m.end(); continue
        if f.getlength(text[cs:m.end()]) > maxw:
            lines.append((cs, ce)); cs, ce = m.start(), m.end()
        else:
            ce = m.end()
    if cs is not None: lines.append((cs, ce))
    return lines

def type_schedule(toks, t_first, fast=0.024, slow=0.06):
    """toks: [(word, start seconds)] -> (text, char times). Each word types from when it's said, letter by letter;
    a word that would start before the last one finishes waits, and types fast to catch up."""
    parts, times = [], []
    prev_end = -1e9
    for i, (w, s) in enumerate(toks):
        nxt = toks[i + 1][1] if i + 1 < len(toks) else s + 0.6
        dt = clamp((nxt - s) / (len(w) + 1.5), fast, slow)
        a = max(s, t_first, prev_end + fast)
        if a > s + 0.08: dt = fast
        if i > 0:
            parts.append(" "); times.append(a - 1e-3)
        for j, ch in enumerate(w):
            parts.append(ch); times.append(a + j * dt)
        prev_end = a + max(0, len(w) - 1) * dt
    return "".join(parts), np.asarray(times, np.float64)

def match_times(c, words, lo, hi):
    """Times for a given list of words: when each one is said (in order, looking a few words ahead),
    else spread evenly over [lo, hi]. Returns [(word, seconds)]."""
    said = spoken(c)
    out, j, n = [], 0, len(words)
    for i, w in enumerate(words):
        ts = None
        for k in range(j, min(len(said), j + 4)):
            if norm_word(said[k]["w"]) == norm_word(w):
                ts = said[k]["s"]; j = k + 1; break
        out.append([w, ts if ts is not None else lo + (hi - lo) * i / max(1, n)])
    for i in range(1, len(out)):
        out[i][1] = max(out[i][1], out[i - 1][1] + 0.04)
    return [tuple(x) for x in out]
