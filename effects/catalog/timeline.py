"""Timeline: your footage shrinks into a rounded viewer under an editing timeline built from this clip's real
thumbnails, words, colours and sound, with a playhead sweeping in time and a render bar climbing to 100%."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, FPS, SS, font, SFP, SFMONO, ease_out, ease_io, back, prog, lerp, clamp, clamp01, text_img)
from ._ui import (spoken, phases, put, stamp, shadow_of, rr_mask, rr_mask_fast, thumbs, loudness, clean, fit_text,
                  check, IOS_GREEN, label_img, clip_fade, contrast)

NAME = "timeline"
KIND = "cards"
ABOUT = "An editing timeline from this clip (thumbnails, captions, colours, waveform) with your footage in a viewer"
DUR = 5.0
PARAMS = dict(
    title="RENDER",   # title bar text (no brand names)
    format=True,      # this video's real format in the title bar (1080×1920 · 30 fps)
    timecode=True,    # the real playhead time in the title bar
    playhead=None,    # playhead colour; default red
)
PX0, PX1, PY0 = 36, 1044, 222         # panel (docked at the top, under Instagram's top bar)
TITLE_H, RULER_H, LANE_H, GAP = 72, 34, 72, 9
LX0, TX0, TX1 = 58, 214, 1018         # label column, lanes
LANES = [("V1 CLIP", (124, 108, 255)), ("CAPTIONS", (255, 214, 10)), ("GRADE", (255, 100, 170)),
         ("AUDIO", (52, 199, 89)), ("RENDER", (90, 200, 250))]
BG_TOP, BG_BOT, PANEL = (30, 22, 38), (12, 10, 16), (38, 30, 46)

def _geom():
    ly0 = PY0 + TITLE_H + RULER_H + 6
    lanes = [ly0 + k * (LANE_H + GAP) for k in range(len(LANES))]
    py1 = lanes[-1] + LANE_H + 20
    return lanes, py1

def _chunks(words, r0, r1):
    """Caption blocks: words grouped at pauses, at most 3 words / 1.2 s each."""
    out, cur = [], []
    for w in words:
        if cur and (w["s"] - cur[-1]["e"] > 0.3 or len(cur) >= 3 or w["e"] - cur[0]["s"] > 1.2):
            out.append(cur); cur = []
        cur.append(w)
    if cur: out.append(cur)
    return [(max(r0, ch[0]["s"]), min(r1, max(ch[-1]["e"], ch[0]["s"] + 0.15)), " ".join(clean(x["w"]) for x in ch)) for ch in out]

def _segments(words, r0, r1, n=3):
    """Split [r0, r1] at the longest pauses in speech (up to n parts)."""
    gaps = sorted(((b["s"] - a["e"], (a["e"] + b["s"]) / 2) for a, b in zip(words, words[1:])), reverse=True)
    cuts = sorted(m for g, m in gaps if g > 0.1 and r0 + 0.6 < m < r1 - 0.6)[:0] or \
        sorted([m for g, m in gaps if g > 0.1 and r0 + 0.6 < m < r1 - 0.6][:n - 1])
    edges = [r0] + cuts + [r1]
    return list(zip(edges, edges[1:]))

def _static(c, r0, r1):
    """Everything on the panel that doesn't move: drawn once."""
    lanes, py1 = _geom()
    pw, ph = PX1 - PX0, py1 - PY0
    s = SS(pw, ph)
    s.rr((0, 0, pw, ph), 30, fill=PANEL + (246,))
    s.rr((0.5, 0.5, pw - 0.5, ph - 0.5), 30, outline=(255, 255, 255, 30), width=1.5)
    # title bar
    for k, col in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        s.circ(34 + k * 30, TITLE_H / 2, 9, fill=col + (255,))
    title = str(c.p.get("title") or "")
    if title:
        s.text((140, TITLE_H / 2), title.upper(), 24, 800, fill=(240, 236, 246, 255), anchor="lm")
    if c.p.get("format", True):
        s.text((pw - 28, TITLE_H / 2), f"{W}×{H} · {FPS} fps", 21, 600, fill=(176, 166, 190, 255), anchor="rm", path=SFMONO)
    s.line([(0, TITLE_H), (pw, TITLE_H)], (255, 255, 255, 26), 1.2, round_caps=False)
    # ruler: real seconds of the video
    X = lambda t: TX0 - PX0 + (t - r0) / (r1 - r0) * (TX1 - TX0)
    ry = TITLE_H + RULER_H - 6
    step = 0.5 if (r1 - r0) <= 7 else (1.0 if (r1 - r0) <= 14 else 2.0)
    k0 = math.ceil(r0 / step)
    t = k0 * step
    while t <= r1 + 1e-6:
        x = X(t)
        major = abs(t - round(t)) < 1e-6 and (step < 2 or int(round(t)) % 2 == 0)
        s.line([(x, ry - (12 if major else 6)), (x, ry)], (255, 255, 255, 110 if major else 60), 1.6, round_caps=False)
        if major: s.text((x + 5, ry - 13), f"{int(round(t))}s", 17, 600, fill=(176, 166, 190, 255), anchor="ls", path=SFMONO)
        t += step
    # lanes
    words = spoken(c, r0, r1)
    for k, ((label, col), y) in enumerate(zip(LANES, lanes)):
        yy = y - PY0
        s.circ(LX0 - PX0 + 6, yy + LANE_H / 2, 5, fill=col + (255,))
        s.text((LX0 - PX0 + 20, yy + LANE_H / 2 + 1), label, 19, 760, fill=(206, 198, 218, 255), anchor="lm")
        s.rr((TX0 - PX0, yy, TX1 - PX0, yy + LANE_H), 12, fill=(255, 255, 255, 12))
    base = s.out()
    # V1: a filmstrip of real frames, cropped around the face
    yv = lanes[0] - PY0
    th = LANE_H - 10; tw = int(round(th * 0.82))
    n = max(1, int((TX1 - TX0 - 8) // tw))
    i0 = int(r0 * FPS); i1 = max(i0 + 1, int(r1 * FPS))
    fs = c.subj.faces[i0:i1] if len(c.subj.faces[i0:i1]) else np.array([c.face], np.float32)
    fcx, fcy, ffh = float(np.median(fs[:, 0])), float(np.median(fs[:, 1])), float(np.median(fs[:, 3]))
    bh = min(H, max(ffh * 2.4, 300)); bw = bh * tw / th
    bx0 = clamp(fcx - bw / 2, 0, W - bw); by0 = clamp(fcy + ffh * 0.1 - bh / 2, 0, H - bh)
    ths = thumbs(c, r0, r1, n, tw, th, (bx0, by0, bx0 + bw, by0 + bh))
    strip = Image.new("RGB", (n * tw, th), (0, 0, 0))
    for k, im in enumerate(ths): strip.paste(im, (k * tw, 0))
    sw = TX1 - TX0 - 8
    strip = strip.resize((sw, th), Image.BILINEAR) if strip.width != sw else strip
    clip = strip.convert("RGBA"); clip.putalpha(rr_mask(sw, th, 9))
    base.alpha_composite(clip, (TX0 - PX0 + 4, yv + 5))
    o = SS(sw + 4, th + 4)
    o.rr((1, 1, sw + 3, th + 3), 10, outline=LANES[0][1] + (255,), width=3)
    for k in range(1, n):
        o.line([(2 + k * sw / n, 3), (2 + k * sw / n, th + 1)], (0, 0, 0, 110), 1.2, round_caps=False)
    base.alpha_composite(o.out(), (TX0 - PX0 + 2, yv + 3))
    # GRADE: the real colours of each part, with their average as a hex code
    yg = lanes[2] - PY0
    means = [np.asarray(im.resize((8, 8), Image.BILINEAR), np.float32).reshape(-1, 3).mean(0) for im in ths]
    g = SS(TX1 - TX0, LANE_H)
    gl = Image.new("RGBA", (TX1 - TX0, LANE_H), (0, 0, 0, 0))
    for a, b in _segments(words, r0, r1):
        x0, x1 = X(a) - (TX0 - PX0) + 3, X(b) - (TX0 - PX0) - 3
        if x1 - x0 < 8: continue
        k0, k1 = int(clamp((a - r0) / (r1 - r0) * n, 0, n - 1)), int(clamp(math.ceil((b - r0) / (r1 - r0) * n), 1, n))
        cols = means[k0:max(k0 + 1, k1)]
        ramp = np.linspace(0, len(cols) - 1, int(x1 - x0))
        row = np.array([cols[int(min(len(cols) - 1, v))] * (1 - (v % 1)) + cols[int(min(len(cols) - 1, v + 1))] * (v % 1) for v in ramp])
        gm = row.mean(1, keepdims=True)
        row = np.clip((gm + (row - gm) * 1.9) * 1.35 + 10, 0, 255)   # shown a little richer; the label is the true average
        pill = Image.fromarray(np.repeat(row[None].astype(np.uint8), LANE_H - 14, 0), "RGB").convert("RGBA")
        pill.putalpha(rr_mask(pill.width, pill.height, 10))
        gl.alpha_composite(pill, (int(x0), 7))
        avg = np.mean(cols, 0)
        hexs = "#{:02X}{:02X}{:02X}".format(*[int(v) for v in avg])
        if x1 - x0 > 120:
            g.rr((x0 + 8, LANE_H / 2 - 16, x0 + 8 + 116, LANE_H / 2 + 16), 9, fill=(0, 0, 0, 120))
            g.text((x0 + 66, LANE_H / 2 + 1), hexs, 18, 600, fill=(255, 255, 255, 240), anchor="mm", path=SFMONO)
        g.rr((x0 + 0.5, 7.5, x1 - 0.5, LANE_H - 7.5), 10, outline=LANES[2][1] + (200,), width=2)
    gl.alpha_composite(g.out())
    base.alpha_composite(gl, (TX0 - PX0, yg))
    # AUDIO: the real waveform
    ya = lanes[3] - PY0
    nb = int((TX1 - TX0 - 16) // 6)
    lv = contrast(loudness(c, r0, r1, nb), 3, 99, 1.0)
    a = SS(TX1 - TX0, LANE_H)
    a.rr((2, 5, TX1 - TX0 - 2, LANE_H - 5), 10, fill=(52, 199, 89, 34))
    for k, v in enumerate(lv):
        x = 10 + k * 6 + 1.5
        hh = 2 + (LANE_H - 22) / 2 * v
        a.rr((x - 1.5, LANE_H / 2 - hh, x + 1.5, LANE_H / 2 + hh), 1.5, fill=(80, 220, 120, 255))
    base.alpha_composite(a.out(), (TX0 - PX0, ya))
    return base, X

def _bg():
    y = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    col = np.array(BG_TOP, np.float32) * (1 - y) + np.array(BG_BOT, np.float32) * y
    yy, xx = np.mgrid[0:H // 4, 0:W // 4].astype(np.float32)
    glow = np.exp(-(((xx - W / 8) / (W / 4 * 0.7)) ** 2 + ((yy - H * 0.62 / 4) / (H / 4 * 0.35)) ** 2))
    glow = np.asarray(Image.fromarray((glow * 255).astype(np.uint8), "L").resize((W, H), Image.BILINEAR), np.float32)[..., None] / 255
    col = col + glow * np.array([46, 26, 64], np.float32)
    return Image.fromarray(np.broadcast_to(np.clip(col, 0, 255), (H, W, 3)).astype(np.uint8), "RGB")

def render(c):
    st = c.state
    ui, uo = phases(c, 0.65, 0.5)
    if ui <= 0 or uo >= 1: return c.img
    lanes, py1 = _geom()
    tin, tout = min(0.65, c.d * 0.28), min(0.5, c.d * 0.22)
    r0, r1 = c.t0, max(c.t0 + 0.5, c.t1 - tout)
    if "base" not in st:
        st["base"], st["X"] = _static(c, r0, r1)
        st["caps"] = _chunks(spoken(c, r0, r1), r0, r1)
        st["bg"] = _bg()
    X = st["X"]
    # ---- the footage, shrinking into its viewer
    vy0, vy1 = py1 + 30, H - 40
    vh = vy1 - vy0; vw = vh * W / H
    vx0 = (W - vw) / 2
    k = min(ease_io(ui) if ui < 1 else 1.0, 1 - ease_io(uo))
    k = clamp01(k)
    if k <= 0.0005: return c.img
    fx0, fy0 = lerp(0, vx0, k), lerp(0, vy0, k)
    fw, fh = lerp(W, vw, k), lerp(H, vh, k)
    img = st["bg"].copy()
    foot = c.img.resize((max(2, int(round(fw))), max(2, int(round(fh)))), Image.BILINEAR) if k > 0.001 else c.img
    fm = rr_mask_fast(foot.width, foot.height, 34 * k)
    fa = foot.convert("RGBA"); fa.putalpha(fm)
    if k > 0.05:
        sh, pad = shadow_of(fa.resize((fa.width // 2, fa.height // 2)), 20, 0.55 * k)
        sh = sh.resize((sh.width * 2, sh.height * 2), Image.BILINEAR)
        put(img, sh, fx0 - pad * 2, fy0 - pad * 2 + 20 * k)
    put(img, fa, fx0, fy0)
    # ---- the panel, dropping in from the top
    pin = prog(c.u, tin * 0.25, tin * 0.75)
    pout = prog(c.u, c.d - tout, tout * 0.8)
    if pin <= 0 or pout >= 1: return img
    panel = st["base"].copy()
    pw, ph = panel.size
    p = clamp01((c.t - r0) / (r1 - r0))
    xp = X(min(c.t, r1))
    d = SS(pw, ph)
    # timecode (real)
    if c.p.get("timecode", True):
        f = int(round(c.t * FPS))
        tc = f"{f // FPS // 60:02d}:{f // FPS % 60:02d}:{f % FPS:02d}"
        d.text((pw / 2 + 40, TITLE_H / 2 + 1), tc, 26, 600, fill=(255, 255, 255, 255), anchor="mm", path=SFMONO)
    # captions: the words, placed in time; the one under the playhead lights up
    yc = lanes[1] - PY0
    caps = st["caps"]
    labels = []
    for j, (a, b, txt) in enumerate(caps):
        x0, x1 = X(a) + 1, X(b)
        nxt = X(caps[j + 1][0]) - 3 if j + 1 < len(caps) else TX1 - PX0 - 2
        fnt = font(19, 700)
        need = fnt.getlength(txt) + 22
        x1 = min(max(x1, min(x0 + need, nxt)), nxt)
        if x1 - x0 < 6: continue
        on = a <= c.t <= max(b, a + 0.25)
        grow = 3 if on else 0
        if on: d.rr((x0 - 2, yc + 11 - grow, x1 + 2, yc + LANE_H - 11 + grow), 11, fill=(255, 255, 255, 255))
        d.rr((x0, yc + 13 - grow, x1, yc + LANE_H - 13 + grow), 9, fill=(255, 226, 60, 255) if on else (240, 200, 16, 255))
        if x1 - x0 > 26:
            li = clip_fade(label_img(txt, 19, 700, (24, 20, 10)), x1 - x0 - 16)
            labels.append((li, x0 + 8, yc + LANE_H / 2 - li.height / 2 + 1))
    # render bar: climbs with the playhead to 100%
    yr = lanes[4] - PY0
    bx0, bx1 = TX0 - PX0 + 10, TX1 - PX0 - 150
    d.rr((bx0, yr + LANE_H / 2 - 9, bx1, yr + LANE_H / 2 + 9), 9, fill=(255, 255, 255, 30))
    pe = ease_io(p) * 0.15 + p * 0.85
    if pe > 0.002:
        d.rr((bx0, yr + LANE_H / 2 - 9, bx0 + (bx1 - bx0) * pe, yr + LANE_H / 2 + 9), 9, fill=(90, 200, 250, 255))
        hx = bx0 + (bx1 - bx0) * pe
        d.circ(hx - 5, yr + LANE_H / 2, 5, fill=(255, 255, 255, 220))
    pct = 100 if c.t >= r1 else int(math.floor(p * 100 + 1e-6))
    done = prog(c.t, r1, 0.4)
    if done > 0:
        check(d, TX1 - PX0 - 30, yr + LANE_H / 2, 17, done, IOS_GREEN)
    d.text((TX1 - PX0 - 58, yr + LANE_H / 2 + 1), f"{pct}%", 22, 700, fill=(255, 255, 255, 255), anchor="rm", path=SFMONO)
    # dim what the playhead hasn't reached yet (clip, grade, audio)
    if xp < TX1 - PX0 - 1:
        shade = Image.new("RGBA", (max(1, int(TX1 - PX0 - xp)), LANE_H), PANEL + (110,))
        for j in (0, 2, 3): panel.alpha_composite(shade, (int(xp), lanes[j] - PY0))
    panel.alpha_composite(d.out())
    for li, lx, ly in labels: panel.alpha_composite(li, (int(round(lx)), int(round(ly))))
    # the playhead
    ph_col = tuple(c.p.get("playhead") or (255, 69, 58))
    hd = SS(40, ph)
    top = TITLE_H + 6
    hd.line([(20, top + 20), (20, lanes[-1] - PY0 + LANE_H + 6)], ph_col + (255,), 3, round_caps=False)
    hd.poly([(9, top), (31, top), (31, top + 14), (20, top + 25), (9, top + 14)], fill=ph_col + (255,))
    panel.alpha_composite(hd.out(), (int(round(xp - 20)), 0))
    # slide in (overshoot), out (up)
    drop = (1 - back(pin, 1.3)) * -(ph + 60) - ease_io(pout) * (ph + 260)
    a = min(1.0, ease_out(pin * 2.5)) * (1 - ease_out(pout) * 0.3)
    stamp(img, panel, PX0 + pw / 2, PY0 + ph / 2 + drop, a=a, shadow=0.55, blur=30, dy=18)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text added beyond the UI labels (RENDER, V1 CLIP, CAPTIONS, GRADE, AUDIO); thumbnails, caption words, colours, waveform, timecode and format all come from this clip",
}
