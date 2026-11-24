#!/usr/bin/env python3
"""Effects library engine (see effects/README.md). Any video in, the same video out with effects on chosen stretches.

1. prep()   turns a source stretch into a "subject" (cached in effects/cache/<key>/):
              base.mp4    1080x1920 30 fps (a horizontal source is cropped 9:16 around the face)
              mask.mkv    a person cutout on every frame (Apple Vision, bin/track)
              faces.json  the face box on every frame, smoothed
              words.json  word timings (the Footage Log transcript if there is one, else whisper.cpp)
              audio.wav   the sound, untouched
2. render() runs frame by frame: each effect gets a Ctx (frame, cutout, face, words, time in its window)
   and returns the new frame. The rest of the video passes through. The sound is the source's.

Effects live in effects/catalog/<name>.py: NAME, KIND, ABOUT, DUR, PARAMS and render(c). See catalog/spotlight.py.
Skins: "dark" (neutral dark panels, white cards, yellow keywords) or "brand" (colours and fonts from a brand's brand.json).
"""
import os, sys, json, math, hashlib, functools, subprocess, re, shutil, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)                       # the kit's root folder
sys.path.insert(0, os.path.join(STUDIO, "lib"))
import studio_config as sc                           # noqa: E402  paths, brands, fonts (lib/studio_config.py)

def _content_root():
    try:
        return str(sc.content_root())
    except Exception:
        return ""

CONTENT = _content_root()                            # the shoots folder (studio.json: content_root)
CACHE = os.environ.get("EFFECTS_CACHE") or os.path.join(HERE, "cache")   # prepped stretches, safe to delete
BIN = os.path.join(HERE, "cache", "bin")             # helpers built on this Mac by effects/build_helpers.sh
TRACK = os.environ.get("EFFECTS_TRACK") or os.path.join(BIN, "track")
WHISPER_MODEL = os.path.expanduser(sc.get("whisper_model") or "~/.cache/whisper.cpp/ggml-base.en.bin")
# every `fx.py apply` export is logged here, so the video tracker can say which raw seconds a test used
APPLIED_LOG = (os.path.join(CONTENT, "Footage Log", "effects-applied.json") if CONTENT and os.path.isdir(CONTENT)
               else os.path.join(CACHE, "applied.json"))
W, H, FPS, SR = 1080, 1920, 30, 48000

GRADES = {  # a light grade for camera originals (the style builders use the same strings)
    "none": "",
    "camera": "eq=contrast=1.08:saturation=1.14:gamma=1.03,unsharp=5:5:0.5",   # a main camera (flat-ish colour)
    "pov": "eq=contrast=1.05:saturation=1.06,unsharp=5:5:0.3",                 # glasses or a head-mounted camera
}
GRADE_ALIASES = {"main": "camera", "osmo": "camera", "glasses": "pov"}

def grade_filter(name):
    """The ffmpeg filter for a grade name ('' for none)."""
    return GRADES.get(GRADE_ALIASES.get(name, name), "")

def ensure_helpers():
    """Build bin/track (Apple Vision) the first time it's needed. setup runs effects/build_helpers.sh too."""
    if os.path.exists(TRACK):
        return TRACK
    sh = os.path.join(HERE, "build_helpers.sh")
    log("effects: building the person tracker (one time, about a minute)...")
    r = subprocess.run(["/bin/sh", sh], capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(TRACK):
        raise RuntimeError("couldn't build effects/cache/bin/track. Run `sh effects/build_helpers.sh` and read what it says "
                           "(it needs the Xcode command line tools: `xcode-select --install`).\n" + r.stderr[-1500:])
    return TRACK

# ------------------------------------------------------------------ small helpers
def log(*a):
    print(*a, file=sys.stderr, flush=True)

def run(cmd, **kw):
    cmd = [str(c) for c in cmd]
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd[:6])} ...\n{r.stderr[-2000:]}")
    return r.stdout

def clamp(v, a, b): return a if v < a else b if v > b else v
def clamp01(x): return 0.0 if x < 0 else 1.0 if x > 1 else x
def prog(t, t0, d): return clamp01((t - t0) / d) if d > 0 else float(t >= t0)
def ease_out(x): x = clamp01(x); return 1 - (1 - x) ** 3
def ease_in(x): x = clamp01(x); return x ** 3
def ease_io(x): x = clamp01(x); return x * x * (3 - 2 * x)
def back(x, s=1.9):
    x = clamp01(x) - 1
    return 1 + (s + 1) * x ** 3 + s * x ** 2
def lerp(a, b, u): return a + (b - a) * u
def lerpc(a, b, u): return tuple(int(round(lerp(x, y, u))) for x, y in zip(a, b))
def decay(t, t0, k=6.0): return math.exp(-(t - t0) * k) if t >= t0 else 0.0
def hexc(s):
    """'#ffd60a' or (255, 214, 10) -> (255, 214, 10)."""
    if isinstance(s, (tuple, list)): return tuple(int(v) for v in s[:3])
    s = s.lstrip("#"); return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
def norm_word(s): return re.sub(r"[^a-z0-9']", "", s.lower())

# ------------------------------------------------------------------ fonts
SFP = "/System/Library/Fonts/SFNS.ttf"
SFMONO = "/System/Library/Fonts/SFNSMono.ttf"
SFROUND = "/System/Library/Fonts/SFNSRounded.ttf"
NEWYORK = "/System/Library/Fonts/NewYork.ttf"
NEWYORK_IT = "/System/Library/Fonts/NewYorkItalic.ttf"
SUPP = "/System/Library/Fonts/Supplemental"
GEORGIA = os.path.join(SUPP, "Georgia.ttf"); GEORGIA_B = os.path.join(SUPP, "Georgia Bold.ttf")
DIDOT = os.path.join(SUPP, "Didot.ttc"); BODONI = os.path.join(SUPP, "Bodoni 72.ttc")
BASKERVILLE = os.path.join(SUPP, "Baskerville.ttc"); TYPEWRITER = os.path.join(SUPP, "AmericanTypewriter.ttc")
HAND = os.path.join(SUPP, "Bradley Hand Bold.ttf"); CHALK = os.path.join(SUPP, "Chalkduster.ttf")
MENLO = "/System/Library/Fonts/Menlo.ttc"
AVENIR_NEXT = "/System/Library/Fonts/Avenir Next.ttc"          # index 0 Bold, 2 Demi Bold, 5 Medium, 8 Heavy
AVENIR_NEXT_COND = "/System/Library/Fonts/Avenir Next Condensed.ttc"
VARIABLE = {SFP, SFROUND, SFMONO, NEWYORK, NEWYORK_IT}

@functools.lru_cache(None)
def font(size, weight=700, path=SFP, index=0, width=100):
    """A font at a size. SF Pro / SF Mono / New York are variable: weight 100-1000 works."""
    f = ImageFont.truetype(path, max(4, int(round(size))), index=index)
    if path in VARIABLE:
        try:
            axes = f.get_variation_axes()
            vals = []
            for ax in axes:
                nm = ax.get("name", b"")
                nm = nm.decode() if isinstance(nm, bytes) else str(nm)
                if "eight" in nm: vals.append(clamp(weight, ax["minimum"], ax["maximum"]))
                elif "idth" in nm: vals.append(clamp(width, ax["minimum"], ax["maximum"]))
                elif "ptical" in nm: vals.append(clamp(size * 0.6, ax["minimum"], ax["maximum"]))
                else: vals.append(ax.get("default", ax["minimum"]))
            f.set_variation_by_axes(vals)
        except Exception:
            pass
    return f

# ------------------------------------------------------------------ skins
# A skin is the colours and fonts an effect draws with. Each font role is (file, index, weight); the weight only
# matters for the variable system fonts (SF Pro, SF Mono, SF Rounded, New York).
SKINS = {
    # Dark: neutral dark panels, white cards and text, yellow keywords. Works for any video without a brand.
    "dark": dict(
        name="dark", light=(252, 252, 250), light2=(234, 233, 229), dark=(14, 15, 18), dark2=(30, 32, 38),
        ink=(17, 17, 19), paper=(255, 255, 255), card=(255, 255, 255), card_dark=(24, 26, 31),
        muted=(138, 138, 146), line=(232, 232, 236), accent=(255, 214, 10), accent_ink=(17, 17, 19),
        good=(40, 190, 105), bad=(255, 59, 48), blue=(10, 132, 255), orange=(255, 149, 0), highlight=(255, 214, 10),
        on_dark=(255, 255, 255),
        title=(SFP, 0, 880), heading=(SFP, 0, 760), body=(SFP, 0, 600), num=(SFP, 0, 860), mono=(SFMONO, 0, 600),
        serif=(NEWYORK, 0, 700), caption=(SFP, 0, 800), restrained=False),
}
SKIN_NAMES = ["dark", "brand"]

def _mixc(a, b, u):
    return tuple(int(round(x + (y - x) * u)) for x, y in zip(a, b))

def _lum(c):
    r, g, b = [v / 255 for v in c[:3]]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def brand_skin(b=None):
    """The Brand skin: colours and fonts from a brand's brand.json (lib/studio_config.py). b: a slug, a brand dict, or
    None for the default brand."""
    if not isinstance(b, dict):
        b = sc.brand(b)
    col = lambda role: tuple(sc.color(b, role))
    bg, text, acc = col("background"), col("text"), col("accent")
    on_dark = col("on_dark")
    acc_ink = text if _lum(acc) > 0.55 else on_dark          # words on an accent fill stay readable
    def f(role, weight):
        path, index = sc.font(b, role)
        return (path, index, weight)
    title = f("title", 880)
    return dict(
        name="brand", brand=b.get("slug", ""), light=bg, light2=_mixc(bg, text, 0.07), dark=col("dark"),
        dark2=col("dark_surface"), ink=text, paper=bg, card=col("surface"), card_dark=col("dark_surface"),
        muted=col("muted"), line=_mixc(bg, text, 0.1), accent=acc, accent_ink=acc_ink, good=col("good"), bad=col("bad"),
        blue=text if _lum(text) < 0.35 else acc, orange=_mixc(acc, col("highlight"), 0.5), highlight=col("highlight"),
        on_dark=on_dark,
        title=title, heading=f("heading", 760), body=f("body", 600), num=f("number", 860), mono=(SFMONO, 0, 600),
        serif=title, caption=f("caption", 800),
        restrained=bool((b.get("effects") or {}).get("restrained")),
        never_background=list(b.get("never_use_as_background") or []))

class Skin(dict):
    __getattr__ = dict.__getitem__
    def font(self, role, size, weight=None):
        path, index, wt = self[role]
        return font(size, weight or wt, path, index)
    def fontspec(self, role, weight=None):
        path, index, wt = self[role]
        return dict(path=path, index=index, weight=weight or wt)

def skin(name="dark", brand=None):
    """A Skin. name: "dark"; "brand" (the brand named by `brand`, else the default brand); "brand:<slug>"; a brand's
    slug; or a brand dict from studio_config.brand(). Anything else gets the Dark skin."""
    if isinstance(name, Skin):
        return name
    if isinstance(name, dict):
        return Skin(brand_skin(name))
    name = (name or "dark").strip()
    if name.startswith("brand:"):
        brand, name = name.split(":", 1)[1] or brand, "brand"
    if name == "brand":
        return Skin(brand_skin(brand))
    if name in SKINS:
        return Skin(SKINS[name])
    try:
        if name in sc.list_brands():
            return Skin(brand_skin(name))
    except Exception:
        pass
    return Skin(SKINS["dark"])

# ------------------------------------------------------------------ drawing
class SS:
    """Draw at 2x, then downscale: PIL shapes have no antialiasing otherwise."""
    def __init__(self, w, h, k=2, bg=(0, 0, 0, 0)):
        self.w, self.h, self.k = int(w), int(h), k
        self.im = Image.new("RGBA", (self.w * k, self.h * k), bg)
        self.d = ImageDraw.Draw(self.im)
    def _b(self, box):
        x0, y0, x1, y1 = box
        if x1 < x0: x0, x1 = x1, x0
        if y1 < y0: y0, y1 = y1, y0
        return [x0 * self.k, y0 * self.k, x1 * self.k, y1 * self.k]
    def rr(self, box, r, fill=None, outline=None, width=1):
        b = self._b(box)
        if b[2] - b[0] < 1 or b[3] - b[1] < 1: return
        r = min(r * self.k, (b[2] - b[0]) / 2, (b[3] - b[1]) / 2)
        self.d.rounded_rectangle(b, radius=r, fill=fill, outline=outline, width=max(1, int(width * self.k)) if outline else 0)
    def rect(self, box, fill=None, outline=None, width=1):
        self.d.rectangle(self._b(box), fill=fill, outline=outline, width=max(1, int(width * self.k)))
    def ell(self, box, fill=None, outline=None, width=1):
        self.d.ellipse(self._b(box), fill=fill, outline=outline, width=max(1, int(width * self.k)))
    def circ(self, cx, cy, r, **kw): self.ell((cx - r, cy - r, cx + r, cy + r), **kw)
    def poly(self, pts, fill=None, outline=None): self.d.polygon([(x * self.k, y * self.k) for x, y in pts], fill=fill, outline=outline)
    def line(self, pts, fill, width, round_caps=True):
        self.d.line([(x * self.k, y * self.k) for x, y in pts], fill=fill, width=max(1, int(width * self.k)), joint="curve")
        if round_caps:
            r = width * self.k / 2
            for x, y in (pts[0], pts[-1]):
                self.d.ellipse([x * self.k - r, y * self.k - r, x * self.k + r, y * self.k + r], fill=fill)
    def arc(self, box, a0, a1, fill, width): self.d.arc(self._b(box), a0, a1, fill=fill, width=max(1, int(width * self.k)))
    def pie(self, box, a0, a1, fill): self.d.pieslice(self._b(box), a0, a1, fill=fill)
    def text(self, xy, txt, size, weight=700, fill=(17, 17, 19), anchor="la", path=SFP, index=0):
        self.d.text((xy[0] * self.k, xy[1] * self.k), txt, font=font(size * self.k, weight, path, index), fill=fill, anchor=anchor)
    def textlen(self, txt, size, weight=700, path=SFP, index=0):
        return font(size * self.k, weight, path, index).getlength(txt) / self.k
    def paste(self, im, x, y):
        im = im.resize((int(im.width * self.k), int(im.height * self.k)), Image.LANCZOS) if self.k != 1 else im
        self.im.alpha_composite(im.convert("RGBA"), (int(x * self.k), int(y * self.k)))
    def out(self): return self.im.resize((self.w, self.h), Image.LANCZOS)

@functools.lru_cache(512)
def text_img(txt, size, weight=800, fill=(255, 255, 255), track=0, path=SFP, index=0, stroke=0, stroke_fill=(0, 0, 0)):
    """Tight RGBA image of one line of text (stroke: outline width in px)."""
    f = font(size, weight, path, index)
    if " " in txt and f.getlength(" ") < size * 0.26:   # some display fonts have hairline spaces
        track = track or -0.0001
    ws = [max(f.getlength(ch), size * 0.34) if ch == " " and f.getlength(" ") < size * 0.26 else f.getlength(ch) for ch in txt] if track else None
    tw = (sum(ws) + track * (len(txt) - 1)) if track else f.getlength(txt)
    asc, desc = f.getmetrics()
    p = 8 + stroke
    im = Image.new("RGBA", (int(tw) + 2 * p, asc + desc + 2 * p), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    kw = dict(stroke_width=stroke, stroke_fill=stroke_fill) if stroke else {}
    if track:
        x = p
        for ch, w_ in zip(txt, ws):
            d.text((x, p), ch, font=f, fill=fill, **kw); x += w_ + track
    else:
        d.text((p, p), txt, font=f, fill=fill, **kw)
    return im.crop(im.getbbox() or (0, 0, 1, 1))

def with_alpha(im, a):
    if a >= 0.999: return im
    im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a)))); return im

def scaled(im, s):
    if abs(s - 1) < 1e-3: return im
    return im.resize((max(1, int(round(im.width * s))), max(1, int(round(im.height * s)))), Image.BICUBIC)

def comp(cv, im, x, y):
    """Alpha-composite im onto cv (both RGBA) at x, y, clipped to the canvas."""
    x, y = int(round(x)), int(round(y))
    w, h = im.size
    ax0, ay0, ax1, ay1 = max(0, x), max(0, y), min(cv.width, x + w), min(cv.height, y + h)
    if ax1 <= ax0 or ay1 <= ay0: return
    if (ax0, ay0, ax1, ay1) != (x, y, x + w, y + h):
        im = im.crop((ax0 - x, ay0 - y, ax1 - x, ay1 - y))
    cv.alpha_composite(im, (ax0, ay0))

def comp_c(cv, im, cx, cy, s=1.0, a=1.0, rot=0.0):
    im = scaled(im, s)
    if rot: im = im.rotate(rot, Image.BICUBIC, expand=True)
    im = with_alpha(im, a)
    comp(cv, im, cx - im.width / 2, cy - im.height / 2)

def _coeffs(dst, src):
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()

def project(w, h, cx, cy, s=1.0, ry=0.0, rx=0.0, rz=0.0, f=2200.0, z=0.0):
    """Screen corners of a w x h card rotated (degrees) about its centre and pushed back by z."""
    ry, rx, rz = math.radians(ry), math.radians(rx), math.radians(rz)
    pts = []
    for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        x, y = x * s, y * s
        x, y = x * math.cos(rz) - y * math.sin(rz), x * math.sin(rz) + y * math.cos(rz)
        X, Z = x * math.cos(ry), -x * math.sin(ry)
        Y, Z = y * math.cos(rx) - Z * math.sin(rx), y * math.sin(rx) + Z * math.cos(rx)
        k = f / (f + Z + z)
        pts.append((cx + X * k, cy + Y * k))
    return pts

def warp_to(cv, im, dst, a=1.0, shadow=0.0, shadow_dy=34):
    """Draw im (RGBA) with its corners at dst (TL, TR, BR, BL) on cv."""
    w, h = im.size
    xs, ys = [p[0] for p in dst], [p[1] for p in dst]
    x0, y0 = int(math.floor(min(xs))) - 2, int(math.floor(min(ys))) - 2
    x1, y1 = int(math.ceil(max(xs))) + 2, int(math.ceil(max(ys))) + 2
    vx0, vy0, vx1, vy1 = max(x0, -60), max(y0, -60), min(x1, cv.width + 60), min(y1, cv.height + 60)
    if vx1 <= vx0 or vy1 <= vy0: return
    try:
        co = _coeffs([(x - vx0, y - vy0) for x, y in dst], [(0, 0), (w, 0), (w, h), (0, h)])
    except np.linalg.LinAlgError:
        return
    warped = im.convert("RGBa").transform((vx1 - vx0, vy1 - vy0), Image.PERSPECTIVE, co, Image.BICUBIC).convert("RGBA")
    if a < 0.999: warped = with_alpha(warped, a)
    if shadow > 0: comp(cv, soft_shadow(warped, shadow), vx0 - 100, vy0 - 100 + shadow_dy)
    comp(cv, warped, vx0, vy0)

def place(cv, im, cx, cy, s=1.0, ry=0.0, rx=0.0, rz=0.0, shadow=0.3, a=1.0, f=2200.0, z=0.0):
    """Draw a flat card in 3D: rotate (degrees) about its centre, perspective-project, soft shadow."""
    if a <= 0.003 or s <= 0.01: return
    warp_to(cv, im, project(im.width, im.height, cx, cy, s, ry, rx, rz, f, z), a, shadow, int(34 * s))

def soft_shadow(im, strength=0.3, blur=10, pad=100, q=4):
    """A blurred dark copy of im's alpha, padded by pad on every side."""
    al = im.getchannel("A")
    sm = Image.new("L", ((im.width + 2 * pad) // q, (im.height + 2 * pad) // q), 0)
    sm.paste(al.resize((max(1, im.width // q), max(1, im.height // q)), Image.BILINEAR), (pad // q, pad // q))
    sm = sm.filter(ImageFilter.GaussianBlur(blur)).resize((im.width + 2 * pad, im.height + 2 * pad), Image.BILINEAR)
    sm = sm.point(lambda v: int(v * strength))
    sh = Image.new("RGBA", sm.size, (0, 0, 0, 0)); sh.putalpha(sm)
    return sh

def rounded(im, r):
    m = Image.new("L", (im.width * 2, im.height * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width * 2 - 1, im.height * 2 - 1], radius=r * 2, fill=255)
    m = m.resize(im.size, Image.LANCZOS)
    out = im.convert("RGBA")
    out.putalpha(ImageChops.multiply(out.getchannel("A"), m))
    return out

def radial(w, h, cin, cout, cx=0.5, cy=0.42, r=1.0):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((x - cx * w) / w) ** 2 + ((y - cy * h) / w) ** 2) / r
    d = np.clip(d, 0, 1) ** 1.4
    a = np.array(cin, np.float32); b = np.array(cout, np.float32)
    img = a[None, None, :] * (1 - d[..., None]) + b[None, None, :] * d[..., None]
    return Image.fromarray(img.astype(np.uint8), "RGB").convert("RGBA")

def vgrad(w, h, a0, a1, y0, y1, color=(0, 0, 0)):
    """Vertical alpha ramp from a0 at y0 to a1 at y1 (alphas 0-255)."""
    y = np.arange(h, dtype=np.float32)
    a = np.clip((y - y0) / max(1, (y1 - y0)), 0, 1)
    a = (a0 + (a1 - a0) * a).astype(np.uint8)
    im = Image.new("RGBA", (w, h), tuple(color) + (0,))
    im.putalpha(Image.fromarray(np.repeat(a[:, None], w, axis=1), "L"))
    return im

@functools.lru_cache(8)
def vignette(strength=0.6, r=0.85, cy=0.42):
    """Float32 HxW multiplier: 1 in the middle, darker toward the edges."""
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((x - 0.5 * W) / W) ** 2 + ((y - cy * H) / W) ** 2) / r
    return (1 - strength * np.clip(d, 0, 1.6) ** 2).clip(0, 1).astype(np.float32)

def glass(frame, box, r=36, blur=22, tint=(255, 255, 255), tint_a=0.38, border_a=0.55, shadow=0.22):
    """A frosted-glass panel: the frame behind box, blurred and tinted, with a light border.
    Returns (RGBA panel, x, y) to comp() onto an RGBA canvas. frame: PIL RGB/RGBA (what's behind)."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    pad = blur * 2
    bx0, by0, bx1, by1 = max(0, x0 - pad), max(0, y0 - pad), min(frame.width, x1 + pad), min(frame.height, y1 + pad)
    w, h = x1 - x0, y1 - y0
    region = frame.convert("RGB").crop((bx0, by0, bx1, by1)).filter(ImageFilter.GaussianBlur(blur))
    panel = Image.new("RGB", (w, h), tint)
    panel.paste(region, (bx0 - x0, by0 - y0))
    panel = Image.blend(panel, Image.new("RGB", (w, h), tint), tint_a).convert("RGBA")
    s = SS(w, h)
    s.rr((1, 1, w - 1, h - 1), r, outline=(255, 255, 255, int(255 * border_a)), width=2)
    panel.alpha_composite(s.out())
    return rounded(panel, r), x0, y0

# ------------------------------------------------------------------ numpy <-> PIL
def to_np(im): return np.asarray(im.convert("RGB"), dtype=np.uint8)
def to_pil(a): return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")
def f32(a): return a.astype(np.float32)

def over(base, layer):
    """base: PIL RGB or np; layer: PIL RGBA the size of the frame. Returns np float32 RGB."""
    b = f32(np.asarray(base.convert("RGB")) if isinstance(base, Image.Image) else base)
    L = np.asarray(layer, dtype=np.float32)
    a = L[..., 3:4] / 255.0
    return b * (1 - a) + L[..., :3] * a

def mix(a, b, m):
    """a where m=1, b where m=0 (m: HxW float)."""
    m = m[..., None] if m.ndim == 2 else m
    return f32(a) * m + f32(b) * (1 - m)

# ------------------------------------------------------------------ probing + prep
def probe(src):
    d = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", src]))
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd: rot = int(round(float(sd["rotation"])))
    if "rotate" in v.get("tags", {}): rot = int(v["tags"]["rotate"])
    w, h = int(v["width"]), int(v["height"])
    if abs(rot) % 180 == 90: w, h = h, w
    num, den = (v.get("avg_frame_rate") or "30/1").split("/")
    fps = float(num) / float(den) if float(den) else 30.0
    dur = float(d["format"].get("duration") or v.get("duration") or 0)
    has_audio = any(s["codec_type"] == "audio" for s in d["streams"])
    return dict(w=w, h=h, fps=fps, dur=dur, audio=has_audio, codec=v.get("codec_name"))

def _key(*parts):
    return hashlib.sha1(json.dumps(parts, default=str).encode()).hexdigest()[:12]

def _face_center(src, a, b, info, tmp):
    ensure_helpers()
    """Median face centre (px, upright source) over the stretch, from a 2 fps proxy."""
    proxy = os.path.join(tmp, "proxy.mp4")
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src, "-map", "0:v:0",
         "-vf", "fps=2,scale=-2:540", "-c:v", "libx264", "-crf", "23", "-an", proxy])
    fj = os.path.join(tmp, "proxy_faces.json")
    run([TRACK, proxy, fj])
    fs = [f for f in json.load(open(fj)) if len(f) > 1]
    if not fs: return info["w"] / 2, info["h"] * 0.4, None
    cx = float(np.median([f[1] + f[3] / 2 for f in fs])) * info["w"]
    cy = float(np.median([f[2] + f[4] / 2 for f in fs])) * info["h"]
    fh = float(np.median([f[4] for f in fs])) * info["h"]
    return cx, cy, fh

def _smooth_faces(raw, n):
    """Per-frame [cx, cy, w, h] in output px, gaps filled, jitter smoothed."""
    t = np.full((n, 4), np.nan, np.float32)
    for k, f in enumerate(raw[:n]):
        if len(f) > 1:
            x, y, w, h = f[1:5]
            t[k] = [(x + w / 2) * W, (y + h / 2) * H, w * W, h * H]
    ok = ~np.isnan(t[:, 0])
    if not ok.any():
        return np.tile(np.array([W / 2, H * 0.36, W * 0.3, W * 0.38], np.float32), (n, 1)), False
    idx = np.arange(n)
    for j in range(4):
        t[:, j] = np.interp(idx, idx[ok], t[ok, j])
    k = 9
    pad = np.pad(t, ((k // 2, k // 2), (0, 0)), mode="edge")
    ker = np.ones(k, np.float32) / k
    sm = np.stack([np.convolve(pad[:, j], ker, mode="valid") for j in range(4)], 1)
    return sm.astype(np.float32), True

def _read_words_txt(p):
    out = []
    for row in open(p, errors="replace"):
        m = re.match(r"\s*([\d.]+)-([\d.]+)\s+(.+)", row)
        if m: out.append({"s": float(m[1]), "e": float(m[2]), "w": m[3].strip()})
    return out

def _whisper(wav16, outbase):
    run(["whisper-cli", "-m", WHISPER_MODEL, "-f", wav16, "-l", "en", "-dtw", "base.en", "-nfa", "-ojf", "-of", outbase, "-np"])
    d = json.load(open(outbase + ".json", errors="replace"))
    words = []
    for seg in d.get("transcription", []):
        for tok in seg.get("tokens", []):
            tx = tok["text"]
            if tx.startswith("[") or not tx.strip(): continue
            s = tok.get("t_dtw", -1) / 100
            if s < 0: s = tok["offsets"]["from"] / 1000
            e = tok["offsets"]["to"] / 1000
            if tx.startswith(" ") or not words: words.append({"s": s, "e": e, "w": tx.strip()})
            else: words[-1]["w"] += tx; words[-1]["e"] = e
    words = [w for w in words if not re.fullmatch(r"[\(\[].*[\)\]]", w["w"])]
    for a, b in zip(words, words[1:]):
        a["e"] = min(max(a["e"], a["s"] + 0.08), b["s"], a["s"] + 0.7)
    if words: words[-1]["e"] = min(max(words[-1]["e"], words[-1]["s"] + 0.08), words[-1]["s"] + 0.7)
    return words

def prep(src, start=None, end=None, cx=None, zoom=1.0, grade="none", force=False, words=None, audio=None):
    """Make (or reuse) the subject for src[start:end]. Returns a Subject.
    words: the words said, [{"w", "s", "e"}] in src seconds (builders pass their own; default the clip's
    .words.txt from the Footage Log, else whisper.cpp). audio: a file with src's sound when src has none (a builder's picture-only render)."""
    src = os.path.abspath(src)
    st = os.stat(src)
    info = probe(src)
    a = max(0.0, start or 0.0)
    b = min(end if end is not None else info["dur"], info["dur"])
    if audio:
        audio = os.path.abspath(audio); ast_ = os.stat(audio)
        info["audio"] = True
    akey = (audio, ast_.st_size, int(ast_.st_mtime)) if audio else None
    wkey = hashlib.sha1(json.dumps(words, sort_keys=True).encode()).hexdigest()[:10] if words is not None else None
    key = _key("v2", src, st.st_size, int(st.st_mtime), round(a, 3), round(b, 3), cx, zoom, grade, akey, wkey)
    d = os.path.join(CACHE, key)
    if os.path.exists(os.path.join(d, "meta.json")) and not force:
        return Subject(d)
    os.makedirs(d, exist_ok=True)
    log(f"prep: {os.path.basename(src)} {a:.2f}-{b:.2f}s -> {d}")
    with tempfile.TemporaryDirectory() as tmp:
        sw, sh = info["w"], info["h"]
        aspect = W / H
        vertical = abs(sw / sh - aspect) < 0.02
        crop = None
        if not vertical or zoom > 1.001:
            ch = sh / zoom; cw = ch * aspect
            if cw > sw: cw = sw; ch = cw / aspect
            fcx, fcy, fh = (cx, sh * 0.4, None) if cx is not None else _face_center(src, a, b, info, tmp)
            x = clamp(fcx - cw / 2, 0, sw - cw)
            y = clamp(fcy - ch * 0.38, 0, sh - ch)
            crop = [int(round(cw / 2)) * 2, int(round(ch / 2)) * 2, int(round(x)), int(round(y))]
        vf = []
        if crop: vf.append("crop={}:{}:{}:{}".format(*crop))
        vf += [f"scale={W}:{H}:flags=lanczos", f"fps={FPS}"]
        if grade_filter(grade): vf.append(grade_filter(grade))
        vf += ["setpts=PTS-STARTPTS", "format=yuv420p"]   # first frame at 0, or Apple's reader adds one and the cutout lags a frame
        hw = ["-hwaccel", "videotoolbox"] if info["codec"] in ("hevc", "h264") else []
        base = os.path.join(d, "base.mp4")
        run(["ffmpeg", "-y", "-v", "error"] + hw + ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src, "-map", "0:v:0",
             "-vf", ",".join(vf), "-c:v", "libx264", "-crf", "12", "-preset", "medium", "-an", base])
        if info["audio"]:
            run(["ffmpeg", "-y", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", audio or src, "-map", "0:a:0",
                 "-ac", "2", "-ar", str(SR), "-c:a", "pcm_s16le", os.path.join(d, "audio.wav")])
        n = int(run(["ffprobe", "-v", "error", "-count_packets", "-select_streams", "v:0", "-show_entries",
                     "stream=nb_read_packets", "-of", "csv=p=0", base]).strip())
        # cutout + faces on every frame
        ensure_helpers()
        fj = os.path.join(d, "faces_raw.json")
        tr = subprocess.Popen([TRACK, base, fj, "--mask", str(W), str(H)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        enc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                              "-r", str(FPS), "-i", "-", "-c:v", "ffv1", "-level", "3", os.path.join(d, "mask.mkv")],
                             stdin=tr.stdout, capture_output=True)
        tr.wait()
        if tr.returncode != 0 or enc.returncode != 0:
            raise RuntimeError("tracking failed: " + tr.stderr.read().decode()[-1000:] + enc.stderr.decode()[-1000:])
        raw = json.load(open(fj))
        if len(raw) != n:   # the tracker must see exactly the frames ffmpeg sees, or the cutout drifts
            raise RuntimeError(f"tracker read {len(raw)} frames, ffmpeg {n}: cutout would be out of step")
        faces, found = _smooth_faces(raw, n)
        json.dump([[round(float(v), 1) for v in r] for r in faces], open(os.path.join(d, "faces.json"), "w"))
        # words
        wt = src + ".words.txt"
        if words is not None:
            words = [dict(w=w["w"], s=round(w["s"] - a, 3), e=round(w["e"] - a, 3)) for w in words
                     if w["s"] >= a - 0.05 and w["s"] <= b]
            wsrc = "given"
        elif os.path.exists(wt):
            words = [dict(w, s=round(w["s"] - a, 3), e=round(w["e"] - a, 3)) for w in _read_words_txt(wt)
                     if w["s"] >= a - 0.05 and w["e"] <= b + 0.05]
            wsrc = "transcript"
        elif info["audio"]:
            wav16 = os.path.join(tmp, "a16.wav")
            run(["ffmpeg", "-y", "-v", "error", "-i", os.path.join(d, "audio.wav"), "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav16])
            try:
                words = _whisper(wav16, os.path.join(tmp, "w")); wsrc = "whisper.cpp"
            except Exception as e:
                log(f"prep: no transcript ({e})"); words = []; wsrc = "none"
        else:
            words = []; wsrc = "none"
        json.dump(words, open(os.path.join(d, "words.json"), "w"), indent=0)
        meta = dict(src=src, start=a, end=b, n=n, fps=FPS, w=W, h=H, crop=crop, zoom=zoom, grade=grade,
                    face_found=found, words_from=wsrc, audio=info["audio"])
        json.dump(meta, open(os.path.join(d, "meta.json"), "w"), indent=1)
    return Subject(d)

# ------------------------------------------------------------------ subject
class Subject:
    def __init__(self, d):
        self.dir = d
        self.meta = json.load(open(os.path.join(d, "meta.json")))
        self.n = self.meta["n"]
        self.dur = self.n / FPS
        self.faces = np.array(json.load(open(os.path.join(d, "faces.json"))), np.float32)
        self.words = json.load(open(os.path.join(d, "words.json")))
        self.base = os.path.join(d, "base.mp4")
        self.mask_path = os.path.join(d, "mask.mkv")
        self.audio = os.path.join(d, "audio.wav") if self.meta.get("audio") else None
        self._plate = None

    def face(self, i):
        return tuple(float(v) for v in self.faces[clamp(i, 0, len(self.faces) - 1)])

    def frames(self, f0=0, f1=None):
        """Yield (i, rgb uint8 HxWx3, cutout float32 HxW) for i in [f0, f1)."""
        f1 = self.n if f1 is None else min(f1, self.n)
        # always decode from frame 0 (exact frame numbers); frames well before f0 are skipped cheaply
        pv = subprocess.Popen(["ffmpeg", "-v", "error", "-i", self.base, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H * 3)
        pm = subprocess.Popen(["ffmpeg", "-v", "error", "-i", self.mask_path, "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H)
        prev = None
        try:
            i = 0
            while i < f1:
                bv = pv.stdout.read(W * H * 3); bm = pm.stdout.read(W * H)
                if len(bv) < W * H * 3: break
                if i < f0 - 8:
                    i += 1; continue
                m = np.frombuffer(bm, np.uint8).reshape(H, W) if len(bm) == W * H else np.zeros((H, W), np.uint8)
                m = np.asarray(Image.fromarray(m, "L").filter(ImageFilter.GaussianBlur(1.6)), np.float32) / 255.0
                m = np.clip((m - 0.12) / 0.76, 0, 1)
                m = m if prev is None else 0.6 * m + 0.4 * prev
                prev = m
                if i >= f0:
                    yield i, np.frombuffer(bv, np.uint8).reshape(H, W, 3), m
                i += 1
        finally:
            for p in (pv, pm):
                p.stdout.close(); p.kill(); p.wait()

    def plate(self):
        """The background without the person: an average of uncovered pixels, holes filled from around them."""
        if self._plate is not None: return self._plate
        p = os.path.join(self.dir, "plate.png")
        if not os.path.exists(p):
            acc = np.zeros((H, W, 3), np.float64); wsum = np.zeros((H, W), np.float64)
            step = max(1, self.n // 90)
            fr_ = os.path.join(self.dir, "faces_raw.json")
            has_face = [len(f) > 1 for f in json.load(open(fr_))] if os.path.exists(fr_) else [True]
            for i, fr, m in self.frames():
                if i % step: continue
                if m.max() < 0.5 and has_face[min(i, len(has_face) - 1)]: continue   # a face but no cutout: the tracker missed the person
                # only pixels well clear of the person (the mask grown by ~24 px)
                grown = np.asarray(Image.fromarray((m * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(9))
                                   .resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.MaxFilter(9))
                                   .resize((W, H), Image.BILINEAR), np.float32) / 255
                wgt = (grown < 0.03).astype(np.float64)
                acc += fr * wgt[..., None]; wsum += wgt
            img = acc / np.maximum(wsum, 1e-6)[..., None]
            img = _fill_holes(img.astype(np.float32), (wsum >= 2).astype(np.float32))
            to_pil(img).save(p)
        self._plate = np.asarray(Image.open(p).convert("RGB"), np.uint8)
        return self._plate

    # ---- words
    def find_word(self, word, after=0.0):
        n = norm_word(word)
        for w in self.words:
            if w["s"] >= after - 1e-6 and norm_word(w["w"]) == n: return w
        for w in self.words:
            if w["s"] >= after - 1e-6 and n and n in norm_word(w["w"]): return w
        return None

def _fill_holes(img, known):
    """Push-pull fill: unknown pixels (known=0) take colour from the nearest known ones, smoothly."""
    levels = [(img * known[..., None], known)]
    while min(levels[-1][1].shape) > 4:
        c, k = levels[-1]
        h, w = k.shape
        h2, w2 = h // 2, w // 2
        c2 = c[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2, 3).sum((1, 3))
        k2 = k[:h2 * 2, :w2 * 2].reshape(h2, 2, w2, 2).sum((1, 3))
        levels.append((c2, k2))
    c, k = levels[-1]
    cur = c / np.maximum(k, 1e-6)[..., None]
    for c, k in reversed(levels[:-1]):
        h, w = k.shape
        up = np.asarray(Image.fromarray(np.clip(cur, 0, 255).astype(np.uint8), "RGB").resize((w, h), Image.BILINEAR), np.float32)
        own = c / np.maximum(k, 1e-6)[..., None]
        kk = np.clip(k, 0, 1)[..., None]
        cur = own * kk + up * (1 - kk)
    filled = cur
    soft = np.asarray(Image.fromarray(np.clip(filled, 0, 255).astype(np.uint8), "RGB").filter(ImageFilter.GaussianBlur(6)), np.float32)
    kk = np.clip(known, 0, 1)[..., None]
    return img * kk + soft * (1 - kk)

# ------------------------------------------------------------------ effects
class Ctx:
    """What an effect sees on one frame.
    c.img      PIL RGB: the frame so far (earlier effects already applied). Return a new one.
    c.src      np uint8 HxWx3: the untouched source frame
    c.mask     np float32 HxW: the person (1) vs the room (0)
    c.face     (cx, cy, w, h) face box in px; c.head_top = top of the head (px)
    c.t        seconds into the video; c.u = seconds into the effect; c.d = effect length; c.k = u / d
    c.p        settings (the effect's PARAMS with any overrides)
    c.skin     colours and fonts (core.SKINS); c.words = word timings for the whole video
    c.state    a dict kept across this effect's frames (frames come in order)
    c.subj     the Subject (c.subj.plate() = the room without the person)
    """
    def __init__(self, **kw): self.__dict__.update(kw)
    def env(self, fade_in=0.3, fade_out=0.3):
        """0 -> 1 over fade_in at the start of the window, 1 -> 0 over fade_out at the end."""
        a = ease_out(self.u / fade_in) if fade_in > 0 else 1.0
        b = ease_out((self.d - self.u) / fade_out) if fade_out > 0 else 1.0
        return min(a, b)
    def words_in(self, a=None, b=None):
        """Words said inside [a, b] (video seconds); default the effect window."""
        a = self.t0 if a is None else a; b = self.t1 if b is None else b
        return [w for w in self.words if w["s"] >= a - 0.05 and w["s"] <= b]
    def said(self, w):
        """Has word w (a dict from words) started yet?"""
        return self.t >= w["s"]
    @property
    def head_top(self):
        cx, cy, fw, fh = self.face
        return cy - fh * 0.85
    def behind(self, layer, base=None):
        """Put an RGBA layer (frame-sized) behind the person: room -> layer -> person. Returns PIL RGB."""
        base = self.img if base is None else base
        b = f32(np.asarray(base.convert("RGB")) if isinstance(base, Image.Image) else base)
        return to_pil(mix(b, over(b, layer), self.mask))
    def front(self, layer, base=None):
        """An RGBA layer over everything. Returns PIL RGB."""
        base = self.img if base is None else base
        return to_pil(over(base, layer))
    def compose(self, room, layer=None, person=None, mask=None):
        """room (np/PIL) -> layer (RGBA, optional) -> person (np/PIL, default the frame so far), cut by the mask."""
        r = f32(np.asarray(room.convert("RGB")) if isinstance(room, Image.Image) else room)
        if layer is not None: r = over(r, layer)
        pe = self.img if person is None else person
        pe = f32(np.asarray(pe.convert("RGB")) if isinstance(pe, Image.Image) else pe)
        return to_pil(mix(pe, r, self.mask if mask is None else mask))
    def plate(self):
        """The room without the person: the 'plate' setting (a photo of the empty set) if given, else worked out."""
        if self.p.get("plate"):
            k = "_plate_" + self.p["plate"]
            if k not in self.state:
                self.state[k] = np.asarray(Image.open(os.path.expanduser(self.p["plate"])).convert("RGB").resize((W, H), Image.LANCZOS))
            return self.state[k]
        return self.subj.plate()
    def word_text(self, default=None):
        """The effect's 'text' setting, else the first strong word said in the window (the speaker's own word, never invented)."""
        if self.p.get("text"): return str(self.p["text"])
        if default: return default
        ws = key_words(self.words_in())
        return re.sub(r"[^\w'-]", "", ws[0]["w"]) if ws else ""
    def canvas(self):
        return Image.new("RGBA", (W, H), (0, 0, 0, 0))

STOP = set("""a an the and or but so um uh like just really very that this these those then than there their they them
i i'm i've i'd me my mine we our you your he she it its is was were be been being am are do did does doing done have has had
to of in on at for with from by as about into over after before again also all any some more most much many not no yes well
what which who when where why how can could would should will shall may might must got get gets going gonna kind sort thing
things stuff actually basically mentioned started start see said say says know think right okay yeah""".split())

def key_words(words, n=None):
    """Words worth showing, in the order said: not filler, at least 4 letters."""
    out = [w for w in words if len(norm_word(w["w"])) >= 4 and norm_word(w["w"]) not in STOP]
    return out[:n] if n else out

def parse_spec(spec, subj, mods):
    """'name', 'name@2.5', 'name@2.5-5', 'name@word', 'name@word+4' -> (module, t0, t1)."""
    name, _, when = spec.partition("@")
    m = mods(name)
    t0, t1 = 0.0, subj.dur
    if when:
        mt = re.fullmatch(r"([\d.]+)(?:-([\d.]+))?", when)
        if mt:
            t0 = float(mt[1]); t1 = float(mt[2]) if mt[2] else t0 + m.DUR
        else:
            word, _, ln = when.partition("+")
            w = subj.find_word(word.strip("\"'"))
            if not w: raise SystemExit(f"'{word}' isn't in the transcript")
            t0 = max(0.0, w["s"] - 0.08); t1 = t0 + (float(ln) if ln else m.DUR)
    return m, max(0.0, t0), min(subj.dur, t1)

def render(subj, specs, out, skin_name="dark", f0=0, f1=None, label=None, frames_only=None, crf=17, sound=True):
    """specs: [(module, t0, t1, params)]. Writes out (mp4) for frames [f0, f1), or returns
    {i: PIL} for frames_only (a list of frame numbers; nothing is written). skin_name: see skin()."""
    f1 = subj.n if f1 is None else min(f1, subj.n)
    sk = skin(skin_name)
    states = [dict() for _ in specs]
    lab = None
    if label:
        s = SS(40 + int(SS(1, 1).textlen(label, 34, 760)), 64)
        s.rr((0, 0, s.w, 64), 32, fill=(0, 0, 0, 150)); s.text((20, 32), label, 34, 760, fill=(255, 255, 255), anchor="lm")
        lab = s.out()
    enc = None
    got = {}
    want = set(frames_only) if frames_only is not None else None
    last = max(want) + 1 if want else f1
    if want is None:
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
        if subj.audio and sound:
            cmd += ["-ss", f"{f0 / FPS:.4f}", "-t", f"{(f1 - f0) / FPS:.4f}", "-i", subj.audio, "-map", "0:v", "-map", "1:a",
                    "-c:a", "aac", "-b:a", "192k"]
        cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                "-shortest", out + ".part.mp4"]
        enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    # effects that keep state need every frame of their window, so start at the earliest window that overlaps
    start = f0
    if want is not None:
        lo, hi = min(want), max(want)
        start = lo
        for _, t0, t1, _ in specs:
            if t0 * FPS <= hi and t1 * FPS >= lo: start = min(start, int(t0 * FPS))
    try:
        for i, fr, m in subj.frames(start, last):
            t = i / FPS
            img = Image.fromarray(fr, "RGB")
            for k, (mod, t0, t1, prm) in enumerate(specs):
                if t0 - 1e-6 <= t <= t1 + 1e-6:
                    c = Ctx(img=img, src=fr, mask=m, face=subj.face(i), t=t, u=t - t0, d=max(1e-3, t1 - t0),
                            t0=t0, t1=t1, i=i, p=prm, skin=sk, words=subj.words, state=states[k], subj=subj, fps=FPS)
                    c.k = clamp01(c.u / c.d)
                    res = mod.render(c)
                    img = res if isinstance(res, Image.Image) else to_pil(res)
                    if img.mode != "RGB": img = img.convert("RGB")
            if lab is not None:
                cv = img.convert("RGBA"); comp(cv, lab, 36, 40); img = cv.convert("RGB")
            if want is not None:
                if i in want: got[i] = img
            elif i >= f0:
                enc.stdin.write(img.tobytes())
    finally:
        if enc:
            enc.stdin.close(); enc.wait()
    if enc:
        if enc.returncode != 0: raise RuntimeError(enc.stderr.read().decode()[-1500:])
        os.replace(out + ".part.mp4", out)
        return out
    return got

def sheet(images, path, cols=4, scale=0.3, labels=None):
    """Contact sheet of PIL frames."""
    ims = [im.resize((int(W * scale), int(H * scale)), Image.LANCZOS) for im in images]
    if not ims: return None
    tw, th = ims[0].size
    rows = (len(ims) + cols - 1) // cols
    cv = Image.new("RGB", (cols * tw + (cols + 1) * 8, rows * (th + 30) + 8), (24, 24, 26))
    d = ImageDraw.Draw(cv)
    for k, im in enumerate(ims):
        x, y = 8 + (k % cols) * (tw + 8), 8 + (k // cols) * (th + 30)
        cv.paste(im, (x, y + 22))
        if labels: d.text((x, y + 2), str(labels[k]), font=font(16, 600), fill=(220, 220, 220))
    cv.save(path, quality=88)
    return path


# ------------------------------------------------------------------ for builders (new edits)
def make_specs(subj, effects, sets=()):
    """Effects as the builders and fx.py give them -> [(module, t0, t1, params)]. Each item can be
      "spotlight@better"                                     (fx.py style: seconds, a word, word+length)
      ("todo", 4.0, 9.5) or ("todo", 4.0, 9.5, {"title": None})
      {"effect": "orbit", "at": "faster+5", "set": {"count": 8}}
    sets: fx.py's --set strings ("key=value" for the first effect, "effect.key=value" for a named one)."""
    if HERE not in sys.path: sys.path.insert(0, HERE)
    import catalog
    out = []
    for k, e in enumerate(effects):
        extra = {}
        if isinstance(e, dict):
            spec = e["effect"] + ("@" + e["at"] if isinstance(e.get("at"), str) else "")
            extra = dict(e.get("set", {}))
            if isinstance(e.get("at"), (list, tuple)):
                mod = catalog.get(e["effect"]); t0, t1 = e["at"]
            else:
                mod, t0, t1 = parse_spec(spec, subj, catalog.get)
        elif isinstance(e, (list, tuple)):
            mod = catalog.get(e[0]); t0, t1 = float(e[1]), float(e[2]); extra = dict(e[3]) if len(e) > 3 else {}
        else:
            mod, t0, t1 = parse_spec(e, subj, catalog.get)
        raw = (e["effect"] if isinstance(e, dict) else e[0] if isinstance(e, (list, tuple)) else e.partition("@")[0])
        prm = dict(mod.PARAMS); prm.update(getattr(catalog, "PRESETS", {}).get(raw, {})); prm.update(extra)
        for st in sets:
            key, _, val = st.partition("=")
            if "." in key:
                en, key = key.split(".", 1)
                if catalog.ALIASES.get(en, en) != mod.NAME: continue
            elif k > 0:
                continue
            try: prm[key] = json.loads(val)
            except Exception: prm[key] = val
        out.append((mod, max(0.0, t0), min(subj.dur, t1), prm))
    try:   # remembered for the builders' records (library/buildrecord.py); changes nothing in the render
        APPLIED.extend((m.NAME, round(a, 3), round(b, 3)) for m, a, b, _ in out)
    except Exception:
        pass
    return out

APPLIED = []   # every effect window resolved in this run: (name, start, end) in the edit's own time

def effects_pass(video, effects, words=None, audio=None, skin="dark", out=None, crf=14):
    """Put effects on an edit's picture before its captions and titles go on. Same length, 1080x1920, 30 fps, silent.
    video: the picture so far (no captions); effects: see make_specs; words: the edit's words in its own time
    [{"w", "s", "e"}] (so "@better" finds the right moment); audio: the edit's sound (for effects that use it).
    skin: "dark", "brand", "brand:<slug>" or a brand dict (see skin()).
    Returns the new picture's path (video itself when there are no effects)."""
    if not effects: return video
    subj = prep(video, words=words, audio=audio)
    specs = make_specs(subj, effects)
    for m, t0, t1, p in specs:
        log(f"  effect {m.NAME:14s} {t0:6.2f}-{t1:6.2f}s")
    out = out or os.path.splitext(video)[0] + ".fx.mp4"
    render(subj, specs, out, skin, crf=crf, sound=False)
    return out

def read_frames(path):
    """PIL RGB frames of a 1080x1920 video, in order."""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=W * H * 3)
    try:
        while True:
            b = p.stdout.read(W * H * 3)
            if len(b) < W * H * 3: break
            yield Image.frombytes("RGB", (W, H), b)
    finally:
        p.stdout.close(); p.kill(); p.wait()

def render_with_effects(n, picture, captions, effects, out, words=None, audio=None, skin="dark", crf=15):
    """For frame-by-frame builders (Fast Cut): picture(f) -> PIL frame without captions; captions(img, f) draws the
    captions and titles onto img (RGBA) and may return it. Writes out (silent): picture -> effects -> captions."""
    clean = os.path.splitext(out)[0] + ".clean.mp4"
    def encoder(path, q):
        return subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                 "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", str(q), "-preset", "medium",
                                 "-pix_fmt", "yuv420p", path], stdin=subprocess.PIPE)
    enc = encoder(clean, 12)
    for f in range(n):
        enc.stdin.write(picture(f).convert("RGB").tobytes())
    enc.stdin.close(); enc.wait()
    fxv = effects_pass(clean, effects, words, audio, skin)
    enc = encoder(out, crf)
    f = 0
    for img in read_frames(fxv):
        if f >= n: break
        cv = img.convert("RGBA")
        r = captions(cv, f)
        enc.stdin.write((r if isinstance(r, Image.Image) else cv).convert("RGB").tobytes()); f += 1
    while f < n:          # never short: hold the last frame
        enc.stdin.write(cv.convert("RGB").tobytes()); f += 1
    enc.stdin.close(); enc.wait()
    return out
