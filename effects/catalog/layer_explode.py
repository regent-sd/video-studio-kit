"""Layer explode: the shot comes apart into stacked 3D layers (room, you, a word) that spread in depth and turn, then
fly back together."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, f32, to_pil, ease_io, prog, clamp, lerp, hexc, text_img, scaled, comp, warp_to, rounded, radial)
from catalog._cam import room, stable_mask, tighten, soften_hole, pil

NAME = "layer-explode"
KIND = "camera"
ABOUT = "The shot splits into 3D layers (room, you, a word) that spread apart and turn, then fly back together"
DUR = 3.5
PARAMS = dict(
    text=None,        # the word on the front layer; default the first key word you say in the window
    turn=38,          # how far the stack turns sideways (degrees)
    tilt=16,          # how far it tips (degrees; we look down on it a little)
    spread=700,       # gap between layers at full size (px)
    size=0.5,         # how big the stack is while apart (share of the frame)
    color=None,       # word colour; default the skin's accent
)
F = 1700.0

def _amount(c):
    """0 -> 1 (apart) -> 0, plus the hold's progress for a slow drift."""
    d = c.d
    t_in = min(0.9, d * 0.3); t_out = min(0.8, d * 0.26)
    a = ease_io(prog(c.u, 0, t_in))
    b = ease_io(prog(c.u, d - t_out - min(0.08, d * 0.03), t_out))
    hold = prog(c.u, t_in * 0.6, max(0.1, d - t_out - t_in * 0.6))
    return min(a, 1 - b), hold

def _corners(w, h, gs, zl, ry, rx, gcx, gcy):
    """Screen corners (TL, TR, BR, BL) of a w x h layer pushed zl along the stack's axis, after turning the stack."""
    cr, sr = math.cos(math.radians(ry)), math.sin(math.radians(ry))
    cx_, sx_ = math.cos(math.radians(rx)), math.sin(math.radians(rx))
    pts, zs = [], []
    for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        x, y, z = x * gs, y * gs, zl * gs
        X = x * cr + z * sr; Z = -x * sr + z * cr
        Y = y * cx_ - Z * sx_; Z = y * sx_ + Z * cx_
        k = F / (F + Z)
        pts.append((gcx + X * k, gcy + Y * k)); zs.append(Z)
    return pts, sum(zs) / 4

def _outline(alpha, r=36):
    """A thin light frame round the whole layer (shows each sheet's edge)."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([2, 2, W - 3, H - 3], radius=r, outline=(255, 255, 255, int(255 * alpha)), width=5)
    return im

def _text_layer(c):
    """The word, big, on a clear sheet the size of the frame (placed above your head, or low if there's no room)."""
    txt = c.word_text().upper()
    col = hexc(c.p["color"]) if c.p.get("color") else tuple(c.skin.accent)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    if not txt: return lay
    path, idx, wt = c.skin["title"]
    t = text_img(txt, 260, wt, col, 0, path, idx)
    t = scaled(t, min(1.0, W * 0.84 / t.width))
    cx, cy, fw, fh = c.face
    top = cy - fh * 0.9
    y = top - t.height * 0.5 - 60 if top - t.height - 80 > 140 else min(H - 260, cy + fh * 2.4)
    sh = text_img(txt, 260, wt, (0, 0, 0), 0, path, idx)
    sh = scaled(sh, t.width / sh.width)
    a = sh.getchannel("A").point(lambda v: int(v * 0.45)); sh.putalpha(a)
    comp(lay, sh, W / 2 - t.width / 2 + 6, y - t.height / 2 + 10)
    comp(lay, t, W / 2 - t.width / 2, y - t.height / 2)
    return lay

def _prep(im, gs):
    """Shrink a layer close to its on-screen size first, so the perspective warp doesn't shimmer."""
    if gs < 0.92:
        return im.resize((max(8, int(W * gs * 1.08)), max(8, int(H * gs * 1.08))), Image.LANCZOS)
    return im

def render(c):
    st = c.state
    e, hold = _amount(c)
    m = stable_mask(c)
    if e < 2e-3:
        return c.img
    p = c.p
    if "text" not in st:
        st["text"] = _text_layer(c)
    img = f32(np.asarray(c.img))
    gs = lerp(1.0, float(p["size"]), e)
    ry = -float(p["turn"]) * e - 7 * hold * e
    rx = float(p["tilt"]) * e
    sep = float(p["spread"]) * e
    gcx, gcy = W / 2, H / 2
    # the layers: the room (with you taken out), you, the word
    rm, _ = room(c, img, m, grow_px=26, feather=26, dim=0.3, soften=10)
    rm = soften_hole(c, rm, e, 0.1)
    room_im = Image.fromarray(np.clip(rm, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    you = np.dstack([np.asarray(c.img), (tighten(m, 0.1) * 255).astype(np.uint8)])
    you_im = Image.fromarray(you, "RGBA")
    frame_a = clamp(e * 2.2, 0, 1)
    if "outline" not in st: st["outline"] = _outline(1.0)
    ol = st["outline"].copy(); ol.putalpha(ol.getchannel("A").point(lambda v: int(v * 0.45 * frame_a)))
    tint = Image.new("RGBA", (W, H), (255, 255, 255, int(8 * frame_a)))
    you_im = Image.alpha_composite(Image.alpha_composite(tint, you_im), ol)
    txt_im = st["text"].copy()
    txt_im.putalpha(txt_im.getchannel("A").point(lambda v: int(v * clamp(e * 1.6 - 0.2, 0, 1))))
    txt_im = Image.alpha_composite(Image.alpha_composite(tint, txt_im), ol)
    ol2 = st["outline"].copy(); ol2.putalpha(ol2.getchannel("A").point(lambda v: int(v * 0.35 * frame_a)))
    room_im = Image.alpha_composite(room_im, ol2)
    layers = [(room_im, sep * 1.0), (you_im, 0.0), (txt_im, -sep * 0.9)]
    # the background: dark, lit a little from the middle
    if "bg" not in st:
        st["bg"] = radial(W, H, c.skin.dark2, tuple(int(v * 0.5) for v in c.skin.dark), 0.5, 0.45, 1.05)
    cv = st["bg"].copy()
    rad = 40 * e
    # centre the whole stack in the frame (the near layer is bigger, so it would sit off to one side)
    allp = [q for _, zl in layers for q in _corners(W, H, gs, zl, ry, rx, 0, 0)[0]]
    xs, ys = [q[0] for q in allp], [q[1] for q in allp]
    gcx -= (min(xs) + max(xs)) / 2; gcy -= (min(ys) + max(ys)) / 2
    drawn = []
    for im, zl in layers:
        pts, zc = _corners(W, H, gs, zl, ry, rx, gcx, gcy)
        drawn.append((zc, im, pts))
    for zc, im, pts in sorted(drawn, key=lambda r: -r[0]):          # far to near
        src = _prep(im, gs)
        if rad > 1: src = rounded(src, rad * src.width / W)
        warp_to(cv, src, pts, 1.0, shadow=0.45 * e, shadow_dy=int(30 * e))
    out = np.asarray(cv.convert("RGB"), np.float32)
    # the first and last frames: straight back to the video
    k = clamp(e * 25, 0, 1)
    if k < 1: out = out * k + img * (1 - k)
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your own (the first key word you say in the window)",
    "still": 0.5,
    "needs": ["person"],
}
