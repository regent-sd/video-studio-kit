"""Dolly zoom (the vertigo shot): you stay the same size while the room behind you stretches in (or out), then eases back."""
import math
import numpy as np
from PIL import Image
from core import W, H, f32, to_pil, vignette, clamp
from catalog._cam import room, tighten, stable_mask, affine, pil, blur, smooth_pulse, pulse_speed

NAME = "dolly-zoom"
KIND = "camera"
ABOUT = "Vertigo shot: you stay put while the room zooms in or out behind you, then eases back"
DUR = 2.5
PARAMS = dict(
    direction="in",   # in: the room rushes toward the camera (grows) | out: the room falls away (shrinks)
    amount=0.32,      # how far the room zooms at the peak (0.32 = 32 % bigger, or 1/1.32 smaller for "out")
    blur=1.0,         # radial motion blur on the room while it moves (0 = off)
    hold=0.16,        # share of the window it holds at the peak before easing back
    darken=0.22,      # extra vignette on the room at the peak (0 = off)
)
SAMPLES = 7           # radial-blur taps

def _scale(z, direction, amount):
    return 1 + amount * z if direction != "out" else 1 / (1 + amount * z)

def render(c):
    p = c.p
    amount = max(0.0, float(p["amount"]))
    hold = clamp(float(p["hold"]), 0.0, 0.6)
    a_end = (1 - hold) * 0.5
    z = smooth_pulse(c.k, 0.0, a_end, a_end + hold, 1.0)
    if z < 1e-3 or amount <= 0:
        return c.img
    out_dir = p["direction"] == "out"
    s = _scale(z, p["direction"], amount)
    cx, cy, fw, fh = c.face
    cx = clamp(cx, 0, W); cy = clamp(cy, 0, H)
    img = f32(np.asarray(c.img))
    mask = stable_mask(c)
    rm, hole = room(c, img, mask)
    # the room, zoomed about the face (mirror the frame past its edges when zooming out, softened)
    if out_dir:
        pad = int(math.ceil(max(cx, W - cx, cy, H - cy) * (1 / s - 1))) + 8
        src = np.pad(rm.astype(np.uint8), ((pad, pad), (pad, pad), (0, 0)), mode="reflect")
        edge = np.ones(src.shape[:2], np.float32); edge[pad:pad + H, pad:pad + W] = 0
        edge = blur(edge * 255, 40) / 255
        src = f32(src) * (1 - edge[..., None]) + blur(src, 18) * 0.72 * edge[..., None]
        src_im, ox, oy = pil(src), pad, pad
    else:
        src_im, ox, oy = pil(rm), 0, 0
    sharp = f32(np.asarray(affine(src_im, s, cx + ox, cy + oy, cx, cy)))
    # radial motion blur: average zooms spread over one frame's worth of scale change (done at half size)
    v = pulse_speed(c.k, 0.0, a_end, a_end + hold, 1.0, c.d) * amount     # d(scale)/dt, roughly
    streak = float(p["blur"]) * v / c.fps * 1.6                          # relative streak length this frame
    reach = max(cx, W - cx, cy, H - cy)
    w_blur = clamp(streak * reach / 7.0, 0, 1)
    if w_blur > 0.02:
        h2 = src_im.resize((src_im.width // 2, src_im.height // 2), Image.BILINEAR)
        acc = np.zeros((H // 2, W // 2, 3), np.float32)
        for j in range(SAMPLES):
            sj = s * (1 + streak * (j / (SAMPLES - 1) - 0.5))
            acc += np.asarray(affine(h2, sj, (cx + ox) / 2, (cy + oy) / 2, cx / 2, cy / 2, size=(W // 2, H // 2)), np.float32)
        soft = f32(np.asarray(pil(acc / SAMPLES).resize((W, H), Image.BILINEAR)))
        # keep the middle (near the face) crisp, streak toward the edges like a real zoom blur
        yy, xx = np.ogrid[0:H, 0:W]
        rr = np.sqrt(((xx - cx) / W) ** 2 + ((yy - cy) / W) ** 2).astype(np.float32)
        wmap = np.clip(rr / 0.35, 0, 1) * w_blur
        sharp = sharp * (1 - wmap[..., None]) + soft * wmap[..., None]
    if p["darken"] > 0:
        sharp = sharp * (1 - float(p["darken"]) * z * (1 - vignette(0.9, 0.75, round(cy / H, 2))))[..., None]
    m = tighten(mask, 0.16)[..., None]
    return to_pil(img * m + sharp * (1 - m))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.5,
    "needs": ["person"],
}
