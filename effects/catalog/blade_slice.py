"""Blade slice: a bright blade flashes diagonally across the frame, the picture splits along the cut and slides apart,
holds, then snaps back together with a little shake."""
import math
import numpy as np
from PIL import Image
from core import W, H, f32, to_pil, ease_out, ease_in, ease_io, prog, clamp, lerp, decay, hexc
from catalog._cam import affine, pil, blur

NAME = "blade-slice"
KIND = "camera"
ABOUT = "A blade flash slices the frame diagonally; the pieces slide apart, hold, then snap back with a shake"
DUR = 1.8
PARAMS = dict(
    angle=-24,        # the cut's angle from level (degrees; negative rises to the right)
    at=0.95,          # where it crosses: face-heights below the middle of your face (0 = through the eyes)
    pieces=2,         # 2, or 3 (two parallel cuts)
    gap=64,           # how far the pieces open (px)
    slide=120,        # how far they slide along the cut (px)
    tilt=1.4,         # how much each piece turns (degrees)
    color=None,       # blade glow colour; default the skin's accent
    shake=14,         # snap-back shake (px)
)

def _times(d):
    tb = clamp(0.1 * d, 0.1, 0.2)            # the blade crossing
    t_open = clamp(0.2 * d, 0.16, 0.36)
    t_close = clamp(0.08 * d, 0.08, 0.14)
    t_settle = clamp(0.2 * d, 0.2, 0.45)
    o0 = tb * 0.75
    c1 = d - t_settle                         # the impact
    c0 = c1 - t_close
    return tb, o0, t_open, c0, c1

def render(c):
    p = c.p
    d, u = c.d, c.u
    tb, o0, t_open, c0, c1 = _times(d)
    cx, cy, fw, fh = c.face
    ang = math.radians(float(p["angle"]))
    tx_, ty_ = math.cos(ang), math.sin(ang)              # along the cut
    nx, ny = -ty_, tx_                                    # across it (pointing to the lower piece)
    px, py = clamp(cx, W * 0.2, W * 0.8), clamp(cy + float(p["at"]) * fh, H * 0.2, H * 0.85)
    col = np.array(hexc(p["color"]) if p.get("color") else c.skin.accent, np.float32)
    npc = 3 if int(p["pieces"]) >= 3 else 2
    offs = [0.0] if npc == 2 else [-0.13 * H, 0.13 * H]
    # how open: eases open after the blade, holds, snaps shut (accelerating) at the impact
    if u < c0: op = ease_out(prog(u, o0, t_open))
    else: op = 1 - ease_in(prog(u, c0, c1 - c0))
    img = c.img
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    rx, ry = xx - px, yy - py
    s0 = rx * nx + ry * ny                                # across-the-cut coordinate in the frame
    a0 = rx * tx_ + ry * ty_                              # along-the-cut coordinate
    dark = np.array(c.skin.dark, np.float32) * 0.7
    out = np.empty((H, W, 3), np.float32); out[:] = dark
    glow = np.zeros((H, W), np.float32)
    if op > 1e-3:
        # the frame mirrored (and softened) past its edges, so a piece sliding in from the side brings picture with it
        P = int(float(p["slide"]) + float(p["gap"]) * (npc - 1) + 80)
        src = np.asarray(img, np.uint8)
        padded = np.pad(src, ((P, P), (P, P), (0, 0)), mode="reflect")
        key = ("edge", P)
        if key not in c.state:
            e = np.ones(padded.shape[:2], np.float32); e[P:P + H, P:P + W] = 0
            c.state[key] = np.clip(blur(e * 255, 30) / 255 * 1.6, 0, 1)[..., None]
        em = c.state[key]
        padded = f32(padded) * (1 - em) + blur(padded, 14) * 0.8 * em
        src_im = pil(padded)
        bounds = [-1e9] + offs + [1e9]
        for j in range(npc):
            sg = 1 if j % 2 == 0 else -1
            Tx = (tx_ * float(p["slide"]) * sg + nx * float(p["gap"]) * (j - (npc - 1) / 2)) * op
            Ty = (ty_ * float(p["slide"]) * sg + ny * float(p["gap"]) * (j - (npc - 1) / 2)) * op
            rot = float(p["tilt"]) * sg * op
            piece = np.asarray(affine(src_im, 1.0, px + P, py + P, px + Tx, py + Ty, rot,
                                      fill=tuple(int(v) for v in dark)), np.float32)
            # where this piece lands: its band of the cut coordinate, moved and turned with it
            ra = math.radians(rot)
            # source s = (R^-1 (p - P0 - T)) . n = (p - P0 - T) . (R n); R turns counter-clockwise on screen
            nrx = nx * math.cos(ra) + ny * math.sin(ra); nry = -nx * math.sin(ra) + ny * math.cos(ra)
            sj = (rx - Tx) * nrx + (ry - Ty) * nry
            lo, hi = bounds[j], bounds[j + 1]
            mk = np.clip(sj - lo + 0.5, 0, 1) * np.clip(hi - sj + 0.5, 0, 1)
            out = out * (1 - mk[..., None]) + piece * mk[..., None]
            # light along the cut edges, spilling into the gap
            for b in (lo, hi):
                if abs(b) > 1e8: continue
                dist = np.abs(sj - b)
                outside = ((sj - b) * (1 if b == hi else -1)) > 0
                glow += np.exp(-(dist / 9.0) ** 2) * outside + 0.35 * np.exp(-(dist / 2.0) ** 2) * (~outside)
    else:
        out = f32(np.asarray(img))
    # edge light: hot on the cut, a soft rim while open, a pulse on the impact
    hot = decay(u, o0, 7.0) * 1.2 + 0.35 * op + 1.4 * decay(u, c1, 9.0) * (u >= c1)
    if hot > 0.01 and op > 1e-3:
        g = np.clip(glow * hot, 0, 1.5)[..., None]
        out = out + g * (col * 0.85 + 255 * 0.15) * 0.9
    # the blade: a streak that crosses the whole frame along the cut, leaving a glowing seam that fades as it opens
    L = math.hypot(W, H) * 0.6
    if u < tb + 0.25:
        head = lerp(-L, L, ease_io(prog(u, 0, tb)))
        tail = 0.55 * L
        along = np.clip(1 - (head - a0) / tail, 0, 1) * (a0 <= head + 2)
        seam = clamp(1 - prog(u, tb, 0.25), 0, 1) * (1 - op * 0.6)
        streak = np.maximum(along ** 1.5, seam * (a0 <= head))
        for off in offs:
            dd = np.abs(s0 - off)
            core_ = np.exp(-(dd / 2.2) ** 2); halo = np.exp(-(dd / 16.0) ** 2) * 0.55 + np.exp(-(dd / 70.0) ** 2) * 0.18
            out = out + (streak * core_)[..., None] * 255 * 0.95 + (streak * halo)[..., None] * col * 1.1
    # a quick flash on the cut and on the impact
    fl = 0.18 * decay(u, tb * 0.6, 14) + 0.22 * decay(u, c1, 16) * (u >= c1)
    if fl > 0.01: out = out + (255 - out) * fl
    # the impact: a short shake and punch, gone by the last frame
    if u >= c1:
        k = decay(u, c1, 11.0) * (1 - prog(u, d - 0.06, 0.06))
        if k > 0.01:
            sh = float(p["shake"]) * k
            dx, dy = sh * math.sin((u - c1) * 95), sh * 0.7 * math.cos((u - c1) * 80)
            out = np.asarray(affine(pil(out), 1 + 0.025 * k, W / 2, H / 2, W / 2 + dx, H / 2 + dy), np.float32)
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.45,
}
