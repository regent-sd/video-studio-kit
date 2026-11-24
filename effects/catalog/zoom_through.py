"""Zoom-through: an accelerating push-in toward your face (or any point) with strong radial motion blur and a flash at the
peak, then the same move reversed: a fast zoom back out that slows to a stop. Over a hard cut it reads as zooming
through into the next shot; on one continuous shot it's a whoosh punch."""
import math
import numpy as np
from PIL import Image
from core import W, H, FPS, f32, to_pil, clamp, clamp01, vignette
from catalog._cam import affine, pil
from catalog._cam2 import zoom_blur, radial_chroma

NAME = "zoom-through"
KIND = "camera"
ABOUT = "Fast zoom-through whoosh: accelerating push into your face with radial blur and a flash, then back out"
DUR = 1.2
PARAMS = dict(
    peak=0.5,         # when it's closest: a share of the window (0-1), or seconds into it (over 1). Put it on the cut.
    amount=5.0,       # how close it gets at the peak (5 = five times closer)
    blur=1.0,         # radial motion blur (0 = none, 1 = like a real fast zoom, 2 = smeared)
    flash=0.8,        # brightness flash at the peak (0 = none)
    x=None,           # the point it dives into (px, or a share of the width); default your face
    y=None,           # (px, or a share of the height)
)
RAMP = 0.85            # longest a push (in or out) lasts; the rest of a long window plays untouched
POW = 2.4              # how hard it accelerates into the peak

def _peak(c):
    pk = float(c.p.get("peak") if c.p.get("peak") is not None else 0.5)
    tp = pk * c.d if 0 < pk <= 1 else pk
    return clamp(tp, min(0.1, c.d * 0.3), max(c.d - 0.1, c.d * 0.7))

def _lz(c, u):
    """(log zoom, its speed per second) at u."""
    L = math.log(max(1.01, float(c.p["amount"])))
    tp = _peak(c)
    a = min(tp, RAMP); b = min(c.d - tp, RAMP)
    if u <= tp:
        if u <= tp - a: return 0.0, 0.0
        x = (u - (tp - a)) / a
        return L * x ** POW, L * POW * x ** (POW - 1) / a
    if u >= tp + b: return 0.0, 0.0
    y = (u - tp) / b
    return L * (1 - y) ** POW, L * POW * (1 - y) ** (POW - 1) / b

def _point(c):
    p = c.p
    cx, cy, fw, fh = c.face
    px, py = cx, cy - fh * 0.05
    if p.get("x") is not None:
        v = float(p["x"]); px = v * W if 0 <= v <= 1 else v
    if p.get("y") is not None:
        v = float(p["y"]); py = v * H if 0 <= v <= 1 else v
    return clamp(px, 0, W), clamp(py, 0, H)

def render(c):
    p, st = c.p, c.state
    lz, sp = _lz(c, c.u)
    tp = _peak(c)
    fl = float(p["flash"]) * math.exp(-((c.u - tp) / 0.052) ** 2)
    if lz < 1e-4 and fl < 0.003:
        return c.img
    z = math.exp(lz)
    px, py = _point(c)
    # as it dives in, the point drifts toward the middle (never showing past the frame's edge)
    w = 1 - 1 / z
    lo, hi = W - (W - px) * z, px * z
    m = min(3.0, (hi - lo) / 2)
    qx = clamp(px + (W / 2 - px) * w, lo + m, hi - m)
    lo, hi = H - (H - py) * z, py * z
    m = min(3.0, (hi - lo) / 2)
    qy = clamp(py + (H * 0.46 - py) * w, lo + m, hi - m)
    sharp = affine(c.img, z, px, py, qx, qy, resample=Image.BICUBIC)
    out = f32(np.asarray(sharp))
    # radial motion blur: this frame's change of scale, streaked about the dive point
    spread = math.exp(sp / FPS * float(p["blur"])) - 1
    if spread > 0.004:
        bl = zoom_blur(c.img, qx, qy, spread, q=2 if spread < 0.12 else 3, passes=4 if spread < 0.06 else 5,
                       z=z, px=px, py=py)
        if "xx" not in st:
            yy, xx = np.ogrid[0:H, 0:W]
            st["xx"], st["yy"] = xx.astype(np.float32), yy.astype(np.float32)
        r = np.sqrt((st["xx"] - qx) ** 2 + (st["yy"] - qy) ** 2) / W
        k = clamp01(spread * 9)
        wm = np.clip(0.2 + r / 0.32, 0, 1) * k
        out = out * (1 - wm[..., None]) + bl * wm[..., None]
        out = radial_chroma(out, qx, qy, 0.012 * clamp01(spread * 5))
        out = out * (1 - 0.3 * k * (1 - vignette(0.9, 0.8, 0.46)))[..., None]
    if fl > 0.003:                      # a bloom: highlights blow out first, then a little haze
        out = out * (1 + 1.3 * fl)
        out = out + (np.array([255, 250, 242], np.float32) - out).clip(0) * min(1.0, fl * 0.62)
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.42,
    "lead": 1.0,
    "tail": 1.0,
}
