"""Voice note: a messaging-app voice message pops in above your head: your face as the avatar, a waveform of the
real sound that fills in as it plays, a play/pause button and the real running time."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, FPS, SS, font, SFP, ease_out, ease_io, back, prog, lerp, lerpc, clamp, clamp01
from ._ui import (phases, put, stamp, avatar, loudness, contrast, play_icon, pause_icon, fmt_clock, label_img, IOS_BLUE,
                  IOS_GREEN)

NAME = "voice-note"
KIND = "cards"
ABOUT = "A voice-message bubble above your head with your face, a live waveform of your voice and the running time"
DUR = 4.0
PARAMS = dict(
    style="light",    # light (grey bubble, blue progress) | blue | green
    text=None,        # optional small label pill under the bubble; None: no label
    side="left",      # left: your face on the left (a received message) | right: on the right (sent)
    y=None,           # top of the bubble (px); default above your head
)
BW, BH, AV, GAPX = 740, 148, 128, 16
STYLES = {
    "light": dict(bub=(240, 240, 245), played=IOS_BLUE, unplayed=(178, 178, 186), btn=IOS_BLUE, icon=(255, 255, 255), txt=(72, 72, 80)),
    "blue": dict(bub=(10, 132, 255), played=(255, 255, 255), unplayed=(118, 186, 255), btn=(255, 255, 255), icon=(10, 132, 255), txt=(255, 255, 255)),
    "green": dict(bub=(48, 196, 88), played=(255, 255, 255), unplayed=(150, 224, 168), btn=(255, 255, 255), icon=(48, 196, 88), txt=(255, 255, 255)),
}

def _quad(p0, c, p1, n=24):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1]) for t in (i / n for i in range(n + 1))]

def _bubble_mask(w, h, tail_left=True, out=2):
    """A pill with an iMessage-style tail curling out of the bottom corner (L, antialiased, out x the size)."""
    k = 4
    m = Image.new("L", (w * k, h * k), 0)
    d = ImageDraw.Draw(m)
    T, R = 16, h * 0.42
    d.rounded_rectangle([T * k, 0, w * k - 1, h * k - 1], radius=R * k, fill=255)
    pts = [(T + 1, h - R)] + _quad((T + 1, h - 24), (T + 1, h - 3), (T - 14, h - 0.5))[:-1] \
        + _quad((T - 14, h - 0.5), (T + 8, h + 0.6), (T + R + 4, h - 0.5)) + [(T + R + 4, h - R)]
    d.polygon([(x * k, y * k) for x, y in pts], fill=255)
    m = m.resize((w * out, h * out), Image.LANCZOS)
    return m if tail_left else m.transpose(Image.FLIP_LEFT_RIGHT)

def _mic_badge(d, cx, cy, r, bg, fg):
    d.circ(cx, cy, r + 3, fill=(255, 255, 255, 255))
    d.circ(cx, cy, r, fill=tuple(bg) + (255,))
    d.rr((cx - r * 0.2, cy - r * 0.55, cx + r * 0.2, cy + r * 0.12), r * 0.2, fill=tuple(fg) + (255,))
    d.arc((cx - r * 0.42, cy - r * 0.4, cx + r * 0.42, cy + r * 0.32), 20, 160, fill=tuple(fg) + (255,), width=r * 0.11)
    d.line([(cx, cy + r * 0.33), (cx, cy + r * 0.5)], tuple(fg) + (255,), r * 0.11)

def render(c):
    st = c.state
    sty = STYLES.get(c.p.get("style"), STYLES["light"])
    ui, uo = phases(c, 0.5, 0.4)
    if ui <= 0 or uo >= 1: return c.img
    tin, tout = min(0.5, c.d * 0.28), min(0.4, c.d * 0.22)
    p0, p1 = c.t0 + min(0.42, c.d * 0.2), c.t1 - tout          # playback: after the tap, until it leaves
    right = c.p.get("side") == "right"
    nb = int((BW - 16 - 150 - 140) // 13)
    if "lv" not in st:
        st["lv"] = contrast(loudness(c, p0, p1, nb), 3, 98, 1.0)
        st["mask"] = _bubble_mask(BW + 16, BH, not right)
        i0 = int(c.t0 * FPS); i1 = max(i0 + 1, int(c.t1 * FPS))
        fs = c.subj.faces[i0:i1] if len(c.subj.faces[i0:i1]) else np.array([c.face], np.float32)
        head = float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], 10))
        chin = float(np.percentile(fs[:, 1] + 0.62 * fs[:, 3], 80))
        lab_h = 80 if c.p.get("text") else 0
        if c.p.get("y") is not None: top = c.p["y"]
        elif head - 30 - BH - lab_h >= 236: top = head - 30 - BH - lab_h
        elif chin + 30 + BH + lab_h <= 1470: top = chin + 30          # no room above your head: under your chin
        else: top = 236
        st["top"] = float(top)
    lv = st["lv"]
    t = c.t
    p = clamp01((t - p0) / max(0.1, p1 - p0))
    playing = p0 <= t < p1
    # ---- the bubble
    bw = BW + 16
    s = SS(bw, BH)
    T = 16
    xo = 0 if right else T          # inner left edge of the pill
    s.im.paste(Image.new("RGBA", s.im.size, sty["bub"] + (255,)), (0, 0), st["mask"])
    # play / pause button, pressed at the start
    bcx, bcy, br = xo + 22 + 48, BH / 2, 48
    press = 1 - 0.14 * math.sin(math.pi * clamp01((t - (p0 - 0.12)) / 0.24))
    s.circ(bcx, bcy, br * press, fill=sty["btn"] + (255,))
    if playing: pause_icon(s, bcx, bcy, 26 * press, sty["icon"])
    else: play_icon(s, bcx + 3, bcy, 30 * press, sty["icon"])
    # waveform: the real loudness, filling in as it plays (the bar under the playhead bounces with the sound)
    wx0 = xo + 150
    live = float(loudness(c, max(0, t - 0.05), t + 0.05, 1)[0]) if playing else 0.0
    for k, v in enumerate(lv):
        x = wx0 + k * 13 + 3.5
        f = (k + 0.5) / nb
        grow = ease_out(prog(c.u, 0.12 + 0.012 * k, 0.3))
        hh = (6 + 46 * v) * grow
        if playing and abs(f - p) < 1.5 / nb: hh = min(54, hh * (1 + 0.25 * live))
        col = sty["played"] if f <= p else sty["unplayed"]
        s.rr((x - 3.5, BH / 2 - hh, x + 3.5, BH / 2 + hh), 3.5, fill=col + (255,))
    # the scrub dot
    if p > 0:
        sx = wx0 + p * nb * 13
        s.circ(sx, BH / 2, 9, fill=sty["played"] + (255,))
    # running time: real seconds since it started playing
    el = clamp(t - p0, 0, p1 - p0)
    s.text((wx0 + nb * 13 + 26, BH / 2 + 2), fmt_clock(el), 38, 600, fill=sty["txt"] + (255,), anchor="lm")
    bub = s.out()
    # ---- avatar (your face, live) with a mic badge
    av = avatar(c, AV, ring=(255, 255, 255), ring_w=4)
    PG = 24                                   # room for the avatar's overshoot
    gw = AV + GAPX + bw + 2 * PG
    gh = BH + 2 * PG
    g = Image.new("RGBA", (gw, gh), (0, 0, 0, 0))
    ax = gw - PG - AV if right else PG
    bx = PG if right else PG + AV + GAPX
    g.alpha_composite(bub, (bx, PG))
    a_in = back(prog(c.u, 0.12, 0.4), 2.2)
    if a_in > 0.02:
        avs = av.resize((max(1, int(AV * a_in)), max(1, int(AV * a_in))), Image.BICUBIC) if abs(a_in - 1) > 0.01 else av
        g.alpha_composite(avs, (int(ax + (AV - avs.width) / 2), int(PG + BH - AV + (AV - avs.height) / 2)))
        bd = SS(gw, gh)
        _mic_badge(bd, ax + AV - 16, PG + BH - 16, 15 * min(1, a_in), IOS_BLUE if c.p.get("style") != "blue" else IOS_GREEN, (255, 255, 255))
        g.alpha_composite(bd.out())
    # ---- pop in from the avatar with overshoot; drift up and fade out
    x0 = (W - gw) / 2
    top = st["top"] - PG - ease_out(uo) * 40
    sc = back(ui, 1.7) * (1 - 0.06 * ease_out(uo))
    a = min(1.0, ease_out(ui * 2.2)) * (1 - ease_out(uo))
    ox, oy = ax + AV / 2 + x0, top + PG + BH - AV / 2       # grows out of the avatar
    gcx, gcy = x0 + gw / 2, top + gh / 2
    img = c.img.copy()
    stamp(img, g, ox + (gcx - ox) * sc, oy + (gcy - oy) * sc, s=max(0.02, sc), a=a, shadow=0.42, blur=22, dy=12)
    # optional label pill under the bubble
    if c.p.get("text"):
        li = label_img(str(c.p["text"]), 32, 650, (255, 255, 255))
        pw, ph = li.width + 44, 58
        pill = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ps = SS(pw, ph); ps.rr((0, 0, pw, ph), ph / 2, fill=(18, 18, 22, 200)); pill = ps.out()
        pill.alpha_composite(li, (22, (ph - li.height) // 2))
        la = back(prog(c.u, 0.35, 0.4), 1.6)
        stamp(img, pill, x0 + bx + bw / 2 + (-T / 2 if right else T / 2), top + PG + BH + 22 + ph / 2,
              s=max(0.02, 0.6 + 0.4 * la), a=a * clamp01(la), shadow=0.3, blur=14, dy=6)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text added: the waveform is the real sound, the time is the real seconds played, the avatar is the face in the clip",
    "needs": ["face"],
}
