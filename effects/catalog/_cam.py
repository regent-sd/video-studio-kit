"""Helpers shared by the camera effects (dolly-zoom, rack-focus, clone-row, blow-away, layer-explode, blade-slice).

Not an effect: catalog/__init__.py skips files that start with an underscore.
"""
import math
import numpy as np
from PIL import Image, ImageFilter
from core import W, H, f32

def u8(a):
    return np.clip(a, 0, 255).astype(np.uint8) if a.dtype != np.uint8 else a

def pil(a):
    """np HxW / HxWx3 / HxWx4 (any dtype, 0-255) -> PIL."""
    a = u8(a)
    return Image.fromarray(a, "L" if a.ndim == 2 else "RGBA" if a.shape[2] == 4 else "RGB")

def blur(a, r):
    """Gaussian blur of a float/uint8 HxW or HxWxC array (0-255), radius r px. Big radii are done on a
    downscaled copy (fast, and the same look). Returns float32."""
    a = np.asarray(a)
    if r < 0.4:
        return f32(a)
    h, w = a.shape[:2]
    q = max(1.0, r / 3.0)
    if q <= 1.05:
        return f32(np.asarray(pil(a).filter(ImageFilter.GaussianBlur(r))))
    sw, sh = max(2, int(round(w / q))), max(2, int(round(h / q)))
    sm = pil(a).resize((sw, sh), Image.BILINEAR if q < 2 else Image.BOX)
    sm = sm.filter(ImageFilter.GaussianBlur(r * sw / w))
    return f32(np.asarray(sm.resize((w, h), Image.BILINEAR)))

def grow(mask, px=24, feather=18):
    """The cutout grown by about px and softened by feather (px). HxW float 0-1. Worked on a quarter-size copy."""
    q = 4
    m = pil(mask * 255).resize((W // q, H // q), Image.BOX)
    k = max(3, int(round(px / q)) * 2 + 1)
    m = m.filter(ImageFilter.MaxFilter(min(k, 25)))
    if feather > 0: m = m.filter(ImageFilter.GaussianBlur(feather / q))
    m = np.asarray(m.resize((W, H), Image.BILINEAR), np.float32) / 255
    return np.clip(m * 1.15, 0, 1)

def tighten(mask, amount=0.18):
    """Pull the cutout's soft edge in a little so the old room doesn't fringe the person on a new background."""
    return np.clip((mask - amount) / (1 - amount), 0, 1)

def coverage(subj):
    """Share of the clip's frames on which the person covers each pixel (quarter size, float 0-1), cached on the
    Subject. Read from the cutout video at quarter size (a fraction of a second)."""
    cov = getattr(subj, "_cam_coverage", None)
    if cov is not None: return cov
    import subprocess
    q = 4
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", subj.mask_path, "-vf", f"fps=8,scale={W // q}:{H // q}:flags=area",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8)
    n = a.size // ((W // q) * (H // q))
    if n == 0:
        cov = np.zeros((H // q, W // q), np.float32)
    else:
        a = a[:n * (W // q) * (H // q)].reshape(n, H // q, W // q)
        keep = a.reshape(n, -1).max(1) > 127                     # frames with a cutout at all
        a = a[keep] if keep.any() else a
        cov = (a > 40).mean(0).astype(np.float32)
    subj._cam_coverage = cov
    return cov

def cover(subj):
    """Where the worked-out plate had to be invented (the person stood there on nearly every frame). HxW 0-1."""
    cv = getattr(subj, "_cam_cover", None)
    if cv is not None: return cv
    from scipy import ndimage
    raw = coverage(subj)
    cov = np.clip((raw - 0.8) / 0.18, 0, 1)
    # a spot inside the body the tracker sometimes dropped (a shirt logo) was still never really seen
    cov = np.maximum(cov, ndimage.binary_fill_holes(raw > 0.8).astype(np.float32))
    im = pil(cov * 255).filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(6))
    cv = np.asarray(im.resize((W, H), Image.BILINEAR), np.float32) / 255
    subj._cam_cover = cv
    return cv

def smudge(subj, plate):
    """The invented part of the plate that sits in a busy room (clutter around it = a smear inside it). A plain
    wall or ceiling fills cleanly and is left alone. HxW float 0-1, cached on the Subject."""
    sm = getattr(subj, "_cam_smudge", None)
    if sm is not None: return sm
    from scipy import ndimage
    from core import _fill_holes
    q = 4
    cv = cover(subj)
    cq = np.asarray(pil(cv * 255).resize((W // q, H // q), Image.BOX), np.float32) / 255
    g = np.asarray(pil(plate).convert("L").resize((W // q, H // q), Image.BOX), np.float32)
    det = ndimage.gaussian_filter(np.abs(g - ndimage.gaussian_filter(g, 1.5)), 4)    # local detail (busy = high)
    known = (cq < 0.05).astype(np.float32)
    lvl = np.clip((det - 1.5) / 4.0, 0, 1) * 255                                      # 0 plain .. 255 busy
    fill = _fill_holes(np.repeat(lvl[..., None], 3, 2), known)[..., 0] / 255          # carry it into the hole
    s = ndimage.gaussian_filter(np.clip(fill, 0, 1) * cq, 3)
    sm = np.asarray(Image.fromarray((np.clip(s, 0, 1) * 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR),
                    np.float32) / 255
    subj._cam_smudge = sm
    return sm

def refill(subj, pl):
    """The never-seen part of a worked-out plate, filled again from the room around it (this also drops any ghost
    of the person that got averaged in). Narrow gaps (behind a head) are filled row by row, so a ceiling line or a
    cabinet edge carries straight across; wide ones (behind a body) get a smooth fill. Cached on the Subject."""
    rf = getattr(subj, "_cam_refill", None)
    if rf is not None: return rf
    from scipy import ndimage
    from core import _fill_holes
    q = 4
    plq = np.asarray(pil(pl).resize((W // q, H // q), Image.BOX), np.float32)
    cvq = np.asarray(pil(cover(subj) * 255).resize((W // q, H // q), Image.BOX), np.float32) / 255
    known = cvq < 0.3
    h, w = known.shape
    pp = _fill_holes(plq, known.astype(np.float32))
    src = ndimage.uniform_filter1d(plq, 5, axis=1)
    xs = np.broadcast_to(np.arange(w)[None, :], (h, w))
    li = np.maximum.accumulate(np.where(known, xs, -1), axis=1)
    ri = np.minimum.accumulate(np.where(known, xs, 10 ** 6)[:, ::-1], axis=1)[:, ::-1]
    both = (li >= 0) & (ri < 10 ** 6)
    rows = np.broadcast_to(np.arange(h)[:, None], (h, w))
    cl = src[rows, np.clip(li, 0, w - 1)]; cr = src[rows, np.clip(ri, 0, w - 1)]
    wr = np.where(both, (xs - li) / np.maximum(1, ri - li), 0.5).astype(np.float32)
    row = ndimage.gaussian_filter(cl * (1 - wr[..., None]) + cr * wr[..., None], (2.0, 1.0, 0))
    span = np.where(both, ri - li, w).astype(np.float32) / w
    wrow = ndimage.gaussian_filter(np.clip((0.5 - span) / 0.2, 0, 1) * both, 6)[..., None]
    fill = row * wrow + pp * (1 - wrow)
    rf = np.asarray(pil(fill).resize((W, H), Image.BILINEAR), np.float32)
    subj._cam_refill = rf
    return rf

def plate_f(c, dim=0.3, soften=8):
    """The empty room as float32. A worked-out plate (not a real photo) is soft where the person always stood,
    so that area is defocused a little, and dimmed where it sits in a busy room, so it reads as shadow, not
    smear. A real plate photo (the 'plate' setting) is used as it is. Cached per effect."""
    st = c.state
    key = ("_room_plate", dim, soften)
    if key not in st:
        pl = f32(c.plate())
        if not c.p.get("plate"):
            cv = cover(c.subj)
            ref = refill(c.subj, pl)
            cv3 = cv[..., None]
            pl = pl * (1 - cv3) + ref * cv3
            if soften > 0: pl = pl * (1 - cv3) + blur(pl, soften) * cv3
            if dim > 0: pl = pl * (1 - dim * smudge(c.subj, c.plate())[..., None])
        st[key] = pl
    return st[key]

def stable_mask(c, max_hole=0.08):
    """c.mask with tracker dropouts patched (a shirt logo read as room on some frames). Two rules:
    - a hole inside the body is filled if the person covered that spot a moment ago or on most of the clip;
    - in the core of the body (covered on nearly every frame of the clip) the cutout can't suddenly thin out.
    A real gap (between an arm and the body) stays open because it was open a moment ago too.
    Call once per frame; keeps its history in c.state."""
    from scipy import ndimage
    q = 4
    m = c.mask
    sm = np.asarray(pil(m * 255).resize((W // q, H // q), Image.BOX), np.float32) / 255
    st = c.state
    ema, slow = st.get("_mask_ema"), st.get("_mask_slow")
    cov = coverage(c.subj)
    prior = np.clip((cov - 0.55) / 0.3, 0, 1)
    core = np.clip((cov - 0.6) / 0.25, 0, 1)
    fill = np.zeros_like(sm)
    trust = prior if ema is None else np.maximum(prior, ema)
    bg = sm < 0.85
    lab, n = ndimage.label(bg)
    if n > 1:
        sizes = np.bincount(lab.ravel())
        edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        ok = sizes < max_hole * sm.size
        ok[edge] = False; ok[0] = False
        if ok.any(): fill = ok[lab].astype(np.float32) * trust
    if slow is not None:
        fill = np.maximum(fill, core * slow)
    out = m
    if fill.max() > 0.02:
        fl = np.asarray(pil(fill * 255).filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(1.5))
                        .resize((W, H), Image.BILINEAR), np.float32) / 255
        out = np.maximum(m, fl)
    # history from the raw cutout (no feedback), so a gap that really opens closes in the patch soon after
    st["_mask_ema"] = sm if ema is None else 0.8 * ema + 0.2 * sm
    st["_mask_slow"] = np.maximum(sm, prior) if slow is None else 0.92 * slow + 0.08 * sm
    return out

def room(c, img=None, mask=None, grow_px=26, feather=26, dim=0.3, soften=8):
    """The frame with the person taken out: the live room, and the plate (dimmed, soft) where the person was.
    img: the frame to start from (default the frame so far). Returns (float32 HxWx3, hole HxW)."""
    base = f32(np.asarray(c.img) if img is None else img)
    hole = grow(c.mask if mask is None else mask, grow_px, feather)
    pl = plate_f(c, dim, soften)
    return base * (1 - hole[..., None]) + pl * hole[..., None], hole

def affine(im, s, cx, cy, tx=None, ty=None, rot=0.0, size=(W, H), resample=Image.BILINEAR, fill=None):
    """Scale im by s (and rotate by rot degrees, counter-clockwise) about (cx, cy), landing that point at (tx, ty).
    im: PIL. Pixels from outside the source are fill (default transparent / black)."""
    tx = cx if tx is None else tx; ty = cy if ty is None else ty
    a = math.radians(rot)
    ca, sa = math.cos(a) / s, math.sin(a) / s
    # output (x, y) -> source: R(-rot)/s * (x - tx, y - ty) + (cx, cy)   (y down, so ccw on screen)
    co = (ca, -sa, cx - ca * tx + sa * ty, sa, ca, cy - sa * tx - ca * ty)
    kw = {}
    if fill is not None: kw["fillcolor"] = fill
    return im.transform(size, Image.AFFINE, co, resample, **kw)

def smooth_pulse(k, a, b, c_, d):
    """0 before a, eases up to 1 by b, holds, eases down to 0 between c_ and d (all fractions of the window)."""
    from core import ease_io
    if k <= a or k >= d: return 0.0
    if k < b: return ease_io((k - a) / (b - a))
    if k <= c_: return 1.0
    return ease_io((d - k) / (d - c_))

def pulse_speed(k, a, b, c_, d, dur):
    """|d/dt| of smooth_pulse in 1/seconds (for motion blur)."""
    if k <= a or k >= d: return 0.0
    if a < k < b:
        x = (k - a) / (b - a); return 6 * x * (1 - x) / ((b - a) * dur)
    if c_ < k < d:
        x = (d - k) / (d - c_); return 6 * x * (1 - x) / ((d - c_) * dur)
    return 0.0

def value_noise(w, h, cell, seed=0):
    """Smooth random field 0-1 of size h x w with features about `cell` px (seeded)."""
    rng = np.random.default_rng(seed)
    gw, gh = max(2, int(math.ceil(w / cell)) + 2), max(2, int(math.ceil(h / cell)) + 2)
    g = (rng.random((gh, gw)) * 255).astype(np.uint8)
    im = Image.fromarray(g, "L").resize((gw * cell, gh * cell), Image.BICUBIC)
    return np.asarray(im, np.float32)[:h, :w] / 255

def fbm(w, h, cell=180, octaves=4, seed=0):
    out = np.zeros((h, w), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        out += amp * value_noise(w, h, max(4, int(cell / 2 ** o)), seed + o * 17); tot += amp; amp *= 0.5
    return out / tot

def _disc(r):
    """Normalised disc kernel of radius r (px, fractional), anti-aliased edge."""
    n = int(math.ceil(r)) + 1
    y, x = np.mgrid[-n:n + 1, -n:n + 1].astype(np.float32)
    k = np.clip(r + 0.5 - np.sqrt(x * x + y * y), 0, 1)
    return k / k.sum()

def lens_blur(a, r, gamma=2.0, q_min=2.0):
    """Lens-style defocus: a disc kernel (bright points become soft discs) instead of a Gaussian. Done on a copy
    at least q_min times smaller, so it is fast at any radius. gamma > 1 lets highlights bloom like real bokeh.
    a: float32 HxWxC (0-255). Returns float32, same size."""
    from scipy.signal import fftconvolve
    h, w = a.shape[:2]
    if r < 0.5: return a
    q = max(q_min, r / 6.0)
    sw, sh = max(4, int(round(w / q))), max(4, int(round(h / q)))
    sm = np.asarray(pil(a).resize((sw, sh), Image.BOX if q >= 2 else Image.BILINEAR), np.float32) / 255
    if gamma != 1: sm = sm ** gamma
    k = _disc(r * sw / w)
    n = k.shape[0] // 2
    pad = np.pad(sm, ((n, n), (n, n), (0, 0)), mode="edge")
    out = fftconvolve(pad, k[..., None], mode="valid", axes=(0, 1))
    out = np.clip(out, 0, None)
    if gamma != 1: out = out ** (1 / gamma)
    out = (np.clip(out, 0, 1) * 255).astype(np.uint8)
    return np.asarray(Image.fromarray(out, "RGBA" if out.shape[2] == 4 else "RGB").resize((w, h), Image.BILINEAR), np.float32)

def defocus(a, r, gamma=2.0):
    """Smooth blur at any radius: a Gaussian for small radii, crossfading into lens_blur from r = 5 to 9."""
    if r < 0.4: return f32(a)
    if r <= 5: return blur(a, r * 0.6)
    lb = lens_blur(f32(a), r, gamma)
    if r >= 9: return lb
    w = (r - 5) / 4
    return blur(a, r * 0.6) * (1 - w) + lb * w

def soften_hole(c, rm, amount=1.0, dim=0.15, reach=70):
    """Where a worked-out plate stands in for the person, spread a wide, edgeless defocus (and a little darkness)
    over it, so the invented patch melts into the room instead of showing as a blurry silhouette. A real plate
    photo is left alone. rm: float32 room. Returns float32."""
    if c.p.get("plate") or amount <= 0: return rm
    st = c.state
    if "_soft_field" not in st:
        cv = cover(c.subj)
        D = blur(cv * 255, reach) / 255
        D = np.clip(np.maximum(D * 1.6, cv), 0, 1)
        st["_soft_field"] = D
    D = st["_soft_field"][..., None] * amount
    soft = blur(rm, 9)
    return (rm * (1 - D) + soft * D) * (1 - dim * D)
