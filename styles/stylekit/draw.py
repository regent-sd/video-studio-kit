"""Pillow drawing for the styles: easing, fonts (variable system fonts get their weight), shapes drawn at 2x for
smooth edges, text images, compositing, flat cards placed in 3D with a soft shadow, pills, icons, contact sheets."""
from __future__ import annotations

import functools
import math

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1920
SFP = "/System/Library/Fonts/SFNS.ttf"


# ---------------------------------------------------------------- easing
def clamp01(x): return 0.0 if x < 0 else 1.0 if x > 1 else x
def prog(t, t0, d): return clamp01((t - t0) / d) if d > 0 else float(t >= t0)
def ease_out(x): x = clamp01(x); return 1 - (1 - x) ** 3
def ease_in(x): x = clamp01(x); return x ** 3
def ease_io(x): x = clamp01(x); return x * x * (3 - 2 * x)
def lerp(a, b, u): return a + (b - a) * u
def lerpc(a, b, u): return tuple(int(round(lerp(x, y, u))) for x, y in zip(a, b))
def decay(t, t0, k=6.0): return math.exp(-(t - t0) * k) if t >= t0 else 0.0


def back(x, s=1.9):
    """Ease out with a small overshoot (pop-ins)."""
    x = clamp01(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2


# ---------------------------------------------------------------- fonts
@functools.lru_cache(None)
def font(size, weight=700, path=SFP, index=0, width=100):
    """A font at a size. Variable fonts (SF Pro, New York...) are set to the weight; others ignore it."""
    f = ImageFont.truetype(path, max(4, int(size)), index=index)
    try:
        axes = f.get_variation_axes()
    except Exception:
        axes = None
    if axes:
        vals = []
        for a in axes:
            nm = str(a.get("name", b"")).lower()
            lo, hi = a.get("minimum", 0), a.get("maximum", 1000)
            if "weight" in nm or "wght" in nm:
                v = weight
            elif "width" in nm or "wdth" in nm:
                v = width
            elif "optical" in nm or "opsz" in nm:
                v = size * 0.6
            else:
                v = a.get("default", lo)
            vals.append(max(lo, min(hi, v)))
        try:
            f.set_variation_by_axes(vals)
        except Exception:
            pass
    return f


def F(spec, size, weight=None):
    """font() from a (path, index, weight) spec, as the skins keep them."""
    path, index, wt = spec
    return font(size, weight or wt, path, index)


class SS:
    """Draw at 2x, then downscale: Pillow shapes have no antialiasing otherwise."""

    def __init__(self, w, h, k=2, bg=(0, 0, 0, 0)):
        self.w, self.h, self.k = int(w), int(h), k
        self.im = Image.new("RGBA", (self.w * k, self.h * k), bg)
        self.d = ImageDraw.Draw(self.im)
        self._bg = bg

    def _b(self, box):
        x0, y0, x1, y1 = box
        if x1 < x0: x0, x1 = x1, x0
        if y1 < y0: y0, y1 = y1, y0
        return [x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k]

    def rr(self, box, r, fill=None, outline=None, width=1):
        b = self._b(box)
        if b[2] - b[0] < 1 or b[3] - b[1] < 1:
            return
        r = min(r * self.k, (b[2] - b[0]) / 2, (b[3] - b[1]) / 2)
        self.d.rounded_rectangle(b, radius=r, fill=fill, outline=outline, width=int(width * self.k))

    def ell(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self._b(box), fill=fill, outline=outline, width=int(width * self.k))

    def circ(self, cx, cy, r, **kw):
        self.ell((cx - r, cy - r, cx + r, cy + r), **kw)

    def poly(self, pts, fill):
        self.d.polygon([(x * self.k, y * self.k) for x, y in pts], fill=fill)

    def line(self, pts, fill, width):
        self.d.line([(x * self.k, y * self.k) for x, y in pts], fill=fill, width=int(width * self.k), joint="curve")
        r = width * self.k / 2
        for x, y in (pts[0], pts[-1]):
            self.d.ellipse([x * self.k - r, y * self.k - r, x * self.k + r, y * self.k + r], fill=fill)

    def arc(self, box, a0, a1, fill, width):
        self.d.arc(self._b(box), a0, a1, fill=fill, width=int(width * self.k))

    def text(self, xy, txt, spec, size, fill, anchor="la", weight=None):
        self.d.text((xy[0] * self.k, xy[1] * self.k), txt, font=F(spec, size * self.k, weight), fill=fill, anchor=anchor)

    def textlen(self, txt, spec, size, weight=None):
        return F(spec, size * self.k, weight).getlength(txt) / self.k

    def out(self):
        return self.im.resize((self.w, self.h), Image.LANCZOS)


@functools.lru_cache(512)
def text_img(txt, spec, size, fill=(255, 255, 255), track=0, weight=None):
    """A line of text as a tight RGBA image. spec: (path, index, weight)."""
    f = F(spec, size, weight)
    if track:
        ws = [f.getlength(c) for c in txt]
        tw = sum(ws) + track * (len(txt) - 1)
    else:
        tw = f.getlength(txt)
    asc, desc = f.getmetrics()
    im = Image.new("RGBA", (int(tw) + 8, asc + desc + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if track:
        x = 4
        for c, w_ in zip(txt, ws):
            d.text((x, 4), c, font=f, fill=fill)
            x += w_ + track
    else:
        d.text((4, 4), txt, font=f, fill=fill)
    return im.crop(im.getbbox() or (0, 0, 1, 1))


def fit_text(txt, spec, size, fill, max_w, track=0, weight=None):
    """text_img, shrunk until it fits max_w."""
    im = text_img(txt, spec, size, fill, track, weight)
    while im.width > max_w and size > 12:
        size = int(size * 0.92)
        im = text_img(txt, spec, size, fill, track, weight)
    return im


def with_alpha(im, a):
    if a >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return im


def scaled(im, s):
    if abs(s - 1) < 1e-3:
        return im
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)


def comp(cv, im, x, y):
    """Alpha-composite im onto cv at (x, y), clipped to the canvas."""
    x, y = int(round(x)), int(round(y))
    w, h = im.size
    ax0, ay0, ax1, ay1 = max(0, x), max(0, y), min(cv.width, x + w), min(cv.height, y + h)
    if ax1 <= ax0 or ay1 <= ay0:
        return
    if (ax0, ay0, ax1, ay1) != (x, y, x + w, y + h):
        im = im.crop((ax0 - x, ay0 - y, ax1 - x, ay1 - y))
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    cv.alpha_composite(im, (ax0, ay0))


def comp_c(cv, im, cx, cy, s=1.0, a=1.0):
    im = with_alpha(scaled(im, s), a)
    comp(cv, im, cx - im.width / 2, cy - im.height / 2)


def _coeffs(dst, src):
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def place(cv, im, cx, cy, s=1.0, ry=0.0, rx=0.0, rz=0.0, shadow=0.3, a=1.0, f=2200.0):
    """Draw a flat card in 3D: rotate (degrees) about its centre, perspective-project, soft shadow below."""
    if a <= 0.003 or s <= 0.01:
        return
    w, h = im.size
    ry, rx, rz = math.radians(ry), math.radians(rx), math.radians(rz)
    dst = []
    for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        x, y = x * s, y * s
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
        X, Z = x * math.cos(ry), -x * math.sin(ry)
        Y, Z = y * math.cos(rx) - Z * math.sin(rx), y * math.sin(rx) + Z * math.cos(rx)
        k = f / (f + Z)
        dst.append((cx + X * k, cy + Y * k))
    xs, ys = [p[0] for p in dst], [p[1] for p in dst]
    x0, y0 = int(math.floor(min(xs))) - 2, int(math.floor(min(ys))) - 2
    x1, y1 = int(math.ceil(max(xs))) + 2, int(math.ceil(max(ys))) + 2
    vx0, vy0, vx1, vy1 = max(x0, -60), max(y0, -60), min(x1, cv.width + 60), min(y1, cv.height + 60)
    if vx1 <= vx0 or vy1 <= vy0:
        return
    co = _coeffs([(x - vx0, y - vy0) for x, y in dst], [(0, 0), (w, 0), (w, h), (0, h)])
    warped = im.convert("RGBa").transform((vx1 - vx0, vy1 - vy0), Image.PERSPECTIVE, co, Image.BICUBIC).convert("RGBA")
    if a < 0.999:
        warped = with_alpha(warped, a)
    if shadow > 0:
        pad, q = 100, 4
        al = warped.getchannel("A")
        sm = Image.new("L", ((warped.width + 2 * pad) // q, (warped.height + 2 * pad) // q), 0)
        sm.paste(al.resize((max(1, warped.width // q), max(1, warped.height // q)), Image.BILINEAR), (pad // q, pad // q))
        sm = sm.filter(ImageFilter.GaussianBlur(10)).resize((warped.width + 2 * pad, warped.height + 2 * pad), Image.BILINEAR)
        sm = sm.point(lambda v: int(v * shadow))
        sh = Image.new("RGBA", sm.size, (0, 0, 0, 0))
        sh.putalpha(sm)
        comp(cv, sh, vx0 - pad, vy0 - pad + int(34 * s))
    comp(cv, warped, vx0, vy0)


def radial(w, h, cin, cout, cx=0.5, cy=0.42, r=1.0):
    """A soft radial gradient background."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x - cx * w) / w) ** 2 + ((y - cy * h) / w) ** 2) / r
    d = np.clip(d, 0, 1) ** 1.4
    a = np.array(cin, np.float32)
    b = np.array(cout, np.float32)
    img = a[None, None, :] * (1 - d[..., None]) + b[None, None, :] * d[..., None]
    return Image.fromarray(img.astype(np.uint8), "RGB").convert("RGBA")


def vgrad(w, h, a0, a1, y0, y1, color=(0, 0, 0)):
    """Vertical alpha ramp from a0 at y0 to a1 at y1 (a shade behind text on footage)."""
    y = np.arange(h, dtype=np.float32)
    a = np.clip((y - y0) / max(1, (y1 - y0)), 0, 1)
    a = (a0 + (a1 - a0) * a).astype(np.uint8)
    im = Image.new("RGBA", (w, h), tuple(color) + (0,))
    im.putalpha(Image.fromarray(np.repeat(a[:, None], w, axis=1), "L"))
    return im


def rounded(im, r):
    m = SS(im.width, im.height)
    m.rr((0, 0, im.width, im.height), r, fill=(255, 255, 255, 255))
    out = im.convert("RGBA")
    out.putalpha(m.out().getchannel("A"))
    return out


def soft_shadow(im, blur=3, a1=0.55, blur2=16, a2=0.5):
    """A soft dark glow behind light text on footage."""
    al = im.getchannel("A")
    s1 = al.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * a1))
    s2 = al.filter(ImageFilter.GaussianBlur(blur2)).point(lambda v: int(v * a2))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    sh.putalpha(ImageChops.lighter(s1, s2))
    sh.alpha_composite(im)
    return sh


def pill(c: SS, cx, cy, txt, spec, size, bg, fg, s=1.0, padx=26, weight=None):
    """A rounded label with text, scaled by s (0..1+, for pop-ins)."""
    if s <= 0.02:
        return
    tw = c.textlen(txt, spec, size * s, weight)
    pw, ph = tw + 2 * padx * s, size * 1.55 * s
    c.rr((cx - pw / 2, cy - ph / 2, cx + pw / 2, cy + ph / 2), ph / 2, fill=bg)
    c.text((cx, cy + size * 0.02 * s), txt, spec, size * s, fg, anchor="mm", weight=weight)


def check(c: SS, cx, cy, r, bg, fg, s=1.0):
    if s <= 0.02:
        return
    c.circ(cx, cy, r * s, fill=bg)
    c.line([(cx - r * .42 * s, cy + r * .02 * s), (cx - r * .1 * s, cy + r * .34 * s), (cx + r * .45 * s, cy - r * .3 * s)], fg, r * .2 * s)


def cross(c: SS, cx, cy, r, bg, fg, s=1.0):
    if s <= 0.02:
        return
    c.circ(cx, cy, r * s, fill=bg)
    k = r * 0.36 * s
    c.line([(cx - k, cy - k), (cx + k, cy + k)], fg, r * .18 * s)
    c.line([(cx - k, cy + k), (cx + k, cy - k)], fg, r * .18 * s)


def ring(r, frac, width, track_col, col):
    size = int(2 * r + width + 8)
    c = SS(size, size)
    m = size / 2
    c.ell((m - r, m - r, m + r, m + r), outline=track_col, width=width)
    if frac > 0.002:
        c.arc((m - r, m - r, m + r, m + r), -90, -90 + 360 * frac, col, width)
    return c.out()


# ---------------------------------------------------------------- contact sheets
def label(im, txt, size=44):
    im = im.convert("RGB")
    d = ImageDraw.Draw(im)
    f = font(size, 700)
    w = f.getlength(txt) + 24
    d.rectangle([0, 0, w, size + 22], fill=(0, 0, 0))
    d.text((12, 8), txt, font=f, fill=(255, 90, 90))
    return im


def contact_sheet(frames, cols=8, tile=(270, 480), title=None, bg=(40, 40, 40)):
    """Frames (PIL, 9:16) side by side in rows, with an optional title bar."""
    cols = max(1, min(cols, len(frames)))
    rows = (len(frames) + cols - 1) // cols
    top = 70 if title else 0
    sh = Image.new("RGB", (cols * tile[0], rows * tile[1] + top), bg)
    if title:
        ImageDraw.Draw(sh).text((16, 14), title, font=font(40, 700), fill=(235, 235, 235))
    for k, im in enumerate(frames):
        sh.paste(im.convert("RGB").resize(tile, Image.LANCZOS), ((k % cols) * tile[0], top + (k // cols) * tile[1]))
    return sh
