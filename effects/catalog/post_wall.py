"""Post wall: the room goes dark and a grid of post tiles pops in behind you, tile by tile, with a header that
counts the tiles on the wall ("24 POSTS")."""
import math
import numpy as np
from PIL import Image, ImageFilter
from core import (W, H, SS, comp, scaled, with_alpha, rounded, f32, over, mix, to_pil, vignette, ease_out, ease_in, back,
                  prog, lerp, clamp)
from catalog._b import stills, load_images, crop_fill, face_stats, font_args, solid_mask

NAME = "post-wall"
KIND = "behind"
ABOUT = "A wall of post tiles pops in behind you on a dark backdrop, with a header counting the tiles"
DUR = 4.5
PARAMS = dict(
    images=None,        # list of image paths for the tiles; default stills from this video (varied crops)
    cols=4,             # tiles across
    shape="square",     # square | portrait (4:5)
    count=None,         # a real number for the header; default the number of tiles actually on the wall
    word="POSTS",       # the word after the number in the header
    label=None,         # optional small line above the header (e.g. your handle); default none
    dim=0.72,           # how dark the room gets behind the wall (0-1)
)
GAP, MARGIN, TOP = 10, 18, 330


def _grid(c):
    cols = int(clamp(int(c.p.get("cols") or 4), 2, 7))
    tw = (W - 2 * MARGIN - (cols - 1) * GAP) / cols
    th = tw * (1.25 if c.p.get("shape") == "portrait" else 1.0)
    rows = int((H - TOP + GAP) // (th + GAP))
    cells = [(MARGIN + j * (tw + GAP), TOP + i * (th + GAP)) for i in range(rows) for j in range(cols)]
    return cells, int(round(tw)), int(round(th))

def _tiles(c, n, tw, th):
    imgs = load_images(c.p.get("images"), (tw * 2, th * 2))
    if imgs:
        src = [imgs[k % len(imgs)] for k in range(n)]
    else:
        m = min(n, 16)
        raw = stills(c.subj, m, (360, 640))
        idx = [int(round((0.04 + 0.92 * k / max(1, m - 1)) * (c.subj.n - 1))) for k in range(m)]
        rng = np.random.default_rng(17)
        src = []
        for k in range(n):
            im, i = raw[k % m], idx[k % m]
            fx, fy, fw, fh = c.subj.face(i)
            # vary the framing so the wall reads like a feed: close-ups, wide shots, details
            kind = rng.choice(["face", "wide", "chest", "side"], p=[0.35, 0.3, 0.2, 0.15])
            if kind == "face": z, cx, cy = rng.uniform(1.9, 2.6), fx / W, fy / H
            elif kind == "wide": z, cx, cy = rng.uniform(1.0, 1.2), 0.5, rng.uniform(0.35, 0.5)
            elif kind == "chest": z, cx, cy = rng.uniform(1.4, 1.8), fx / W, (fy + fh * 1.1) / H
            else: z, cx, cy = rng.uniform(1.5, 2.0), rng.choice([0.2, 0.8]), rng.uniform(0.35, 0.55)
            src.append(crop_fill(im, (tw * 2, th * 2), cx, cy, z))
    out = []
    for k, im in enumerate(src):
        im = im.resize((tw, th), Image.LANCZOS).convert("RGBA")
        s = SS(tw, th)
        s.rr((0.5, 0.5, tw - 0.5, th - 0.5), 16, outline=(255, 255, 255, 46), width=1.5)
        if k % 3 == 1:   # a small play mark on some tiles, like video posts
            s.poly([(tw - 40, 22), (tw - 40, 46), (tw - 20, 34)], fill=(255, 255, 255, 235))
        im.alpha_composite(s.out())
        out.append(rounded(im, 16))
    return out

def _header(c, num):
    """'24 POSTS' with a grid icon and a tab underline. Returns RGBA."""
    F = font_args(c.skin, "title")
    word = str(c.p.get("word") or "")
    txt = f"{num} {word}".strip()
    s0 = SS(1, 1)
    size = 44
    tw = s0.textlen(txt, size, F["weight"], F["path"], F["index"])
    w, h = int(tw + 64 + 40), 76
    s = SS(w, h)
    # grid icon
    for i in range(3):
        for j in range(3):
            s.rr((20 + j * 12, 18 + i * 12, 29 + j * 12, 27 + i * 12), 2, fill=(255, 255, 255, 255))
    s.text((64 + 14, 34), txt, size, fill=(255, 255, 255, 255), anchor="lm", **F)
    s.rr((0, h - 5, w, h), 2.5, fill=(255, 255, 255, 255))
    return s.out()

def render(c):
    st = c.state
    d, u = c.d, c.u
    if "cells" not in st:
        cells, tw, th = _grid(c)
        st["cells"], st["tw"], st["th"] = cells, tw, th
        st["tiles"] = _tiles(c, len(cells), tw, th)
        (fx, fy, fw, fh), _ = face_stats(c)
        st["f0"] = (fx, fy)
        # pop order: rippling out from behind your head
        dist = [math.hypot(x + tw / 2 - fx, (y + th / 2 - fy) * 0.9) for x, y in cells]
        mx = max(dist) or 1
        rng = np.random.default_rng(3)
        st["delay"] = [0.75 * (dd / mx) + rng.uniform(0, 0.08) for dd in dist]
        st["heads"] = {}
        st["vig"] = vignette(0.55, 0.8)
        # once the wall is up, a tile now and then flips over to another post (outer tiles, which you don't cover)
        sp0 = min(1.0, c.d / 4.0)
        t_full = 0.12 + max(st["delay"]) * sp0 + 0.45
        t_end = c.d - min(0.7, c.d * 0.28) - 0.5
        outer = [k for k, dd in enumerate(dist) if dd > 0.45 * mx]
        flips, t, e = [], t_full, 0
        while outer and t < t_end:
            k = int(rng.choice(outer))
            flips.append((t, k, (k + 5 + 7 * e) % len(cells)))
            t += rng.uniform(0.35, 0.6); e += 1
        st["flips"] = flips
    cells, tiles, tw, th = st["cells"], st["tiles"], st["tw"], st["th"]
    n = len(cells)
    sp = min(1.0, d / 4.0)
    t_in = 0.12
    t_out = d - min(0.7, d * 0.28)
    k_bg = ease_out(prog(u, 0, 0.4 * sp + 0.05)) * (1 - ease_in(prog(u, d - 0.4 * sp - 0.05, 0.4 * sp + 0.05)))
    if k_bg <= 0.001: return c.img
    fx, fy, fw, fh = c.face
    # parallax: the wall shifts a little against your movement and drifts slowly up
    ox = -(fx - st["f0"][0]) * 0.12
    oy = -(fy - st["f0"][1]) * 0.12 - 22 * ease_out(u / max(d, 0.1)) + 11
    lay = c.canvas()
    shown = 0
    FL = 0.42
    for k, (x, y) in enumerate(cells):
        im, sx = tiles[k], 1.0
        for te, kk, ni in st["flips"]:
            if kk != k or te > u: continue
            f = (u - te) / FL
            if f >= 0.5: im = tiles[ni]
            if f < 1: sx = abs(math.cos(math.pi * f))
        dl = st["delay"][k] * sp
        p = prog(u, t_in + dl, 0.38)
        q = prog(u, t_out + (0.75 * sp - dl) * 0.35, 0.26)       # leave: outer tiles first, then in toward you
        if p <= 0 or q >= 1: continue
        if p >= 0.5 and q < 0.5: shown += 1
        s = lerp(0.35, 1.0, back(p, 2.0)) * lerp(1.0, 0.4, ease_in(q))
        a = ease_out(p * 2.2) * (1 - ease_in(q))
        rot = (1 - ease_out(p)) * (7 if k % 2 else -7)
        cx, cy = x + tw / 2 + ox, y + th / 2 + oy
        if sx < 0.999:
            im = im.resize((max(1, int(round(tw * sx))), th), Image.BILINEAR)
        if s < 0.999 or rot:
            im2 = scaled(im, s)
            if abs(rot) > 0.05: im2 = im2.rotate(rot, Image.BICUBIC, expand=True)
        else:
            im2 = im
        if a < 0.999: im2 = with_alpha(im2, a)
        comp(lay, im2, cx - im2.width / 2, cy - im2.height / 2)
    # the room behind: darker and vignetted, the wall on it, and your soft shadow on the wall
    src = f32(np.asarray(c.img))
    room = src * (1 - float(c.p.get("dim", 0.72)) * k_bg * st["vig"][..., None] ** 0.2)
    wall = over(room, lay)
    q = 4
    mask = solid_mask(c)
    m8 = Image.fromarray((mask * 255).astype(np.uint8), "L").resize((W // q, H // q), Image.BILINEAR)
    sh = Image.new("L", m8.size, 0); sh.paste(m8, (0, 26 // q))
    sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(9)).resize((W, H), Image.BILINEAR), np.float32) / 255
    wall *= (1 - 0.6 * k_bg * sh)[..., None]
    # a slightly tighter cutout, so the bright edge of the old background doesn't glow against the dark wall
    mt = np.clip((mask - 0.3) / 0.62, 0, 1)
    mt = mt * k_bg + mask * (1 - k_bg)
    out = to_pil(mix(f32(np.asarray(c.img)), wall, mt))
    # header: counts the tiles that are actually up on the wall (or a real number from PARAMS)
    cnt = c.p.get("count")
    if cnt is not None:
        try: num = int(round(float(cnt) * shown / n))
        except (TypeError, ValueError): num = cnt
        if shown == n: num = cnt
    else:
        num = shown
    # once tiles start leaving, the header keeps the full count while it fades
    st["peak"] = max(st.get("peak", 0), shown)
    if u >= t_out - 0.05 and cnt is None: num = st["peak"]
    first = t_in + min(st["delay"]) * sp
    ha = ease_out(prog(u, first + 0.1, 0.3)) * (1 - ease_in(prog(u, t_out - 0.05, 0.25)))
    if ha > 0.01:
        key = str(num)
        if key not in st["heads"]: st["heads"][key] = _header(c, num)
        hd = st["heads"][key]
        fr = c.canvas()
        hy = TOP - hd.height - 18 + oy * 0.5 + 14 * (1 - ease_out(prog(u, first + 0.1, 0.4)))
        comp(fr, with_alpha(hd, ha), W / 2 - hd.width / 2, hy)
        if c.p.get("label"):
            F = font_args(c.skin, "body")
            s = SS(W, 50)
            s.text((W / 2, 25), str(c.p["label"]), 30, fill=(235, 235, 240, int(230 * ha)), anchor="mm", **F)
            comp(fr, s.out(), 0, hy - 52)
        out = c.front(fr, out)
    return out

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "CLAUDE-WROTE: the header word 'POSTS' (the default). The number is the count of tiles actually on the wall; the tiles are stills from this same clip.",
    "needs": ["person"],
}
