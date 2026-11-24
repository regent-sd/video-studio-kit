"""Shared print-making helpers for code-body, banknote, news, letter-dive, day-dial and paper-tear:
value noise, paper texture, halftone dots, line engraving, guilloche curves, torn-paper edges.
Everything is numpy and seeded, so the same settings give the same picture on every frame."""
import math, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import W, H, f32

# ------------------------------------------------------------------ small maths
def smooth(e0, e1, x):
    """Smoothstep from e0 to e1 (works on arrays, e0 > e1 allowed)."""
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

@functools.lru_cache(4)
def grid(h, w):
    """(yy, xx) float32 pixel coordinates, cached."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    yy.setflags(write=False); xx.setflags(write=False)
    return yy, xx

def lum(rgb):
    """Luminance 0..1 of an HxWx3 array (uint8 or float 0..255)."""
    a = f32(rgb)
    return (a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114) / 255.0

def _rs(a, w, h, f=Image.BILINEAR):
    return np.asarray(Image.fromarray(np.ascontiguousarray(a, np.float32), "F").resize((w, h), f), np.float32)

def blur(a, r, q=1):
    """Gaussian blur of a float HxW (or HxWxC) array, r = sigma in px; q > 1 blurs a q-times smaller copy (faster)."""
    from scipy.ndimage import gaussian_filter
    if a.ndim == 3:
        return np.stack([blur(a[..., k], r, q) for k in range(a.shape[2])], -1)
    h, w = a.shape
    if q > 1:
        sm = _rs(a, max(1, w // q), max(1, h // q), Image.BOX)
        sm = gaussian_filter(sm, r / q, mode="nearest")
        return _rs(sm, w, h)
    return gaussian_filter(a.astype(np.float32), r, mode="nearest")

def stretch(L, mask=None, lo=2, hi=98, gamma=1.0):
    """Stretch tones to 0..1 using percentiles (inside mask if given)."""
    sel = L[mask > 0.5] if mask is not None and (mask > 0.5).sum() > 200 else L.ravel()
    if sel.size > 40000: sel = sel[:: max(1, sel.size // 40000)]
    a, b = np.percentile(sel, [lo, hi])
    out = np.clip((L - a) / max(1e-3, b - a), 0, 1)
    return out ** gamma if gamma != 1.0 else out

# ------------------------------------------------------------------ noise
@functools.lru_cache(32)
def noise(w, h, scale, seed):
    """Smooth value noise 0..1 (features about `scale` px), float32 h x w."""
    rng = np.random.default_rng(seed)
    gw, gh = int(w / scale) + 3, int(h / scale) + 3
    g = rng.random((gh, gw)).astype(np.float32)
    im = Image.fromarray(g, "F").resize((int(gw * scale), int(gh * scale)), Image.BICUBIC)
    a = np.asarray(im, np.float32)
    o = int(scale)
    a = a[o:o + h, o:o + w]
    a.setflags(write=False)
    return a

@functools.lru_cache(32)
def fbm(w, h, scale, octaves=4, seed=0):
    """Fractal noise roughly 0..1: octaves of value noise, each half the size and weight."""
    acc = np.zeros((h, w), np.float32); tot = 0.0; amp = 1.0; s = scale
    for k in range(octaves):
        acc += amp * (noise(w, h, max(1.5, s), seed * 31 + k) - 0.5); tot += amp
        amp *= 0.5; s /= 2
    a = np.clip(acc / tot * 1.6 + 0.5, 0, 1)
    a.setflags(write=False)
    return a

def fbm1(n, scale, octaves=5, seed=0, rough=0.55):
    """1-D fractal noise, n samples, about -1..1."""
    rng = np.random.default_rng(seed)
    x = np.arange(n, dtype=np.float32)
    out = np.zeros(n, np.float32); amp = 1.0; tot = 0.0; s = float(scale)
    for k in range(octaves):
        m = int(n / s) + 3
        pts = rng.uniform(-1, 1, m).astype(np.float32)
        xi = x / s
        i0 = np.floor(xi).astype(int); fr = xi - i0
        fr = fr * fr * (3 - 2 * fr)
        out += amp * (pts[i0] * (1 - fr) + pts[np.minimum(i0 + 1, m - 1)] * fr)
        tot += amp; amp *= rough; s = max(1.0, s / 2.2)
    return out / tot * 1.5

# ------------------------------------------------------------------ paper
@functools.lru_cache(12)
def paper(w, h, base=(244, 240, 230), seed=1, grain=6.0, mottle=9.0, fibers=0.6, edge=0.0):
    """Paper texture as float32 h x w x 3 (0..255): soft mottling, fine grain, faint fibres, optional darker edges.
    Cached and read-only: copy before drawing on it."""
    rng = np.random.default_rng(seed)
    b = np.array(base, np.float32)
    mot = (fbm(w, h, 220, 4, seed) - 0.5) * 2 * mottle
    g = rng.normal(0, 1, (h, w)).astype(np.float32)
    g = blur(g, 0.6) * grain * 1.6
    tone = mot + g
    if fibers > 0:
        fl = Image.new("L", (w, h), 128)
        d = ImageDraw.Draw(fl)
        for _ in range(int(w * h / 2600 * fibers)):
            x, y = rng.uniform(0, w), rng.uniform(0, h)
            ang = rng.uniform(0, math.pi); ln = rng.uniform(5, 22); bend = rng.uniform(-0.4, 0.4)
            pts = []
            for s in np.linspace(-0.5, 0.5, 5):
                a2 = ang + bend * s * 2
                pts.append((x + math.cos(a2) * ln * s, y + math.sin(a2) * ln * s))
            d.line(pts, fill=int(128 + rng.choice([-1, 1]) * rng.uniform(10, 28)), width=1)
        fa = np.asarray(fl.filter(ImageFilter.GaussianBlur(0.5)), np.float32) - 128
        tone = tone + fa * 0.55
    out = b[None, None, :] + tone[..., None] * np.array([1.0, 0.99, 0.95], np.float32)[None, None, :]
    if edge > 0:
        yy, xx = grid(h, w)
        dx = np.minimum(xx, w - 1 - xx) / (w * 0.5); dy = np.minimum(yy, h - 1 - yy) / (h * 0.5)
        e = np.clip(1 - np.minimum(dx, dy) * 3.2, 0, 1) ** 2
        out = out - e[..., None] * edge * np.array([22, 26, 40], np.float32)[None, None, :]
    out = np.clip(out, 0, 255).astype(np.float32)
    out.setflags(write=False)
    return out

# ------------------------------------------------------------------ print screens
def halftone(tone, cell=8.0, angle=45.0, soft=0.9, x0=0.0, y0=0.0):
    """Round halftone dots. tone: HxW 0..1 (1 = white paper). Returns ink 0..1 (1 = ink).
    The tone is averaged over about a cell first, so dots stay round."""
    h, w = tone.shape
    yy, xx = grid(h, w)
    a = math.radians(angle); ca, sa = math.cos(a), math.sin(a)
    u = ((xx + x0) * ca + (yy + y0) * sa) / cell
    v = (-(xx + x0) * sa + (yy + y0) * ca) / cell
    fu = u - np.floor(u) - 0.5; fv = v - np.floor(v) - 0.5
    d = np.sqrt(fu * fu + fv * fv) * cell
    dark = 1 - blur(tone, cell * 0.35, 2 if cell > 6 else 1)
    r = cell * np.sqrt(np.clip(dark, 0, 1) / math.pi) * 1.08
    return np.clip((r - d) / soft + 0.5, 0, 1)

def engrave(tone, period=6.0, angle=0.0, warp=None, warp_amp=0.0, thick=1.0, soft=0.75, minw=0.0, x0=0.0, y0=0.0):
    """Line engraving. tone: HxW 0..1 (1 = white). Parallel lines at `angle` degrees, `period` px apart, each line as
    thick as the tone is dark. warp (HxW, any units) bends the lines by warp*warp_amp periods so they follow the form.
    Returns ink 0..1."""
    h, w = tone.shape
    yy, xx = grid(h, w)
    a = math.radians(angle)
    ph = ((xx + x0) * math.sin(a) + (yy + y0) * math.cos(a)) / period
    if warp is not None and warp_amp: ph = ph + warp * warp_amp
    fr = ph - np.floor(ph)
    dist = 0.5 - np.abs(fr - 0.5)                        # periods from the nearest line centre
    halfw = np.clip((1 - tone) * 0.5 * thick, 0, 0.5)
    if minw > 0: halfw = np.where(tone < 0.97, np.maximum(halfw, minw * 0.5), halfw)
    return np.clip((halfw - dist) * period / soft + 0.5, 0, 1)

# ------------------------------------------------------------------ guilloche (drawn on a PIL ImageDraw, any scale)
def trochoid(R, r, d, n=1400, turns=None, rot=0.0, cx=0.0, cy=0.0, epi=False):
    """Points of a hypotrochoid (or epitrochoid) closed curve centred on cx, cy."""
    from math import gcd
    if turns is None:
        a, b = int(round(R)), int(round(r))
        turns = b // gcd(a, b) if a and b else 1
    t = np.linspace(0, 2 * math.pi * turns, n * max(1, turns // 2 + 1))
    if epi:
        x = (R + r) * np.cos(t) - d * np.cos((R + r) / r * t)
        y = (R + r) * np.sin(t) - d * np.sin((R + r) / r * t)
    else:
        x = (R - r) * np.cos(t) + d * np.cos((R - r) / r * t)
        y = (R - r) * np.sin(t) - d * np.sin((R - r) / r * t)
    c, s = math.cos(rot), math.sin(rot)
    return list(zip((cx + x * c - y * s).tolist(), (cy + x * s + y * c).tolist()))

def wave_ring(cx, cy, r0, amp, lobes, phase=0.0, n=1600, sx=1.0, sy=1.0, amp2=0.0, lobes2=0):
    """A circle (or ellipse via sx, sy) whose radius waves: r0 + amp*sin(lobes*t + phase)."""
    t = np.linspace(0, 2 * math.pi, n + 1)
    r = r0 + amp * np.sin(lobes * t + phase)
    if amp2: r = r + amp2 * np.sin(lobes2 * t)
    return list(zip((cx + r * np.cos(t) * sx).tolist(), (cy + r * np.sin(t) * sy).tolist()))

def rosette(d, cx, cy, R, color, width=1, k=1.0, layers=3):
    """A banknote-style rosette: several trochoid families, each rotated a little."""
    for L in range(layers):
        rr = R * (1 - 0.22 * L)
        for j in range(5):
            pts = trochoid(rr * 0.62, rr * 0.62 / (7 + 2 * L), rr * (0.42 - 0.05 * L), n=900, rot=j * 0.0897 + L * 0.3,
                           cx=cx, cy=cy, epi=False)
            d.line(pts, fill=color, width=width)
    for j in range(36):
        pts = wave_ring(cx, cy, R * 0.93, R * 0.06, 24, phase=j * 2 * math.pi / 36 / 24 * 4, n=900)
        d.line(pts, fill=color, width=width)

# ------------------------------------------------------------------ torn paper
def torn_path(n, seed, big=60.0, mid=14.0, fine=3.5, scale=None):
    """A torn-paper offset profile, n samples (px): big wander, jagged mid teeth, fine fibre chatter."""
    scale = scale or n / 3.0
    p = fbm1(n, scale, 3, seed, 0.5) * big
    p = p + fbm1(n, 26, 3, seed + 1, 0.6) * mid
    rng = np.random.default_rng(seed + 2)
    p = p + (rng.uniform(-1, 1, n).astype(np.float32) * 0.5 + fbm1(n, 4, 2, seed + 3, 0.6) * 0.8) * fine
    return p.astype(np.float32)

def fibre_lines(d, pts, normals, rng, color, k=1.0, density=0.35, length=(4, 13)):
    """Short loose fibres sticking out of a torn edge. pts/normals: lists of (x, y) on the edge and outward normals."""
    for (x, y), (nx, ny) in zip(pts, normals):
        if rng.random() > density: continue
        ln = rng.uniform(*length) * k
        a = math.atan2(ny, nx) + rng.uniform(-0.9, 0.9)
        x1, y1 = x + math.cos(a) * ln, y + math.sin(a) * ln
        xm, ym = (x + x1) / 2 + rng.uniform(-2, 2) * k, (y + y1) / 2 + rng.uniform(-2, 2) * k
        d.line([(x, y), (xm, ym), (x1, y1)], fill=color, width=max(1, int(round(k))))

# ------------------------------------------------------------------ words
FILLERS = {"um", "uh", "so", "and", "but", "like"}

def sentences(words):
    """Split word dicts into sentences (lists of word dicts) at . ! ?"""
    import re
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w["w"]): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def sentence_with(words, target, t0, t1, maxlen=64):
    """The sentence (text) that contains `target` said between t0 and t1, leading fillers dropped; None if it's
    missing or longer than maxlen characters."""
    import re
    from core import norm_word
    tn = norm_word(target)
    for snt in sentences(words):
        if any(norm_word(w["w"]) == tn and t0 - 0.05 <= w["s"] <= t1 for w in snt):
            while snt and norm_word(snt[0]["w"]) in FILLERS: snt = snt[1:]
            txt = " ".join(w["w"] for w in snt).strip()
            if not txt: return None
            txt = txt[0].upper() + txt[1:]
            return txt if len(txt) <= maxlen else None
    return None

# ------------------------------------------------------------------ cutout
def solid(mask, q=4, edge=3):
    """The cutout made solid inside: enclosed holes filled and see-through patches inside the body (a printed shirt
    logo can read as half 'room') made opaque, keeping the soft outer edge. float32 HxW."""
    from scipy.ndimage import binary_fill_holes, binary_erosion
    h, w = mask.shape
    sm = np.asarray(Image.fromarray(np.ascontiguousarray(mask, np.float32), "F").resize((w // q, h // q), Image.BOX), np.float32)
    filled = binary_fill_holes(sm > 0.5)
    core_ = binary_erosion(filled, iterations=edge, border_value=1)
    if not core_.any(): return mask
    hu = np.asarray(Image.fromarray(core_.astype(np.float32), "F").resize((w, h), Image.BILINEAR), np.float32)
    return np.maximum(mask, np.clip(hu * 1.5, 0, 1))

def key_word(c):
    """The 'text' setting, else the first strong word said in the window, else the strong word said nearest the
    window (always the speaker's own word); '' if the video has no words."""
    import re
    from core import key_words
    w = c.word_text()
    if w: return w
    ws = key_words(c.words or [])
    if not ws: return ""
    mid = (c.t0 + c.t1) / 2
    best = min(ws, key=lambda x: abs(x["s"] - mid))
    return re.sub(r"[^\w'-]", "", best["w"])
