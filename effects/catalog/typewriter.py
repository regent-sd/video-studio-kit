"""Typewriter: the words you say type onto the screen letter by letter, in sync, with a blinking caret."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, FPS, SS, font, SFP, SFMONO, TYPEWRITER, key_words, ease_out, ease_io, back, prog, clamp, clamp01,
                  norm_word)
from ._ui import spoken, phases, frost, put, stamp, shadow_of, clean, is_filler

NAME = "typewriter"
KIND = "cards"
ABOUT = "Your words type onto the screen letter by letter as you say them, with a blinking caret"
DUR = 5.0
PARAMS = dict(
    text=None,          # what gets typed; default the words you say in the window (ums dropped). Typed at your pace
                        # where its words match what you say, else evenly across the window.
    font="mono",        # mono | sans | typewriter
    position="top",     # top (above your head) | middle | bottom (under your chin) | a y in px (top of the box)
    style="box",        # box (dark rounded backdrop) | bare (text over the room with a shadow)
    lines=3,            # most lines on screen; older lines scroll up
    size=None,          # text size in px; default per font
    highlight="keys",   # keys: key words in the accent colour | none
)
FONTS = {"mono": (SFMONO, 0, 560, 56), "sans": (SFP, 0, 720, 64), "typewriter": (TYPEWRITER, 0, 400, 60)}
BOX_W, PADX, PADY = 960, 40, 30

def _tokens(c):
    """[(display word, start time, char interval, is key)] in typing order."""
    if c.p.get("text"):
        words = str(c.p["text"]).split()
        said = spoken(c)
        out, j = [], 0
        lo, hi = c.t0 + min(0.35, c.d * 0.1), c.t1 - min(0.8, c.d * 0.25)
        n = len(words)
        for i, w in enumerate(words):
            ts = None
            for k in range(j, min(len(said), j + 4)):
                if norm_word(said[k]["w"]) == norm_word(w):
                    ts = said[k]["s"]; j = k + 1; break
            out.append([w, ts if ts is not None else lo + (hi - lo) * i / max(1, n)])
        for i in range(1, len(out)):          # keep times in order
            out[i][1] = max(out[i][1], out[i - 1][1] + 0.04)
    else:
        stop = c.t1 - min(0.4, c.d * 0.22)          # nothing starts typing once the box is leaving
        ws = [w for w in spoken(c) if w["s"] <= stop]
        out = [[w["w"], max(c.t0, w["s"])] for w in ws]
        if out and out[0][0][:1].isalpha(): out[0][0] = out[0][0][0].upper() + out[0][0][1:]
    res = []
    for i, (w, s) in enumerate(out):
        nxt = out[i + 1][1] if i + 1 < len(out) else s + 0.6
        dt = clamp((nxt - s) / (len(w) + 1.5), 0.022, 0.065)
        key = bool(key_words([{"w": w}]))
        res.append((w, s, dt, key))
    return res

def _setup(c):
    fk = c.p.get("font") if c.p.get("font") in FONTS else "mono"
    path, idx, wt, sz = FONTS[fk]
    size = int(c.p.get("size") or sz)
    toks = _tokens(c)
    maxl = max(1, int(c.p.get("lines") or 3))
    # where: above the head by default; fewer lines / smaller text if it won't fit
    i0 = int(c.t0 * FPS); i1 = max(i0 + 1, int(c.t1 * FPS))
    fs = c.subj.faces[i0:i1] if len(c.subj.faces[i0:i1]) else np.array([c.face], np.float32)
    head = float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], 10))
    chin = float(np.percentile(fs[:, 1] + 0.62 * fs[:, 3], 80))
    pos = c.p.get("position", "top")
    def fit(maxl, size):
        f = font(size, wt, path, idx)
        lh = int(size * 1.34)
        lines = _wrap(toks, f, BOX_W - 2 * PADX)
        bh = min(maxl, len(lines)) * lh + 2 * PADY
        return f, lh, lines, bh
    tries = [(maxl, size), (max(1, min(maxl, 2)), size), (max(1, min(maxl, 2)), int(size * 0.88))]
    if isinstance(pos, (int, float)):
        f, lh, lines, bh = fit(maxl, size); top = float(pos)
    elif pos == "middle":
        f, lh, lines, bh = fit(maxl, size); top = H * 0.45 - bh / 2
    else:
        order = ["bottom", "top"] if pos == "bottom" else ["top", "bottom"]
        top = None
        for where in order:
            for ml, sz in tries:
                f, lh, lines, bh = fit(ml, sz)
                cand = max(232, head - 26 - bh) if where == "top" else chin + 20
                ok = (cand + bh <= head + 8) if where == "top" else (cand + bh <= 1490)
                if ok: top, maxl, size = cand, ml, sz; break
            if top is not None: break
        if top is None:
            maxl, size = tries[-1]; f, lh, lines, bh = fit(maxl, size); top = 232
    widest = max((f.getlength(" ".join(toks[k][0] for k in ln)) for ln in lines), default=0)
    bw = min(BOX_W, int(widest + 2 * PADX + size * 0.7))
    # when each line starts typing
    starts = [toks[ln[0]][1] for ln in lines]
    return dict(f=f, size=size, lh=lh, toks=toks, lines=lines, maxl=maxl, top=top, bw=bw, starts=starts,
                path=path, idx=idx, wt=wt)

def _wrap(toks, f, maxw):
    lines, cur, cw = [], [], 0.0
    sp = f.getlength(" ")
    for i, (w, *_r) in enumerate(toks):
        lw = f.getlength(w)
        if cur and cw + sp + lw > maxw:
            lines.append(cur); cur, cw = [], 0.0
        cw = lw if not cur else cw + sp + lw
        cur.append(i)
    if cur: lines.append(cur)
    return lines

def render(c):
    st = c.state
    if "L" not in st: st["L"] = _setup(c)
    L = st["L"]
    toks, lines = L["toks"], L["lines"]
    if not toks: return c.img
    ui, uo = phases(c, 0.4, 0.4)
    if ui <= 0 or uo >= 1: return c.img
    t = c.t
    f, lh, size, maxl = L["f"], L["lh"], L["size"], L["maxl"]
    acc = tuple(c.skin.accent)
    hl = c.p.get("highlight", "keys") == "keys"
    # how much is typed
    typed = []
    last_key = -9.0
    for w, s, dt, key in toks:
        k = 0 if t < s else min(len(w), int((t - s) / dt) + 1)
        typed.append(k)
        if k: last_key = max(last_key, s + (k - 1) * dt)
    # scroll: one line per new line past the limit; the box grows line by line first
    off = sum(ease_io(prog(t, L["starts"][li] - 0.04, 0.3)) for li in range(maxl, len(lines)))
    shown = 1 + sum(ease_io(prog(t, L["starts"][li] - 0.04, 0.26)) for li in range(1, min(maxl, len(lines))))
    bw = L["bw"]
    bh = shown * lh + 2 * PADY
    # the text layer: the visible lines (plus the one scrolling out)
    tl = Image.new("RGBA", (bw, int(maxl * lh + 2 * PADY)), (255, 255, 255, 0))
    d = ImageDraw.Draw(tl)
    asc, desc = f.getmetrics()
    sp = f.getlength(" ")
    caret = None
    for li, ln in enumerate(lines):
        p = li - off
        y = PADY + p * lh + (lh - (asc + desc)) / 2
        la = clamp01(1 + p * 1.8)             # a line scrolling out of the top fades as it goes
        if la <= 0.01 or y > tl.height: continue
        x = PADX
        for k in ln:
            w, s, dt, key = toks[k]
            n = typed[k]
            if n:
                col = acc if (hl and key) else (255, 255, 255)
                d.text((x, y), w[:n], font=f, fill=col + (int(255 * la),))
            if n and (k + 1 >= len(toks) or typed[k + 1] == 0):
                caret = (x + f.getlength(w[:n]) + 3, y, li)
            x += f.getlength(w) + sp
    if caret is None and toks:
        caret = (PADX, PADY + (lh - (asc + desc)) / 2, 0)
    # nothing shows above the top padding
    if off > 0.001:
        a = np.asarray(tl.getchannel("A"), np.float32)
        ramp = np.clip((np.arange(tl.height) - PADY * 0.35) / (PADY * 0.5), 0, 1)
        tl.putalpha(Image.fromarray((a * ramp[:, None]).astype(np.uint8), "L"))
    # the caret: solid while typing, blinking when you pause
    idle = t - last_key
    blink = 1.0 if idle < 0.45 else (0.5 + 0.5 * math.cos((idle - 0.45) * math.pi / 0.53)) ** 0.6
    cx, cy, cl = caret
    cs = SS(tl.width, tl.height)
    ch = asc * 0.95
    cs.rr((cx, cy + asc * 0.12, cx + max(4, size * 0.075), cy + asc * 0.12 + ch), 2, fill=acc + (int(255 * blink),))
    tl.alpha_composite(cs.out())
    # assemble the box
    a = min(ease_out(ui * 1.5), 1 - ease_out(uo))
    sc = (0.9 + 0.1 * back(ui, 1.6)) * (1 - 0.04 * ease_out(uo))
    rise = -ease_out(uo) * 30
    top = L["top"] + rise
    x0 = (W - bw) / 2
    bh_i = int(round(bh))
    content = tl.crop((0, 0, bw, bh_i))
    if c.p.get("style", "box") == "box":
        box = frost(c.img, (x0, top, x0 + bw, top + bh_i), 30, tint=(12, 12, 15), tint_a=0.66, blur=7)
        box.alpha_composite(content)
        img = c.img.copy()
        stamp(img, box, x0 + bw / 2, top + bh_i / 2, s=sc, a=a, shadow=0.4, blur=24, dy=14)
    else:
        img = c.img.copy()
        stamp(img, content, x0 + bw / 2, top + bh_i / 2, s=sc, a=a, shadow=0.85, blur=10, dy=4)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "your own words as you say them",
    "needs": ["talk"],
}
