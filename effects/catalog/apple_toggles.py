"""Apple toggles: an iPhone-style settings card under your face; each switch flips on as you say its word."""
import math
from PIL import Image
from core import (key_words, W, H, SS, glass, comp, place, ease_out, back, prog, lerpc, clamp01, hexc, norm_word, font, text_img, SFP)

NAME = "apple-toggles"
KIND = "cards"
ABOUT = "iPhone settings switches under your face that flip on as you say each word"
DUR = 5.0
PARAMS = dict(
    rows=None,    # [{"label": "Sleep more", "on": "sleep"}, ...]  "on": a word you say, or seconds into the video.
                  # Default: the first three key words you say in the window, each flipping on as you say it.
    icons=["#FF9F0A", "#BF5AF2", "#FF453A", "#30D158", "#0A84FF"],
    style="glass",  # glass (frosted, light) | dark (iOS dark mode list)
    y=None,       # top of the card (px); default just under your chin
)
ROW_H, CARD_W, PAD = 128, 900, 22

def _rows(c):
    rows = c.p.get("rows")
    out = []
    if rows:
        for r in rows:
            on = r.get("on")
            if isinstance(on, (int, float)): t = float(on)
            else:
                w = next((w for w in c.words_in(c.t0, c.t1) if norm_word(w["w"]) == norm_word(str(on))), None) \
                    or c.subj.find_word(str(on), c.t0)
                t = w["s"] if w else c.t0 + 0.6 + 0.8 * len(out)
            out.append((r["label"], t))
    else:
        out = [(w["w"].strip(".,!?").capitalize(), w["s"]) for w in key_words(c.words_in(), 3)]
    return out

def _icon(s, x, y, col, k):
    s.rr((x, y, x + 64, y + 64), 16, fill=col)
    # a simple glyph so the squares read as app icons
    g = (255, 255, 255)
    cx, cy = x + 32, y + 32
    if k % 3 == 0: s.circ(cx, cy, 14, fill=g)
    elif k % 3 == 1: s.poly([(cx, cy - 17), (cx + 5, cy - 5), (cx + 17, cy - 5), (cx + 7, cy + 3), (cx + 11, cy + 16), (cx, cy + 8),
                            (cx - 11, cy + 16), (cx - 7, cy + 3), (cx - 17, cy - 5), (cx - 5, cy - 5)], fill=g)
    else: s.rr((cx - 14, cy - 10, cx + 14, cy + 12), 5, fill=g); s.circ(cx, cy + 1, 6, fill=col)

def render(c):
    st = c.state
    if "rows" not in st: st["rows"] = _rows(c)
    rows = st["rows"]
    dark = c.p["style"] == "dark"
    cx, cy, fw, fh = c.face
    n = len(rows)
    ch = n * ROW_H + 2 * PAD - (ROW_H - 96) // 1
    top = c.p["y"] if c.p.get("y") is not None else min(H - 300 - ch, cy + fh * 0.78)
    x0 = (W - CARD_W) // 2
    # in: rise with a little overshoot; out: drop and fade
    u_in = prog(c.u, 0, 0.45); u_out = prog(c.u, c.d - 0.35, 0.35)
    if u_in <= 0: return c.img
    rise = (1 - back(u_in)) * 90 + ease_out(u_out) * 60
    a = min(ease_out(u_in * 1.4), 1 - ease_out(u_out))
    sc = 0.94 + 0.06 * ease_out(u_in)
    # the card
    if dark:
        card = Image.new("RGBA", (CARD_W, ch), (28, 28, 30, 236))
        from core import rounded; card = rounded(card, 34); bx, by = x0, top
    else:
        card, bx, by = glass(c.img, (x0, top, x0 + CARD_W, top + ch), r=34, blur=26, tint=(250, 250, 252), tint_a=0.74)
    s = SS(CARD_W, ch)
    ink = (245, 245, 247) if dark else (17, 17, 19)
    sep = (58, 58, 60) if dark else (200, 200, 206)
    icols = [hexc(x) for x in c.p["icons"]]
    for k, (label, t_on) in enumerate(rows):
        y = PAD + k * ROW_H
        if k: s.line([(118, y), (CARD_W - 30, y)], sep + (255,), 1.5, round_caps=False)
        _icon(s, 32, y + (ROW_H - 64) / 2, icols[k % len(icols)], k)
        s.text((124, y + ROW_H / 2), label, 50, 600, fill=ink, anchor="lm")
        # the switch
        on = ease_out(prog(c.t, t_on, 0.22))
        tw, th = 128, 76
        tx, ty = CARD_W - 34 - tw, y + (ROW_H - th) / 2
        off_col = (57, 57, 61) if dark else (226, 226, 232)
        s.rr((tx, ty, tx + tw, ty + th), th / 2, fill=lerpc(off_col, (52, 199, 89), on))
        bump = 1 + 0.12 * math.sin(math.pi * clamp01((c.t - t_on) / 0.22)) if c.t >= t_on else 1
        kr = (th / 2 - 4) * bump
        kx = tx + th / 2 + (tw - th) * on
        s.circ(kx, ty + th / 2 + 2, kr, fill=(0, 0, 0, 40))
        s.circ(kx, ty + th / 2, kr, fill=(255, 255, 255))
    card.alpha_composite(s.out())
    cv = c.canvas()
    place(cv, card, W / 2, top + ch / 2 + rise, s=sc, rx=-8 * (1 - ease_out(u_in)), shadow=0.28, a=a)
    return c.front(cv)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "dur": 7.0,
    "params": {},
    "note": "the labels are your own key words in the window; a label you write in rows is your wording (flag it)",
}
