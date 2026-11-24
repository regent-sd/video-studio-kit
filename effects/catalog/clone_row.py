"""Clone row: copies of you slide out from behind you and line up on both sides, smaller and darker into the distance."""
import numpy as np
from PIL import Image, ImageFilter
from core import W, H, f32, to_pil, ease_out, ease_io, prog, clamp, lerp, hexc
from catalog._cam import stable_mask, tighten, affine, pil, blur

NAME = "clone-row"
KIND = "camera"
ABOUT = "Copies of you slide out from behind you and recede into the distance on both sides"
DUR = 3.5
PARAMS = dict(
    copies=3,         # copies on each side (1-4)
    sides="both",     # both | left | right
    delay=4,          # frames between one copy and the next (each copy moves a moment after the one in front)
    spacing=0.21,     # gap from you to the first copy, as a share of the frame width
    depth=0.36,       # how quickly they shrink into the distance
    fade=0.20,        # how much darker each copy gets
    rise=0.0,         # lift each copy this share of your face height (0 = eyes on one line, like a real row)
    dim_room=0.18,    # how much the room darkens while the clones are out
)
Q = 2                 # the clones are drawn at half size (they're behind you, darker and a touch soft)

def _ring(c, mask):
    """Keep the last few frames at half size: (rgb uint8, cutout uint8, face)."""
    st = c.state
    n = int(clamp(int(c.p["copies"]), 1, 4)) * max(1, int(c.p["delay"])) + 1
    ring = st.setdefault("ring", [])
    if ring and ring[-1][3] == c.i: return ring
    rgb = np.asarray(Image.fromarray(np.asarray(c.img)).resize((W // Q, H // Q), Image.BILINEAR))
    m = tighten(mask, 0.12)
    al = np.asarray(pil(m * 255).resize((W // Q, H // Q), Image.BILINEAR))
    ring.append((rgb, al, c.face, c.i))
    del ring[:-n]
    return ring

def _slide(c, j, n):
    """0 (hidden behind you) -> 1 (in place) -> 0, staggered: the nearest copy leads out, the farthest leads back."""
    d = c.d
    t_out = min(0.55, d * 0.22)
    st = min(0.07, d * 0.025)
    a = ease_out(prog(c.u, (j - 1) * st, t_out))
    b = ease_io(prog(c.u, d - t_out - (n - j) * st - 0.02, t_out))
    return min(a, 1 - b)

def render(c):
    p = c.p
    mask = stable_mask(c)
    ring = _ring(c, mask)
    n = int(clamp(int(p["copies"]), 1, 4))
    dly = max(1, int(p["delay"]))
    sides = {"left": [-1], "right": [1]}.get(p["sides"], [-1, 1])
    if max(_slide(c, j, n) for j in range(1, n + 1)) < 1e-3:
        return c.img
    cx, cy, fw, fh = c.face
    dz = max(0.05, float(p["depth"]))
    sp = float(p["spacing"]) * W
    fog = np.array(c.skin.dark, np.float32)
    w2, h2 = W // Q, H // Q
    acc = np.zeros((h2, w2, 3), np.float32); A = np.zeros((h2, w2), np.float32)
    # farthest first, so nearer copies cover farther ones
    for j in range(n, 0, -1):
        e = _slide(c, j, n)
        if e < 1e-3: continue
        rgb, al, (fx, fy, ffw, ffh), _ = ring[max(0, len(ring) - 1 - j * dly)]
        s_end = 1 / (1 + j * dz)
        off = sp * (1 + dz) * j / (1 + j * dz)
        for sd in sides:
            # keep the face of the farthest copy inside the frame on a narrow side
            room = (cx - 0.05 * W) if sd < 0 else (0.95 * W - cx)
            far = sp * (1 + dz) * n / (1 + n * dz)
            k_fit = min(1.0, max(0.35, room / far)) if far > 0 else 1.0
            tx = cx + sd * off * k_fit * e
            ty = cy - float(p["rise"]) * fh * j * e
            s = lerp(0.97, s_end, ease_out(e))
            src = np.dstack([rgb, al])
            im = affine(Image.fromarray(src, "RGBA"), s, fx / Q, fy / Q, tx / Q, ty / Q, size=(w2, h2))
            a4 = np.asarray(im, np.float32)
            a = a4[..., 3] / 255
            # fade the copy out toward its own bottom edge (the source frame ends there)
            bottom = (ty + (H - fy) * s) / Q
            yy = np.arange(h2, dtype=np.float32)[:, None]
            ramp = np.clip((bottom - yy) / (0.28 * (H - fy) * s / Q + 1), 0, 1) ** 1.3
            a = a * ramp * min(1.0, e * 2.5)
            # darker and foggier with distance
            br = clamp(1 - float(p["fade"]) * j, 0.15, 1)
            col = a4[..., :3] * br + fog * (1 - br) * 0.6
            # a soft shadow from this copy onto the ones behind it
            sh = blur(a * 255, 10) / 255
            acc *= (1 - 0.35 * sh)[..., None]
            acc = acc * (1 - a[..., None]) + col * a[..., None]
            A = A * (1 - a) + a
    # up to full size, a touch soft (depth of field)
    lay = np.dstack([acc, A * 255])
    lay = blur(lay, 1.2)
    lay = np.asarray(pil(lay).resize((W, H), Image.BILINEAR), np.float32)
    La = np.clip(lay[..., 3:4] / 255, 0, 1)
    img = f32(np.asarray(c.img))
    env = max(_slide(c, j, n) for j in range(1, n + 1))
    roomk = 1 - float(p["dim_room"]) * env
    back = img * roomk * (1 - La) + lay[..., :3]
    # your own shadow on the first clones, then you on top
    m = mask
    sh = blur(m * 255, 22) / 255
    back = back * (1 - 0.3 * sh * La[..., 0])[..., None]
    mm = tighten(m, 0.1)[..., None]          # pull the soft edge in so the old room doesn't rim you over the clones
    return to_pil(img * mm + back * (1 - mm))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.55,
    "needs": ["person"],
}
