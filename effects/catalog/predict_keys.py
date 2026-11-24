"""Predict keys: an iPhone keyboard slides up over the bottom of the frame and types what you say, key by key
(each key pops), while the predictive bar offers your next words and taps the middle one as you say it."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, FPS, SS, font, SFP, ease_out, ease_io, ease_in, back, prog, lerp, clamp, clamp01
from ._ui import spoken, phases, put, stamp, shadow_of, clean, label_img, clip_fade, IOS_BLUE

NAME = "predict-keys"
KIND = "cards"
ABOUT = "A phone keyboard slides up and types your words key by key, tapping the predicted word as you say it"
DUR = 5.0
PARAMS = dict(
    text=None,          # what gets typed; default the words you say in the window (ums dropped)
    cover=0.38,         # how much of the frame the keyboard covers (0.3-0.45)
    placeholder="",     # grey text in the empty field (e.g. "Message"); default none
)
KB_BG = (209, 212, 218)
KEY = (255, 255, 255)
KEY_SP = (172, 177, 188)
KEY_SH = (137, 139, 144)
INK = (0, 0, 0)
ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
PRED_H, KEY_H, ROW_GAP, MARGIN, KGAP = 108, 100, 24, 8, 14

def _layout(cover):
    kb_h = int(round(H * clamp(cover, 0.3, 0.45)))
    ky0 = H - kb_h
    kw = (W - 2 * MARGIN - 9 * KGAP) / 10
    keys = {}
    y = PRED_H + 14
    for r, row in enumerate(ROWS):
        n = len(row)
        tot = n * kw + (n - 1) * KGAP
        x = (W - tot) / 2
        for ch in row:
            keys[ch] = (x, y, x + kw, y + KEY_H); x += kw + KGAP
        y += KEY_H + ROW_GAP
    y2 = PRED_H + 14 + 2 * (KEY_H + ROW_GAP)
    sw = kw * 1.32
    keys["shift"] = (MARGIN, y2, MARGIN + sw, y2 + KEY_H)
    keys["delete"] = (W - MARGIN - sw, y2, W - MARGIN, y2 + KEY_H)
    y3 = y2 + KEY_H + ROW_GAP
    bw = kw * 2.6
    keys["123"] = (MARGIN, y3, MARGIN + bw, y3 + KEY_H)
    keys["return"] = (W - MARGIN - bw, y3, W - MARGIN, y3 + KEY_H)
    keys[" "] = (MARGIN + bw + KGAP, y3, W - MARGIN - bw - KGAP, y3 + KEY_H)
    return dict(kb_h=kb_h, ky0=ky0, kw=kw, keys=keys, bottom=y3 + KEY_H)

def _shift_pts(cx, cy, s):
    p = [(0, -1), (1, 0.05), (0.45, 0.05), (0.45, 0.78), (-0.45, 0.78), (-0.45, 0.05), (-1, 0.05)]
    return [(cx + x * s, cy + y * s) for x, y in p]

def _key(s, name, box, pressed=False, active=False):
    x0, y0, x1, y1 = box
    special = name in ("shift", "delete", "123", "return")
    fill = KEY_SP if special else KEY
    if pressed: fill = KEY if special else KEY_SP
    if active: fill = KEY
    s.rr((x0, y0 + 2.5, x1, y1 + 2.5), 13, fill=KEY_SH + (255,))
    s.rr((x0, y0, x1, y1), 13, fill=fill + (255,))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if len(name) == 1 and name != " ":
        s.text((cx, cy + 1), name, 54, 380, fill=INK + (255,), anchor="mm")
    elif name == "shift":
        pts = _shift_pts(cx, cy - 2, 21)
        if active: s.poly(pts, fill=INK + (255,))
        else: s.line(pts + [pts[0]], INK + (255,), 3.2)
    elif name == "delete":
        sz = 22
        pts = [(cx - 1.05 * sz, cy), (cx - 0.45 * sz, cy - 0.68 * sz), (cx + 0.95 * sz, cy - 0.68 * sz),
               (cx + 0.95 * sz, cy + 0.68 * sz), (cx - 0.45 * sz, cy + 0.68 * sz)]
        s.line(pts + [pts[0]], INK + (255,), 3.0)
        xc = cx + 0.22 * sz
        s.line([(xc - 0.28 * sz, cy - 0.28 * sz), (xc + 0.28 * sz, cy + 0.28 * sz)], INK + (255,), 3.0)
        s.line([(xc - 0.28 * sz, cy + 0.28 * sz), (xc + 0.28 * sz, cy - 0.28 * sz)], INK + (255,), 3.0)
    else:
        s.text((cx, cy + 1), {"123": "123", "return": "return", " ": "space"}[name], 40, 400, fill=INK + (255,), anchor="mm")

def _base(L):
    """The keyboard with nothing pressed (drawn once)."""
    s = SS(W, L["kb_h"])
    s.rect((0, 0, W, L["kb_h"]), fill=KB_BG + (255,))
    s.rect((0, 0, W, 1.2), fill=(178, 181, 188, 255))
    for name, box in L["keys"].items(): _key(s, name, box)
    # the bar under the keys: emoji and dictation
    yb = (L["bottom"] + L["kb_h"]) / 2 + 4
    ex, mx = 84, W - 84
    s.circ(ex, yb, 25, outline=(80, 82, 88, 255), width=3)
    s.circ(ex - 8, yb - 6, 3.2, fill=(80, 82, 88, 255)); s.circ(ex + 8, yb - 6, 3.2, fill=(80, 82, 88, 255))
    s.arc((ex - 13, yb - 10, ex + 13, yb + 14), 25, 155, fill=(80, 82, 88, 255), width=3)
    s.rr((mx - 8, yb - 24, mx + 8, yb + 4), 8, outline=(80, 82, 88, 255), width=3)
    s.arc((mx - 16, yb - 14, mx + 16, yb + 14), 15, 165, fill=(80, 82, 88, 255), width=3)
    s.line([(mx, yb + 14), (mx, yb + 22)], (80, 82, 88, 255), 3)
    # predictive bar dividers
    for k in (1, 2):
        s.line([(W * k / 3, PRED_H * 0.28), (W * k / 3, PRED_H * 0.72)], (178, 181, 189, 255), 1.6, round_caps=False)
    return s.out()

def _pop(L, ch):
    """The iOS key-pop balloon over a key, with the letter large. Returns (RGBA, x, y) in keyboard coords."""
    kx0, ky0, kx1, ky1 = L["keys"][ch.lower()]
    kw, kh = kx1 - kx0, ky1 - ky0
    bw, bh = kw * 1.5, kh * 1.12
    kcx = (kx0 + kx1) / 2
    bx0 = clamp(kcx - bw / 2, 4, W - 4 - bw); bx1 = bx0 + bw
    by1 = ky0 - 8; by0 = by1 - bh
    ox, oy = bx0 - 30, by0 - 30
    w, h = int(bw + 60), int(ky1 - by0 + 60)
    s = SS(w, h)
    def q(p0, c, p1, n=18):
        return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t * t * p1[0] - ox,
                 (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t * t * p1[1] - oy) for t in (i / n for i in range(n + 1))]
    left = q((bx0, by1 - 22), (bx0, by1 + 14), (kx0, ky0 + 30))
    right = q((bx1, by1 - 22), (bx1, by1 + 14), (kx1, ky0 + 30))
    neck = left + [(kx0 - ox, ky1 - 14 - oy), (kx1 - ox, ky1 - 14 - oy)] + right[::-1]
    s.poly(neck, fill=KEY + (255,))
    s.rr((bx0 - ox, by0 - oy, bx1 - ox, by1 - oy), 16, fill=KEY + (255,))
    s.rr((kx0 - ox, ky0 + 10 - oy, kx1 - ox, ky1 - oy), 13, fill=KEY + (255,))
    s.text(((bx0 + bx1) / 2 - ox, by0 + bh * 0.46 - oy), ch, 84, 360, fill=INK + (255,), anchor="mm")
    return s.out(), ox, oy

def _plan(c, ui_end, out_start):
    """The keystrokes and taps: [(time, kind, payload)] and the words as committed: [(time, word)]."""
    if c.p.get("text"):
        words = str(c.p["text"]).split()
        lo, hi = c.t0 + ui_end, c.t0 + out_start - 0.3
        ws = [dict(w=w, s=lo + (hi - lo) * i / max(1, len(words))) for i, w in enumerate(words)]
    else:
        ws = [dict(w=w["w"], s=w["s"]) for w in spoken(c) if c.t0 + ui_end * 0.6 <= w["s"] <= c.t0 + out_start - 0.15]
    words = []
    for w in ws:
        cw = clean(w["w"]).replace("’", "'")
        if cw: words.append((cw, w["s"]))
    if words: words[0] = (words[0][0][0].upper() + words[0][0][1:], words[0][1])
    ev, commits = [], []
    t_free = c.t0 + ui_end * 0.8
    for i, (w, s) in enumerate(words):
        s = max(s, t_free)
        nxt = words[i + 1][1] if i + 1 < len(words) else s + 0.6
        slot = max(0.08, min(nxt, s + 0.75) - s)
        letters = [ch for ch in w if ch.isalpha()]
        simple = len(w) <= 3 and "'" not in w and len(letters) == len(w)
        n_type = len(w) if simple else (min(2, len(letters)) if "'" not in w[:2] else 1)
        if slot < 0.2: n_type = 0
        dt = clamp(slot * 0.72 / (n_type + 1), 0.045, 0.11)
        for k in range(n_type):
            ev.append((s + k * dt, "key", w[k], dt, i))
        tc = s + n_type * dt
        if simple and n_type == len(w):
            ev.append((tc, "key", " ", dt, i))
        else:
            ev.append((tc, "tap", w, dt, i))
        commits.append((tc, w, i))
        t_free = tc + 0.02
    return words, ev, commits

def render(c):
    st = c.state
    ui, uo = phases(c, 0.42, 0.38)
    if ui <= 0 or uo >= 1: return c.img
    tin, tout = min(0.42, c.d * 0.28), min(0.38, c.d * 0.22)
    if "L" not in st:
        st["L"] = _layout(c.p.get("cover") or 0.38)
        st["base"] = _base(st["L"])
        st["words"], st["ev"], st["commits"] = _plan(c, tin, c.d - tout)
        st["pops"] = {}
    L, words, ev, commits = st["L"], st["words"], st["ev"], st["commits"]
    t = c.t
    kb = st["base"].copy()
    # ---- keys being pressed right now
    pressed = [e for e in ev if e[0] <= t < e[0] + max(0.09, min(0.13, e[3] * 1.1)) and e[1] == "key"]
    upper_soon = any(e[1] == "key" and e[2].isupper() and e[0] - 0.12 <= t < e[0] + 0.05 for e in ev)
    dyn = SS(W, L["kb_h"])
    if upper_soon: _key(dyn, "shift", L["keys"]["shift"], active=True)
    for e in pressed:
        if e[2] == " ": _key(dyn, " ", L["keys"][" "], pressed=True)
    # ---- predictive bar: the next words you say; the middle one is tapped when you say it
    cur = next((k for k, (tc, w, i) in enumerate(commits) if tc > t), len(commits))
    # the bar shows the word being typed in the middle; a tapped word flashes, then the bar moves on
    HL = 0.17
    tap = None
    for j, e in enumerate(ev):
        end = min(e[0] + HL, ev[j + 1][0]) if j + 1 < len(ev) else e[0] + HL   # cut short by the next keystroke
        if e[1] == "tap" and e[0] <= t < end: tap = e
    shown_i = tap[4] if tap else cur
    if st.get("shown") != shown_i: st["shown"], st["since"] = shown_i, t
    sw = 0.4 + 0.6 * ease_out(prog(t, st["since"], 0.12)) if st["since"] > c.t0 + 0.05 else 1.0
    sugg = [words[i][0] if 0 <= i < len(words) else "" for i in (shown_i + 1, shown_i, shown_i + 2)]
    if tap:
        k = (t - tap[0]) / HL
        dyn.rr((W / 3 + 8, 12, 2 * W / 3 - 8, PRED_H - 12), 14, fill=(255, 255, 255, int(235 * (1 - ease_in(k) * 0.6))))
    preds = []
    for j, wd in enumerate(sugg):
        if not wd: continue
        f = font(42, 600 if j == 1 else 420)
        txt = wd
        while f.getlength(txt) > W / 3 - 30 and len(txt) > 2: txt = txt[:-1]
        if txt != wd: txt = txt[:-1] + "…"
        preds.append((j, txt))
    for j, txt in preds:
        dyn.text((W / 6 + j * W / 3, PRED_H / 2 + 2 + (1 - sw) * 8), txt, 42, 600 if j == 1 else 420,
                 fill=(20, 20, 22, int(255 * sw)), anchor="mm")
    kb.alpha_composite(dyn.out())
    # ---- the key-pop balloon (drawn over the bar, so it lives on the frame layer)
    pops = []
    for e in pressed:
        if e[2] != " " and e[2].lower() in L["keys"]:
            key = e[2]
            if key not in st["pops"]: st["pops"][key] = _pop(L, key)
            pops.append(st["pops"][key])
    # ---- the text field: what's been typed so far
    typed = ""
    for tc, w, i in commits:
        if tc <= t: typed += w + " "
    part = "".join(e[2] for e in ev if e[1] == "key" and e[2] != " " and e[0] <= t and e[4] == cur
                   and (cur >= len(commits) or e[0] < commits[cur][0]))
    shown = typed + part
    # ---- slide up from the bottom
    slide = (1 - ease_out(ui)) * (L["kb_h"] + 160) + ease_in(uo) * (L["kb_h"] + 180)
    ky = L["ky0"] + slide
    img = c.img.copy()
    if ky < H:
        put(img, kb, 0, ky)
        for im, ox, oy in pops:
            sh, pad = shadow_of(im, 10, 0.32)
            put(img, sh, ox - pad, ky + oy - pad + 3)
            put(img, im, ox, ky + oy)
    # the field floats just above the keyboard
    fh, fx0, fx1 = 86, 34, W - 34
    fy = ky - 18 - fh
    if fy < H:
        fl = SS(fx1 - fx0, fh)
        fl.rr((0, 0, fx1 - fx0, fh), fh / 2, fill=(255, 255, 255, 250), outline=(196, 198, 204, 255), width=1.6)
        has = bool(shown.strip())
        sb = back(prog(t, ev[0][0], 0.3), 2.0) if (has and ev) else 0.0
        bx = fx1 - fx0 - fh / 2 - 2
        tx_max = (fx1 - fx0) - 40 - (fh if sb > 0 else 20)
        if sb > 0.02:
            r = (fh / 2 - 9) * sb
            fl.circ(bx, fh / 2, r, fill=IOS_BLUE + (255,))
            a = r / (fh / 2 - 9)
            fl.line([(bx, fh / 2 + 13 * a), (bx, fh / 2 - 13 * a)], (255, 255, 255, 255), 4.2)
            fl.line([(bx - 10 * a, fh / 2 - 3 * a), (bx, fh / 2 - 13 * a), (bx + 10 * a, fh / 2 - 3 * a)], (255, 255, 255, 255), 4.2)
        field = fl.out()
        if has:
            li = label_img(shown.rstrip() + (" " if shown.endswith(" ") else ""), 40, 450, (0, 0, 0))
            caret_x = li.width - 2
            if li.width > tx_max:   # keep the end in view; the start fades away on the left
                li = li.crop((li.width - int(tx_max), 0, li.width, li.height))
                a = np.asarray(li.getchannel("A"), np.float32)
                ramp = np.clip(np.arange(li.width) / 40.0, 0, 1)
                li.putalpha(Image.fromarray((a * ramp[None, :]).astype(np.uint8), "L"))
                caret_x = li.width - 2
            field.alpha_composite(li, (30, int((fh - li.height) / 2)))
        else:
            caret_x = 0
            ph = str(c.p.get("placeholder") or "")
            if ph:
                li = label_img(ph, 40, 450, (160, 160, 166)); field.alpha_composite(li, (32, int((fh - li.height) / 2)))
        last = max([e[0] for e in ev if e[0] <= t], default=-9)
        blink = 1.0 if t - last < 0.5 else (1.0 if ((t - last) % 1.0) < 0.55 else 0.0)
        if blink:
            cs = SS(8, fh); cs.rr((2, fh / 2 - 24, 5.5, fh / 2 + 24), 1.7, fill=IOS_BLUE + (255,))
            field.alpha_composite(cs.out(), (int(30 + caret_x - 2), 0))
        fa = min(1.0, ease_out(ui * 1.5)) * (1 - ease_out(uo))
        stamp(img, field, (fx0 + fx1) / 2, fy + fh / 2, a=fa, shadow=0.3, blur=18, dy=6)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "typed text and predictions are your own words in the order you say them",
    "needs": ["talk"],
}
