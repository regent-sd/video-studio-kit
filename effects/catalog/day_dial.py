"""Day dial: a huge cream clock dial spins in behind your head, with serif hour numerals, a minute track, your word
running around the rim and a sweeping hand. It spins back out at the end."""
import math, re, functools
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, f32, to_pil, font, text_img, scaled, comp, ease_out, ease_in, ease_io, back, prog, lerp, hexc,
                  with_alpha, DIDOT, NEWYORK)
from ._print import paper, grid, solid, key_word

NAME = "day-dial"
KIND = "behind"
ABOUT = "A huge clock dial behind your head: hour numerals, your word around the rim, a sweeping hand"
DUR = 4.0
PARAMS = dict(
    label=None,         # the word around the rim; default the key word you say in the window
    dial="#F2EBDD",     # dial colour (cream paper)
    ink=None,           # numerals and ticks; default the skin's ink
    hand=None,          # the sweep hand's disc colour; default the skin's accent
    size=0.52,          # dial radius as a share of the frame width
    turns=0.75,         # how far the hand sweeps over the effect (1 = once round)
    numerals="arabic",  # arabic (1-12) | roman (I-XII)
)
ROMAN = ["XII", "I", "II", "III", "IIII", "V", "VI", "VII", "VIII", "IX", "X", "XI"]

def _dial(R, label, dial, ink, numerals):
    """The dial face, RGBA (2R+8 square), drawn at 2x."""
    k = 2
    S = (2 * R + 8) * k; c0 = S / 2
    Rk = R * k
    # paper disc, lighter in the middle, a soft bevel at the edge
    pp = paper(S, S, tuple(dial), seed=71, grain=5.0, mottle=7.0, fibers=0.5)
    yy, xx = grid(S, S)
    r = np.sqrt((xx - c0) ** 2 + (yy - c0) ** 2) / Rk
    shade = (1 - 0.10 * r ** 2)[..., None] - 0.06 * np.clip((r - 0.9) / 0.1, 0, 1)[..., None]
    rgb = np.clip(pp * shade, 0, 255).astype(np.uint8)
    im = Image.fromarray(rgb, "RGB").convert("RGBA")
    al = Image.new("L", (S, S), 0)
    ImageDraw.Draw(al).ellipse([c0 - Rk, c0 - Rk, c0 + Rk, c0 + Rk], fill=255)
    im.putalpha(al)
    d = ImageDraw.Draw(im)
    ink4 = tuple(ink) + (255,)
    soft = tuple(int(lerp(a, b, 0.55)) for a, b in zip(ink, dial)) + (255,)
    def ring(rr, w, col=ink4):
        d.ellipse([c0 - rr * k, c0 - rr * k, c0 + rr * k, c0 + rr * k], outline=col, width=max(1, int(w * k)))
    # bezel
    ring(R - 3, 7); ring(R - 13, 1.4)
    # the label running round the rim
    band_r = R - 38
    if label:
        unit = label + "  •  "
        f = font(30 * k, 700, DIDOT, 2)
        trk = 6 * k
        ws = [f.getlength(ch) + trk for ch in unit]
        circ = 2 * math.pi * band_r * k
        rep = max(1, int(circ // sum(ws)))
        stretch = circ / (sum(ws) * rep)
        a = -math.pi / 2
        for _ in range(rep):
            for ch, wch in zip(unit, ws):
                adv = wch * stretch / (band_r * k)
                am = a + adv / 2
                if ch.strip():
                    t = text_img(ch, 30 * k, 700, tuple(ink), 0, DIDOT, 2)
                    t = t.rotate(-math.degrees(am + math.pi / 2), Image.BICUBIC, expand=True)
                    x = c0 + math.cos(am) * band_r * k; y = c0 + math.sin(am) * band_r * k
                    im.alpha_composite(t, (int(x - t.width / 2), int(y - t.height / 2)))
                a += adv
    ring(R - 62, 1.4)
    # minute track
    r0, r1 = R - 70, R - 100
    ring(r0, 1.2); ring(r1, 1.2)
    for m in range(60):
        a = 2 * math.pi * m / 60 - math.pi / 2
        major = m % 5 == 0
        ri = r1 - (16 if major else 0)
        wd = 5.0 if major else 1.6
        d.line([(c0 + math.cos(a) * ri * k, c0 + math.sin(a) * ri * k), (c0 + math.cos(a) * r0 * k, c0 + math.sin(a) * r0 * k)],
               fill=ink4, width=int(wd * k))
    # hour numerals, upright
    nr = R - 172
    for hh in range(12):
        a = 2 * math.pi * hh / 12 - math.pi / 2
        txt = ROMAN[hh] if numerals == "roman" else str(12 if hh == 0 else hh)
        t = text_img(txt, (78 if numerals != "roman" else 64) * k, 700, tuple(ink), 0, DIDOT, 2)
        x = c0 + math.cos(a) * nr * k; y = c0 + math.sin(a) * nr * k
        im.alpha_composite(t, (int(x - t.width / 2), int(y - t.height / 2)))
    ring(R - 236, 1.0, soft)
    # a fine sunray in the middle
    for j in range(120):
        a = 2 * math.pi * j / 120
        d.line([(c0 + math.cos(a) * 30 * k, c0 + math.sin(a) * 30 * k), (c0 + math.cos(a) * (R - 250) * k, c0 + math.sin(a) * (R - 250) * k)],
               fill=tuple(dial[:3]) + (0,) if j % 2 else tuple(int(v * 0.965) for v in dial) + (255,), width=k)
    return im.resize((2 * R + 8, 2 * R + 8), Image.LANCZOS)

def _hand(R, ink, disc):
    """The sweep hand pointing up, centred on its pivot: RGBA (2L square)."""
    k = 2
    L = R - 60
    S = 2 * L * k; c0 = S / 2
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink4 = tuple(ink) + (255,)
    # tapered blade with a tail
    tip, tail = L - 6, 150
    d.polygon([(c0 - 7 * k, c0 + tail * k), (c0 + 7 * k, c0 + tail * k), (c0 + 3 * k, c0 - tip * k), (c0 - 3 * k, c0 - tip * k)], fill=ink4)
    # a disc near the tip (railway-clock style) and the hub
    dr, dy = 30, L - 120
    d.ellipse([c0 - dr * k, c0 - (dy + dr) * k, c0 + dr * k, c0 - (dy - dr) * k], fill=tuple(disc) + (255,), outline=ink4, width=4 * k)
    d.ellipse([c0 - 22 * k, c0 - 22 * k, c0 + 22 * k, c0 + 22 * k], fill=ink4)
    d.ellipse([c0 - 9 * k, c0 - 9 * k, c0 + 9 * k, c0 + 9 * k], fill=tuple(disc) + (255,))
    return im.resize((2 * L, 2 * L), Image.LANCZOS)

def _shadow(D, blur_r=26, strength=0.55):
    pad = 120
    m = Image.new("L", ((D + 2 * pad) // 4, (D + 2 * pad) // 4), 0)
    ImageDraw.Draw(m).ellipse([pad // 4, pad // 4, (pad + D) // 4, (pad + D) // 4], fill=255)
    m = m.filter(ImageFilter.GaussianBlur(blur_r / 4)).resize((D + 2 * pad, D + 2 * pad), Image.BILINEAR)
    sh = Image.new("RGBA", m.size, (0, 0, 0, 0)); sh.putalpha(m.point(lambda v: int(v * strength)))
    return sh, pad

def render(c):
    st = c.state
    ink = hexc(c.p["ink"]) if c.p.get("ink") else tuple(c.skin.ink)
    disc = hexc(c.p["hand"]) if c.p.get("hand") else tuple(c.skin.accent)
    R = int(W * c.p["size"])
    if "dial" not in st:
        label = (c.p.get("label") or re.sub(r"[^\w'-]", "", key_word(c))).upper()
        st["dial"] = _dial(R, label, hexc(c.p["dial"]), ink, c.p.get("numerals", "arabic"))
        st["hand"] = _hand(R, ink, disc)
        st["sh"], st["pad"] = _shadow(st["dial"].width)
        cx, cy, fw, fh = c.face
        st["cx"], st["cy"] = cx, cy - fh * 0.12
    cx, cy, fw, fh = c.face
    # follow the head slowly, so the dial stays put when you move a little
    st["cx"] += (cx - st["cx"]) * 0.06; st["cy"] += ((cy - fh * 0.12) - st["cy"]) * 0.06
    u, d = c.u, c.d
    tin = min(0.85, d * 0.3); tout = min(0.65, d * 0.24)
    pi_, po = prog(u, 0, tin), prog(u, d - tout, tout)
    e_in, e_out = back(pi_, 1.4), ease_in(po)
    rot = lerp(-150, 0, ease_out(pi_)) + lerp(0, 110, e_out)
    sc = lerp(0.35, 1.0, e_in) * lerp(1.0, 0.55, e_out)
    al = min(ease_out(pi_ * 1.8), 1 - ease_in(po))
    if al <= 0.003: return c.img
    lay = c.canvas()
    dial = st["dial"].rotate(rot, Image.BICUBIC) if abs(rot) > 0.05 else st["dial"]
    # the hand sweeps clockwise all the way through
    ang = rot - 360 * c.p["turns"] * (u / d) + 40
    hand = st["hand"].rotate(ang, Image.BICUBIC)
    sh = st["sh"]
    if abs(sc - 1) > 1e-3:
        dial = scaled(dial, sc); hand = scaled(hand, sc); sh = scaled(sh, sc)
    # behind the head, but kept on screen when the face is near an edge
    X = min(max(st["cx"], W * 0.28), W * 0.72); Y = min(max(st["cy"], R * 0.55 + 120), H * 0.62)
    comp(lay, with_alpha(sh, al), X + 16 * sc - sh.width / 2, Y + 30 * sc - sh.height / 2)
    comp(lay, with_alpha(dial, al), X - dial.width / 2, Y - dial.height / 2)
    hs = Image.new("RGBA", hand.size, (0, 0, 0, 0)); hs.putalpha(hand.getchannel("A").point(lambda v: int(v * 0.3)))
    hs = hs.filter(ImageFilter.GaussianBlur(5))
    comp(lay, with_alpha(hs, al), X + 8 * sc - hand.width / 2, Y + 14 * sc - hand.height / 2)
    comp(lay, with_alpha(hand, al), X - hand.width / 2, Y - hand.height / 2)
    # the room dims a touch so the dial reads
    base = f32(np.asarray(c.img))
    room = base * (1 - 0.25 * al)
    return c.compose(room, lay, mask=solid(c.mask))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the label is your own word; the numerals are the clock face, not a stat",
    "needs": ["face"],
}
