"""Helpers shared by frame-break, digital-zoom, zoom-through, green-screen and paper-cut.

Not an effect: catalog/__init__.py skips files that start with an underscore.
"""
import os, math, atexit, subprocess, functools
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
from core import W, H, FPS, f32, clamp, CONTENT
from catalog._cam import affine, pil, blur

# ------------------------------------------------------------------ time
def stepped(c, n=3):
    """Stop-motion time: (seconds into the effect, step number), held for n frames at a time ("on threes")."""
    f0 = int(round(c.t0 * FPS))
    k = max(0, c.i - f0) // max(1, n)
    return k * n / FPS, k

# ------------------------------------------------------------------ layers
def premul_over(base, rgb, a):
    """base (float HxWx3) with rgb (float HxWx3, straight) over it at alpha a (HxW 0-1)."""
    a = a[..., None] if a.ndim == 2 else a
    return base * (1 - a) + rgb * a

def edge_fade(shape, px=40, sides="lrt"):
    """HxW 1 inside, ramping to 0 within px of the chosen frame edges (l, r, t, b): hides the cut where the
    picture ends when a cutout is moved or scaled."""
    h, w = shape
    out = np.ones((h, w), np.float32)
    x = np.arange(w, dtype=np.float32); y = np.arange(h, dtype=np.float32)
    if "l" in sides: out *= np.clip(x / px, 0, 1)[None, :]
    if "r" in sides: out *= np.clip((w - 1 - x) / px, 0, 1)[None, :]
    if "t" in sides: out *= np.clip(y / px, 0, 1)[:, None]
    if "b" in sides: out *= np.clip((h - 1 - y) / px, 0, 1)[:, None]
    return out

def move_layer(rgb, alpha, s, ax, ay, tx, ty, rot=0.0, resample=Image.BILINEAR):
    """Scale an image + alpha by s about (ax, ay), landing that point at (tx, ty). Returns (float rgb, alpha 0-1)
    on the frame, premultiplied while moving so edges don't pick up black."""
    a8 = (np.clip(alpha, 0, 1) * 255).astype(np.uint8)
    im = Image.fromarray(np.dstack([np.asarray(rgb, np.uint8), a8]), "RGBA").convert("RGBa")
    out = np.asarray(affine(im, s, ax, ay, tx, ty, rot, resample=resample).convert("RGBA"), np.float32)
    return out[..., :3], out[..., 3] / 255.0

def rr_alpha(box, r, shape=(H, W)):
    """Float HxW alpha of a rounded rectangle (x0, y0, x1, y1), anti-aliased, any sub-pixel position."""
    h, w = shape
    x0, y0, x1, y1 = box
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    out = np.zeros((h, w), np.float32)
    X0, Y0 = max(0, int(math.floor(x0)) - 1), max(0, int(math.floor(y0)) - 1)
    X1, Y1 = min(w, int(math.ceil(x1)) + 1), min(h, int(math.ceil(y1)) + 1)
    if X1 <= X0 or Y1 <= Y0: return out
    yy, xx = np.mgrid[Y0:Y1, X0:X1].astype(np.float32) + 0.5
    qx = np.maximum(np.maximum(x0 + r - xx, xx - (x1 - r)), 0)
    qy = np.maximum(np.maximum(y0 + r - yy, yy - (y1 - r)), 0)
    d = np.sqrt(qx * qx + qy * qy) - r                                  # >0 outside the rounded corner
    inside = np.minimum(np.minimum(xx - x0, x1 - xx), np.minimum(yy - y0, y1 - yy))
    sd = np.where((qx > 0) & (qy > 0), d, -inside)
    out[Y0:Y1, X0:X1] = np.clip(0.5 - sd, 0, 1)
    return out

def rr_sdf(box, r, pad=12, shape=(H, W)):
    """Signed distance (px, <0 inside) to a rounded rectangle, worked out only over its bounding box + pad.
    Returns (sd float32, (X0, Y0)): sd covers [Y0:Y0+h, X0:X0+w] of the frame; outside it, treat as far away."""
    h, w = shape
    x0, y0, x1, y1 = box
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    X0, Y0 = max(0, int(math.floor(x0)) - pad), max(0, int(math.floor(y0)) - pad)
    X1, Y1 = min(w, int(math.ceil(x1)) + pad), min(h, int(math.ceil(y1)) + pad)
    if X1 <= X0 or Y1 <= Y0: return np.full((1, 1), 1e3, np.float32), (0, 0)
    xx = np.arange(X0, X1, dtype=np.float32)[None, :] + 0.5
    yy = np.arange(Y0, Y1, dtype=np.float32)[:, None] + 0.5
    qx = np.abs(xx - (x0 + x1) / 2) - ((x1 - x0) / 2 - r)          # (1, w)
    qy = np.abs(yy - (y0 + y1) / 2) - ((y1 - y0) / 2 - r)          # (h, 1)
    ox, oy = np.maximum(qx, 0), np.maximum(qy, 0)
    sd = np.sqrt(ox * ox + oy * oy) + np.minimum(np.maximum(qx, qy), 0) - r
    return sd.astype(np.float32), (X0, Y0)

def place_map(part, origin, shape=(H, W)):
    """A map worked out over a region (part, at origin (X0, Y0)) put on a full frame of zeros."""
    out = np.zeros(shape, np.float32)
    X0, Y0 = origin
    h, w = part.shape
    out[Y0:Y0 + h, X0:X0 + w] = part
    return out

def rr_ring(box, r, width, shape=(H, W)):
    """A thin rounded-rect outline (inside the box edge), anti-aliased. HxW 0-1."""
    x0, y0, x1, y1 = box
    return np.clip(rr_alpha(box, r, shape) - rr_alpha((x0 + width, y0 + width, x1 - width, y1 - width),
                                                      max(0, r - width), shape), 0, 1)

def soft(a, r):
    """Blur of a 0-1 float map (fast, downscaled)."""
    return blur(np.clip(a, 0, 1) * 255, r) / 255.0

def shift(a, dx, dy):
    """Move a 2-D map by whole pixels (zeros come in)."""
    out = np.zeros_like(a)
    dx, dy = int(round(dx)), int(round(dy))
    h, w = a.shape[:2]
    xs0, xs1 = max(0, -dx), min(w, w - dx); ys0, ys1 = max(0, -dy), min(h, h - dy)
    if xs1 > xs0 and ys1 > ys0:
        out[ys0 + dy:ys1 + dy, xs0 + dx:xs1 + dx] = a[ys0:ys1, xs0:xs1]
    return out

# ------------------------------------------------------------------ 3D
def tilt_pts(pts, cx, cy, ry=0.0, rx=0.0, f=2400.0):
    """Points on a flat plane (screen px) turned ry (about the vertical axis) and rx (about the horizontal axis)
    around (cx, cy), then put back in perspective."""
    a, b = math.radians(ry), math.radians(rx)
    out = []
    for x, y in pts:
        x, y = x - cx, y - cy
        X, Z = x * math.cos(a), -x * math.sin(a)
        Y, Z = y * math.cos(b) - Z * math.sin(b), y * math.sin(b) + Z * math.cos(b)
        k = f / (f + Z)
        out.append((cx + X * k, cy + Y * k))
    return out

# ------------------------------------------------------------------ camera artefacts
def zoom_blur(img, cx, cy, spread, q=2, passes=4, z=1.0, px=None, py=None):
    """Radial (zoom) motion blur: the average of 2**passes copies of img zoomed by z about (px, py) (landing on
    (cx, cy)), with the zoom spread evenly over z / sqrt(1 + spread) .. z * sqrt(1 + spread). Built by repeated
    doubling (each pass scales up about (cx, cy)), on a q-times smaller copy, so it never shows past the frame's
    edge while z / sqrt(1 + spread) >= 1. img: PIL RGB (the unzoomed frame). Returns float32 HxWx3, full size."""
    px = cx if px is None else px; py = cy if py is None else py
    w, h = img.width // q, img.height // q
    small = img.resize((w, h), Image.BILINEAR if q <= 2 else Image.BOX)
    S = 1 + max(0.0, spread)
    # the lowest zoom that still covers the frame with this landing point
    lo = max(1.0, cx / max(px, 1e-3), (img.width - cx) / max(img.width - px, 1e-3),
             cy / max(py, 1e-3), (img.height - cy) / max(img.height - py, 1e-3))
    z0 = max(lo, z / math.sqrt(S))
    S = max(1.0, (z * math.sqrt(S)) / z0)
    cur = np.asarray(affine(small, z0, px / q, py / q, cx / q, cy / q, size=(w, h)), np.float32)
    if S > 1.0001:
        n = 2 ** passes
        s = S ** (1 / max(1, n - 1))
        for _ in range(passes):
            zz = np.asarray(affine(pil(cur), s, cx / q, cy / q, size=(w, h)), np.float32)
            cur = (cur + zz) * 0.5
            s = s * s
    return np.asarray(pil(cur).resize((img.width, img.height), Image.BILINEAR), np.float32)

def chroma(a, dx, dy=0):
    """Lateral colour fringe: red moved by +d, blue by -d (whole px). a: float HxWx3."""
    out = a.copy()
    if abs(dx) >= 1 or abs(dy) >= 1:
        out[..., 0] = shift(a[..., 0], dx, dy) + (shift(np.ones_like(a[..., 0]), dx, dy) == 0) * a[..., 0]
        out[..., 2] = shift(a[..., 2], -dx, -dy) + (shift(np.ones_like(a[..., 2]), -dx, -dy) == 0) * a[..., 2]
    return out

def radial_chroma(a, cx, cy, k):
    """Colour fringe that grows toward the edges (a lens / zoom fringe): red scaled up by 2k, green by k, blue
    left as it is (only scaled up, so nothing comes in from past the frame's edge)."""
    if abs(k) < 1e-4: return a
    out = a.copy()
    for ch, s in ((0, 1 + 2 * abs(k)), (1, 1 + abs(k))):
        out[..., ch] = np.asarray(affine(pil(a[..., ch]), s, cx, cy, resample=Image.BILINEAR), np.float32)
    return out

def pixelate(a, block, cells=None):
    """Blocky resample (a digital zoom glitch). cells: HxW 0-1 map of where (default everywhere). float in/out."""
    h, w = a.shape[:2]
    sm = pil(a).resize((max(1, w // block), max(1, h // block)), Image.BOX)
    big = np.asarray(sm.resize((w, h), Image.NEAREST), np.float32)
    if cells is None: return big
    m = cells[..., None]
    return a * (1 - m) + big * m

def block_cells(seed, block, density=0.35, shape=(H, W)):
    """A seeded map of whole macro-blocks (block px) where a glitch shows. HxW float 0/1."""
    h, w = shape
    rng = np.random.default_rng(seed)
    g = (rng.random((h // block + 1, w // block + 1)) < density).astype(np.float32)
    # runs of blocks along rows, like a corrupt slice
    g = np.maximum(g, np.roll(g, 1, 1) * (rng.random(g.shape) < 0.6))
    return np.repeat(np.repeat(g, block, 0), block, 1)[:h, :w]

def sharpen(img, amount=1.0, radius=2.0):
    """Unsharp mask (PIL in, PIL out)."""
    if amount <= 0.01: return img
    return img.filter(ImageFilter.UnsharpMask(radius=radius, percent=int(140 * amount), threshold=2))

# ------------------------------------------------------------------ outlines and light
def dilate(mask, px, q=4):
    """The cutout grown by about px with a smooth rounded edge (a die-cut sticker outline). HxW 0-1."""
    h, w = mask.shape
    sm = np.asarray(pil(mask * 255).resize((w // q, h // q), Image.BOX), np.float32) / 255
    from scipy.ndimage import gaussian_filter
    g = gaussian_filter(sm, max(0.6, px / q * 0.55), mode="constant")
    big = np.asarray(Image.fromarray(np.clip(g * 255, 0, 255).astype(np.uint8), "L").resize((w, h), Image.BICUBIC),
                     np.float32) / 255
    # threshold low: the grown shape; a narrow ramp keeps the edge anti-aliased
    return np.clip((big - 0.07) / 0.06, 0, 1)

def rim(mask, width=7.0, top=0.6):
    """A thin light rim just inside the cutout's edge, stronger on top (light from behind and above). HxW 0-1."""
    inner = soft(mask, width)
    edge = np.clip(mask - inner * 1.15, 0, 1) * mask
    if top > 0:
        gy = np.zeros_like(inner); gy[1:-1] = inner[2:] - inner[:-2]   # >0 where the inside is below: a top edge
        edge = edge * (1 - top + top * np.clip(gy * 18 + 0.35, 0, 1.6))
    return np.clip(edge * 2.2, 0, 1)

# ------------------------------------------------------------------ media (an image or a video, for cards)
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"}

def media_path(p):
    """A path from a setting: absolute, ~, or relative to the content folder (studio.json)."""
    if not p: return None
    p = os.path.expanduser(str(p))
    if os.path.exists(p): return p
    q = os.path.join(CONTENT, p)
    return q if os.path.exists(q) else None

def cover(im, size, cx=0.5, cy=0.5):
    """Crop-fill a PIL image to size (w, h) around (cx, cy) (0-1 of the image)."""
    tw, th = size
    a = tw / th
    cw = min(im.width, im.height * a); ch = cw / a
    x0 = clamp(cx * im.width - cw / 2, 0, im.width - cw); y0 = clamp(cy * im.height - ch / 2, 0, im.height - ch)
    return im.resize((int(tw), int(th)), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))

_READERS = []

@atexit.register
def _close_readers():
    for r in _READERS:
        r.close()

class Reader:
    """Frames of a video from `start` seconds at 30 fps, read in order through ffmpeg, scaled to cover size
    (w, h) around (cx, cy). get(k) -> PIL RGB for the k-th frame (holds the last one at the end)."""
    def __init__(self, path, start, size, cx=0.5, cy=0.5, n=None):
        self.path, self.size, self.k, self.last = path, (int(size[0]) // 2 * 2, int(size[1]) // 2 * 2), -1, None
        info = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                               "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip().split(",")
        sw, sh = (int(info[0]), int(info[1])) if len(info) == 2 and info[0].isdigit() else (W, H)
        rot = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                              "stream_side_data=rotation", "-of", "csv=p=0", path], capture_output=True, text=True).stdout
        if any(abs(int(float(v))) % 180 == 90 for v in rot.replace(",", " ").split() if v.strip("-").replace(".", "").isdigit()):
            sw, sh = sh, sw
        tw, th = self.size
        a = tw / th
        cw = min(sw, sh * a); ch = cw / a
        x0 = clamp(cx * sw - cw / 2, 0, sw - cw); y0 = clamp(cy * sh - ch / 2, 0, sh - ch)
        vf = f"fps={FPS},crop={int(cw) // 2 * 2}:{int(ch) // 2 * 2}:{int(x0)}:{int(y0)},scale={tw}:{th}:flags=bicubic"
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0.0, start):.3f}", "-i", path, "-map", "0:v:0", "-vf", vf]
        if n: cmd += ["-frames:v", str(int(n) + 2)]
        cmd += ["-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=tw * th * 3 * 2)
        _READERS.append(self)

    def get(self, k):
        tw, th = self.size
        while self.k < k and self.p is not None:
            b = self.p.stdout.read(tw * th * 3)
            if len(b) < tw * th * 3:
                self.close(); break
            self.last = Image.frombytes("RGB", (tw, th), b); self.k += 1
        return self.last if self.last is not None else Image.new("RGB", (tw, th), (30, 30, 34))

    def close(self):
        if self.p is not None:
            try:
                self.p.stdout.close(); self.p.kill(); self.p.wait()
            except Exception:
                pass
            self.p = None

def load_still(path, size, cx=0.5, cy=0.5):
    """An image (or one frame of a video at 0 s) crop-filled to size."""
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        r = Reader(path, 0.0, size, cx, cy, n=1); im = r.get(0); r.close(); return im
    return cover(Image.open(path).convert("RGB"), size, cx, cy)

# ------------------------------------------------------------------ the person
def head_top_px(c, face):
    """Top of the head (px) on this frame, from the cutout above the face; falls back to the face box."""
    fx, fy, fw, fh = face
    x0, x1 = int(clamp(fx - fw * 0.2, 0, W - 2)), int(clamp(fx + fw * 0.2, 1, W - 1))
    ys = int(clamp(fy - fh * 1.6, 0, H - 2)); ye = int(clamp(fy, ys + 1, H))
    rows = np.where((c.mask[ys:ye, x0:x1] > 0.5).any(1))[0]
    guess = fy - fh * 0.9
    ht = ys + rows[0] if len(rows) else guess
    return float(guess if abs(ht - guess) > fh * 0.5 else ht)

def media_size(path):
    """(w, h) of an image or video (upright)."""
    ext = os.path.splitext(path)[1].lower()
    if ext not in VIDEO_EXT:
        try:
            with Image.open(path) as im: return im.size
        except Exception:
            return (W, H)
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation", "-of", "default=nw=1", path],
                         capture_output=True, text=True).stdout
    vals = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
    try:
        w, h = int(vals["width"]), int(vals["height"])
    except Exception:
        return (W, H)
    try:
        if abs(int(float(vals.get("rotation", 0)))) % 180 == 90: w, h = h, w
    except ValueError:
        pass
    return (w, h)
