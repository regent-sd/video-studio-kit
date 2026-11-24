"""Blow away (the snap): you crumble into dust from one side and drift off on the wind, leaving the empty room; then you
reassemble so the video carries on."""
import math
import numpy as np
from PIL import Image
from core import W, H, f32, to_pil, ease_io, ease_out, clamp, clamp01
from catalog._cam import room, stable_mask, fbm, blur, pil, soften_hole

NAME = "blow-away"
KIND = "camera"
ABOUT = "You crumble into dust and blow away, leaving the empty room, then reassemble"
DUR = 4.0
PARAMS = dict(
    back=True,        # reassemble near the end (False: stay gone to the end of the window, e.g. the last shot of a video)
    side="right",     # where the crumbling starts: right | left | top
    wind=1.0,         # how hard the dust blows (to the right and up)
    grain=3,          # dust size: one speck per grain x grain px of you (2 = finer and slower, 4 = coarser)
    plate=None,       # a photo of the empty set (same framing) for a clean room; default: worked out from the video
    dim=0.35,         # how much the worked-out room behind you is darkened (ignored with a real plate photo)
)
ASH = np.array([128, 120, 112], np.float32)

def _times(c):
    """(dissolve start, dissolve end, reassemble start, reassemble end) in seconds into the window."""
    d = c.d
    a0 = min(0.1 * d, 0.35)
    a1 = a0 + clamp(0.4 * d, 0.5, 1.8)                 # gone by about mid-window
    life = clamp(0.32 * d, 0.45, 1.5)                  # how long a speck lasts
    if c.p.get("back", True):
        r1 = d - min(0.06 * d, 0.25)
        r0 = r1 - clamp(0.33 * d, 0.5, 1.6)
        r0 = max(r0, a1 + 0.1 * d)
    else:
        r0 = r1 = d + 1
    return a0, a1, r0, r1, life

def _front_map(c, mask, seed):
    """When each pixel goes (0 first .. 1 last): a sweep across you from one side, ragged with noise."""
    q = 4
    sm = np.asarray(pil(mask * 255).resize((W // q, H // q), Image.BOX), np.float32) / 255
    ys, xs = np.nonzero(sm > 0.4)
    if len(xs) == 0:
        x0, x1, y0, y1 = 0, W, 0, H
    else:
        x0, x1, y0, y1 = xs.min() * q, (xs.max() + 1) * q, ys.min() * q, (ys.max() + 1) * q
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    side = c.p.get("side", "right")
    if side == "left": lin = (xx - x0) / max(1, x1 - x0)
    elif side == "top": lin = (yy - y0) / max(1, y1 - y0)
    else: lin = (x1 - xx) / max(1, x1 - x0)
    lin = np.clip(lin, 0, 1)
    big = fbm(W, H, 240, 3, seed)
    mid = fbm(W, H, 40, 2, seed + 50)
    grain = np.random.default_rng(seed + 99).random((H, W)).astype(np.float32)
    t = 0.62 * lin + 0.22 * big + 0.08 * mid + 0.08 * grain        # a ragged front that breaks into grains
    lo, hi = np.percentile(t[mask > 0.5], [1, 99]) if (mask > 0.5).any() else (t.min(), t.max())
    return np.clip((t - lo) / max(1e-3, hi - lo), 0, 1).astype(np.float32)

def _specks(c, img, mask, tmap, seed):
    """One speck per grain x grain px of you, coloured from this frame."""
    g = int(clamp(int(c.p["grain"]), 2, 6))
    rng = np.random.default_rng(seed)
    ys, xs = np.mgrid[0:H:g, 0:W:g]
    ys = ys.ravel() + rng.integers(0, g, ys.size); xs = xs.ravel() + rng.integers(0, g, xs.size)
    ys = np.clip(ys, 0, H - 1); xs = np.clip(xs, 0, W - 1)
    keep = mask[ys, xs] > rng.uniform(0.35, 0.65, ys.size)
    ys, xs = ys[keep], xs[keep]
    n = len(xs)
    wind = float(c.p["wind"])
    sp = dict(
        x=xs.astype(np.float32), y=ys.astype(np.float32), col=img[ys, xs].astype(np.float32), T=tmap[ys, xs],
        vx=rng.uniform(40, 240, n).astype(np.float32) * wind, vy=rng.uniform(-220, -30, n).astype(np.float32) * wind,
        ax=rng.uniform(120, 520, n).astype(np.float32) * wind, ay=rng.uniform(-300, -60, n).astype(np.float32) * wind,
        ph=rng.uniform(0, 2 * math.pi, (2, n)).astype(np.float32), om=rng.uniform(3, 9, (2, n)).astype(np.float32),
        turb=rng.uniform(10, 45, n).astype(np.float32), lf=rng.uniform(0.6, 1.0, n).astype(np.float32),
        big=(rng.random(n) < 0.3),
    )
    # a fifth of the dust floats: slower, longer-lived and fainter, a haze that hangs where you stood
    fl = rng.random(n) < 0.2
    for k in ("vx", "vy", "ax", "ay"): sp[k][fl] *= 0.3
    sp["lf"][fl] *= 2.4
    sp["big"][fl] = False
    sp["w"] = np.where(fl, 0.55, 1.0).astype(np.float32)
    return sp

def _splat(sp, age, life):
    """Specks at this age (seconds since each left, or until each lands) -> (rgb sum, weight) frame-size arrays."""
    L = life * sp["lf"]
    vis = (age >= 0) & (age < L)
    if not vis.any():
        return None
    a = age[vis]; Lv = L[vis]
    x = sp["x"][vis] + sp["vx"][vis] * a + 0.5 * sp["ax"][vis] * a * a + sp["turb"][vis] * a * np.sin(sp["om"][0][vis] * a + sp["ph"][0][vis])
    y = sp["y"][vis] + sp["vy"][vis] * a + 0.5 * sp["ay"][vis] * a * a + sp["turb"][vis] * a * np.cos(sp["om"][1][vis] * a + sp["ph"][1][vis])
    fade = np.clip(1 - a / Lv, 0, 1) ** 1.6 * sp["w"][vis]
    ash = np.clip(a / Lv, 0, 1)[:, None] * 0.5
    col = (sp["col"][vis] * 1.08 + 6) * (1 - ash) + ASH * ash      # catches the light, then greys to ash
    big = sp["big"][vis]
    rgb = np.zeros((H * W, 3), np.float32); wsum = np.zeros(H * W, np.float32)
    # small specks: bilinear splat (smooth sub-pixel motion); big flakes: 2x2 px
    for sel, scale in ((~big, 1.0), (big, 2.2)):
        if not sel.any(): continue
        xs, ys, f, cl = x[sel], y[sel], fade[sel] * scale, col[sel]
        x0 = np.floor(xs).astype(np.int64); y0 = np.floor(ys).astype(np.int64)
        fx = xs - x0; fy = ys - y0
        offs = [(0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)]
        if scale > 1:
            offs += [(2, 0, (1 - fy) * fx * 0.5), (2, 1, fy * fx * 0.5), (0, 2, (1 - fx) * fy * 0.5), (1, 2, fx * fy * 0.5)]
        for dx, dy, wgt in offs:
            xi, yi = x0 + dx, y0 + dy
            ok = (xi >= 0) & (xi < W) & (yi >= 0) & (yi < H)
            if not ok.any(): continue
            idx = (yi[ok] * W + xi[ok])
            ww = (wgt * f)[ok]
            wsum += np.bincount(idx, ww, H * W).astype(np.float32)
            for ch in range(3):
                rgb[:, ch] += np.bincount(idx, ww * cl[ok, ch], H * W).astype(np.float32)
    return rgb.reshape(H, W, 3), wsum.reshape(H, W)

def _front(u, t0, t1, ws, rev):
    """The sweep's position at u (0 .. 1 + ws), eased; rev runs it backwards (reassembly)."""
    e = ease_io(clamp01((u - t0) / max(1e-3, t1 - t0)))
    return ((1 - e) if rev else e) * (1 + ws)

def _cross(T, t0, t1, ws, rev):
    """When the sweep passes each speck's spot (seconds into the window), from a lookup of the eased curve."""
    us = np.linspace(t0, t1, 256)
    pf = np.array([_front(x, t0, t1, ws, rev) for x in us])
    target = np.clip(T + ws * 0.5, 0, 1 + ws)
    if rev: return np.interp(target, pf[::-1], us[::-1]).astype(np.float32)
    return np.interp(target, pf, us).astype(np.float32)

def render(c):
    st = c.state
    a0, a1, r0, r1, life = _times(c)
    u = c.u
    if u < a0 or u >= r1:
        return c.img
    img = f32(np.asarray(c.img))
    m = stable_mask(c)
    ws = 0.035
    # which way we're going: out (crumbling) or back (reassembling); each captures its dust from the frame it starts on
    rev = u >= r0
    key = "back" if rev else "out"
    if key not in st:
        seed = 11 + (7 if rev else 0)
        tm = _front_map(c, m, seed)
        sp = _specks(c, img, m, tm, seed)
        sp["tc"] = _cross(sp["T"], r0 if rev else a0, r1 if rev else a1, ws, rev)
        st[key] = dict(tmap=tm, specks=sp)
    tm, sp = st[key]["tmap"], st[key]["specks"]
    pf = _front(u, r0, r1, ws, True) if rev else _front(u, a0, a1, ws, False)
    body = m * np.clip((tm - pf) / ws + 1, 0, 1)            # what's left of you (or what's back)
    age = (sp["tc"] - u) if rev else (u - sp["tc"])         # seconds since a speck left / until it lands
    rm, hole = room(c, img, m, grow_px=30, feather=30, dim=float(c.p["dim"]), soften=12)
    gone = float(np.clip(1 - body.sum() / max(1.0, m.sum()), 0, 1))
    rm = soften_hole(c, rm, gone, 0.12)
    out = rm * (1 - body[..., None]) + img * body[..., None]
    res = _splat(sp, age, life)
    if rev and "out" in st:
        # the last of the outgoing dust keeps drifting off while the new dust comes in
        so = st["out"]["specks"]
        r2 = _splat(so, u - so["tc"], life)
        fade = 1 - ease_io(clamp01((u - r0) / max(1e-3, (r1 - r0) * 0.7)))   # gone before the end: no pop
        if r2 is not None and fade > 0.01:
            r2 = (r2[0] * fade, r2[1] * fade)
            res = r2 if res is None else (res[0] + r2[0], res[1] + r2[1])
    if res is not None:
        rgb, wsum = res
        pa = np.clip(wsum * 1.7, 0, 1)[..., None]
        pc = rgb / np.maximum(wsum, 1e-4)[..., None]
        out = out * (1 - pa) + pc * pa
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.5,
    "needs": ["person"],
}
