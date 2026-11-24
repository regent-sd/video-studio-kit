"""Spotlight: the room goes dark, you stay lit, and a big glowing word sits behind your head."""
import math
import numpy as np
from PIL import Image, ImageFilter
from core import (W, H, f32, to_pil, mix, over, vignette, ease_out, ease_io, prog, hexc, font, text_img, DIDOT, BODONI,
                  NEWYORK, SFP, scaled, comp, with_alpha)

NAME = "spotlight"
KIND = "behind"
ABOUT = "Room goes dark, you stay lit, a glowing word sits behind your head"
DUR = 3.5
PARAMS = dict(
    text=None,          # the word behind you; default: the first key word you say in the window
    color=None,         # glow colour; default the skin's accent (yellow on the Dark skin)
    font="didot",       # didot | bodoni | newyork | sf | skin (the skin's title font: a brand's own, on the Brand skin)
    darkness=0.78,      # how dark the room gets (0-1)
    rim=0.35,           # coloured light on your outline (0 = off)
    y=None,             # centre of the word (px); default just above your eyes so your head covers its lower half
)
FONTS = {"didot": (DIDOT, 2, 700), "bodoni": (BODONI, 2, 700), "newyork": (NEWYORK, 0, 900), "sf": (SFP, 0, 900)}

def _word_layer(txt, col, fname, skin=None):
    """The word, sized to the frame width, with a neon glow. RGBA, frame width."""
    path, idx, wt = tuple(skin["title"]) if (fname == "skin" and skin) else FONTS.get(fname, FONTS["didot"])
    size = 400
    t = text_img(txt, size, wt, (255, 255, 255), 0, path, idx)
    s = min(1.0, (W * 0.94) / t.width, 420 / t.height)
    t = scaled(t, s)
    pad = 120
    cv = Image.new("RGBA", (t.width + 2 * pad, t.height + 2 * pad), (0, 0, 0, 0))
    cv.alpha_composite(t, (pad, pad))
    a = cv.getchannel("A")
    glow = Image.new("RGBA", cv.size, col + (0,))
    g1 = a.filter(ImageFilter.GaussianBlur(46)).point(lambda v: min(255, int(v * 2.4)))
    g2 = a.filter(ImageFilter.GaussianBlur(14)).point(lambda v: min(255, int(v * 1.6)))
    out = Image.new("RGBA", cv.size, (0, 0, 0, 0))
    glow.putalpha(g1); out.alpha_composite(glow)
    glow2 = Image.new("RGBA", cv.size, col + (0,)); glow2.putalpha(g2); out.alpha_composite(glow2)
    core_col = tuple(int(255 * 0.55 + c * 0.45) for c in col)       # hot centre: near white, tinted
    face = Image.new("RGBA", cv.size, core_col + (0,)); face.putalpha(a); out.alpha_composite(face)
    return out

def render(c):
    st = c.state
    col = hexc(c.p["color"]) if c.p.get("color") else c.skin.accent
    if "word" not in st:
        st["word"] = _word_layer(c.word_text().upper(), col, c.p["font"], c.skin)
    e = c.env(0.4, 0.35)
    src = f32(c.src)
    cx, cy, fw, fh = c.face
    # room: darker, a little desaturated, with a soft pool of light behind the person
    g = src.mean(2, keepdims=True)
    room = src * 0.75 + g * 0.25
    pool = np.exp(-(((np.arange(W) - cx) / (W * 0.55)) ** 2))[None, :] * np.exp(-(((np.arange(H) - cy) / (H * 0.42)) ** 2))[:, None]
    k = 1 - c.p["darkness"] * e * (1 - 0.35 * pool) * (2 - vignette(0.7, 0.8))
    room = room * np.clip(k, 0.05, 1)[..., None]
    # the word: flickers on like a neon sign, then breathes
    u = c.u
    fl = 1.0 if u > 0.42 else (0.25 if int(u * 30) in (2, 3, 7, 10) else ease_out(u / 0.3))
    breathe = 0.92 + 0.08 * math.sin(u * 5.0)
    a = fl * breathe * c.env(0.25, 0.3)
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    wl = st["word"]
    s = 1.06 - 0.06 * ease_out(u / 0.8)
    wl = scaled(wl, s)
    y = c.p["y"] if c.p.get("y") is not None else (cy - fh * 0.62)
    comp(lay, with_alpha(wl, a), W / 2 - wl.width / 2, y - wl.height / 2)
    room = over(room, lay)
    # rim light: a thin coloured glow just outside the outline
    if c.p["rim"] > 0:
        m8 = Image.fromarray((c.mask * 255).astype(np.uint8), "L")
        halo = np.asarray(m8.filter(ImageFilter.GaussianBlur(14)), np.float32) / 255
        rim = np.clip(halo - c.mask, 0, 1) * c.p["rim"] * e
        room = room + rim[..., None] * np.array(col, np.float32)[None, None, :] * 1.4
    person = f32(np.asarray(c.img)) * (1 + 0.06 * e)
    return to_pil(mix(person, room, c.mask))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your own (the first key word you say in the window)",
    "needs": ["person"],
}
