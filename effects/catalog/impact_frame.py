"""Impact frame: you, redrawn as black-and-white comic ink, with speed lines bursting from your face and a big word."""
import math, functools
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
from core import W, H, f32, to_pil, text_img, scaled, comp, font, SFP, ease_out, prog, decay

NAME = "impact-frame"
KIND = "restyle"
ABOUT = "Black-and-white comic ink version of you with speed lines and a big word"
DUR = 1.6
PARAMS = dict(
    text=None,      # the big word; default the first key word you say in the window
    ink=0.5,        # line strength (0-1)
    paper="#F4F1E8",
)

@functools.lru_cache(4)
def _rays(cx, cy, seed=7):
    """Speed lines from (cx, cy): black wedges on paper, denser and longer toward the edges."""
    rng = np.random.default_rng(seed)
    im = Image.new("L", (W * 2, H * 2), 255)
    d = ImageDraw.Draw(im)
    R = 2.6 * max(W, H)
    for k in range(260):
        a = rng.uniform(0, 2 * math.pi)
        w = rng.uniform(0.002, 0.009)
        r0 = rng.uniform(0.18, 0.42) * max(W, H) * 2
        p = [(cx * 2 + math.cos(a) * r0, cy * 2 + math.sin(a) * r0),
             (cx * 2 + math.cos(a - w) * R, cy * 2 + math.sin(a - w) * R),
             (cx * 2 + math.cos(a + w) * R, cy * 2 + math.sin(a + w) * R)]
        d.polygon(p, fill=0)
    return np.asarray(im.resize((W, H), Image.LANCZOS), np.float32) / 255

@functools.lru_cache(2)
def _hatch(spacing=7):
    y, x = np.mgrid[0:H, 0:W]
    return (((x + y) % spacing) < 2).astype(np.float32)

def render(c):
    st = c.state
    if "rays" not in st:
        cx, cy, fw, fh = c.face
        st["rays"] = _rays(int(cx // 8 * 8), int(cy // 8 * 8))
        st["word"] = c.word_text().upper()
    paper = np.array([int(c.p["paper"][i:i + 2], 16) for i in (1, 3, 5)], np.float32)
    g = f32(c.src).mean(2)
    # ink lines: difference of gaussians
    gi = Image.fromarray(g.astype(np.uint8), "L")
    b1 = np.asarray(gi.filter(ImageFilter.GaussianBlur(1.4)), np.float32)
    b2 = np.asarray(gi.filter(ImageFilter.GaussianBlur(4.0)), np.float32)
    dog = b1 - b2
    line = np.clip((-dog - 2.0) * (0.12 + 0.25 * c.p["ink"]), 0, 1)
    # three tones: paper, hatching, solid black
    gs = b2
    lo, hi = np.percentile(gs[c.mask > 0.5], [22, 58]) if (c.mask > 0.5).any() else (70, 140)
    tone = np.where(gs < lo, 0.0, np.where(gs < hi, 1 - _hatch(), 1.0))
    ink = np.clip(tone - line, 0, 1)
    person = ink[..., None] * paper[None, None, :] + (1 - ink[..., None]) * np.array([14, 14, 16], np.float32)
    # room: paper with speed lines; the bottom third is black with white streaks for the word
    rays = st["rays"]
    room = rays[..., None] * paper[None, None, :] + (1 - rays[..., None]) * 14
    yb = int(H * 0.70)
    streak = 1 - rays[yb:]
    room[yb:] = streak[..., None] * paper * 0.9 + (1 - streak[..., None]) * 10
    m = c.mask[..., None]
    out = person * m + room * (1 - m)
    # the word, slammed in
    u = c.u
    im = to_pil(out).convert("RGBA")
    wd = st["word"]
    if wd:
        t = text_img(wd, 260, 900, (255, 255, 255), 0, SFP, 0, 14, (12, 12, 14))
        s = min(1.0, W * 0.9 / t.width) * (1.35 - 0.35 * ease_out(u / 0.18))
        t = scaled(t, s)
        comp(im, t, W / 2 - t.width / 2, H * 0.78 - t.height / 2)
    im = im.convert("RGB")
    # a punch: white flash and a shake on the first frames, then a slow push in
    z = 1.0 + 0.05 * (1 - ease_out(u / 0.3)) + 0.02 * u
    if z > 1.001:
        zw, zh = int(W / z), int(H / z)
        dx = int(10 * decay(u, 0, 18) * math.sin(u * 90)); dy = int(8 * decay(u, 0, 18) * math.cos(u * 77))
        x0 = (W - zw) // 2 + dx; y0 = (H - zh) // 2 + dy
        im = im.crop((x0, y0, x0 + zw, y0 + zh)).resize((W, H), Image.BICUBIC)
    fl = decay(u, 0, 14)
    if fl > 0.02:
        a = np.asarray(im, np.float32); im = to_pil(a + (255 - a) * fl * 0.85)
    return im

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your own (the first key word you say in the window)",
    "needs": ["person"],
}
