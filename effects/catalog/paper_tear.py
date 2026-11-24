"""Paper tear: an off-white sheet drops over the frame with your word on it, then rips open (in two pieces that fall
away, or with a torn edge sweeping across) to reveal the video. Optionally it tears back closed at the end."""
import math, re
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, f32, to_pil, font, text_img, ease_out, ease_in, ease_io, back, prog, lerp, clamp, clamp01, hexc,
                  key_words)
from ._print import paper, blur, torn_path, fbm, noise, fibre_lines, sentence_with, smooth, grid, key_word

NAME = "paper-tear"
KIND = "cards"
ABOUT = "A paper sheet with your word drops over the frame, then tears open to reveal you"
DUR = 3.0
PARAMS = dict(
    text=None,          # the word on the sheet; default the key word you say in the window
    line=True,          # your sentence in small type under the word
    mode="split",       # split (rips in two, the halves fall away) | sweep (a torn edge sweeps across)
    close=False,        # True: the tear closes back up near the end, then the sheet drops away
    tear_at=None,       # seconds into the effect when it rips; default about 40% in
    paper="#F3F0E9",    # sheet colour
    ink=None,           # word colour; default the skin's ink
)
MG = 70                  # the sheet is bigger than the frame by this much on every side

def _sheet(c, word, line, pap, ink, acc):
    """The sheet with the word on it: float32 (H+2MG) x (W+2MG) x 3."""
    PWm, PHm = W + 2 * MG, H + 2 * MG
    sh = paper(PWm, PHm, tuple(pap), seed=91, grain=5.0, mottle=5.0, fibers=0.9).copy()
    yy, xx = grid(PHm, PWm)
    v = np.sqrt(((xx - PWm / 2) / PWm) ** 2 + ((yy - PHm * 0.45) / PHm) ** 2)
    sh *= (1 - 0.10 * v ** 2)[..., None]
    lay = Image.new("RGBA", (PWm, PHm), (0, 0, 0, 0))
    cx, cy = PWm / 2, MG + H * 0.44
    if word:
        path, idx, wt = c.skin.fontspec("title").values()
        size = 300
        while size > 60 and font(size, wt, path, idx).getlength(word) > W * 0.84: size -= 6
        t = text_img(word, size, wt, tuple(ink), int(-size * 0.02), path, idx)
        lay.alpha_composite(t, (int(cx - t.width / 2), int(cy - t.height / 2)))
        bar_y = cy + t.height / 2 + 34
        d = ImageDraw.Draw(lay)
        d.rounded_rectangle([cx - 70, bar_y, cx + 70, bar_y + 14], radius=7, fill=tuple(acc) + (255,))
        if line:
            bp, bi, bw = c.skin.fontspec("body").values()
            s2 = 40
            while s2 > 22 and font(s2, bw, bp, bi).getlength(line) > W * 0.8: s2 -= 2
            t2 = text_img(line, s2, bw, tuple(int(v_ * 0.55 + 120 * 0.45) for v_ in ink), 0, bp, bi)
            lay.alpha_composite(t2, (int(cx - t2.width / 2), int(bar_y + 50)))
    la = f32(np.asarray(lay)); a = la[..., 3:4] / 255.0
    # ink sits in the paper: a hair of the texture shows through
    tex = (fbm(PWm, PHm, 3, 2, 5) - 0.5)[..., None] * 0.18
    return np.clip(sh * (1 - a) + la[..., :3] * a * (1 + tex), 0, 255), cy

def _premul(rgb, alpha):
    """Premultiplied RGBa image from float rgb and alpha (0..1)."""
    a = np.clip(alpha, 0, 1)[..., None]
    arr = np.concatenate([np.clip(rgb * a, 0, 255), a * 255], -1).astype(np.uint8)
    return Image.fromarray(arr, "RGBa")

def _split_pieces(sheet, cy, seed):
    """Top and bottom halves along a jagged tear through the word: two premultiplied RGBa images."""
    PHm, PWm = sheet.shape[:2]
    yy, xx = grid(PHm, PWm)
    prof = torn_path(PWm, seed, big=34, mid=9, fine=2.6, scale=PWm / 2.2)
    slope = np.linspace(-1, 1, PWm, dtype=np.float32) * 46
    py = (cy + 18 + prof + slope).astype(np.float32)
    D = yy - py[None, :]
    fine = (noise(PWm, PHm, 1.6, seed + 7) - 0.5) * 2.2
    Dn = D + fine
    a_top = np.clip(0.5 - Dn, 0, 1)
    # the top half keeps a ragged strip of bright paper core along its torn edge
    band = 4.5 + 5.5 * (torn_path(PWm, seed + 11, big=1.0, mid=0.7, fine=0.25, scale=60) * 0.5 + 0.5)
    inner = Dn + band[None, :]
    strip = np.clip(0.5 + inner, 0, 1) * a_top
    streak = noise(PWm, PHm, 2.2, seed + 13)
    core = np.array([253, 252, 249], np.float32) - (streak[..., None] * 14)
    top = sheet * (1 - strip[..., None]) + core * strip[..., None]
    # a faint shade just above the strip, where the sheet lifts
    lift = np.clip(1 - (-(D + band[None, :])) / 26, 0, 1) * (D < -band[None, :]) * 0.06
    top = top * (1 - lift[..., None])
    a_bot = np.clip(0.5 + Dn, 0, 1)
    bot = sheet * (1 - (np.clip(1 - np.abs(Dn - 1.0), 0, 1) * 0.12)[..., None])
    im_top, im_bot = _premul(top, a_top), _premul(bot, a_bot)
    # loose fibres along both edges
    k = 2
    y0, y1 = int(py.min()) - 30, int(py.max()) + 30
    for im, sgn, dens in ((im_top, 1, 0.42), (im_bot, -1, 0.16)):
        band_im = Image.new("RGBA", (PWm * k, (y1 - y0) * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(band_im)
        rng = np.random.default_rng(seed + (3 if sgn > 0 else 4))
        xs = np.arange(0, PWm, 3)
        pts = [(x * k, (py[x] - y0 + (-band[x] * 0.3 if sgn > 0 else 1)) * k) for x in xs]
        nrm = [(0, sgn)] * len(pts)
        fibre_lines(d, pts, nrm, rng, (255, 254, 250, 200), k=k, density=dens, length=(3, 11))
        band_im = band_im.resize((PWm, y1 - y0), Image.LANCZOS)
        base = im.convert("RGBA")
        base.alpha_composite(band_im, (0, y0))
        im.paste(base.convert("RGBa"))
    return im_top, im_bot, py

def _xform(im, dx, dy, rot, px, py, sc=1.0):
    """Place a sheet-sized RGBa image on the frame: rotate rot degrees (clockwise) about screen point (px, py), move
    by (dx, dy), then scale by sc about the frame centre. Returns float32 premultiplied HxWx4."""
    t = math.radians(rot)
    cs, sn = math.cos(t), math.sin(t)
    ox, oy = W / 2 * (1 - 1 / sc), H / 2 * (1 - 1 / sc)
    a, b = cs / sc, sn / sc
    c_ = cs * (ox - px - dx) + sn * (oy - py - dy) + px + MG
    d, e = -sn / sc, cs / sc
    f = -sn * (ox - px - dx) + cs * (oy - py - dy) + py + MG
    out = im.transform((W, H), Image.AFFINE, (a, b, c_, d, e, f), Image.BICUBIC)
    return np.asarray(out, np.float32)

def _over(base, pm, shadow=0.42, off=(12, 22), soft=16):
    """Composite a premultiplied layer over base with a soft drop shadow."""
    A = pm[..., 3] / 255.0
    if shadow > 0:
        s = blur(A, soft, 4)
        s = np.roll(np.roll(s, off[1], 0), off[0], 1)
        base = base * (1 - shadow * s[..., None])
    return base * (1 - A[..., None]) + pm[..., :3]

def render(c):
    st = c.state
    pap = hexc(c.p["paper"]); ink = hexc(c.p["ink"]) if c.p.get("ink") else tuple(c.skin.ink)
    u, d = c.u, c.d
    if "sheet" not in st:
        word = re.sub(r"[^\w'-]", "", key_word(c)).upper()
        line = sentence_with(c.words, word, c.t0, c.t1, 52) if (word and c.p.get("line")) else None
        sheet, cy = _sheet(c, word, line, pap, ink, c.skin.accent)
        st["sheet"], st["cy"] = sheet, cy
        st["full"] = _premul(sheet, np.ones(sheet.shape[:2], np.float32))
        if c.p["mode"] == "split":
            st["top"], st["bot"], st["py"] = _split_pieces(sheet, cy, 5)
        else:
            prof = torn_path(H + 2 * MG, 23, big=40, mid=10, fine=2.8, scale=(H + 2 * MG) / 2.5)
            st["px"] = (prof + np.linspace(-1, 1, H + 2 * MG, dtype=np.float32) * 120)[MG:MG + H]
            st["band"] = (4.5 + 5.5 * (torn_path(H, 31, big=1.0, mid=0.7, fine=0.25, scale=60) * 0.5 + 0.5)).astype(np.float32)
            fi = Image.new("RGBA", (240 * 2, H * 2), (0, 0, 0, 0))
            rng = np.random.default_rng(7)
            ys = np.arange(0, H, 3)
            pts = [((120 + st["px"][y] - st["band"][y] * 0.3) * 2, y * 2) for y in ys]
            fibre_lines(ImageDraw.Draw(fi), pts, [(-1, 0)] * len(pts), rng, (255, 254, 250, 200), k=2, density=0.42, length=(3, 11))
            st["fib"] = f32(np.asarray(fi.resize((240, H), Image.LANCZOS)))
    tear = c.p["tear_at"] if c.p.get("tear_at") is not None else clamp(d * 0.42, min(0.8, d * 0.4), max(0.8, d - 1.0))
    arrive = min(0.38, d * 0.16)
    base = f32(np.asarray(c.img))
    # 1) the sheet drops in from the top
    pa = prog(u, 0, arrive)
    ea = back(pa, 0.8)
    close = bool(c.p.get("close"))
    t_back = d - 1.0 if close else None
    # while it's whole, the sheet creeps toward you a little
    zs = 1 + 0.03 * ease_io(prog(min(u, tear), arrive, max(0.1, tear - arrive)))
    if u < tear:
        dy = lerp(-H * 1.08, 0, ea); rot = lerp(-4.0, 0, ease_out(pa))
        if pa >= 1: return to_pil(_over(base, _xform(st["full"], 0, 0, 0, W / 2, H / 2, zs), shadow=0))
        return to_pil(_over(base, _xform(st["full"], 0, dy, rot, W / 2, 0)))
    # the end of a closing tear: the sheet whips down and away
    if close and u > d - 0.34:
        po = ease_in(prog(u, d - 0.34, 0.34))
        return to_pil(_over(base, _xform(st["full"], 0, po * H * 1.1, po * 5, W / 2, H, zs)))
    if c.p["mode"] == "split":
        # 2) rip: the halves pull apart, then fall away (top flies up-left, bottom drops)
        # the halves need about 1.1 s to clear the frame: speed up when the window leaves less
        spd = max(1.0, 1.1 / max(0.3, (t_back if close else d) - tear))
        T = (u - tear) * spd
        if close and u > t_back:
            T = max(0.0, (d - 0.34) - u) * 1.35          # the same motion backwards: the halves come back and join
        if T > 1.4 and not close: return c.img
        crack = clamp01(T / 0.14)
        g = 5200.0
        Tt = max(0.0, T - 0.1)
        top_dy = -(160 * Tt + 0.5 * g * Tt * Tt) - 6 * crack
        top_dx = -60 * Tt
        top_rot = -(9 * clamp01(Tt / 0.5) + 6 * Tt)
        Tb = max(0.0, T - 0.16)
        bot_dy = 40 * Tb + 0.5 * g * 0.9 * Tb * Tb + 6 * crack
        bot_dx = 30 * Tb
        bot_rot = 7 * clamp01(Tb / 0.5) + 5 * Tb
        py = st["py"]
        left_y, right_y = float(py[MG]) - MG, float(py[MG + W - 1]) - MG
        out = base
        pb = _xform(st["bot"], bot_dx, bot_dy, bot_rot, W, right_y, zs)
        pt = _xform(st["top"], top_dx, top_dy, top_rot, 0, left_y, zs)
        out = _over(out, pb, shadow=0.38 * clamp01(T / 0.2))
        out = _over(out, pt, shadow=0.42 * clamp01(T / 0.2))
        return to_pil(out)
    # sweep: a torn edge runs across the sheet left to right, revealing the video
    T = u - tear
    dur = min(0.75, max(0.4, d * 0.22))
    if close and u > t_back:
        p = 1 - ease_io(prog(u, t_back, d - 0.34 - t_back))
    else:
        p = ease_io(clamp01(T / dur))
    if p >= 1 and not close: return c.img
    xe = lerp(-260, W + 260, p)
    yy, xx = grid(H, W)
    D = xx - (xe + st["px"][:, None])
    a = np.clip(0.5 + D, 0, 1)
    band = st["band"][:, None]
    strip = np.clip(0.5 + (band - D), 0, 1) * a
    if "sheet_z" not in st:     # the sheet as it was when it tore (crept in by zs)
        cx_, cy_ = MG + W / 2, MG + H / 2
        bx = (cx_ - W / 2 / zs, cy_ - H / 2 / zs, cx_ + W / 2 / zs, cy_ + H / 2 / zs)
        st["sheet_z"] = np.asarray(Image.fromarray(st["sheet"].astype(np.uint8), "RGB").resize((W, H), Image.BICUBIC, box=bx), np.float32)
    sheet = st["sheet_z"]
    core = np.array([253, 252, 249], np.float32)
    lift = np.clip(1 - (D - band) / 40, 0, 1) * (D > band) * 0.07
    col = sheet * (1 - lift[..., None])
    col = col * (1 - strip[..., None]) + core * strip[..., None]
    shadow = np.clip(1 + (D + 2) / 34, 0, 1) ** 2 * (D < 0) * 0.5
    out = base * (1 - shadow[..., None])
    out = out * (1 - a[..., None]) + col * a[..., None]
    # fibres along the edge
    fx0 = int(round(xe - 120))
    fb = st["fib"]
    x0, x1 = max(0, fx0), min(W, fx0 + fb.shape[1])
    if x1 > x0:
        seg = fb[:, x0 - fx0:x1 - fx0]
        fa = seg[..., 3:4] / 255.0
        out[:, x0:x1] = out[:, x0:x1] * (1 - fa) + seg[..., :3] * fa
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your own; the small line is your sentence",
}
