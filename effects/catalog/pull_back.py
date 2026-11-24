"""Pull back: the camera pulls back to reveal the clip playing inside an app window (rounded, title-bar chrome) on a
light soft-grey backdrop. A small "Working on" card overlaps it on the left and ticks off steps (spinner, then check)
as you say them; under the window a render bar fills over a waveform of the real sound. Then it pushes back in."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, FPS, SS, font, SFMONO, ease_out, ease_io, ease_in, back, prog, lerp, clamp, clamp01
from ._ui import phases, put, stamp, shadow_of, rr_mask_fast, spinner, fit_text, loudness, contrast
from ._ui2 import key_items, given_items

NAME = "pull-back"
KIND = "camera"
ABOUT = "The camera pulls back: your clip plays in an app window, a 'Working on' card ticks off steps, a render bar fills"
DUR = 6.0
PARAMS = dict(
    items=None,             # the card's steps: ["Trim the intro", ...] or [{"label": "Trim the intro", "on": "intro"}, ...]
                            #   on: a word you say, or seconds into the video. Default: the key words you say, each
                            #   ticking off as you say it. Steps without a time are spread over the window.
    max_items=4,            # most default steps
    header="Working on",    # the card's header (Claude's wording: flag it before posting)
    status="Rendering",     # the label on the bar under the window (Claude's wording: flag it); "" for none
    title=None,             # text in the window's title bar; None: just the three dots
    percent=True,           # the bar's percentage (it follows the effect's own time, not a real render)
)
VW = 572.0
VH = VW * H / W
VX0, VY0 = 404.0, 306.0           # where the clip ends up (the window's video area)
TB, WR = 56.0, 26.0               # title bar height, window corner radius (final size)
CX0, CY0, CW = 92.0, 430.0, 408.0  # the card (top-left, width)
HEAD_H, ROW_H, PAD = 76, 60, 16
BAR_Y, BAR_H = VY0 + VH + 26, 104
INK, MUTED, FAINT = (24, 24, 27), (138, 138, 146), (196, 196, 204)
BG0, BG1 = (247, 247, 250), (228, 229, 234)

def _backdrop():
    y, x = np.mgrid[0:H // 4, 0:W // 4].astype(np.float32)
    d = np.sqrt(((x - W / 8) / (W / 4)) ** 2 + ((y - H * 0.42 / 4) / (W / 4)) ** 2)
    d = np.clip(d / 1.25, 0, 1) ** 1.3
    col = np.array(BG0, np.float32) * (1 - d[..., None]) + np.array(BG1, np.float32) * d[..., None]
    bg = Image.fromarray(col.astype(np.uint8), "RGB").resize((W, H), Image.BICUBIC).convert("RGBA")
    s = SS(W, H, k=1)
    for yy in range(20, H, 40):
        for xx in range(20, W, 40):
            s.d.ellipse((xx - 1.6, yy - 1.6, xx + 1.6, yy + 1.6), fill=(0, 0, 0, 20))
    bg.alpha_composite(s.im)
    return bg.convert("RGB")

def _chrome(w, tb, z, title):
    """The title bar at width w, height tb (z = size relative to the final window)."""
    s = SS(max(2, int(round(w))), max(2, int(round(tb))))
    s.rect((0, 0, w + 1, tb + 1), fill=(252, 252, 253, 255))
    s.line([(0, tb - 0.6), (w, tb - 0.6)], (222, 222, 228, 255), 1.2 * z, round_caps=False)
    for k, col in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        s.circ(26 * z + k * 24 * z, tb / 2, 7.5 * z, fill=col + (255,))
    if title:
        f = font(21 * z, 650)
        s.text((w / 2, tb / 2 + 1), fit_text(str(title), f, w - 200 * z), 21 * z, 650, fill=(70, 70, 78, 255), anchor="mm")
    return s.out()

def _items(c, st):
    lo, limit = c.t0 + st["tin"] + 0.35, c.t1 - st["tout"] - 0.75
    if c.p.get("items"):
        its = given_items(c, list(c.p["items"])[:6], lo, limit)
    else:
        its = [(l, s) for l, s in key_items(c, 12) if s <= limit]
        m = max(1, int(c.p.get("max_items") or 4))
        if len(its) > m: its = [its[int(round(i * (len(its) - 1) / (m - 1)))] for i in range(m)] if m > 1 else its[:1]
    return [(l, clamp(s, lo, limit)) for l, s in its]

def _card(c, st, t):
    items = st["items"]
    n = len(items)
    ch = HEAD_H + n * ROW_H + PAD + 4
    s = SS(CW, ch)
    s.rr((0, 0, CW, ch), 26, fill=(255, 255, 255, 255))
    s.rr((0.5, 0.5, CW - 0.5, ch - 0.5), 26, outline=(228, 228, 234, 255), width=1.2)
    acc, ink_acc = tuple(c.skin.accent), tuple(c.skin.accent_ink)
    hsp, bsp = c.skin.fontspec("title", 720), c.skin.fontspec("body", 560)
    all_done = prog(t, items[-1][1] + 0.2, 0.4) if n else 0.0
    hx, hy = 34, HEAD_H / 2 + 4
    if all_done > 0:
        _tick(s, hx, hy, 13, all_done, acc, ink_acc)
    else:
        spinner(s, hx, hy, 13, t, INK, 1.0)
    head = str(c.p.get("header") or "")
    if head:
        s.text((60, hy + 1), fit_text(head, font(29, hsp["weight"], hsp["path"], hsp["index"]), CW - 140), 29,
               hsp["weight"], fill=INK + (255,), anchor="lm", path=hsp["path"], index=hsp["index"])
    if n:
        ndone = sum(1 for _, ts in items if t >= ts)
        s.text((CW - 26, hy + 1), f"{ndone}/{n}", 22, 600, fill=MUTED + (255,), anchor="rm", path=SFMONO)
    s.line([(22, HEAD_H), (CW - 22, HEAD_H)], (234, 234, 238, 255), 1.2, round_caps=False)
    lf = font(27, bsp["weight"], bsp["path"], bsp["index"])
    for k, (label, ts) in enumerate(items):
        y = HEAD_H + 6 + k * ROW_H + ROW_H / 2
        prev = items[k - 1][1] if k else -1e9
        done, active = t >= ts, prev <= t < ts
        enter = ease_out(prog(t, st["card_t"] + 0.08 * k, 0.35))
        if enter <= 0: continue
        dx = (1 - enter) * 24
        if done:
            _tick(s, 34 + dx, y, 12, prog(t, ts, 0.45), acc, ink_acc)
            col = MUTED
        elif active:
            spinner(s, 34 + dx, y, 12, t, INK, enter)
            col = INK
        else:
            s.circ(34 + dx, y, 11, outline=FAINT + (int(255 * enter),), width=2.2)
            col = (160, 160, 168)
        lab = fit_text(label, lf, CW - 90)
        s.text((60 + dx, y + 1), lab, 27, bsp["weight"] + (80 if active else 0), fill=col + (int(255 * enter),), anchor="lm",
               path=bsp["path"], index=bsp["index"])
        if done:   # a strike through, drawn left to right
            sk = ease_out(prog(t, ts + 0.12, 0.35))
            if sk > 0:
                lw = s.textlen(lab, 27, bsp["weight"], bsp["path"], bsp["index"])
                s.line([(60 + dx, y + 2), (60 + dx + lw * sk, y + 2)], MUTED + (220,), 2.0, round_caps=False)
    return s.out()

def _tick(s, cx, cy, r, k, col, ink):
    if k <= 0: return
    rr = r * back(prog(k, 0, 0.55), 2.4)
    if rr > 0.3: s.circ(cx, cy, rr, fill=tuple(col) + (255,))
    kk = ease_out(prog(k, 0.3, 0.7))
    if kk <= 0: return
    pts = [(cx - r * 0.45, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.34), (cx + r * 0.46, cy - r * 0.32)]
    l1 = math.dist(pts[0], pts[1]); l2 = math.dist(pts[1], pts[2]); L = (l1 + l2) * kk
    path = [pts[0], (lerp(pts[0][0], pts[1][0], min(1, L / l1)), lerp(pts[0][1], pts[1][1], min(1, L / l1)))]
    if L > l1:
        f = (L - l1) / l2; path.append((lerp(pts[1][0], pts[2][0], f), lerp(pts[1][1], pts[2][1], f)))
    s.line(path, tuple(ink) + (255,), r * 0.22)

def _bar(c, st, t):
    """The render bar: label, percentage, and the real waveform filling in as it renders."""
    bw = int(VW)
    s = SS(bw, BAR_H)
    s.rr((0, 0, bw, BAR_H), 22, fill=(255, 255, 255, 255))
    s.rr((0.5, 0.5, bw - 0.5, BAR_H - 0.5), 22, outline=(228, 228, 234, 255), width=1.2)
    r0, r1 = st["r0"], st["r1"]
    p = clamp01((t - r0) / max(0.2, r1 - r0))
    pe = ease_io(p) * 0.25 + p * 0.75
    lab = str(c.p.get("status") or "")
    bsp = c.skin.fontspec("body", 640)
    if lab:
        s.text((24, 30), lab, 22, bsp["weight"], fill=INK + (255,), anchor="lm", path=bsp["path"], index=bsp["index"])
    if c.p.get("percent", True):
        s.text((bw - 24, 30), f"{int(math.floor(pe * 100 + 1e-6))}%", 21, 600, fill=MUTED + (255,), anchor="rm", path=SFMONO)
    lv = st["wave"]
    nb = len(lv)
    x0, x1 = 24, bw - 24
    step = (x1 - x0) / nb
    ym = 70
    acc = tuple(c.skin.accent)
    dark = INK
    for k, v in enumerate(lv):
        x = x0 + (k + 0.5) * step
        hh = 2.5 + 15 * v
        on = (k + 0.5) / nb <= pe
        col = dark + (255,) if on else FAINT + (255,)
        s.rr((x - 1.6, ym - hh, x + 1.6, ym + hh), 1.6, fill=col)
    xp = x0 + (x1 - x0) * pe
    if 0 < pe < 1:
        s.rr((xp - 1.5, ym - 22, xp + 1.5, ym + 22), 1.5, fill=acc + (255,))
        s.circ(xp, ym - 22, 5, fill=acc + (255,))
    return s.out()

def render(c):
    st = c.state
    if "bg" not in st:
        st["tin"], st["tout"] = min(0.8, c.d * 0.3), min(0.7, c.d * 0.25)
        st["bg"] = _backdrop()
        st["items"] = _items(c, st)
        st["card_t"] = c.t0 + st["tin"] * 0.8
        st["r0"], st["r1"] = c.t0 + st["tin"] * 0.8, c.t1 - st["tout"] - 0.15
        nb = int((VW - 48) // 7)
        st["wave"] = contrast(loudness(c, c.t0, c.t1, nb), 3, 99, 1.0)
        st["chrome_full"] = _chrome(VW, TB, 1.0, c.p.get("title"))
        st["shadow"] = None
    ui, uo = phases(c, st["tin"], st["tout"])
    if ui <= 0 or uo >= 1: return c.img
    t = c.t
    k = clamp01(min(ease_io(ui), 1 - ease_io(uo)))
    if k <= 0.0005: return c.img
    sf = VW / W
    s = math.exp(math.log(sf) * k)                     # the zoom, even in log space
    px, py = VX0 / (1 - sf), VY0 / (1 - sf)            # the point that stays put
    vx0, vy0 = px * (1 - s), py * (1 - s)
    vw, vh = W * s, H * s
    z = s / sf
    tb = TB * z
    r = WR * z * clamp01(k * 5)
    img = st["bg"].copy()
    # ---- the window: the clip under its title bar, rounded, with a soft shadow
    full = k > 0.999
    vwi, vhi = int(round(vw)), int(round(vh))
    if full:
        vwi, vhi = int(VW), int(round(VH))
    foot = c.img.resize((vwi, vhi), Image.BILINEAR, reducing_gap=2.0)
    tbi = int(round(tb))
    win = Image.new("RGBA", (vwi, vhi + tbi), (255, 255, 255, 255))
    win.paste(foot, (0, tbi))
    chrome = st["chrome_full"] if full else _chrome(vwi, tbi, z, c.p.get("title"))
    win.alpha_composite(chrome.resize((vwi, tbi), Image.BILINEAR) if chrome.size != (vwi, tbi) else chrome, (0, 0))
    win.putalpha(rr_mask_fast(win.width, win.height, r))
    wx, wy = vx0, vy0 - tb
    if k > 0.02:
        if full and st["shadow"] is not None:
            sh, pad = st["shadow"]
        else:
            small = win.resize((max(1, win.width // 4), max(1, win.height // 4)), Image.BILINEAR)
            sh, pad = shadow_of(small, 9, 0.42)
            sh = sh.resize((sh.width * 4, sh.height * 4), Image.BILINEAR); pad *= 4
            if full: st["shadow"] = (sh, pad)
        put(img, sh, wx - pad, wy - pad + 22 * z, min(1.0, k * 1.5))
    put(img, win, wx, wy)
    # ---- the render bar rises in under the window; the card pops in on the left
    pin = prog(c.u, st["tin"] * 0.82, 0.5)
    pout = prog(c.u, c.d - st["tout"] - 0.12, st["tout"] * 0.55)
    if pin > 0 and pout < 1:
        bar = _bar(c, st, t)
        a = min(1.0, ease_out(pin * 1.8)) * (1 - ease_out(pout))
        dy = (1 - back(pin, 1.3)) * 140 + ease_in(pout) * 120
        stamp(img, bar, VX0 + VW / 2, BAR_Y + BAR_H / 2 + dy, a=a, shadow=0.16, blur=22, dy=10)
    cin = prog(c.u, st["tin"] * 0.72, 0.5)
    if cin > 0 and pout < 1 and (st["items"] or c.p.get("header")):
        card = _card(c, st, t)
        a = min(1.0, ease_out(cin * 1.8)) * (1 - ease_out(pout))
        dx = -(1 - back(cin, 1.4)) * 180 - ease_in(pout) * 220
        bob = 6 * math.sin(2 * math.pi * 0.3 * (c.u - st["tin"]))
        sc = 0.9 + 0.1 * back(cin, 1.6)
        stamp(img, card, CX0 + CW / 2 + dx, CY0 + card.height / 2 + bob, s=sc, a=a, shadow=0.26, blur=30, dy=16)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "CLAUDE-WROTE: the card header 'Working on' and the bar label 'Rendering' (the defaults). The steps are your own key words, ticking off as you say them; the waveform is the clip's real sound.",
    "needs": ["talk"],
}
