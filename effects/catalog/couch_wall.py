"""Couch wall: the room behind you turns into a tall wall of big rounded 9:16 video tiles, staggered like a masonry
feed and tilted a little in perspective. The tiles play other moments of this same video (short loops) and pop in
as a ripple from behind your head, then leave the same way."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, FPS, SS, f32, to_pil, mix, vignette, project, ease_out, ease_in, ease_io, back, prog, lerp,
                  clamp)
from catalog._b import load_images, face_stats, solid_mask, smooth_noise
from catalog._wall import homog, apply_h, pil_coeffs, loops, pingpong

NAME = "couch-wall"
KIND = "behind"
ABOUT = "The room behind you becomes a tilted wall of big rounded video tiles playing other moments of this video"
DUR = 4.5
PARAMS = dict(
    images=None,     # list of image paths for the tiles; default short loops from this video, playing
    cols=4,          # tile columns across the wall (3-6; fewer = bigger tiles)
    tilt=12,         # perspective tilt of the wall in degrees (0 = flat on)
    dim=0.86,        # how dark the wall between the tiles is (0-1)
    border=0.4,      # brightness of the thin tile borders (0 = none)
    loop=1.4,        # seconds in each tile's loop (played forward, then back)
)
WW, WH = 1400, 2500          # the wall, flat, before it's tilted (bigger than the frame so it fills it edge to edge)
GAP, RAD = 16, 30
LW, LH = 270, 480            # loop frames are kept at this size
NLOOP = 6


def _layout(cols):
    """Tile boxes on the flat wall: [(x, y, w, h)], columns staggered like a masonry feed."""
    tw = (WW - (cols + 1) * GAP) / cols
    th = tw * 16 / 9
    stag = [0.18, 0.68, 0.38, 0.88, 0.1, 0.55]
    out = []
    for j in range(cols):
        x = GAP + j * (tw + GAP)
        y = -stag[j % len(stag)] * th
        while y < WH:
            if y + th > 0: out.append((x, y, tw, th))
            y += th + GAP
    return out, int(round(tw)), int(round(th))

def _plane(c, u, st):
    """Matrix taking a flat-wall point to the screen at time u (a slow drift in tilt, a gentle push in)."""
    tilt = float(c.p.get("tilt", 12) or 0)
    d = max(c.d, 0.1)
    k = ease_io(u / d)
    ry = -tilt * lerp(0.9, 0.55, k) + 0.6 * smooth_noise(u * 0.4, 5)
    rx = tilt * lerp(0.75, 0.5, k) + 0.4 * smooth_noise(u * 0.4, 9)
    s = st["scale"] * lerp(1.0, 1.045, k)
    fx, fy = st["f0"]
    ox = -(c.face[0] - fx) * 0.08
    oy = -(c.face[1] - fy) * 0.08 + lerp(18, -18, k)
    rz = -1.6 * tilt / 12 + 0.3 * smooth_noise(u * 0.3, 13)
    dst = project(WW, WH, W / 2 + ox, H * 0.47 + oy, s, ry, rx, rz, 1500)
    return homog([(0, 0), (WW, 0), (WW, WH), (0, WH)], dst)

def _covers(M):
    """Does the wall (through M, wall -> screen) cover the whole frame?"""
    inv = np.linalg.inv(M)
    p = apply_h(inv, [(-4, -4), (W + 4, -4), (W + 4, H + 4), (-4, H + 4), (W / 2, -4), (W / 2, H + 4), (-4, H / 2), (W + 4, H / 2)])
    return bool((p[:, 0] > 0).all() and (p[:, 0] < WW).all() and (p[:, 1] > 0).all() and (p[:, 1] < WH).all())

def _backing():
    """The wall between the tiles: near black, a touch lighter in the middle, with faint grain."""
    y, x = np.mgrid[0:WH // 4, 0:WW // 4].astype(np.float32)
    d = np.sqrt(((x - WW / 8) / (WW / 4)) ** 2 + ((y - WH / 9) / (WH / 4)) ** 2)
    g = np.clip(1 - d * 0.9, 0, 1)
    base = np.array([9, 9, 11], np.float32) + g[..., None] * np.array([16, 15, 17], np.float32)
    im = Image.fromarray(base.astype(np.uint8), "RGB").resize((WW, WH), Image.BILINEAR)
    return im

def _tile_art(tw, th, border):
    m = Image.new("L", (tw * 2, th * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, tw * 2 - 1, th * 2 - 1], radius=RAD * 2, fill=255)
    m = m.resize((tw, th), Image.LANCZOS)
    s = SS(tw, th)
    if border > 0:
        s.rr((0.75, 0.75, tw - 0.75, th - 0.75), RAD, outline=(255, 255, 255, int(255 * min(1, border))), width=1.6)
    # a soft sheen down from the top edge, like glass over a screen
    sheen = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
    a = (np.clip(1 - np.arange(th, dtype=np.float32) / (th * 0.35), 0, 1) ** 2 * 26).astype(np.uint8)
    sheen.putalpha(Image.fromarray(np.repeat(a[:, None], tw, 1), "L"))
    ov = s.out(); sheen.alpha_composite(ov)
    return m, sheen

def _sources(c, n, tw, th):
    """Per tile: a function f(i) -> PIL RGB at (tw, th)."""
    imgs = load_images(c.p.get("images"), (tw, th))
    if imgs:
        return [(lambda i, im=imgs[k % len(imgs)]: im) for k in range(n)]
    L = int(clamp(round(float(c.p.get("loop") or 1.4) * FPS), 8, 60))
    N = c.subj.n
    starts = [int(round((0.03 + 0.94 * k / (NLOOP - 1)) * max(0, N - L))) for k in range(NLOOP)]
    arr = loops(c.subj, starts, L, (LW, LH))
    arr = (arr.astype(np.float32) * 0.8 + 3).astype(np.uint8)       # tiles a little darker than you
    rng = np.random.default_rng(41)
    out = []
    for k in range(n):
        lp = (k * 5 + 2) % NLOOP
        si = starts[lp] + L // 2
        fx, fy, fw, fh = c.subj.face(si)
        kind = rng.choice(["face", "wide", "chest", "side"], p=[0.3, 0.35, 0.2, 0.15])
        if kind == "face": z, cx, cy = rng.uniform(1.4, 1.6), fx / W, fy / H
        elif kind == "wide": z, cx, cy = rng.uniform(1.0, 1.12), 0.5, 0.5
        elif kind == "chest": z, cx, cy = rng.uniform(1.25, 1.4), fx / W, (fy + fh * 0.9) / H
        else: z, cx, cy = rng.uniform(1.3, 1.45), rng.choice([0.3, 0.7]), rng.uniform(0.4, 0.55)
        cw, ch = LW / z, LH / z
        x0 = clamp(cx * LW - cw / 2, 0, LW - cw); y0 = clamp(cy * LH - ch / 2, 0, LH - ch)
        box = (x0, y0, x0 + cw, y0 + ch)
        ph = int(rng.integers(0, 2 * L))
        def f(i, lp=lp, box=box, ph=ph):
            return Image.fromarray(arr[lp, pingpong(i + ph, L)], "RGB").resize((tw, th), Image.BILINEAR, box=box)
        out.append(f)
    return out

def render(c):
    st = c.state
    d, u = c.d, c.u
    if "boxes" not in st:
        cols = int(clamp(int(c.p.get("cols") or 4), 3, 6))
        boxes, tw, th = _layout(cols)
        (fx, fy, fw, fh), _ = face_stats(c)
        st["f0"] = (fx, fy)
        st["scale"] = 1.0
        for _ in range(30):                      # big enough to fill the frame through the whole drift
            if all(_covers(_plane(c, uu, st)) for uu in np.linspace(0, d, 6)): break
            st["scale"] *= 1.04
        M0 = _plane(c, 0, st)
        ctr = apply_h(M0, [(x + w / 2, y + h / 2) for x, y, w, h in boxes])
        on = [k for k, (px, py) in enumerate(ctr) if -th < px < W + th and -th < py < H + th]
        boxes = [boxes[k] for k in on]; ctr = ctr[on]
        dist = np.hypot(ctr[:, 0] - fx, (ctr[:, 1] - fy) * 0.85)
        mx = float(dist.max()) or 1.0
        rng = np.random.default_rng(7)
        st["delay"] = [0.7 * dd / mx + rng.uniform(0, 0.07) for dd in dist]
        st["boxes"], st["tw"], st["th"] = boxes, tw, th
        st["mask"], st["art"] = _tile_art(tw, th, float(c.p.get("border", 0.4)))
        st["src"] = _sources(c, len(boxes), tw, th)
        st["back"] = _backing()
        st["vig"] = vignette(0.55, 0.78, 0.45)
        st["spin"] = [rng.uniform(-4, 4) for _ in boxes]
    sp = min(1.0, d / 4.0)
    t_out = d - min(0.75, d * 0.28)
    k_bg = ease_io(prog(u, 0, 0.5 * sp + 0.05)) * (1 - ease_in(prog(u, d - 0.3 * sp - 0.06, 0.3 * sp + 0.06)))
    if k_bg <= 0.001: return c.img
    tw, th = st["tw"], st["th"]
    wall = st["back"].copy()
    mx_delay = max(st["delay"])
    for k, (x, y, w_, h_) in enumerate(st["boxes"]):
        dl = st["delay"][k] * sp
        p = prog(u, 0.08 + dl, 0.42)
        q = prog(u, t_out + (mx_delay - st["delay"][k]) * sp * 0.4, 0.3)     # outer tiles leave first
        if p <= 0 or q >= 1: continue
        s = lerp(0.6, 1.0, back(p, 1.7)) * lerp(1.0, 0.82, ease_in(q))
        a = ease_out(min(1, p * 2.4)) * (1 - ease_in(q))
        im = st["src"][k](c.i)
        mk, art = st["mask"], st["art"]
        if p < 1 and p > 0:                      # a quick flash as each tile lands
            fl = 0.28 * (1 - ease_out(min(1, p * 1.6)))
            if fl > 0.02: im = Image.blend(im, Image.new("RGB", im.size, (255, 255, 255)), fl)
        rot = st["spin"][k] * (1 - ease_out(p)) + st["spin"][k] * 0.6 * ease_in(q)
        if abs(s - 1) > 1e-3 or abs(rot) > 0.05:
            sw, sh = max(2, int(round(tw * s))), max(2, int(round(th * s)))
            im = im.resize((sw, sh), Image.BILINEAR); mk = mk.resize((sw, sh), Image.BILINEAR)
            art = art.resize((sw, sh), Image.BILINEAR)
            if abs(rot) > 0.05:
                im = im.rotate(rot, Image.BILINEAR, expand=True)
                mk = mk.rotate(rot, Image.BILINEAR, expand=True); art = art.rotate(rot, Image.BILINEAR, expand=True)
        if a < 0.999: mk = mk.point(lambda v, a=a: int(v * a))
        px, py = int(round(x + w_ / 2 - im.width / 2)), int(round(y + h_ / 2 - im.height / 2))
        wall.paste(im, (px, py), mk)
        if a < 0.999:
            art = art.copy(); art.putalpha(art.getchannel("A").point(lambda v, a=a: int(v * a)))
        wall.paste(art, (px, py), art)
    M = _plane(c, u, st)
    scr = wall.transform((W, H), Image.PERSPECTIVE, pil_coeffs(np.linalg.inv(M)), Image.BILINEAR)
    scr = scr.resize((W * 2 // 3, H * 2 // 3), Image.BILINEAR).resize((W, H), Image.BILINEAR)   # a touch of depth of field
    wl = f32(np.asarray(scr)) * st["vig"][..., None]
    # your soft shadow on the wall, a little below and behind you
    q4 = 4
    mask = solid_mask(c)
    m8 = Image.fromarray((mask * 255).astype(np.uint8), "L").resize((W // q4, H // q4), Image.BILINEAR)
    sh = Image.new("L", m8.size, 0); sh.paste(m8, (6 // q4, 34 // q4))
    sh = np.asarray(sh.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR), np.float32) / 255
    wl *= (1 - 0.62 * sh)[..., None]
    src = f32(np.asarray(c.img))
    dim = float(c.p.get("dim", 0.86))
    room = src * (1 - dim * k_bg)
    back_ = room * (1 - k_bg) + wl * k_bg
    # a slightly tighter cutout, so the bright edge of the old room doesn't glow against the dark wall
    mt = np.clip((mask - 0.3) / 0.62, 0, 1)
    mt = mt * k_bg + mask * (1 - k_bg)
    person = src * (1 - 0.06 * k_bg * (1 - st["vig"][..., None]))
    return to_pil(mix(person, back_, mt))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text; the tiles are loops from this same clip",
    "needs": ["person"],
}
