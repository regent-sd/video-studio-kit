"""Glass widgets: frosted-glass widget cards pop in and float around your head (some behind you, some in front)."""
import math, re
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, SS, place, rounded, key_words, ease_out, ease_in, back, prog, lerp, clamp, clamp01, SFP
from catalog._b import face_stats, frost_src, frost_panel, loudness, font_args, clamp_rect, behind

NAME = "glass-widgets"
KIND = "cards"
ABOUT = "Frosted-glass widget cards (stat, chart, progress, ring, profile, pill) float around your head"
DUR = 5.0
PARAMS = dict(
    stat=None,            # {"value": "3x", "label": "per week"}: a real number for the big card.
                          # Default: no number; the card shows the latest strong word you say.
    ring=None,            # a real 0-1 value (or "75%") for the ring card, with ring_label. Default: rings that fill with the effect's time
    ring_label=None,      # small text under a ring value
    progress_label="Rendering",  # the progress card's label (its % is the effect's own time, not a claim)
    name=None,            # name on the profile card (the avatar is your face from the video). Default: no name, placeholder lines
    editor=None,          # "Edited by <editor>" pill. Default: a recording dot and the video's own timecode
    cards=None,           # which cards, e.g. ["stat", "chart", "progress", "ring", "profile", "pill"]; default all of them
    style="light",        # light (white frosted glass, dark text) | dark (smoked glass, white text)
    follow=0.5,           # how much the cards follow your head (0 = stay put, 1 = stuck to it)
)
ORDER = ["stat", "progress", "ring", "chart", "profile", "pill"]
SIZE = dict(stat=(330, 214), chart=(290, 200), progress=(330, 136), ring=(214, 214), profile=(380, 140), pill=(300, 78))
ZONES = dict(stat=["top", "left", "right", "bottom"], ring=["top", "right", "left", "bottom"],
             chart=["left", "right", "top", "bottom"], progress=["right", "left", "bottom", "top"],
             profile=["bottom", "left", "right"], pill=["bottom", "right", "left", "top"])
BEHIND = {"stat", "ring", "chart"}
R = 40  # corner radius


# ------------------------------------------------------------------ layout (once per window)
def _layout(c, kinds):
    (fx, fy, fw, fh), u = face_stats(c)
    S = c.state["size"]
    fol = clamp01(float(c.p.get("follow", 0.5)))
    # keep-out: the face (a little inside its detection box, which includes the ears), grown by how far the face
    # wanders from the cards (they follow it by `follow`)
    mx0, mx1 = fx - fw * 0.46, fx + fw * 0.46
    x0 = mx0 - (1 - fol) * max(0, mx0 - (u[0] + fw * 0.04))
    x1 = mx1 + (1 - fol) * max(0, (u[2] - fw * 0.04) - mx1)
    cy_lo, cy_hi = u[1] + fh / 2, u[3] - fh / 2                    # highest / lowest face centre in the window
    top = max(240, fy - fh * 0.98 - (1 - fol) * max(0, fy - cy_lo) - 18)
    ex = (x0 - 18, top, x1 + 18, fy + fh * 0.62 + (1 - fol) * max(0, cy_hi - fy) + 30)
    zones = dict(top=(28, 236, W - 28, ex[1] - 14), bottom=(28, ex[3] + 16, W - 28, 1466),
                 left=(24, max(236, ex[1] - 40), ex[0] - 6, min(1466, ex[3] + 150)),
                 right=(ex[2] + 6, max(236, ex[1] - 40), W - 24, min(1466, ex[3] + 150)))
    horiz = {"top", "bottom"}
    used = {z: [] for z in zones}
    for k in kinds:
        w, h = S[k]
        for z in ZONES[k]:
            zx0, zy0, zx1, zy1 = zones[z]
            zw, zh = zx1 - zx0, zy1 - zy0
            if zw < 120 or zh < 90: continue
            items = used[z] + [k]
            if z in horiz:
                need_w = sum(S[i][0] for i in items) + 40 * (len(items) - 1)
                s = min(1.0, zw / need_w, zh / max(S[i][1] for i in items))
            else:
                need_h = sum(S[i][1] for i in items) + 36 * (len(items) - 1)
                s = min(1.0, zh / need_h, zw / max(S[i][0] for i in items))
            if s >= 0.66:
                used[z].append(k); break
    out = {}
    for z, items in used.items():
        if not items: continue
        zx0, zy0, zx1, zy1 = zones[z]
        if z in horiz:
            need = sum(S[i][0] for i in items) + 40 * (len(items) - 1)
            s = min(1.0, (zx1 - zx0) / need, (zy1 - zy0) / max(S[i][1] for i in items))
            gap = ((zx1 - zx0) - sum(S[i][0] * s for i in items)) / (len(items) + 1)
            x = zx0 + gap
            for j, k in enumerate(items):
                w, h = S[k][0] * s, S[k][1] * s
                # stagger: alternate cards sit a little higher / lower
                yy = (zy0 + zy1) / 2 + ((zy1 - zy0) - h) * (0.22 if j % 2 else -0.22) * (1 if z == "top" else -1)
                out[k] = (x + w / 2, yy, s); x += w + gap
        else:
            need = sum(S[i][1] for i in items) + 36 * (len(items) - 1)
            s = min(1.0, (zy1 - zy0) / need, (zx1 - zx0) / max(S[i][0] for i in items))
            # sit beside the face, not at the ends of the band
            mid = clamp(fy - fh * 0.05, zy0 + need * s / 2, zy1 - need * s / 2)
            y = mid - need * s / 2
            for k in items:
                w, h = S[k][0] * s, S[k][1] * s
                out[k] = ((zx0 + zx1) / 2, y + h / 2, s); y += h + 36 * s
    # keep every card inside the frame and the Instagram-safe band
    for k, (x, y, s) in list(out.items()):
        w, h = S[k][0] * s, S[k][1] * s
        r = clamp_rect((x - w / 2, y - h / 2, x + w / 2, y + h / 2), (34, 236, W - 34, 1462))
        out[k] = ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, s)
    return out


# ------------------------------------------------------------------ the cards' contents
def _pal(c):
    dark = c.p.get("style") == "dark"
    ink = (255, 255, 255) if dark else (17, 17, 19)
    muted = (210, 210, 216) if dark else (96, 96, 104)
    track = (255, 255, 255, 46) if dark else (17, 17, 19, 30)
    return dark, ink, muted, track

def _glass(c, small, k, cx, cy, s, draw):
    """A frosted card: the blurred frame under it, tinted, with the contents and a hairline border."""
    w, h = c.state["size"][k]
    box = (cx - w * s / 2, cy - h * s / 2, cx + w * s / 2, cy + h * s / 2)
    bg = frost_panel(small, box).resize((w, h), Image.BILINEAR)
    dark, ink, muted, track = _pal(c)
    tint = (22, 23, 27) if dark else (250, 250, 252)
    bg = Image.blend(bg, Image.new("RGB", (w, h), tint), 0.52 if dark else 0.62).convert("RGBA")
    key = ("chrome", k, dark)
    if key not in c.state:
        sh = SS(w, h)
        # a soft sheen from the top-left, and a hairline edge
        for j in range(10):
            a = int((20 if dark else 34) * (1 - j / 10))
            sh.rr((2 + j * 3, 2 + j * 2, w * 0.92 - j * 10, h * 0.55 - j * 4), R - j, fill=(255, 255, 255, max(0, a // 3)))
        sh.rr((1, 1, w - 1, h - 1), R, outline=(255, 255, 255, 120 if dark else 210), width=2)
        c.state[key] = sh.out()
    bg.alpha_composite(c.state[key])
    ss = SS(w, h)
    draw(ss, w, h)
    bg.alpha_composite(ss.out())
    return rounded(bg, R)

def _stat(c, st, tl):
    dark, ink, muted, track = _pal(c)
    acc = c.skin.accent
    sp = c.p.get("stat")
    T = font_args(c.skin, "num"); B = font_args(c.skin, "body")
    def draw(s, w, h):
        if sp:
            val = str(sp.get("value", "")); lab = str(sp.get("label", ""))
            size = 104
            while size > 50 and s.textlen(val, size, T["weight"], T["path"], T["index"]) > w - 56: size -= 4
            x = 28
            for j, ch in enumerate(val):
                p = ease_out(prog(tl, 0.18 + j * 0.07, 0.32))
                if p > 0:
                    col = ink + (int(255 * p),)
                    s.text((x, 30 + (1 - p) * 46), ch, size, fill=col, anchor="la", **T)
                x += s.textlen(ch, size, T["weight"], T["path"], T["index"])
            la = ease_out(prog(tl, 0.35, 0.4))
            s.circ(36, h - 44, 8 * la, fill=acc + (255,))
            s.text((52, h - 44), lab, 32, fill=muted + (int(255 * la),), anchor="lm", **B)
        else:
            ws = st["kw"]
            said = [x for x in ws if x["s"] <= c.t]
            # header: a quote mark and a live dot
            s.text((28, 26), "“", 64, fill=acc + (255,), anchor="la", weight=900, path=SFP)
            blink = 0.5 + 0.5 * math.cos(c.u * 2 * math.pi * 0.9)
            s.circ(w - 40, 46, 9, fill=(255, 69, 58, int(110 + 145 * blink)))
            if not said: return
            for j in (len(said) - 2, len(said) - 1):
                if j < 0: continue
                wd = re.sub(r"[^\w'-]", "", said[j]["w"])
                tin = ease_out(prog(c.t, said[-1]["s"], 0.28))
                if j == len(said) - 1: dy, a = (1 - tin) * 60, tin
                else: dy, a = -tin * 60, 1 - tin
                if a <= 0.01: continue
                size = 78
                while size > 36 and s.textlen(wd, size, 860) > w - 56: size -= 3
                s.text((28, h - 52 + dy), wd, size, fill=ink + (int(255 * a),), anchor="ls", weight=860, path=SFP)
            s.rr((28, h - 34, 28 + 40, h - 28), 3, fill=acc + (255,))
    return draw

def _chart(c, st, tl):
    dark, ink, muted, track = _pal(c)
    acc = c.skin.accent
    L = st["loud"]
    def bar(b):  # loudness of bin b (3 frames)
        if L is None or b < 0: return 0.0
        seg = L[b * 3:b * 3 + 3]
        return float(seg.mean()) if len(seg) else 0.0
    def draw(s, w, h):
        # header: a small mic and a live level meter
        s.rr((28, 24, 44, 50), 8, fill=ink + (255,)); s.arc((21, 31, 51, 58), 20, 160, fill=ink + (255,), width=3)
        s.line([(36, 58), (36, 64)], ink + (255,), 3)
        grow = ease_out(prog(tl, 0.1, 0.5))
        lv = sum(bar(c.i // 3 - j) for j in range(2)) / 2
        for j in range(5):
            on = lv * 5 > j + 0.3
            s.rr((w - 28 - (5 - j) * 17, 34, w - 28 - (5 - j) * 17 + 11, 50), 3,
                 fill=(acc + (255,)) if on else track)
        n = 12
        bx0, bx1, by1 = 28, w - 28, h - 26
        bw = (bx1 - bx0) / n
        top_h = h - 104
        frac = (c.i % 3) / 3.0                       # smooth scroll between bins
        newest = c.i // 3
        for j in range(n + 1):
            b = newest - (n - j)
            v = 0.06 + 0.94 * bar(b)
            hh = max(10, top_h * v * grow)
            x0 = bx0 + (j - frac) * bw + bw * 0.16; x1 = x0 + bw * 0.68
            a = clamp01((x1 - bx0) / (bw * 0.68))
            if a <= 0: continue
            x0 = max(x0, bx0)
            q = j / n
            col = (acc + (int(255 * a),)) if j >= n - 1 else (ink + (int((70 + 150 * q) * a),))
            s.rr((x0, by1 - hh, x1, by1), (x1 - x0) / 2, fill=col)
    return draw

def _progress(c, st, tl, tend):
    dark, ink, muted, track = _pal(c)
    acc = c.skin.accent
    B = font_args(c.skin, "heading"); N = font_args(c.skin, "num")
    p = ease_io(prog(tl, 0.25, max(0.3, tend - 0.45)))
    done = p >= 0.999
    def draw(s, w, h):
        # icon: a document that turns into a check when done
        s.rr((26, 24, 78, 76), 14, fill=acc + (255,))
        if done:
            ck = back(prog(tl, 0.25 + max(0.3, tend - 0.45), 0.3))
            s.line([(39, 51), (39 + 10 * ck, 51 + 10 * ck)], (17, 17, 19, 255), 6)
            if ck > 0.5: s.line([(49, 61), (49 + 19 * (ck - 0.5) * 2, 61 - 22 * (ck - 0.5) * 2)], (17, 17, 19, 255), 6)
        else:
            for j, ln in enumerate((28, 20, 24)):
                s.rr((38, 37 + j * 10, 38 + ln, 42 + j * 10), 2, fill=(17, 17, 19, 230))
        lab = str(c.p.get("progress_label") or "")
        if lab:
            size = 34
            while size > 22 and s.textlen(lab, size, B["weight"], B["path"], B["index"]) > w - 96 - 26: size -= 2
            s.text((96, 50), lab, size, fill=ink + (255,), anchor="lm", **B)
        pct = f"{int(round(p * 100))}%"
        s.text((w - 26, h - 34), pct, 28, fill=ink + (255,), anchor="rm", **N)
        bx0, bx1, by = 26, w - 26 - 78, h - 34
        s.rr((bx0, by - 7, bx1, by + 7), 7, fill=track)
        fx = bx0 + (bx1 - bx0) * p
        if fx > bx0 + 4:
            s.rr((bx0, by - 7, fx, by + 7), 7, fill=acc + (255,))
            # a shine running along the fill
            sx = bx0 + ((c.u * 1.1) % 1.5 - 0.25) * (bx1 - bx0)
            if bx0 + 12 < sx < fx - 12:
                s.rr((sx - 16, by - 5, min(fx - 4, sx + 16), by + 5), 5, fill=(255, 255, 255, 140))
    return draw

def ease_io(x):
    x = clamp01(x); return x * x * (3 - 2 * x)

def _ring(c, st, tl, tend):
    dark, ink, muted, track = _pal(c)
    rv = c.p.get("ring")
    if isinstance(rv, str):
        m = re.match(r"\s*([\d.]+)\s*(%?)", rv)
        rv = (float(m[1]) / (100 if (m[2] or float(m[1]) > 1) else 1)) if m else None
    elif rv is not None:
        rv = float(rv); rv = rv / 100 if rv > 1 else rv
    cols = [c.skin.accent, c.skin.blue, c.skin.good]
    N = font_args(c.skin, "num"); B = font_args(c.skin, "body")
    def arc(s, cx, cy, r, p, col, wd):
        s.ell((cx - r, cy - r, cx + r, cy + r), outline=col + (52,), width=wd)
        if p > 0.003:
            s.arc((cx - r, cy - r, cx + r, cy + r), -90, -90 + 360 * p, fill=col + (255,), width=wd)
            for ang in (-90, -90 + 360 * p):    # round caps
                a = math.radians(ang)
                s.circ(cx + (r - wd / 2) * math.cos(a), cy + (r - wd / 2) * math.sin(a), wd / 2, fill=col + (255,))
    def draw(s, w, h):
        cx, cy = w / 2, h / 2
        if rv is not None:
            p = rv * ease_io(prog(tl, 0.2, 1.2))
            arc(s, cx, cy, w / 2 - 26, p, cols[0], 22)
            lab = c.p.get("ring_label")
            s.text((cx, cy - (10 if lab else 0)), f"{int(round(p * 100))}%", 44, fill=ink + (255,), anchor="mm", **N)
            if lab: s.text((cx, cy + 30), str(lab), 22, fill=muted, anchor="mm", **B)
            return
        span = max(0.4, tend - 0.3)
        for j in range(3):
            r = w / 2 - 24 - j * 25
            p = ease_io(prog(tl, 0.15 + j * 0.15, span * (0.95 - 0.1 * j))) * (1.0 - 0.13 * j)
            arc(s, cx, cy, r, p, cols[j], 20)
    return draw

def _profile(c, st, tl):
    dark, ink, muted, track = _pal(c)
    acc = c.skin.accent
    nm = c.p.get("name")
    B = font_args(c.skin, "heading")
    L = st["loud"]
    # live avatar: your face in this frame, cut to a circle
    fx, fy, fw, fh = c.face
    r = fw * 0.62
    x0 = clamp(fx - r, 0, W - 2 * r); y0 = clamp(fy - r * 1.04, 0, H - 2 * r)
    AV = 92
    def draw(s, w, h):
        cx, cy = 26 + 52, h / 2
        s.circ(cx, cy, 52, fill=acc + (255,))
        s.circ(cx, cy, 47, fill=(255, 255, 255, 255))
        k = s.k
        av = Image.fromarray(c.src).resize((AV * k, AV * k), Image.LANCZOS, box=(x0, y0, x0 + 2 * r, y0 + 2 * r)).convert("RGBA")
        m = Image.new("L", av.size, 0); ImageDraw.Draw(m).ellipse((0, 0, av.width - 1, av.height - 1), fill=255)
        av.putalpha(m)
        s.im.alpha_composite(av, (int((cx - AV / 2) * k), int((cy - AV / 2) * k)))
        x = 152
        if nm:
            n = int(round(len(str(nm)) * ease_out(prog(tl, 0.25, 0.5))))
            size = 36
            while size > 24 and s.textlen(str(nm), size, B["weight"], B["path"], B["index"]) > w - x - 26: size -= 2
            s.text((x, cy - 20), str(nm)[:n], size, fill=ink + (255,), anchor="lm", **B)
        else:
            sh = (c.u * 0.9) % 1.6 - 0.3
            s.rr((x, cy - 29, x + 170, cy - 11), 9, fill=track)
            sx = x + sh * 190
            if x < sx < x + 170: s.rr((max(x, sx - 26), cy - 29, min(x + 170, sx + 26), cy - 11), 9, fill=(255, 255, 255, 90 if dark else 170))
        # speaking indicator: little bars that move with your voice
        for j in range(7):
            fi = clamp(c.i - j * 2, 0, (len(L) - 1) if L is not None else 0)
            v = float(L[fi]) if L is not None else 0.3
            v = v * (0.55 + 0.45 * abs(math.sin(j * 1.7 + 0.6)))
            hh = 8 + 26 * v * ease_out(prog(tl, 0.3, 0.4))
            bx = x + j * 15
            s.rr((bx, cy + 22 - hh / 2, bx + 8, cy + 22 + hh / 2), 4, fill=(acc + (255,)) if j < 2 else (ink + (150,)))
    return draw

def _pill(c, st, tl):
    dark, ink, muted, track = _pal(c)
    ed = c.p.get("editor")
    B = font_args(c.skin, "heading"); N = font_args(c.skin, "mono")
    def draw(s, w, h):
        cy = h / 2
        if ed:
            s.circ(28 + 18, cy, 18, fill=c.skin.accent + (255,))
            s.text((28 + 46, cy), f"Edited by {ed}", 30, fill=ink + (255,), anchor="lm", **B)
        else:
            blink = 1.0 if (c.u % 1.0) < 0.62 else 0.25
            s.circ(28 + 14, cy, 13, fill=(255, 59, 48, int(255 * blink)))
            s.circ(28 + 14, cy, 22, outline=(255, 59, 48, int(90 * blink)), width=3)
            t = max(0.0, c.t)
            s.text((28 + 46, cy), f"{int(t // 60)}:{int(t % 60):02d}.{int((t * 10) % 10)}", 34, fill=ink + (255,), anchor="lm", **N)
    return draw

def _pill_w(c):
    ed = c.p.get("editor")
    if ed:
        B = font_args(c.skin, "heading")
        return int(28 + 46 + SS(1, 1).textlen(f"Edited by {ed}", 30, B["weight"], B["path"], B["index"]) + 30)
    return 236


# ------------------------------------------------------------------ render
def render(c):
    st = c.state
    if "lay" not in st:
        kinds = [k for k in ORDER if k in (c.p.get("cards") or ORDER)]
        st["kw"] = key_words(c.words_in())
        st["loud"] = loudness(c.subj.audio)
        if not c.p.get("stat") and not st["kw"]: kinds = [k for k in kinds if k != "stat"]
        if st["loud"] is None: kinds = [k for k in kinds if k != "chart"]
        st["size"] = dict(SIZE, pill=(_pill_w(c), 78))
        st["lay"] = _layout(c, kinds)
        st["kinds"] = [k for k in kinds if k in st["lay"]]
        st["med"] = face_stats(c)[0]
    kinds = st["kinds"]
    n = max(1, len(kinds))
    d = c.d
    pop = min(0.5, d * 0.3)
    stag = min(0.11, d * 0.22 / n)
    out = min(0.36, d * 0.2)
    ostag = min(0.06, d * 0.1 / n)
    fx, fy, fw, fh = c.face
    mx, my = st["med"][0], st["med"][1]
    fol = float(c.p.get("follow", 0.5))
    small = frost_src(c)
    back_cv, front_cv = None, None
    rng = np.random.default_rng(11)
    phases = rng.uniform(0, 2 * math.pi, (len(ORDER), 5))
    for j, k in enumerate(kinds):
        x, y, s = st["lay"][k]
        t_in = 0.04 + j * stag
        t_out = d - out - (n - 1 - j) * ostag
        p_in = prog(c.u, t_in, pop)
        p_out = prog(c.u, t_out, out)
        if p_in <= 0 or p_out >= 1: continue
        ph = phases[ORDER.index(k)]
        # float: each card bobs on its own
        bob_x = 7 * math.sin(c.u * 2 * math.pi * 0.31 + ph[0])
        bob_y = 10 * math.sin(c.u * 2 * math.pi * 0.37 + ph[1])
        rz = 1.3 * math.sin(c.u * 2 * math.pi * 0.23 + ph[2])
        ry = 5 * math.sin(c.u * 2 * math.pi * 0.19 + ph[3])
        rx = 4 * math.sin(c.u * 2 * math.pi * 0.27 + ph[4])
        # in: pop with overshoot and a flip up; out: shrink, drift up, fade
        sc = lerp(0.45, 1.0, back(p_in, 2.2)) * lerp(1.0, 0.7, ease_in(p_out))
        a = min(ease_out(p_in * 1.8), 1 - ease_in(p_out))
        rx += 32 * (1 - ease_out(p_in)) - 10 * ease_in(p_out)
        rz += (8 if j % 2 else -8) * (1 - ease_out(p_in))
        cx = x + bob_x + (fx - mx) * fol
        cy = y + bob_y + (fy - my) * fol - 40 * ease_in(p_out) + 30 * (1 - ease_out(p_in))
        tl = c.u - t_in
        tend = t_out - t_in
        draw = {"stat": lambda: _stat(c, st, tl), "chart": lambda: _chart(c, st, tl), "progress": lambda: _progress(c, st, tl, tend),
                "ring": lambda: _ring(c, st, tl, tend), "profile": lambda: _profile(c, st, tl), "pill": lambda: _pill(c, st, tl)}[k]()
        card = _glass(c, small, k, cx, cy, s * sc, draw)
        if k in BEHIND:
            if back_cv is None: back_cv = c.canvas()
            cv = back_cv
        else:
            if front_cv is None: front_cv = c.canvas()
            cv = front_cv
        place(cv, card, cx, cy, s=s * sc, rx=rx, ry=ry, rz=rz, shadow=0.34, a=a)
    img = c.img
    if back_cv is not None: img = behind(c, back_cv, img)
    if front_cv is not None: img = c.front(front_cv, img)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "CLAUDE-WROTE: the progress label 'Rendering' (the default). No number is shown (no stat given); the rings and the timecode pill follow the effect's own time; the chart is the real loudness of the voice.",
    "still": 0.6,
    "needs": ["face"],
}
