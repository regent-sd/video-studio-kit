"""Sketch words: your words, hand-written in marker on the room beside your head as you say them,
with doodles (an underline, a loose circle, an arrow pointing at you)."""
import math, re
import numpy as np
from PIL import Image, ImageFilter
from core import (W, H, SS, text_img, comp, scaled, key_words, norm_word, ease_out, ease_in, ease_io, prog, lerp,
                  clamp, hexc, HAND, CHALK)
from catalog._b import face_stats, behind

NAME = "sketch-words"
KIND = "behind"
ABOUT = "Hand-written marker words and doodles appear on the room as you say them"
DUR = 4.0
PARAMS = dict(
    words=None,       # ["better", ...] or [{"text": "...", "on": "word you say" | seconds}]; default your strongest words in the window
    max_words=3,      # how many words (default picks the longest ones, spread out in time)
    font="hand",      # hand (Bradley Hand) | chalk (Chalkduster)
    color=None,       # word colour; default white
    doodle=None,      # doodle colour; default the skin's accent
    doodles=["underline", "arrow", "circle"],   # per spot (above your head, roomier side, other side): underline | arrow | circle | none
    layer="behind",   # behind (written on the room, you in front) | front
    case="lower",     # lower | upper | as-said
)
FONTS = {"hand": HAND, "chalk": CHALK}
BOIL = 3            # frames per hand-jitter step (10 fps "boil")


# ------------------------------------------------------------------ which words, and when
def _pick(c):
    ws = c.p.get("words")
    out = []
    if ws:
        for k, it in enumerate(ws):
            txt, on = (it.get("text"), it.get("on")) if isinstance(it, dict) else (str(it), str(it))
            t = None
            if isinstance(on, (int, float)): t = float(on)
            else:
                w = next((w for w in c.words_in() if norm_word(w["w"]) == norm_word(str(on))), None)
                t = w["s"] if w else None
            if t is None: t = c.t0 + 0.3 + k * max(0.6, (c.d - 1.0) / max(1, len(ws)))
            out.append((str(txt), t))
        return sorted(out, key=lambda x: x[1])
    cand = key_words(c.words_in(c.t0, c.t1 - 0.5))
    seen, uniq = set(), []
    for w in cand:
        n = norm_word(w["w"])
        if n in seen: continue
        seen.add(n); uniq.append(w)
    n = int(c.p.get("max_words") or 3)
    chosen = []
    for w in sorted(uniq, key=lambda w: (-len(norm_word(w["w"])), w["s"])):
        if len(chosen) >= n: break
        if all(abs(w["s"] - x["s"]) >= 0.9 for x in chosen): chosen.append(w)
    chosen.sort(key=lambda w: w["s"])
    return [(re.sub(r"[^\w'-]", "", w["w"]), w["s"]) for w in chosen]

def _case(c, s):
    m = c.p.get("case", "lower")
    return s.lower() if m == "lower" else s.upper() if m == "upper" else s


# ------------------------------------------------------------------ where they go
def _slots(c):
    """Room space beside / above the head: [(cx, cy, max_w, max_h, rot, kind)] in the order to use them."""
    (fx, fy, fw, fh), u = face_stats(c)
    top = min(u[1], fy - fh * 0.5) - fh * 0.45            # roughly the top of the head at its highest
    left_edge, right_edge = u[0] + fw * 0.06, u[2] - fw * 0.06
    slots = []
    tb = top - 30 - 236                                     # height of the band above the head
    if tb >= 110:
        slots.append(((W / 2 + clamp(fx, 300, W - 300)) / 2, 236 + tb * 0.5, W - 120, min(tb * 0.8, 210), -3, "top"))
    lw, rw = left_edge - 40, W - right_edge - 40
    sy = clamp(fy - fh * 0.78, 300, 1300)
    sides = sorted([("left", lw, (24 + left_edge - 16) / 2, 6), ("right", rw, (right_edge + 16 + W - 24) / 2, -6)],
                   key=lambda s: -s[1])
    for name, bw, x, rot in sides:
        if bw >= 170:
            slots.append((x, sy, bw, 150, rot, name))
    if tb >= 330:                                             # tall room above: a second line up there
        slots.append((W / 2 - 120, 236 + tb * 0.2, W - 260, 160, 4, "top2"))
    if not slots:                                             # nowhere clear: the top of the frame anyway
        slots.append((W / 2, 330, W - 120, 160, -3, "top"))
    return slots


# ------------------------------------------------------------------ the strokes
def _word_layers(txt, size, col, path):
    """(word RGBA, its shadow RGBA, per-column ink centre y, ink x range)."""
    im = text_img(txt, size, 400, col, 0, path, 0, max(1, int(size / 70)), col)
    pad = 26
    cv = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    cv.alpha_composite(im, (pad, pad))
    A = np.asarray(cv.getchannel("A"), np.float32) / 255
    cols = A.sum(0)
    ys = np.arange(A.shape[0], dtype=np.float32)
    cy = np.where(cols > 0.5, (A * ys[:, None]).sum(0) / np.maximum(cols, 1e-6), np.nan)
    xs = np.arange(len(cy))
    ok = ~np.isnan(cy)
    cy = np.interp(xs, xs[ok], cy[ok]) if ok.any() else np.full(len(cy), A.shape[0] / 2)
    k = 15
    cy = np.convolve(np.pad(cy, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    inked = np.where(ok)[0]
    x0, x1 = (int(inked[0]), int(inked[-1])) if len(inked) else (0, A.shape[1])
    sh = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    sh.putalpha(cv.getchannel("A").filter(ImageFilter.GaussianBlur(5)).point(lambda v: int(v * 0.55)))
    return cv, sh, cy, (x0, x1)

def _path_underline(box, rng):
    x0, y0, x1, y1 = box
    n = 40
    y = y1 + 6
    pts = []
    for i in range(n + 1):
        f = i / n
        x = lerp(x0 - 6, x1 + 14, f)
        yy = y + 5 * math.sin(f * math.pi * 1.6 + 0.4) - 10 * f ** 3     # a gentle wave with a flick up at the end
        pts.append((x, yy))
    return pts

def _path_circle(box, rng):
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2 + 34, (y1 - y0) / 2 + 26
    a0 = math.radians(200)
    n = 70
    pts = []
    for i in range(n + 1):
        f = i / n
        a = a0 + f * 2 * math.pi * 1.1
        r = 1 + 0.05 * math.sin(f * 7 + 1) + 0.06 * f                 # loose: it doesn't close exactly
        pts.append((cx + rx * r * math.cos(a), cy + ry * r * math.sin(a) - 6 * f))
    return pts

def _path_arrow(box, target, rng):
    x0, y0, x1, y1 = box
    tx, ty = target
    side = 1 if tx < (x0 + x1) / 2 else -1                  # 1: the word is right of the head
    sx = (x0 + 0.3 * (x1 - x0)) if side > 0 else (x1 - 0.3 * (x1 - x0))
    sy = y1 + 18
    ty = max(ty, sy + 120)
    cx_, cy_ = sx + side * 14, ty - 6                        # down first, then hook in
    pts = []
    n = 44
    for i in range(n + 1):
        f = i / n
        x = (1 - f) ** 2 * sx + 2 * (1 - f) * f * cx_ + f ** 2 * tx
        y = (1 - f) ** 2 * sy + 2 * (1 - f) * f * cy_ + f ** 2 * ty
        pts.append((x, y))
    return pts

def _jit(pts, rng, amt):
    off = rng.normal(0, amt, (len(pts), 2))
    off = np.cumsum(off, 0) * 0.25                                   # correlated wobble, not fizz
    off -= np.linspace(0, 1, len(pts))[:, None] * off[-1:]           # pinned ends
    return [(x + o[0], y + o[1]) for (x, y), o in zip(pts, off)]

def _draw_stroke(cv, pts, p, col, width, head=None):
    """Draw the first p (0-1) of a polyline with round caps (and an arrow head once complete), antialiased."""
    if p <= 0 or len(pts) < 2: return
    n = max(2, int(round(len(pts) * p)))
    sub = pts[:n]
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
    pad = width + 40
    bx0, by0 = int(min(xs)) - pad, int(min(ys)) - pad
    bx1, by1 = int(max(xs)) + pad, int(max(ys)) + pad
    s = SS(bx1 - bx0, by1 - by0)
    loc = [(x - bx0, y - by0) for x, y in sub]
    s.line([(x + 2, y + 4) for x, y in loc], (0, 0, 0, 80), width + 2)
    s.line(loc, col + (255,), width)
    if head is not None and head > 0:
        (ax, ay), (bx, by) = pts[-6], pts[-1]
        ang = math.atan2(by - ay, bx - ax)
        L = 34 * min(1, head * 1.6)
        for da in (2.55, -2.55):
            ex, ey = bx + L * math.cos(ang + da), by + L * math.sin(ang + da)
            s.line([(bx - bx0 + 2, by - by0 + 4), (ex - bx0 + 2, ey - by0 + 4)], (0, 0, 0, 80), width + 2)
            s.line([(bx - bx0, by - by0), (ex - bx0, ey - by0)], col + (255,), width)
    o = s.out()
    comp(cv, o, bx0, by0)


# ------------------------------------------------------------------ render
def render(c):
    st = c.state
    path = FONTS.get(c.p.get("font", "hand"), HAND)
    col = hexc(c.p["color"]) if c.p.get("color") else (255, 255, 255)
    dcol = hexc(c.p["doodle"]) if c.p.get("doodle") else tuple(c.skin.accent)
    if "items" not in st:
        words = _pick(c)
        slots = _slots(c)
        (fx, fy, fw, fh), u = face_stats(c)
        doods = list(c.p.get("doodles") or [])
        words = words[:len(slots)]
        by_len = sorted(range(len(words)), key=lambda j: -len(words[j][0]))
        pairs = sorted(((words[j], slots[r], r) for r, j in enumerate(by_len)), key=lambda x: x[0][1])
        items = []
        for k, ((txt, t), sl, r) in enumerate(pairs):
            txt = _case(c, txt)
            if not txt: continue
            sx, sy, mw, mh, rot, kind = sl
            size = 170 if kind.startswith("top") else 124
            lay, sh, cyc, (ix0, ix1) = _word_layers(txt, size, col, path)
            s = min(1.0, mw / (ix1 - ix0 + 20), mh / lay.height * 1.25)
            if s < 0.999:
                lay, sh, cyc, (ix0, ix1) = _word_layers(txt, size * s, col, path)
            dur = clamp(0.065 * len(txt), 0.35, 0.8)
            x = sx - lay.width / 2; y = sy - lay.height / 2
            dd = doods[r] if r < len(doods) else "none"
            m = 60 if dd == "circle" else 24                  # a circle reaches further out than the word
            x = clamp(x, m - ix0, W - m - ix1)
            box = (x + ix0, y + 26 + lay.height * 0.12, x + ix1, y + lay.height - 26 - lay.height * 0.05)
            if dd == "arrow" and not kind.startswith(("left", "right")): dd = "underline"
            rng = np.random.default_rng(31 + k)
            if dd == "underline": pts = _path_underline(box, rng)
            elif dd == "circle": pts = _path_circle(box, rng)
            elif dd == "arrow":
                side = 1 if (box[0] + box[2]) / 2 > fx else -1
                pts = _path_arrow(box, (fx + side * (fw * 0.5 + 30), fy - fh * 0.08), rng)
            else: pts = None
            items.append(dict(txt=txt, t=t, dur=dur, lay=lay, sh=sh, cy=cyc, ix=(ix0, ix1), x=x, y=y, rot=rot,
                              dd=dd, pts=pts, seed=97 * k + 5))
        st["items"] = items
    out_d = min(0.35, c.d * 0.2)
    fade = 1 - ease_in(prog(c.u, c.d - out_d, out_d))
    if fade <= 0.001: return c.img
    cv = c.canvas()
    step = c.i // BOIL
    drawn = False
    for it in st["items"]:
        p = prog(c.t, it["t"] - 0.04, it["dur"])
        if p <= 0: continue
        drawn = True
        rng = np.random.default_rng(it["seed"] * 1000 + step)
        jx, jy, jr = rng.normal(0, 1.1), rng.normal(0, 1.1), rng.normal(0, 0.35)
        lay, sh = it["lay"], it["sh"]
        ix0, ix1 = it["ix"]
        # reveal left to right with a soft edge, as if written
        rx = ix0 + (ix1 - ix0 + 6) * ease_io(p) if p < 1 else lay.width + 50
        if p < 1:
            xs = np.arange(lay.width, dtype=np.float32)
            ramp = np.clip((rx - xs) / 10 + 0.5, 0, 1)
            a = np.asarray(lay.getchannel("A"), np.float32) * ramp[None, :]
            l2 = lay.copy(); l2.putalpha(Image.fromarray(a.astype(np.uint8), "L"))
            a2 = np.asarray(sh.getchannel("A"), np.float32) * np.clip((rx + 6 - xs) / 14 + 0.5, 0, 1)[None, :]
            s2 = sh.copy(); s2.putalpha(Image.fromarray(a2.astype(np.uint8), "L"))
        else:
            l2, s2 = lay, sh
        rot = it["rot"] + jr
        # a tiny settle: the word lands slightly big and eases to size
        pop = 1 + 0.03 * (1 - ease_out(prog(c.t, it["t"], it["dur"] + 0.25)))
        if fade < 1: pop *= 0.97 + 0.03 * fade
        cxw, cyw = it["x"] + lay.width / 2 + jx, it["y"] + lay.height / 2 + jy - 10 * (1 - fade)
        for im, dx, dy in ((s2, 4, 7), (l2, 0, 0)):
            r = scaled(im, pop).rotate(rot, Image.BICUBIC, expand=True)
            if fade < 1:
                r = r.copy(); r.putalpha(r.getchannel("A").point(lambda v: int(v * fade)))
            comp(cv, r, cxw - r.width / 2 + dx, cyw - r.height / 2 + dy)
        # the pen tip, leading the ink
        if 0 < p < 1:
            px = int(clamp(rx, 0, lay.width - 1))
            py = it["cy"][px]
            # rotate (px, py) about the word centre to match the word
            ox, oy = (px - lay.width / 2) * pop, (py - lay.height / 2) * pop
            ar = math.radians(-rot)
            qx = cxw + ox * math.cos(ar) - oy * math.sin(ar); qy = cyw + ox * math.sin(ar) + oy * math.cos(ar)
            s = SS(48, 48)
            s.circ(24, 24, 17, fill=dcol + (70,)); s.circ(24, 24, 9, fill=dcol + (255,)); s.circ(22, 22, 3.5, fill=(255, 255, 255, 220))
            comp(cv, s.out(), qx - 24, qy - 24)
        # the doodle, after the word
        if it["pts"]:
            dd_dur = 0.45 if it["dd"] == "circle" else 0.38
            q = prog(c.t, it["t"] - 0.04 + it["dur"] * 0.92, dd_dur)
            if q > 0:
                pts = _jit(it["pts"], np.random.default_rng(it["seed"] + step), 1.6)
                pts = [(x + jx, y + jy) for x, y in pts]
                head = prog(c.t, it["t"] + it["dur"] * 0.92 + dd_dur - 0.04, 0.16) if it["dd"] == "arrow" else None
                lay_d = Image.new("RGBA", (W, H), (0, 0, 0, 0)) if fade < 1 else cv
                _draw_stroke(lay_d, pts, ease_io(q), dcol, 8, head)
                if fade < 1:
                    lay_d.putalpha(lay_d.getchannel("A").point(lambda v: int(v * fade)))
                    cv.alpha_composite(lay_d)
    if not drawn: return c.img
    if c.p.get("layer", "behind") == "front": return c.front(cv)
    return behind(c, cv)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the words are your own (picked from what you say in the window)",
    "needs": ["talk"],
}
