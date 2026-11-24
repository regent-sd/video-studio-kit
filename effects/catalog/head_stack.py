"""Head stack: word stickers drop from above and land on your head as you say them, stacking into a wobbly tower
that rides along with you, then tumble off at the end."""
import math, re
import numpy as np
from PIL import Image
from core import (W, FPS, SS, comp, with_alpha, soft_shadow, key_words, norm_word, ease_in, lerp, clamp, clamp01,
                  hexc)
from catalog._b import head_top, font_args, behind

NAME = "head-stack"
KIND = "cards"
ABOUT = "Word stickers drop onto your head as you say them and stack into a wobbly tower"
DUR = 5.0
PARAMS = dict(
    words=None,       # ["faster", ...] or [{"text": "...", "on": "word you say" | seconds}]; default your strongest words
    max_tags=4,       # most stickers in the tower (they get smaller when there are more)
    case="upper",     # upper | lower | as-said
    flyby=True,       # fast blurred stickers whooshing past behind you (your other words from the video)
    colors=None,      # list of [background, text] pairs; default the skin's white, accent, dark and blue
)
FALL = 0.34          # seconds from the top of the frame to the landing


def _pick(c):
    ws = c.p.get("words")
    if ws:
        out = []
        for k, it in enumerate(ws):
            txt, on = (it.get("text"), it.get("on")) if isinstance(it, dict) else (str(it), str(it))
            if isinstance(on, (int, float)): t = float(on)
            else:
                w = next((w for w in c.words_in() if norm_word(w["w"]) == norm_word(str(on))), None)
                t = w["s"] if w else c.t0 + 0.3 + k * max(0.5, (c.d - 1.2) / max(1, len(ws)))
            out.append((str(txt), t))
        return sorted(out, key=lambda x: x[1])
    cand, seen = [], set()
    for w in key_words(c.words_in(c.t0, c.t1 - 0.8)):
        n = norm_word(w["w"])
        if n in seen: continue
        seen.add(n); cand.append(w)
    n = int(c.p.get("max_tags") or 4)
    chosen = []
    for w in sorted(cand, key=lambda w: (-len(norm_word(w["w"])), w["s"])):
        if len(chosen) >= n: break
        if all(abs(w["s"] - x["s"]) >= 0.45 for x in chosen): chosen.append(w)
    chosen.sort(key=lambda w: w["s"])
    return [(re.sub(r"[^\w'-]", "", w["w"]), w["s"]) for w in chosen]

def _case(c, s):
    m = c.p.get("case", "upper")
    return s.upper() if m == "upper" else s.lower() if m == "lower" else s

def _palette(c):
    if c.p.get("colors"):
        return [(hexc(a), hexc(b)) for a, b in c.p["colors"]]
    k = c.skin
    return [(tuple(k.paper), tuple(k.ink)), (tuple(k.accent), tuple(k.accent_ink)), (tuple(k.dark2), (255, 255, 255)),
            (tuple(k.blue), (255, 255, 255))]

def _sticker(txt, th, bg, fg, skin):
    """A die-cut pill sticker: coloured pill, white border, soft shadow. Returns (RGBA, shadow RGBA)."""
    F = font_args(skin, "title")
    fs = th * 0.5
    tw = SS(1, 1).textlen(txt, fs, F["weight"], F["path"], F["index"])
    bd = max(4, th * 0.07)
    w, h = int(tw + th * 0.95 + 2 * bd), int(th)
    s = SS(w, h)
    s.rr((0, 0, w, h), h / 2, fill=(255, 255, 255, 255))
    s.rr((bd, bd, w - bd, h - bd), (h - 2 * bd) / 2, fill=bg + (255,))
    if bg == (255, 255, 255) or sum(bg) > 720:
        s.rr((1, 1, w - 1, h - 1), h / 2, outline=(0, 0, 0, 40), width=1.5)
    s.text((w / 2, h / 2 + th * 0.02), txt, fs, fill=fg + (255,), anchor="mm", **F)
    im = s.out()
    return im, soft_shadow(im, 0.42, blur=5, pad=40)

def _hblur(im, n):
    """Horizontal motion blur of an RGBA image over n px."""
    a = np.asarray(im.convert("RGBa"), np.float32)
    pad = np.pad(a, ((0, 0), (n, n), (0, 0)))
    cs = np.cumsum(pad, 1)
    out = (cs[:, n:] - cs[:, :-n]) / n
    out = out[:, :a.shape[1] + n]
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBa").convert("RGBA")

def render(c):
    st = c.state
    d, u = c.d, c.u
    if "tags" not in st:
        words = _pick(c)
        pal = _palette(c)
        rng = np.random.default_rng(23)
        ht = head_top(c)
        avail = max(160, ht + c.face[3] * 0.09 - 205)        # the top sticker's text stays below y ~240
        th = clamp(avail / max(1, len(words)) / 0.92, 58, 104)
        tags = []
        for k, (txt, t) in enumerate(words):
            bg, fg = pal[k % len(pal)]
            im, sh = _sticker(_case(c, txt), th, bg, fg, c.skin)
            rot = (rng.uniform(2.0, 5.5)) * (1 if k % 2 else -1)
            tags.append(dict(im=im, sh=sh, t=t - 0.06, rot=rot, dx=rng.uniform(-0.12, 0.12) * im.width,
                             spin=rng.uniform(260, 520) * (1 if k % 2 else -1), vx=rng.uniform(650, 1000) * (-1 if k % 2 else 1)))
        st["tags"], st["th"] = tags, th
        st["lean"], st["lv"], st["px"] = 0.0, 0.0, None
        # flybys: other words from the whole video, streaking past behind you
        st["fly"] = []
        if c.p.get("flyby", True):
            pool = [re.sub(r"[^\w'-]", "", w["w"]) for w in key_words(c.words)]
            used = {norm_word(x[0]) for x in words}
            pool = [p for p in pool if norm_word(p) not in used] or [x[0] for x in words]
            nf = int(clamp(round(d * 0.9), 1, 8))
            for j in range(nf):
                txt = pool[(j * 3) % len(pool)] if pool else ""
                if not txt: continue
                bg, fg = pal[(j + 1) % len(pal)]
                im, _ = _sticker(_case(c, txt), th * rng.uniform(0.7, 0.95), bg, fg, c.skin)
                tf = 0.35 + (d - 1.1) * (j + rng.uniform(0.1, 0.9)) / nf
                st["fly"].append(dict(im=_hblur(im, 90), t=tf, y=rng.uniform(300, max(320, ht - 40)) if j % 2 == 0
                                      else rng.uniform(ht + 120, min(1350, ht + 600)),
                                      dir=1 if j % 2 else -1, dur=rng.uniform(0.32, 0.45)))
    tags, th = st["tags"], st["th"]
    fx, fy, fw, fh = c.face
    ht = head_top(c)
    # the tower leans against your head's movement and springs back
    if st["px"] is not None:
        vx = (fx - st["px"]) * FPS
        acc = -st["lean"] * 140 - st["lv"] * 13 - vx * 0.0035 * 140
        st["lv"] += acc / FPS; st["lean"] += st["lv"] / FPS
        st["lean"] = clamp(st["lean"], -0.5, 0.5)
    st["px"] = fx
    lean = st["lean"]
    cv = c.canvas()
    # exit: the top sticker goes first
    ex_len = min(0.75, d * 0.3)
    t_exit = d - ex_len
    ex_stag = min(0.06, ex_len * 0.25 / max(1, len(tags)))
    ex_fade = ex_len - (len(tags) - 1) * ex_stag - 0.02
    landed_h = 0.0
    n = len(tags)
    for k, tg in enumerate(tags):
        tt = c.t - tg["t"]
        if tt <= 0: continue
        im, sh = tg["im"], tg["sh"]
        # where it sits in the tower (bottom of the sticker), riding on the head
        sit = th * 0.9
        base_y = ht + fh * 0.09 - landed_h                # the cutout's top sits a little above the hair
        bx = fx + tg["dx"] * 0.4 + lean * (landed_h + sit * 0.5) * 0.9
        rot = tg["rot"] + lean * 30 * (1 + k * 0.4)
        if tt < FALL:
            f = tt / FALL
            y_bot = lerp(-40, base_y, f * f)                        # falling, speeding up
            sx = sy = 1.0
            rot = tg["rot"] + (1 - f) * tg["spin"] * 0.08
        else:
            y_bot = base_y
            q = tt - FALL
            sq = math.exp(-8.5 * q) * math.cos(2 * math.pi * 3.0 * q)
            # later stickers landing on top press this one a little
            for j in range(k + 1, n):
                qj = c.t - tags[j]["t"] - FALL
                if qj > 0: sq += 0.3 * math.exp(-10 * qj) * math.cos(2 * math.pi * 3.4 * qj) * (0.7 ** (j - k - 1))
            sy, sx = 1 - 0.24 * sq, 1 + 0.16 * sq
            landed_h += im.height * sy * 0.92
        # tumble off at the end
        a = 1.0
        te = u - (t_exit + (n - 1 - k) * ex_stag)
        if te > 0:
            g = te
            bx += tg["vx"] * g
            y_bot += -700 * g + 2600 * g * g
            rot += tg["spin"] * g
            a = 1 - ease_in(clamp01(g / max(0.05, ex_fade)))
        if a <= 0.01: continue
        w2, h2 = max(1, int(im.width * sx)), max(1, int(im.height * sy))
        sim = im.resize((w2, h2), Image.BICUBIC) if (w2, h2) != im.size else im
        ssh = sh.resize((sh.width + w2 - im.width, sh.height + h2 - im.height), Image.BILINEAR) if (w2, h2) != im.size else sh
        r_im = sim.rotate(rot, Image.BICUBIC, expand=True)
        r_sh = ssh.rotate(rot, Image.BICUBIC, expand=True)
        cyc = y_bot - h2 / 2
        if a < 1: r_im, r_sh = with_alpha(r_im, a), with_alpha(r_sh, a)
        comp(cv, r_sh, bx - r_sh.width / 2, cyc - r_sh.height / 2 + 10)
        comp(cv, r_im, bx - r_im.width / 2, cyc - r_im.height / 2)
    img = c.img
    # flybys behind you
    if st["fly"]:
        bcv = None
        for fl in st["fly"]:
            q = (u - fl["t"]) / fl["dur"]
            if not 0 < q < 1: continue
            im = fl["im"]
            x = lerp(-im.width - 40, W + 40, q) if fl["dir"] > 0 else lerp(W + 40, -im.width - 40, q)
            if bcv is None: bcv = c.canvas()
            comp(bcv, with_alpha(im, 0.85), x, fl["y"] - im.height / 2)
        if bcv is not None: img = behind(c, bcv, img)
    return c.front(cv, img)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the stickers are your own words; the flybys are other words you say in the clip",
    "needs": ["face"],
}
