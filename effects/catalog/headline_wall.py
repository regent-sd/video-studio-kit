"""Headline wall: snippets of what you say pop up on the room around your head, each in a different style (a post
card, a search bar, a sticky note, a newspaper clipping, a chat bubble, a headline strip), tilted at different depths
with a little parallax, then pop away one by one."""
import math, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, FPS, SS, font, place, f32, to_pil, mix, over, ease_out, ease_in, back, prog, lerp, clamp,
                  norm_word, SFP, HAND, NEWYORK, GEORGIA)
from catalog._b import face_stats, smooth_noise, solid_mask
from catalog._ui import circle_mask, heart_pts
from catalog._print import paper, torn_path
from catalog._wall import chunks, near_window, short_phrases, has_strong

NAME = "headline-wall"
KIND = "behind"
ABOUT = "Your lines pop up around your head as a post, a search, a sticky note, a clipping, a chat bubble and a headline"
DUR = 5.0
PARAMS = dict(
    lines=None,      # the snippets, in the order of styles: a list of texts; default lines and phrases you say
    styles=["clipping", "post", "search", "sticky", "chat", "headline"],   # which snippets (post | search | sticky | clipping | chat | headline), in pop order
    handle="you",    # the name on the post card; "" for a blank name bar
    dim=0.35,        # how much the room darkens behind the snippets (0-1)
)
# each style's tilt (ry, rx, rz) and depth z (far ones are a touch smaller, softer and move less with you)
TILT = {
    "clipping": ((12, 4, -4.5), 0.86),
    "post":     ((-10, 3, 3.0), 1.0),
    "search":   ((0, 8, -1.5), 1.02),
    "sticky":   ((10, -2, -6.0), 0.95),
    "chat":     ((-14, 0, 2.5), 0.97),
    "headline": ((8, -3, -2.0), 0.9),
}
PRIORITY = ["post", "search", "sticky", "headline", "chat", "clipping"]     # who gets first pick of the lines
INK = (22, 22, 24)


# ------------------------------------------------------------------ which words
def _texts(c, styles):
    given = c.p.get("lines")
    if given:
        g = [str(x.get("text") if isinstance(x, dict) else x) for x in given]
        return {s: (g[k] if k < len(g) else "") for k, s in enumerate(styles)}
    words = c.words or []
    longs = [x for x in near_window(chunks(words, 58), c.t0, c.t1) if has_strong(x[0])]
    sp = short_phrases(words, 32)
    inwin = sorted([x for x in sp if c.t0 - 0.3 <= x[1] <= c.t1], key=lambda x: -x[4])
    shorts = inwin + near_window([x for x in sp if x not in inwin], c.t0, c.t1)
    used = []
    def take(pool):
        for x in pool:
            if any(x[1] < ue - 0.01 and x[2] > us + 0.01 for us, ue in used): continue
            used.append((x[1], x[2])); return x[0].rstrip(",")
        return ""
    out = {}
    tiny = [x for x in shorts if len(x[0]) <= 20]
    for s in sorted(styles, key=lambda s: PRIORITY.index(s) if s in PRIORITY else 9):
        short = s in ("search", "sticky", "headline")
        out[s] = (take(tiny) if s == "headline" else "") or take(shorts if short else longs) or take(longs if short else shorts) or \
                 ((shorts if short else longs) or [("",)])[0][0]
    return out


def _regions(c):
    """Room around the head: the band above it and the strips either side (from the face over the whole window,
    allowing for some of the head's movement: snippets sit behind you, so a lean can cover an edge for a moment)."""
    (fx, fy, fw, fh), (bx0, by0, bx1, by1) = face_stats(c)
    ht = by0 - fh * 0.17                                     # top of the hair at its highest
    hx0 = fx - fw * 0.5 - 0.35 * max(0, fx - fw / 2 - bx0)
    hx1 = fx + fw * 0.5 + 0.35 * max(0, bx1 - fx - fw / 2)
    sh = min(1460, fy + fh * 0.72)                          # where the shoulders start
    top = (24, 226, W - 24, clamp(ht - 10, 420, 1000))
    left = (24, max(top[3] - 30, ht), hx0 - 8, sh)
    right = (hx1 + 8, max(top[3] - 30, ht) + 20, W - 24, sh)
    return (fx, fy, fw, fh), top, left, right

def _slots(c):
    """A target box (x0, y0, x1, y1) for each style."""
    (fx, fy, fw, fh), top, left, right = _regions(c)
    tx0, ty0, tx1, ty1 = top
    mid = clamp(fx, tx0 + 290, tx1 - 290)
    out = {
        "search": (mid - 290, ty0, mid + 290, ty0 + 100),
        "clipping": (tx0, ty0 + 56, mid + 20, ty1 + 50),
        "post": (mid + 10, ty0 + 70, tx1, ty1 + 40),
    }
    ok = [r for r in (left, right) if r[2] - r[0] >= 210]
    def part(r, a, b): return (r[0], r[1] + (r[3] - r[1]) * a, r[2], r[1] + (r[3] - r[1]) * b)
    if len(ok) == 2:
        out["sticky"] = part(left, 0, 0.62); out["chat"] = part(right, 0, 0.56)
        wide = max(ok, key=lambda r: r[2] - r[0])
        out["headline"] = part(right if wide is right else left, 0.62, 1.0) if (wide is right) else part(left, 0.66, 1.0)
    elif len(ok) == 1:
        r = ok[0]
        out["sticky"] = part(r, 0, 0.42); out["chat"] = part(r, 0.42, 0.76); out["headline"] = part(r, 0.76, 1.0)
    else:                                   # no room beside the head: everything up top, overlapping
        out["sticky"] = (tx0, ty0 + 60, tx0 + 320, ty1); out["chat"] = (tx1 - 360, ty0 + 120, tx1, ty1)
        out["headline"] = (tx0 + 40, ty1 - 90, tx1 - 40, ty1 + 10)
    return out


# ------------------------------------------------------------------ text helpers
def _wrap(txt, f, maxw, maxlines=4):
    words, lines, cur = txt.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and f.getlength(t) > maxw:
            lines.append(cur); cur = w
        else:
            cur = t
    if cur: lines.append(cur)
    if len(lines) > maxlines:
        lines = lines[:maxlines]
        while lines[-1] and f.getlength(lines[-1] + "…") > maxw: lines[-1] = lines[-1].rsplit(" ", 1)[0]
        lines[-1] = lines[-1].rstrip(",.") + "…"
    return lines

def _fit(txt, path, weight, maxw, maxlines, smax, smin, index=0):
    for size in range(smax, smin - 1, -2):
        f = font(size, weight, path, index)
        ls = _wrap(txt, f, maxw, 99)
        if len(ls) <= maxlines and all(f.getlength(l) <= maxw for l in ls): return size, ls
    f = font(smin, weight, path, index)
    return smin, _wrap(txt, f, maxw, maxlines)


# ------------------------------------------------------------------ the snippets (RGBA, drawn once)
def _post(c, txt, sf, maxw=9999):
    w = int(min(520 * sf, maxw)); pad = int(30 * sf)
    size, lines = _fit(txt, SFP, 600, w - 2 * pad, 3, int(38 * sf), int(28 * sf))
    av = int(66 * sf)
    lh = size * 1.24
    h = int(pad + av + 18 * sf + lh * len(lines) + 24 * sf + 40 * sf + pad * 0.7)
    s = SS(w, h)
    s.rr((0, 0, w, h), 30 * sf, fill=(255, 255, 255, 255))
    # avatar: your face, from the frame the effect starts on
    cx, cy, fw, fh = c.face
    side = max(40.0, fh * 1.45)
    x0, y0 = clamp(cx - side / 2, 0, W - side), clamp(cy - side * 0.52, 0, H - side)
    face = Image.fromarray(c.src).crop((int(x0), int(y0), int(x0 + side), int(y0 + side))).resize((av, av), Image.LANCZOS)
    s.circ(pad + av / 2, pad + av / 2, av / 2 + 3 * sf, fill=(232, 232, 236, 255))
    handle = c.p.get("handle")
    if handle:
        s.text((pad + av + 18 * sf, pad + av / 2 - 1), str(handle), 32 * sf, 760, fill=INK + (255,), anchor="lm")
    else:
        s.rr((pad + av + 18 * sf, pad + av / 2 - 10 * sf, pad + av + 170 * sf, pad + av / 2 + 10 * sf), 10 * sf, fill=(226, 226, 230, 255))
    # dots menu
    for k in range(3):
        s.circ(w - pad - 6 * sf - k * 13 * sf, pad + av / 2, 4 * sf, fill=(150, 150, 158, 255))
    y = pad + av + 18 * sf
    for ln in lines:
        s.text((pad, y + size * 0.92), ln, size, 600, fill=INK + (255,), anchor="ls")
        y += lh
    y += 22 * sf
    # action row: heart, comment, share (outlines, no counts)
    g = (120, 120, 128, 255); r = 17 * sf; ix = pad + r
    s.line(heart_pts(ix, y + r, r * 2.1) + heart_pts(ix, y + r, r * 2.1)[:1], g, 3.2 * sf)
    ix += r * 3.4
    s.circ(ix, y + r, r * 0.95, outline=g, width=3.2 * sf)
    s.poly([(ix - r * 0.75, y + r * 1.55), (ix - r * 0.95, y + r * 2.05), (ix - r * 0.25, y + r * 1.8)], fill=g)
    ix += r * 3.2
    s.line([(ix - r, y + r * 1.7), (ix + r, y + r * 0.3)], g, 3.2 * sf)
    s.line([(ix - r * 1.05, y + r * 0.9), (ix + r * 1.1, y + r * 0.15), (ix - r * 0.05, y + r * 1.95), (ix - r * 1.05, y + r * 0.9)], g, 3.2 * sf)
    im = s.out()
    fm = face.convert("RGBA"); fm.putalpha(circle_mask(av))
    im.alpha_composite(fm, (int(pad), int(pad)))
    return im

def _search(txt, sf, typed=None, caret=True, maxw=9999):
    """The search bar with the first `typed` characters of txt (all if None)."""
    q = txt.lower().rstrip(".!?,")
    w = int(min(560 * sf, maxw)); h = int(98 * sf)
    f = font(int(34 * sf), 500)
    while f.getlength(q) > w - 150 * sf and f.size > 22: f = font(f.size - 2, 500)
    shown = q if typed is None else q[:typed]
    s = SS(w, h)
    s.rr((0, 0, w, h), h / 2, fill=(255, 255, 255, 255))
    s.rr((1, 1, w - 1, h - 1), h / 2, outline=(0, 0, 0, 28), width=1.5)
    g = (110, 110, 118, 255)
    mx, my, mr = 50 * sf, h / 2 - 3 * sf, 14 * sf
    s.circ(mx, my, mr, outline=g, width=4 * sf)
    s.line([(mx + mr * 0.72, my + mr * 0.72), (mx + mr * 1.55, my + mr * 1.55)], g, 4.4 * sf)
    tx = 88 * sf
    s.text((tx, h / 2 + 1), shown, f.size, 500, fill=INK + (255,), anchor="lm")
    if caret:
        cxp = tx + f.getlength(shown) + 4 * sf
        s.rr((cxp, h / 2 - 20 * sf, cxp + 3.4 * sf, h / 2 + 20 * sf), 1.7 * sf, fill=(10, 132, 255, 255))
    return s.out()

def _sticky(txt, sf, maxw=9999):
    w = h = int(min(300 * sf, maxw - 24))
    size, lines = _fit(txt, HAND, 400, w - 56 * sf, 4, int(52 * sf), int(32 * sf))
    s = SS(w + 20, h + 40)
    ox, oy = 10, 26
    # the note, a little darker toward the bottom, with a lifted corner
    s.poly([(ox, oy), (ox + w, oy), (ox + w, oy + h - 34 * sf), (ox + w - 34 * sf, oy + h), (ox, oy + h)], fill=(255, 224, 82, 255))
    s.poly([(ox + w, oy + h - 34 * sf), (ox + w - 30 * sf, oy + h - 30 * sf), (ox + w - 34 * sf, oy + h)], fill=(226, 190, 52, 255))
    lh = size * 1.12
    y = oy + h / 2 - lh * len(lines) / 2 + 6 * sf
    for ln in lines:
        s.text((ox + w / 2, y + size * 0.78), ln, size, 400, fill=(34, 34, 40, 255), anchor="ms", path=HAND)
        y += lh
    im = s.out()
    # tape across the top
    tp = SS(int(120 * sf), int(40 * sf))
    tp.rect((0, 0, tp.w, tp.h), fill=(250, 250, 244, 150))
    tape = tp.out().rotate(-4, Image.BICUBIC, expand=True)
    im.alpha_composite(tape, (int(ox + w / 2 - tape.width / 2), int(oy - tape.height * 0.55)))
    # a soft shading gradient so it reads as paper
    a = np.asarray(im, np.float32)
    yy = np.linspace(0, 1, im.height, dtype=np.float32)[:, None, None]
    a[..., :3] *= (1.02 - 0.08 * yy)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")

def _clipping(c, txt, sf, maxw=9999):
    w = int(min(440 * sf, maxw)); pad = int(28 * sf)
    size, lines = _fit(txt, NEWYORK, 800, w - 2 * pad, 4, int(46 * sf), int(32 * sf))
    lh = size * 1.06
    body_f = font(int(17 * sf), 400, GEORGIA)
    blh = 17 * sf * 1.42
    nb = 4
    h = int(pad * 1.2 + 22 * sf + lh * len(lines) + 18 * sf + nb * blh + pad * 1.4)
    pg = paper(w, h, (240, 235, 222), seed=5, grain=4.0, mottle=7.0, fibers=0.4, edge=0.0)
    im = Image.fromarray(np.ascontiguousarray(pg, np.float32).astype(np.uint8), "RGB").convert("RGBA")
    k = 2
    big = im.resize((w * k, h * k), Image.BICUBIC)
    d = ImageDraw.Draw(big)
    y = pad * 1.2
    d.line([(pad * k, y * k), ((w - pad) * k, y * k)], fill=INK, width=int(2 * k * sf))
    d.line([(pad * k, (y + 6 * sf) * k), ((w - pad) * k, (y + 6 * sf) * k)], fill=INK, width=max(1, int(k * sf)))
    y += 22 * sf
    fh_ = font(size * k, 800, NEWYORK)
    for ln in lines:
        d.text((pad * k, (y + size * 0.8) * k), ln, font=fh_, fill=INK, anchor="ls")
        y += lh
    y += 14 * sf
    # body: the rest of what you said, small and grey
    body = " ".join(w_["w"] for w_ in c.words if norm_word(w_["w"]) not in ("um", "uh")) or txt
    bf = font(int(17 * sf * k), 400, GEORGIA)
    blines = _wrap(body, bf, (w - 2 * pad) * k, nb)
    for ln in blines:
        d.text((pad * k, (y + 17 * sf * 0.9) * k), ln.rstrip("…"), font=bf, fill=(92, 88, 82), anchor="ls")
        y += blh
    im = big.resize((w, h), Image.LANCZOS)
    # torn top and bottom edges
    a = np.ones((h, w), np.float32)
    xs = np.arange(w)
    top = 4 + torn_path(w, 11, big=3, mid=2.2, fine=1.2)
    bot = h - 5 + torn_path(w, 12, big=3, mid=2.2, fine=1.2)
    yy = np.arange(h, dtype=np.float32)[:, None]
    a *= np.clip(yy - top[None, :] + 0.5, 0, 1) * np.clip(bot[None, :] - yy + 0.5, 0, 1)
    al = np.asarray(im.getchannel("A"), np.float32) / 255 * a
    im.putalpha(Image.fromarray((al * 255).astype(np.uint8), "L"))
    return im

def _chat(txt, sf, dots=None, maxw=9999):
    """The chat bubble (blue, text) or, with dots (0..1 phase), the grey typing bubble."""
    if dots is not None:
        w, h = int(130 * sf), int(78 * sf)
        s = SS(w + 20, h + 20)
        s.rr((0, 0, w, h), h / 2, fill=(233, 233, 238, 255))
        s.circ(w - 6 * sf, h - 2 * sf, 11 * sf, fill=(233, 233, 238, 255)); s.circ(w + 8 * sf, h + 10 * sf, 5 * sf, fill=(233, 233, 238, 255))
        for k in range(3):
            ph = (dots * 2.2 - k * 0.22) % 1.0
            b = 0.5 + 0.5 * math.sin(ph * 2 * math.pi)
            s.circ(w / 2 + (k - 1) * 26 * sf, h / 2 - 4 * sf * b, 8.5 * sf, fill=(140, 140, 148, int(140 + 110 * b)))
        return s.out()
    maxw = int(min(400 * sf, maxw - 30)); pad = int(26 * sf)
    size, lines = _fit(txt, SFP, 500, maxw - 2 * pad, 4, int(34 * sf), int(26 * sf))
    f = font(size, 500)
    tw = max(f.getlength(l) for l in lines)
    lh = size * 1.22
    w = int(tw + 2 * pad); h = int(lh * len(lines) + pad * 1.25)
    s = SS(w + 24, h + 10)
    blue = (10, 132, 255, 255)
    # tail at the bottom right
    s.poly([(w - 34 * sf, h - 30 * sf), (w + 12 * sf, h + 6 * sf), (w - 4 * sf, h - 46 * sf)], fill=blue)
    s.rr((0, 0, w, h), min(h / 2, 40 * sf), fill=blue)
    y = pad * 0.62
    for ln in lines:
        s.text((pad, y + size * 0.9), ln, size, 500, fill=(255, 255, 255, 255), anchor="ls")
        y += lh
    return s.out()

def _headline(txt, sf, maxw=9999):
    """A black headline strip (two stacked strips when it's long), white caps, a yellow tab."""
    t = re.sub(r"[.!?,]+$", "", txt).upper()
    trk = 2.4 * sf
    lim = min(560 * sf, maxw - 60 * sf)
    def width(s_, f): return sum(f.getlength(ch) + trk for ch in s_)
    size = int(36 * sf)
    words = t.split()
    while True:
        f = font(size, 860)
        if width(t, f) <= lim: lines = [t]; break
        best = None
        for k in range(1, len(words)):
            a_, b_ = " ".join(words[:k]), " ".join(words[k:])
            m = max(width(a_, f), width(b_, f))
            if best is None or m < best[0]: best = (m, [a_, b_])
        if best and best[0] <= lim: lines = best[1]; break
        if size <= 18: lines = best[1] if best else [t]; break
        size -= 2
    f = font(size, 860)
    bh = int(size * 1.9); gap = int(6 * sf)
    ws = [int(width(l, f) + 58 * sf) for l in lines]
    w, h = max(ws), bh * len(lines) + gap * (len(lines) - 1)
    s = SS(w, h)
    for k, (l, lw) in enumerate(zip(lines, ws)):
        y0 = k * (bh + gap)
        s.rect((0, y0, lw, y0 + bh), fill=(16, 16, 18, 255))
        s.rect((0, y0, 12 * sf, y0 + bh), fill=(255, 214, 10, 255))
        x = 32 * sf
        for ch in l:
            s.text((x, y0 + bh / 2 + 1), ch, size, 860, fill=(255, 255, 255, 255), anchor="lm")
            x += f.getlength(ch) + trk
    return s.out()


# ------------------------------------------------------------------ render
def render(c):
    st = c.state
    d, u = c.d, c.u
    if "cards" not in st:
        styles = [s for s in (c.p.get("styles") or []) if s in TILT][:6]
        texts = _texts(c, styles)
        slots = _slots(c)
        (fx, fy, fw, fh), box = face_stats(c)
        sf = clamp(fh / 370, 0.78, 1.15)
        n = len(styles)
        gap = clamp((c.d * 0.42) / max(1, n), 0.12, 0.34)
        cards = []
        rng = np.random.default_rng(29)
        for k, sty in enumerate(styles):
            txt = texts.get(sty, "")
            if not txt: continue
            x0, y0, x1, y1 = slots[sty]
            mw = x1 - x0
            if sty == "post": im = _post(c, txt, sf, mw)
            elif sty == "search": im = _search(txt, sf, maxw=mw)
            elif sty == "sticky": im = _sticky(txt, sf, mw)
            elif sty == "clipping": im = _clipping(c, txt, sf, mw)
            elif sty == "chat": im = _chat(txt, sf, maxw=mw)
            else: im = _headline(txt, sf, mw)
            (ry, rx, rz), z = TILT[sty]
            fit = min(1.0, (x1 - x0) / im.width, max(0.85, (y1 - y0) / im.height))
            x = (x0 + x1) / 2; y = (y0 + y1) / 2
            if sty == "chat": x = x0 + im.width * fit / 2 + 6           # the bubble hugs the head side
            hw, hh = im.width * fit / 2 + abs(rz) * 3, im.height * fit / 2 + abs(rz) * 2     # room for the tilt
            x = clamp(x, 26 + hw, W - 26 - hw)
            y = clamp(y, 226 + hh, 1460 - hh)
            if z < 0.92:            # far snippets: a touch soft and dim
                im = im.filter(ImageFilter.GaussianBlur((1 - z) * 6))
                a = np.asarray(im, np.float32); a[..., :3] *= (0.8 + 0.2 * z); im = Image.fromarray(a.astype(np.uint8), "RGBA")
            cards.append(dict(sty=sty, txt=txt, im=im, x=x, y=y, ry=ry, rx=rx, rz=rz, z=z, fit=fit, sf=sf, mw=mw,
                              t=0.1 + k * gap, ph=rng.uniform(0, 6.28), cache={}))
        st["cards"] = cards
        st["f0"] = (fx, fy)
    cards = st["cards"]
    if not cards: return c.img
    n = len(cards)
    out_len = min(0.6, d * 0.24)
    t_out = d - out_len
    ostag = min(0.07, out_len * 0.45 / max(1, n))
    odur = out_len - ostag * (n - 1)
    k_bg = ease_out(prog(u, 0, 0.35)) * (1 - ease_in(prog(u, d - 0.3, 0.3)))
    fx, fy, fw, fh = c.face
    lay = c.canvas()
    drawn = False
    for k, cd in sorted(enumerate(cards), key=lambda kc: kc[1]["z"]):
        p = prog(u, cd["t"], 0.48)
        q = prog(u, t_out + ostag * k, odur)
        if p <= 0 or q >= 1: continue
        drawn = True
        im = cd["im"]
        sty = cd["sty"]
        if sty == "search":           # types itself in once it has landed
            L = len(cd["txt"].rstrip(".!?,"))
            tk = prog(u, cd["t"] + 0.32, clamp(L * 0.035, 0.4, 0.9))
            ntyped = int(round(L * tk))
            blink = (int((u - cd["t"]) * 2.2) % 2 == 0) or tk < 1
            key = (ntyped, blink)
            if key not in cd["cache"]: cd["cache"][key] = _search(cd["txt"], cd["sf"], ntyped, blink, cd["mw"])
            im = cd["cache"][key]
        elif sty == "chat":           # typing dots first, then the message
            dt = u - cd["t"]
            if dt < 0.5:
                key = ("dots", int(dt * FPS))
                if key not in cd["cache"]: cd["cache"][key] = _chat("", cd["sf"], dots=dt, maxw=cd["mw"])
                im = cd["cache"][key]
        z = cd["z"]
        s = cd["fit"] * lerp(0.35, 1.0, back(p, 2.1)) * lerp(1.0, 0.55, ease_in(q))
        a = ease_out(min(1, p * 3.0)) * (1 - ease_in(q))
        if sty == "chat" and 0.5 <= u - cd["t"] < 0.66:       # the message pops out of the dots
            s *= lerp(0.7, 1.0, back(prog(u - cd["t"], 0.5, 0.16), 2.4))
        # drift, parallax (far snippets move less with you) and a slow 3D sway
        dx = 7 * smooth_noise(u * 0.5, 3 + k) - (fx - st["f0"][0]) * (1 - z) * 0.9
        dy = 9 * smooth_noise(u * 0.45, 11 + k) - (fy - st["f0"][1]) * (1 - z) * 0.6 - 16 * ease_in(q)
        spin = (1 - ease_out(p)) * (24 if k % 2 else -24)
        ry = cd["ry"] + spin + 3 * smooth_noise(u * 0.35, 21 + k)
        rx = cd["rx"] + 2 * smooth_noise(u * 0.3, 31 + k)
        rz = cd["rz"] * lerp(2.4, 1.0, ease_out(p)) + 0.8 * smooth_noise(u * 0.4, 41 + k)
        place(lay, im, cd["x"] + dx, cd["y"] + dy, s, ry, rx, rz, shadow=0.42 * z, a=a, f=1800)
    if not drawn and k_bg <= 0.001: return c.img
    base = f32(np.asarray(c.img))
    dim = float(c.p.get("dim", 0.35))
    room = base * (1 - dim * k_bg)
    room = over(room, lay)
    return to_pil(mix(base, room, solid_mask(c)))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "CLAUDE-WROTE: the handle 'you' on the post card (the default). Every snippet is your own words from the transcript, cut at sentence and comma breaks.",
    "needs": ["talk"],
}
