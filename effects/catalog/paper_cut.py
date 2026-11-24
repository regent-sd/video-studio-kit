"""Paper cut: a scrapbook / ransom-note collage. The room becomes a page of paper scraps (torn white, kraft and pastel
papers, grid and lined paper, washi tape, pen scribbles and x-marks), you're stuck on it as a die-cut sticker with a
thick white border and a drop shadow, and your word goes across the top in ransom-note letters, each on its own scrap
in its own font and colour, popping on one by one. It all moves on threes, like stop-motion: it slaps on at the start
and the page slides away at the end."""
import math, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, FPS, SS, f32, to_pil, font, text_img, clamp, clamp01, hexc, soft_shadow, comp, scaled,
                  GEORGIA_B, DIDOT, BODONI, TYPEWRITER, HAND, CHALK, SFP, NEWYORK, SUPP)
from catalog._cam import tighten, affine, pil
from catalog._b import face_stats, solid_mask
from catalog._print import paper, torn_path, fbm, key_word
from catalog._cam2 import move_layer, dilate, soft, shift, head_top_px

NAME = "paper-cut"
KIND = "restyle"
ABOUT = "Scrapbook collage: you as a die-cut sticker on torn paper scraps, your word in ransom-note letters, stop-motion"
DUR = 4.0
PARAMS = dict(
    text=None,        # the ransom-note title; default the key word you say in the window
    size=0.9,         # your size on the page (share of full size; made smaller if your head would hit the title)
    border=26,        # thickness of the white sticker border (px)
    page="#D6BC95",   # the page under the scraps (kraft card)
    steps=3,          # frames per stop-motion step (2 = on twos, 3 = on threes)
    seed=7,           # a different number shuffles the scraps, fonts and colours
)
PINK, MINT, BLUE, LAV, LEMON = (246, 198, 206), (192, 228, 206), (196, 219, 240), (216, 203, 238), (252, 233, 152)
WHITE, KRAFT, KRAFT_D, NEWS = (249, 247, 241), (204, 168, 118), (164, 126, 84), (228, 225, 216)
INK_BLUE, INK_BLACK, INK_RED = (34, 58, 150), (26, 24, 26), (206, 38, 44)
FONTS = [(GEORGIA_B, 0), (DIDOT, 2), (BODONI, 2), (TYPEWRITER, 2), (SUPP + "/Impact.ttf", 0),
         (SUPP + "/Arial Black.ttf", 0), (SUPP + "/Futura.ttc", 4), (SUPP + "/Rockwell.ttc", 2),
         (SUPP + "/Copperplate.ttc", 2), (SUPP + "/Cochin.ttc", 1), (HAND, 0), (SUPP + "/Courier New Bold.ttf", 0),
         (SUPP + "/Hoefler Text.ttc", 1), (SUPP + "/GillSans.ttc", 6), (SUPP + "/Baskerville.ttc", 1),
         (SUPP + "/DIN Condensed Bold.ttf", 0), (CHALK, 0)]

# ------------------------------------------------------------------ paper pieces
def _outline(w, h, rng, torn, k=2, amp=1.0):
    """Polygon points (at k x scale) of a w x h piece: torn sides get a ragged profile, cut sides a slight wobble."""
    pts = []
    def side(p0, p1, n_out, is_torn, seed):
        (x0, y0), (x1, y1) = p0, p1
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(2, int(L / 3)) if is_torn else 2
        prof = torn_path(n, seed, big=4.0 * amp, mid=3.0 * amp, fine=1.2 * amp, scale=max(8, n / 3)) if is_torn else None
        out = []
        for j in range(n):
            t = j / (n - 1) if n > 1 else 0
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            o = (prof[j] - 6 * amp if is_torn else rng.uniform(-2.5, 2.5))
            out.append(((x + n_out[0] * o) * k, (y + n_out[1] * o) * k))
        return out[:-1]
    s = int(rng.integers(1 << 30))
    pts += side((0, 0), (w, 0), (0, -1), "t" in torn, s)
    pts += side((w, 0), (w, h), (1, 0), "r" in torn, s + 1)
    pts += side((w, h), (0, h), (0, 1), "b" in torn, s + 2)
    pts += side((0, h), (0, 0), (-1, 0), "l" in torn, s + 3)
    return pts

def _piece(w, h, col, seed, torn="", kind="plain", rot=0.0, shadow=0.34):
    """A paper scrap: RGBA with texture, torn or cut edges (torn ones show a white core), rotated, with its shadow.
    Returns (RGBA, pad): draw it centred where you want it."""
    rng = np.random.default_rng(seed)
    m = 14
    W2, H2 = w + 2 * m, h + 2 * m
    k = 2
    tex = paper(W2, H2, tuple(col), seed=seed % 97 + 3, grain=4.0, mottle=6.0, fibers=0.35)
    tex = tex.copy()
    if kind == "grid":
        for x in range(m + 12, W2 - m, 30): tex[:, x:x + 2] = tex[:, x:x + 2] * 0.55 + np.array([120, 170, 220]) * 0.45
        for y in range(m + 12, H2 - m, 30): tex[y:y + 2, :] = tex[y:y + 2, :] * 0.55 + np.array([120, 170, 220]) * 0.45
    elif kind == "lined":
        for y in range(m + 40, H2 - m, 34): tex[y:y + 2, :] = tex[y:y + 2, :] * 0.5 + np.array([110, 150, 215]) * 0.5
        tex[:, m + 46:m + 49] = tex[:, m + 46:m + 49] * 0.4 + np.array([230, 90, 100]) * 0.6
    elif kind == "dots":
        for y in range(m + 14, H2 - m, 28):
            for x in range(m + 14 + (14 if (y // 28) % 2 else 0), W2 - m, 28):
                tex[y - 3:y + 3, x - 3:x + 3] = tex[y - 3:y + 3, x - 3:x + 3] * 0.3 + np.array([255, 255, 255]) * 0.7
    outer = Image.new("L", (W2 * k, H2 * k), 0)
    inner = Image.new("L", (W2 * k, H2 * k), 0)
    po = [(x + m * k, y + m * k) for x, y in _outline(w, h, rng, torn, k)]
    ImageDraw.Draw(outer).polygon(po, fill=255)
    if torn:
        pi = [(x + m * k, y + m * k) for x, y in _outline(w, h, np.random.default_rng(seed + 5), torn, k, amp=1.6)]
        ImageDraw.Draw(inner).polygon(pi, fill=255)
        inner = Image.fromarray(np.minimum(np.asarray(inner), np.asarray(outer)), "L")
    else:
        inner = outer
    ao = np.asarray(outer.resize((W2, H2), Image.LANCZOS), np.float32) / 255
    ai = np.asarray(inner.resize((W2, H2), Image.LANCZOS), np.float32) / 255
    core = np.array([252, 251, 248], np.float32)
    rgb = core * (1 - ai[..., None]) + tex * ai[..., None]
    im = Image.fromarray(np.dstack([np.clip(rgb, 0, 255), ao * 255]).astype(np.uint8), "RGBA")
    if rot: im = im.rotate(rot, Image.BICUBIC, expand=True)
    pad = 40
    out = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (0, 0, 0, 0))
    if shadow > 0:
        sh = soft_shadow(im, shadow, 5, pad=pad, q=2)
        out.alpha_composite(sh, (5, 8))
    out.alpha_composite(im, (pad, pad))
    return out

def _tape(w, h, col, seed, rot):
    """A strip of washi tape: see-through, with stripes and crinkled short ends."""
    rng = np.random.default_rng(seed)
    k = 2
    ys = np.linspace(0, h, 7)
    left = [(rng.uniform(0, 7) * k, y * k) for y in ys]
    right = [((w - rng.uniform(0, 7)) * k, y * k) for y in ys[::-1]]
    poly = left + right
    im = Image.new("RGBA", (w * k, h * k), tuple(col) + (150,))
    d = ImageDraw.Draw(im)
    for x in range(-h * k, w * k, 26 * k):
        d.polygon([(x, 0), (x + 11 * k, 0), (x + 11 * k + h * k, h * k), (x + h * k, h * k)], fill=(255, 255, 255, 150))
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)
    a = np.asarray(im, np.float32).copy()
    a[..., 3] = np.asarray(mask, np.float32) * (a[..., 3] / 255)
    im = Image.fromarray(a.astype(np.uint8), "RGBA").resize((w, h), Image.LANCZOS)
    return im.rotate(rot, Image.BICUBIC, expand=True)

# ------------------------------------------------------------------ pen marks (three boil variants each)
def _scribble(rng, kind, size, col, width):
    s = SS(size, size)
    c = size / 2
    if kind == "spiral":
        pts = []
        for j in range(120):
            t = j / 119 * 5.5 * math.pi
            r = size * 0.08 + size * 0.36 * j / 119
            pts.append((c + math.cos(t) * r * 1.15 + rng.normal(0, 1.3), c + math.sin(t) * r * 0.8 + rng.normal(0, 1.3)))
        s.line(pts, tuple(col) + (235,), width)
    elif kind == "x":
        a = size * 0.32
        s.line([(c - a + rng.normal(0, 2), c - a + rng.normal(0, 2)), (c + a, c + a + rng.normal(0, 2))], tuple(col) + (240,), width)
        s.line([(c + a + rng.normal(0, 2), c - a), (c - a + rng.normal(0, 2), c + a + rng.normal(0, 2))], tuple(col) + (240,), width)
    elif kind == "star":
        pts = []
        for j in range(11):
            ang = -math.pi / 2 + j * 2 * math.pi / 5 * 2
            pts.append((c + math.cos(ang) * size * 0.4 + rng.normal(0, 1.6), c + math.sin(ang) * size * 0.4 + rng.normal(0, 1.6)))
        s.line(pts, tuple(col) + (235,), width)
    elif kind == "arrow":
        p0, p1 = (size * 0.12, size * 0.2), (size * 0.82, size * 0.78)
        mid = (size * 0.62 + rng.normal(0, 2), size * 0.3 + rng.normal(0, 2))
        pts = [(p0[0] + (1 - t) * t * 2 * (mid[0] - p0[0]) + t * t * (p1[0] - p0[0]) + rng.normal(0, 0.6),
                p0[1] + (1 - t) * t * 2 * (mid[1] - p0[1]) + t * t * (p1[1] - p0[1]) + rng.normal(0, 0.6))
               for t in np.linspace(0, 1, 30)]
        s.line(pts, tuple(col) + (240,), width)
        ang = math.atan2(p1[1] - pts[-4][1], p1[0] - pts[-4][0])
        for da in (2.6, -2.6):
            s.line([p1, (p1[0] + math.cos(ang + da) * size * 0.16, p1[1] + math.sin(ang + da) * size * 0.16)],
                   tuple(col) + (240,), width)
    elif kind == "hatch":
        for j in range(6):
            x = size * 0.15 + j * size * 0.13
            s.line([(x + rng.normal(0, 1.5), size * 0.25), (x + size * 0.1 + rng.normal(0, 1.5), size * 0.75)],
                   tuple(col) + (230,), width)
    elif kind == "circle":
        pts = [(c + math.cos(t) * size * 0.42 * (1 + 0.04 * math.sin(3 * t)) + rng.normal(0, 1),
                c + math.sin(t) * size * 0.3 + rng.normal(0, 1)) for t in np.linspace(-0.3, 2 * math.pi + 0.5, 60)]
        s.line(pts, tuple(col) + (230,), width)
    return s.out()

# ------------------------------------------------------------------ ransom letters
def _letters(c, text, seed):
    """Each letter on its own scrap: [(RGBA, x_centre, y_centre)] laid out across the top (frame px)."""
    rng = np.random.default_rng(seed + 101)
    pairs = [(WHITE, INK_BLACK), ((24, 22, 24), (250, 248, 240)), (tuple(c.skin.accent), INK_BLACK),
             (INK_RED, (250, 248, 240)), (KRAFT, INK_BLACK), (PINK, INK_RED), (BLUE, (24, 36, 96)), (NEWS, INK_BLACK),
             (WHITE, INK_RED), (LEMON, (24, 36, 96)), (MINT, INK_BLACK)]
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    tiles, last_pair, last_font = [], -1, -1
    for wi, wd in enumerate(words):
        row = []
        for ch in wd:
            if not ch.strip(): continue
            fi = int(rng.integers(len(FONTS)))
            if fi == last_font: fi = (fi + 3) % len(FONTS)
            pi = int(rng.integers(len(pairs)))
            if pi == last_pair: pi = (pi + 4) % len(pairs)
            last_font, last_pair = fi, pi
            path, idx = FONTS[fi]
            pap, ink = pairs[pi]
            g = ch.upper() if (rng.random() < 0.62 or not ch.isalpha()) else ch.lower()
            try:
                f = font(200, 800, path, idx)
                if f.getbbox(g) is None or f.getlength(g) < 4: raise OSError
            except OSError:
                path, idx = SFP, 0
            t = text_img(g, 200, 860, tuple(ink), 0, path, idx)
            target = 150 * rng.uniform(0.86, 1.1) * (0.82 if g.islower() and g not in "bdfhklt" else 1.0)
            t = scaled(t, target / max(1, t.height))
            if t.width > 190: t = scaled(t, 190 / t.width)
            pw, ph = int(t.width + rng.uniform(22, 44)), int(t.height + rng.uniform(26, 46))
            torn = "".join(sd for sd in "trbl" if rng.random() < 0.22)
            sh = int(rng.integers(1 << 20))
            base = _piece(pw, ph, pap, sh, torn, "plain", 0.0, 0.0)
            pad = 40 + 14
            base.alpha_composite(t, (int(pad + (pw - t.width) / 2 + rng.uniform(-4, 4)), int(pad + (ph - t.height) / 2 + rng.uniform(-4, 4))))
            rot = float(rng.uniform(-9, 9))
            body = base.rotate(rot, Image.BICUBIC, expand=True)
            out = Image.new("RGBA", body.size, (0, 0, 0, 0))
            out.alpha_composite(soft_shadow(body, 0.42, 5, pad=0, q=2), (4, 7))
            out.alpha_composite(body)
            bb = body.getbbox() or (0, 0, body.width, body.height)
            row.append(dict(im=out, w=bb[2] - bb[0], h=bb[3] - bb[1], dy=float(rng.uniform(-16, 16)), gap=float(rng.uniform(-10, 6))))
        if row: tiles.append(row)
    # lines: words packed greedily (at most 3 lines), then scaled so the widest fits 92 % of the frame
    SPACE = 46
    ww = [sum(t["w"] + t["gap"] for t in r) for r in tiles]
    n = len(ww)
    splits = [[list(range(n))]]
    splits += [[list(range(0, i)), list(range(i, n))] for i in range(1, n)]
    splits += [[list(range(0, i)), list(range(i, j)), list(range(j, n))] for i in range(1, n) for j in range(i + 1, n)]
    best = None
    for lines in splits:
        lw = max(sum(ww[j] for j in ln) + SPACE * (len(ln) - 1) for ln in lines)
        sc = min(1.0, W * 0.92 / lw)
        score = sc * (1.0 if len(lines) == 1 else 0.88 if len(lines) == 2 else 0.74)
        if best is None or score > best[0] + 1e-6: best = (score, lines, sc)
    _, lines, sc = best
    out = []
    y0 = 335 if len(lines) == 1 else 300
    for ri, ln in enumerate(lines):
        tw = (sum(ww[j] for j in ln) + SPACE * (len(ln) - 1)) * sc
        x = W / 2 - tw / 2
        y = y0 + ri * 168 * sc
        for j in ln:
            for t in tiles[j]:
                im = scaled(t["im"], sc) if sc < 0.999 else t["im"]
                out.append((im, x + t["w"] * sc / 2, y + t["dy"] * sc))
                x += (t["w"] + t["gap"]) * sc
            x += SPACE * sc
    return out, (y0 + (len(lines) - 1) * 168 * sc + 95 * sc)

# ------------------------------------------------------------------ the page
def _page(c, seed):
    """The base page and the scraps: [(RGBA, x_centre, y_centre, step it appears)] (frame px)."""
    rng = np.random.default_rng(seed)
    pc = hexc(c.p["page"])
    base = paper(W, H, tuple(pc), seed=seed + 11, grain=5.0, mottle=10.0, fibers=0.6, edge=0.8)
    jr = lambda a, b: float(rng.uniform(a, b))
    S = [
        # (w, h, colour, torn sides, kind, centre x, centre y, rotation, step)
        (820, 1040, WHITE, "tlr", "plain", W * 0.5 + jr(-20, 20), H * 0.6, jr(-5, -2), 2),
        (360, 430, PINK, "rb", "plain", 170 + jr(-20, 20), 420, jr(6, 11), 2),
        (420, 300, LAV, "lb", "dots", 900 + jr(-20, 20), 300, jr(-9, -5), 3),
        (330, 470, MINT, "lt", "plain", 980, 880 + jr(-40, 40), jr(-12, -7), 3),
        (380, 330, (250, 250, 246), "", "grid", 150, 1290 + jr(-40, 40), jr(4, 8), 3),
        (330, 420, (251, 250, 244), "rt", "lined", 110, 830 + jr(-30, 30), jr(-13, -8), 4),
        (290, 290, LEMON, "", "plain", 940, 1380 + jr(-30, 30), jr(-8, -3), 4),
        (1000, 320, KRAFT_D, "t", "plain", W * 0.5, 1800, jr(-3, 3), 2),
        (300, 260, BLUE, "rb", "plain", 960, 1640, jr(5, 10), 4),
    ]
    pieces = []
    for j, (w, h, col, torn, kind, x, y, rot, step) in enumerate(S):
        pieces.append((_piece(w, h, col, seed * 31 + j, torn, kind, rot), x, y, step))
    acc = tuple(c.skin.accent)
    pieces.append((_tape(250, 58, acc, seed + 1, jr(28, 38)), 70, 260, 4))
    pieces.append((_tape(230, 54, (240, 150, 170), seed + 2, jr(-25, -15)), 225, 1150, 5))
    pieces.append((_tape(220, 52, (140, 200, 230), seed + 3, jr(-40, -30)), 1010, 640, 5))
    return f32(base), pieces

def _doodles(seed):
    """Pen marks: [(three boil variants, x_centre, y_centre, step it appears)]."""
    out = []
    spec = [("spiral", 210, INK_BLUE, 5, 905, 560, 5), ("x", 120, INK_RED, 9, 150, 1050, 6), ("x", 90, INK_BLACK, 7, 1010, 1130, 7),
            ("star", 150, INK_BLACK, 6, 140, 640, 6), ("arrow", 200, INK_RED, 7, 900, 1030, 7), ("hatch", 160, INK_BLUE, 5, 960, 1500, 7),
            ("circle", 170, INK_BLACK, 5, 160, 1450, 8)]
    for j, (kind, size, col, wd, x, y, step) in enumerate(spec):
        vs = [_scribble(np.random.default_rng(seed * 13 + j * 7 + v), kind, size, col, wd) for v in range(3)]
        out.append((vs, x, y, step))
    return out

def _timing(c, n):
    """(entry step k, exit stage 0-4) for this frame, counted in stop-motion steps of n frames."""
    f0 = int(round(c.t0 * FPS)); f1 = int(math.floor(c.t1 * FPS + 1e-6))
    k = (c.i - f0 + n - 1) // n
    out_stage = max(0, 4 - (f1 - c.i) // n)
    return k, out_stage

def render(c):
    p, st = c.p, c.state
    n = int(clamp(int(p.get("steps") or 3), 1, 6))
    k, ex = _timing(c, n)
    if k <= 0 or ex >= 4:
        return c.img
    seed = int(p.get("seed") or 7)
    if "page" not in st:
        st["page"], st["pieces"] = _page(c, seed)
        st["doodles"] = _doodles(seed)
        word = re.sub(r"[^\w' -]", "", str(p["text"]) if p.get("text") else key_word(c))
        st["letters"], title_bottom = _letters(c, word, seed) if word else ([], 220)
        (fx, fy, fw, fh), _ = face_stats(c)
        ht = head_top_px(c, (fx, fy, fw, fh))
        sp = clamp(min(float(p["size"]), (H - title_bottom - 40) / max(1.0, H - ht)), 0.5, 1.0)
        st["you"] = dict(fx=fx, sp=sp)
        f0 = int(round(c.t0 * FPS)); f1 = int(math.floor(c.t1 * FPS + 1e-6))
        total = (f1 - f0) // n + 1
        avail = max(1, total - 5 - 4 - 3)
        st["per"] = max(1, math.ceil(len(st["letters"]) / avail))
        st["rng_y"] = np.random.default_rng(seed + 55)
    rng = np.random.default_rng(seed * 1000 + k)             # this step's jitter
    # ---- the page and its scraps (built once per step)
    if st.get("step_k") != k:
        cv = pil(st["page"]).convert("RGBA")
        for im, x, y, s0 in st["pieces"]:
            if k < s0: continue
            sc = 1.1 if k == s0 else 1.0
            el = scaled(im, sc) if sc != 1.0 else im
            comp(cv, el, x - el.width / 2 + rng.uniform(-2.5, 2.5), y - el.height / 2 + rng.uniform(-2.5, 2.5))
        for vs, x, y, s0 in st["doodles"]:                       # pen marks on the page, boiling
            if k < s0: continue
            im = vs[k % 3]
            comp(cv, im, x - im.width / 2, y - im.height / 2)
        st["page_k"] = f32(np.asarray(cv.convert("RGB")))
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))            # in front of you: the title
        for j, (im, x, y) in enumerate(st["letters"]):
            s0 = 5 + j // st["per"]
            if k < s0: continue
            sc = 1.28 if k == s0 else 1.0
            el = scaled(im, sc) if sc != 1.0 else im
            comp(lay, el, x - el.width / 2 + rng.uniform(-3, 3), y - el.height / 2 + rng.uniform(-3, 3))
        st["front_k"] = lay
        st["step_k"] = k
    page = st["page_k"]
    # ---- you, as a sticker: slapped on at step 3, settling at 4
    Y = st["you"]
    if k >= 3:
        pop, rot = (1.16, -6.0) if k == 3 else (0.985, -0.6) if k == 4 else (1.0, -1.5)
        rot += float(np.random.default_rng(seed * 7 + k).uniform(-0.3, 0.3))
        sp = Y["sp"] * pop
        m = solid_mask(c)
        prgb, pa = move_layer(c.img, tighten(m, 0.1), sp, Y["fx"], H, W / 2, H + 30, rot)
        border = dilate(pa, float(p["border"]))
        if "tex" not in st:
            st["tex"] = f32(paper(W, H, (250, 249, 244), seed=seed + 3, grain=3.0, mottle=4.0, fibers=0.4))
        sh = shift(soft(border, 9), 9, 16) * 0.5
        page = page * (1 - sh[..., None])
        page = page * (1 - border[..., None]) + st["tex"] * border[..., None]
        edge = np.clip(border - soft(border, 1.2) * 1.0, 0, 1) * 0.25               # a hair of grey on the cut edge
        page = page * (1 - edge[..., None])
        page = page * (1 - pa[..., None]) + prgb * pa[..., None]
    # ---- the title, in front
    L = np.asarray(st["front_k"], np.float32)
    la = L[..., 3:4] / 255
    out = page * (1 - la) + L[..., :3] * la
    # ---- arriving: the page slaps in from below on step 1, overshoots on 2; leaving: it slides off in jumps
    off, ang, zs = 0.0, 0.0, 1.0
    if k == 1: off, ang = H * 0.42, 5.0
    elif k == 2: off, ang, zs = -H * 0.012, -1.2, 1.045        # the overshoot, a touch big so no edge shows
    if ex > 0:
        off, ang = ((H * 0.07, 1.5), (H * 0.3, 4.0), (H * 0.68, 7.5), (H * 1.3, 11))[ex - 1]
    if off or ang:
        im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        moved = affine(im, zs, W / 2, H, W / 2, H + off, ang)
        bg = c.img.convert("RGBA")
        bg.alpha_composite(soft_shadow(moved, 0.5, 12, pad=60, q=4), (-60 + 6, -60 + 16))
        bg.alpha_composite(moved)
        return bg.convert("RGB")
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the title is your own word; the pen marks are doodles, no words",
    "still": 0.6,
    "needs": ["person"],
}
