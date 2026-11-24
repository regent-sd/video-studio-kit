"""Digital zoom: a camcorder-style punch-in to your face in quick steps (1.0x, then 1.4x, then 2.0x), each landing with a
tiny overshoot and a one-frame digital glitch (blocky resample, colour fringe, over-sharpening), under a minimal
viewfinder HUD (corner brackets, a REC dot with the real elapsed time, a zoom bar with the real zoom factor).
It eases back out at the end."""
import math
import numpy as np
from PIL import Image, ImageFilter
from core import (W, H, FPS, SS, f32, to_pil, font, SFP, SFMONO, text_img, ease_out, ease_io, prog, clamp, clamp01,
                  hexc, soft_shadow, comp)
from catalog._cam2 import pixelate, block_cells, chroma, sharpen

NAME = "digital-zoom"
KIND = "camera"
ABOUT = "Camcorder digital punch-in to your face in quick steps, with a glitch on each step and a REC viewfinder"
DUR = 3.5
PARAMS = dict(
    steps=2,          # how many zoom jumps on the way in (1-4)
    max=2.0,          # the zoom it ends on (2.0 = twice as close)
    hud=True,         # the viewfinder: corner brackets, REC dot with the real time, zoom bar with the real zoom factor
    glitch=1.0,       # strength of the one-frame digital glitch on each jump (0 = none)
    color=None,       # HUD colour; default white
)
OVERSHOOT = 0.14       # share of each jump it overshoots before settling
INSET, TOP, BOT = 62, 196, 1496   # viewfinder brackets (px)
BAR_Y, BAR_W = 1392, 420

def _plan(c):
    """Jump start times (s into the effect), log-zoom levels, and the zoom-out start."""
    d = c.d
    n = int(clamp(int(c.p["steps"]), 1, 4))
    mx = max(1.05, float(c.p["max"]))
    a = clamp(0.12 * d, 0.15, 0.45)
    gap = clamp((0.5 * d - a) / n, 0.3, 1.1)
    times = [a + j * gap for j in range(n)]
    levels = [math.log(mx) * j / n for j in range(n + 1)]
    t_out = clamp(0.2 * d, 0.3, 0.8)
    return times, levels, d - t_out, t_out

def _lz(c, u):
    """Log of the zoom at u seconds into the effect."""
    times, levels, o0, t_out = _plan(c)
    lz = 0.0
    for j, tj in enumerate(times):
        if u < tj: break
        l0, l1 = levels[j], levels[j + 1]
        x = u - tj + 1.0 / FPS                          # the jump's first frame already moves
        if x < 0.1:                                     # snap (3 frames), past the target
            lz = l0 + (l1 - l0) * (1 + OVERSHOOT) * ease_out(x / 0.1)
        else:                                           # settle back
            lz = l1 + (l1 - l0) * OVERSHOOT * (1 - ease_io((x - 0.1) / 0.16))
    return lz * (1 - ease_io(prog(u, o0, t_out)))

def _glitch_at(c):
    """(strength 0-1, which jump, frames since it) for the digital glitch on the frames right after a jump."""
    times, _, _, _ = _plan(c)
    for j, tj in enumerate(times):
        n = int(math.floor((c.u - tj) * FPS + 1e-6))
        if 0 <= n < 2:
            return (1.0, 0.45)[n], j, n
    return 0.0, 0, 0

def _hud_static(col):
    """Brackets, the zoom bar's track and its W / T ends: drawn once."""
    s = SS(W, H)
    a = 235
    arm, sw = 74, 5
    for x, y, dx, dy in ((INSET, TOP, 1, 1), (W - INSET, TOP, -1, 1), (INSET, BOT, 1, -1), (W - INSET, BOT, -1, -1)):
        s.line([(x + dx * arm, y), (x, y), (x, y + dy * arm)], col + (a,), sw)
    x0, x1 = W / 2 - BAR_W / 2, W / 2 + BAR_W / 2
    s.text((x0 - 34, BAR_Y), "W", 34, 760, fill=col + (a,), anchor="rm", path=SFP)
    s.text((x1 + 34, BAR_Y), "T", 34, 760, fill=col + (a,), anchor="lm", path=SFP)
    s.rr((x0, BAR_Y - 3, x1, BAR_Y + 3), 3, fill=col + (90,))
    for k in range(11):
        x = x0 + BAR_W * k / 10
        s.line([(x, BAR_Y - (13 if k % 5 == 0 else 8)), (x, BAR_Y + (13 if k % 5 == 0 else 8))], col + (150,), 2.4,
               round_caps=False)
    im = s.out()
    sh = soft_shadow(im, 0.55, 6, pad=40, q=2)
    out = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    comp(out, sh, -40, -38)
    out.alpha_composite(im)
    return out

def _shadowed(txt, size, weight, col, path):
    t = text_img(txt, size, weight, col, 0, path)
    sh = text_img(txt, size, weight, (0, 0, 0), 0, path)
    out = Image.new("RGBA", (t.width + 6, t.height + 6), (0, 0, 0, 0))
    sa = sh.copy(); sa.putalpha(sa.getchannel("A").point(lambda v: v * 120 // 255))
    out.alpha_composite(sa, (3, 4)); out.alpha_composite(t, (0, 0))
    return out

def _hud(c, img, z, a):
    st = c.state
    col = hexc(c.p["color"]) if c.p.get("color") else (255, 255, 255)
    if "hud" not in st: st["hud"] = _hud_static(col)
    cv = img.convert("RGBA")
    lay = st["hud"]
    if a < 0.999:
        lay = lay.copy(); lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
    cv.alpha_composite(lay)
    dyn = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # REC: a red dot that blinks once a second, and the real elapsed time of the video
    x, y = INSET + 40, TOP + 62
    s = SS(40, 40)
    if (c.t % 1.0) < 0.62:
        s.circ(20, 20, 13, fill=(255, 59, 48, 255))
    comp(dyn, s.out(), x - 20, y - 20)
    comp(dyn, _shadowed("REC", 38, 800, col, SFP), x + 26, y - 19)
    sec = int(c.t)
    tc = f"{sec // 3600:02d}:{sec // 60 % 60:02d}:{sec % 60:02d}"
    t = _shadowed(tc, 38, 600, col, SFMONO)
    comp(dyn, t, W - INSET - 40 - t.width, y - 19)
    # the zoom bar: filled from W up to the real zoom, with the factor over the marker
    mx = max(1.05, float(c.p["max"]))
    k = clamp01(math.log(max(1.0, z)) / math.log(mx))
    x0 = W / 2 - BAR_W / 2
    xm = x0 + BAR_W * k
    b = SS(BAR_W + 40, 60)
    if xm - x0 > 2: b.rr((20, 27, 20 + xm - x0, 33), 3, fill=col + (255,))
    b.rr((20 + xm - x0 - 5, 8, 20 + xm - x0 + 5, 52), 4, fill=col + (255,))
    comp(dyn, b.out(), x0 - 20, BAR_Y - 30)
    lab = _shadowed(f"{z:.1f}×", 40, 700, col, SFMONO)
    comp(dyn, lab, xm - lab.width / 2, BAR_Y - 36 - lab.height)
    if a < 0.999: dyn.putalpha(dyn.getchannel("A").point(lambda v: int(v * a)))
    cv.alpha_composite(dyn)
    return cv.convert("RGB")

def render(c):
    p, st = c.p, c.state
    lz = _lz(c, c.u)
    z = math.exp(lz)
    hud_a = c.env(0.22, 0.28) if p.get("hud", True) else 0.0
    if z < 1.0005 and hud_a < 0.003:
        return c.img
    # the zoom centre follows the face (a little below the eyes), smoothly, kept inside the frame
    cx, cy, fw, fh = c.face
    tx, ty = cx, cy + fh * 0.12
    if "cxy" in st:
        px, py = st["cxy"]; tx, ty = px + (tx - px) * 0.25, py + (ty - py) * 0.25
    st["cxy"] = (tx, ty)
    out = c.img
    if z > 1.0005:
        hw, hh = W / 2 / z, H / 2 / z
        zx, zy = clamp(tx, hw, W - hw), clamp(ty, hh, H - hh)
        out = c.img.resize((W, H), Image.BICUBIC, box=(zx - hw, zy - hh, zx + hw, zy + hh))
        out = sharpen(out, 0.35 * min(1.0, z - 1), 2.4)            # the camera's digital sharpening
        g, j, n = _glitch_at(c)
        g *= float(p["glitch"])
        if g > 0.01:
            a = f32(np.asarray(out))
            key = ("cells", j, n)
            if key not in st:
                st[key] = block_cells(1000 + j * 7 + n, 24 if n == 0 else 12, 0.42 if n == 0 else 0.22)
            a = pixelate(a, 24 if n == 0 else 12, st[key] * min(1.0, g * 1.2))
            a = chroma(a, 8 * g, 0)
            a = a * (1 + 0.07 * g)
            out = sharpen(to_pil(a), 1.3 * g, 1.6)
    if hud_a > 0.003:
        out = _hud(c, out, z, hud_a)
    return out

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text added: REC, the real elapsed time and the real zoom factor",
    "still": 0.55,
    "needs": ["face"],
}
