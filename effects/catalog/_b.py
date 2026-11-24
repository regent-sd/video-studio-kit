"""Helpers shared by glass-widgets, live-cursor, sketch-words, orbit, head-stack and post-wall.
(The leading underscore keeps this file out of the effects list.)"""
import os, math, wave, subprocess
import numpy as np
from PIL import Image, ImageFilter, ImageOps
from core import W, H, FPS, clamp

# ------------------------------------------------------------------ easing
def spring(x, f=2.0, z=6.0):
    """0 -> 1 with a damped wobble; x = seconds since the start. f = wobbles per second, z = damping."""
    if x <= 0: return 0.0
    return 1 - math.exp(-z * x) * math.cos(2 * math.pi * f * x)

def smooth_noise(t, seed, speeds=(0.31, 0.53, 0.97)):
    """A smooth wander in -1..1 (sum of sines with seeded phases)."""
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * math.pi, len(speeds))
    return sum(math.sin(2 * math.pi * s * t + p) for s, p in zip(speeds, ph)) / len(speeds)

# ------------------------------------------------------------------ the window
def window_frames(c):
    f0 = int(round(c.t0 * FPS)); f1 = max(f0 + 1, int(round(c.t1 * FPS)) + 1)
    return f0, min(f1, len(c.subj.faces))

def face_stats(c):
    """(median face (cx, cy, w, h), union of face boxes over the window (x0, y0, x1, y1)), cached in c.state."""
    st = c.state
    if "_face_stats" not in st:
        f0, f1 = window_frames(c)
        F = np.asarray(c.subj.faces[f0:f1], np.float32)
        if not len(F): F = np.asarray([c.face], np.float32)
        med = tuple(float(v) for v in np.median(F, 0))
        box = (float((F[:, 0] - F[:, 2] / 2).min()), float((F[:, 1] - F[:, 3] / 2).min()),
               float((F[:, 0] + F[:, 2] / 2).max()), float((F[:, 1] + F[:, 3] / 2).max()))
        st["_face_stats"] = (med, box)
    return st["_face_stats"]

def head_top(c, key="_htop"):
    """Top of the head (px) from the cutout above the face, smoothed across frames; falls back to the face box."""
    cx, cy, fw, fh = c.face
    x0, x1 = int(clamp(cx - fw * 0.22, 0, W - 2)), int(clamp(cx + fw * 0.22, 1, W - 1))
    y0 = int(clamp(cy - fh * 1.6, 0, H - 1)); y1 = int(clamp(cy, 1, H))
    col = c.mask[y0:y1:2, x0:x1:3] > 0.5
    rows = np.where(col.any(1))[0]
    guess = cy - fh * 0.92
    v = y0 + rows[0] * 2 if len(rows) else guess
    if abs(v - guess) > fh * 0.45: v = guess          # a hand or something above the head: ignore it
    prev = c.state.get(key)
    v = v if prev is None else prev + (v - prev) * 0.35
    c.state[key] = v
    return float(v)

def solid_mask(c, key="_solid"):
    """The cutout with holes inside the person filled (a shirt graphic can read as background). Cached per frame.
    Use it for "behind" layers: c.compose(c.img, layer, mask=solid_mask(c))."""
    st = c.state
    if st.get(key + "_i") == c.i: return st[key]
    m = c.mask
    try:
        from scipy.ndimage import binary_fill_holes
        q = 4
        small = np.asarray(Image.fromarray((m * 255).astype(np.uint8), "L").resize((W // q, H // q), Image.BILINEAR)) > 127
        holes = binary_fill_holes(small) & ~small
        if holes.any():
            hm = Image.fromarray((holes * 255).astype(np.uint8), "L").filter(ImageFilter.MaxFilter(3))
            hm = hm.filter(ImageFilter.GaussianBlur(1.2)).resize((W, H), Image.BILINEAR)
            m = np.maximum(m, np.asarray(hm, np.float32) / 255)
    except Exception:
        pass
    st[key], st[key + "_i"] = m, c.i
    return m

def behind(c, layer, base=None):
    """Like c.behind, but with the hole-filled cutout."""
    base = c.img if base is None else base
    return c.compose(base, layer, base, mask=solid_mask(c))

# ------------------------------------------------------------------ stills from the video
_STILLS = {}
def stills(subj, n, size=(360, 640), lo=0.04, hi=0.96):
    """n frames from the video at spread-out times, scaled to size (w, h). One ffmpeg pass, cached per process."""
    key = (subj.dir, n, tuple(size), lo, hi)
    if key in _STILLS: return _STILLS[key]
    w, h = size
    idx = [int(round((lo + (hi - lo) * k / max(1, n - 1)) * (subj.n - 1))) for k in range(n)]
    uniq = sorted(set(idx))
    expr = "+".join(f"eq(n,{i})" for i in uniq)
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", subj.base, "-vf", f"select='{expr}',scale={w}:{h}:flags=area",
                        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    raw = p.stdout
    got = {}
    for k, i in enumerate(uniq):
        b = raw[k * w * h * 3:(k + 1) * w * h * 3]
        if len(b) == w * h * 3: got[i] = Image.frombytes("RGB", (w, h), b)
    blank = Image.new("RGB", (w, h), (40, 40, 44))
    out = [got.get(i, blank) for i in idx]
    _STILLS[key] = out
    return out

def load_images(paths, size):
    """Images from PARAMS, crop-filled to size."""
    out = []
    for p in paths or []:
        try:
            out.append(ImageOps.fit(Image.open(os.path.expanduser(str(p))).convert("RGB"), size, Image.LANCZOS))
        except Exception:
            pass
    return out

def crop_fill(im, size, cx=0.5, cy=0.5, zoom=1.0):
    """Crop im to the aspect of size around (cx, cy) (0-1), zoomed in by zoom, and scale it to size."""
    tw, th = size
    a = tw / th
    cw = min(im.width, im.height * a) / zoom
    ch = cw / a
    x0 = clamp(cx * im.width - cw / 2, 0, im.width - cw)
    y0 = clamp(cy * im.height - ch / 2, 0, im.height - ch)
    return im.resize((tw, th), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))

# ------------------------------------------------------------------ sound
_LOUD = {}
def loudness(path):
    """Loudness per video frame, 0-1 (RMS in dB, top 2% = 1, 36 dB below = 0). None without sound."""
    if not path or not os.path.exists(path): return None
    if path in _LOUD: return _LOUD[path]
    try:
        with wave.open(path) as wf:
            sr, ch, sw = wf.getframerate(), wf.getnchannels(), wf.getsampwidth()
            raw = wf.readframes(wf.getnframes())
        if sw != 2: return None
        a = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, ch).mean(1) / 32768.0
        hop = int(sr / FPS)
        n = len(a) // hop
        r = np.sqrt((a[:n * hop].reshape(n, hop) ** 2).mean(1))
        db = 20 * np.log10(r + 1e-6)
        top = float(np.percentile(db, 98))
        v = np.clip((db - (top - 36)) / 36, 0, 1).astype(np.float32)
    except Exception:
        v = None
    _LOUD[path] = v
    return v

def loud_at(L, t):
    """Loudness at t seconds (interpolated)."""
    if L is None or not len(L): return 0.0
    x = clamp(t * FPS, 0, len(L) - 1)
    i = int(x); j = min(i + 1, len(L) - 1)
    return float(L[i] + (L[j] - L[i]) * (x - i))

# ------------------------------------------------------------------ frosted glass
def frost_src(c, src=None, q=4, radius=6, key="_frost"):
    """One blurred, downscaled copy of the frame per frame (cached), to cut glass panels from."""
    st = c.state
    if st.get(key + "_i") != c.i:
        im = (src if src is not None else c.img).convert("RGB")
        st[key] = im.resize((W // q, H // q), Image.BILINEAR).filter(ImageFilter.GaussianBlur(radius))
        st[key + "_i"] = c.i
    return st[key]

def frost_panel(small, box, q=4):
    """The blurred frame under box (x0, y0, x1, y1 in px), at the box's size (RGB)."""
    x0, y0, x1, y1 = box
    w, h = max(1, int(round(x1 - x0))), max(1, int(round(y1 - y0)))
    sx0, sy0 = clamp(x0 / q, 0, small.width - 2), clamp(y0 / q, 0, small.height - 2)
    sx1, sy1 = clamp(x1 / q, sx0 + 1, small.width), clamp(y1 / q, sy0 + 1, small.height)
    return small.resize((w, h), Image.BILINEAR, box=(sx0, sy0, sx1, sy1))

# ------------------------------------------------------------------ layout
def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])

def push_out(r, ex, bounds):
    """Move rect r (x0, y0, x1, y1) out of rect ex by the shortest way that stays inside bounds."""
    if not overlap(r, ex): return r
    w, h = r[2] - r[0], r[3] - r[1]
    opts = [(r[0] - (ex[0] - w), (ex[0] - w, r[1])),       # left
            ((ex[2]) - r[0], (ex[2], r[1])),                # right
            (r[1] - (ex[1] - h), (r[0], ex[1] - h)),        # up
            ((ex[3]) - r[1], (r[0], ex[3]))]                # down
    best = None
    for cost, (x, y) in sorted(opts, key=lambda o: o[0]):
        if bounds[0] <= x and x + w <= bounds[2] and bounds[1] <= y and y + h <= bounds[3]:
            best = (x, y); break
    if best is None: return r
    return (best[0], best[1], best[0] + w, best[1] + h)

def clamp_rect(r, bounds):
    w, h = r[2] - r[0], r[3] - r[1]
    x = clamp(r[0], bounds[0], bounds[2] - w); y = clamp(r[1], bounds[1], bounds[3] - h)
    return (x, y, x + w, y + h)

def font_args(skin, role, weight=None):
    """(weight, path, index) for SS.text from a skin font role."""
    sp = skin.fontspec(role, weight)
    return dict(weight=sp["weight"], path=sp["path"], index=sp["index"])
