"""Cover story: you become a magazine cover. A huge white Didot masthead (your key word) runs across the top behind
your head, so your head overlaps its lower part; its letters rise in one by one. Small cover lines (your own
phrases) sit at the left and right with thin rules, a date line shows today's date, and the frame gets a slight
editorial grade. At the end the type lifts away."""
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, SS, font, f32, to_pil, mix, over, vgrad, ease_out, ease_in, ease_io, prog, clamp, hexc,
                  key_words, norm_word, DIDOT, SFP)
from catalog._b import face_stats, solid_mask, head_top
from catalog._print import key_word
from catalog._wall import short_phrases, near_window, today_line

NAME = "cover-story"
KIND = "behind"
ABOUT = "A magazine cover: a huge serif masthead behind your head, cover lines of your words, today's date"
DUR = 5.0
PARAMS = dict(
    masthead=None,   # the big word across the top; default your key word in the window, in capitals
    lines=None,      # cover lines: a list of texts (or {"kicker": "...", "text": "..."}); default short phrases you say
    date=None,       # the date line; default today's date; "" for none
    color=None,      # masthead colour; default white
    accent=None,     # colour of the short rules, the highlighted word in each line and any kickers; default the skin's accent
    grade=0.6,       # how strong the editorial grade is (contrast, warmth, darker top), 0-1
)
MARGIN = 44


# ------------------------------------------------------------------ the masthead
def _masthead(txt, maxw, cap_max, cap_min=215):
    """Letters of the masthead: [(RGBA, x, top)] laid out from x=0 with the baseline at y=0 (tops are negative),
    plus the width, cap height and the font size. Tight tracking; long words are condensed a little."""
    probe = font(400, 700, DIDOT, 2)
    trk = -0.025
    nat_w = sum(probe.getlength(ch) for ch in txt) + trk * 400 * (len(txt) - 1)
    bb = probe.getbbox("H")
    cap400 = bb[3] - bb[1]
    size = 400 * maxw / max(1, nat_w)
    cap = cap400 * size / 400
    cond = 1.0
    if cap > cap_max: size *= cap_max / cap; cap = cap_max
    elif cap < cap_min:                       # long word: condense it a little rather than shrink it to nothing
        cond = max(0.62, cap / cap_min)
        size = 400 * maxw / max(1, nat_w * cond); cap = cap400 * size / 400
        if cap > cap_max: size *= cap_max / cap; cap = cap_max
    f = font(size * 2, 700, DIDOT, 2)
    asc, desc = f.getmetrics()
    out, x = [], 0.0
    for k, ch in enumerate(txt):
        adv = f.getlength(ch)
        im = Image.new("RGBA", (int(adv + 40), asc + desc + 20), (255, 255, 255, 0))
        ImageDraw.Draw(im).text((20, asc + 10), ch, font=f, fill=(255, 255, 255, 255), anchor="ls")
        im = im.resize((max(1, int(im.width * cond / 2)), im.height // 2), Image.LANCZOS)
        out.append((im, x * cond / 2 - 20 * cond / 2, -(asc + 10) / 2))
        kern = f.getlength(txt[:k + 2]) - f.getlength(txt[:k + 1]) - f.getlength(txt[k + 1]) if k + 1 < len(txt) else 0
        x += adv + kern + trk * size * 2
    width = (x - trk * size * 2) * cond / 2
    return out, width, cap, size


# ------------------------------------------------------------------ cover lines
def _blocks(c):
    """[(kicker, text)] for the cover lines."""
    given = c.p.get("lines")
    if given is not None:
        out = []
        for g in given:
            if isinstance(g, dict): out.append((str(g.get("kicker") or ""), str(g.get("text") or "")))
            else: out.append(("", str(g)))
        return out
    mast = norm_word(_mast_text(c))
    sp = short_phrases(c.words or [], 30, 10)
    sp = [x for x in sp if mast not in [norm_word(w["w"]) for w in x[3]]]
    inwin = sorted([x for x in sp if c.t0 - 0.3 <= x[1] <= c.t1], key=lambda x: -x[4])
    pool = inwin + near_window([x for x in sp if x not in inwin], c.t0, c.t1)
    return [("", x[0]) for x in pool[:4]]

def _mast_text(c):
    if c.p.get("masthead"): return str(c.p["masthead"]).upper()
    return key_word(c).upper()

def _block_img(kicker, text, maxw, acc, style=0):
    """A cover line: a short accent rule (or a kicker in accent caps), then the line in caps with its strongest word
    in the accent colour. style 0: Didot Bold; style 1: letter-spaced sans. RGBA."""
    t = re.sub(r"[.!?,;:]+$", "", text).upper()
    hot = max(key_words([{"w": w} for w in t.split()]), key=lambda w: len(norm_word(w["w"])), default=None)
    hot = norm_word(hot["w"]) if hot else None
    if style == 0: path, idx, wt, smax, trk = DIDOT, 2, 700, 56, 0.0
    else: path, idx, wt, smax, trk = SFP, 0, 860, 34, 0.12
    def width(l, f): return f.getlength(l) + trk * f.size * max(0, len(l) - 1)
    size = smax
    while size > 22:
        f = font(size, wt, path, idx)
        lines = _wrap(t, f, maxw, trk)
        if len(lines) <= 3 and all(width(l, f) <= maxw for l in lines): break
        size -= 2
    f = font(size, wt, path, idx)
    lines = _wrap(t, f, maxw, trk)[:3]
    lh = size * (1.0 if style == 0 else 1.18)
    kh = 34 if kicker else 22
    h = int(kh + lh * len(lines) + 10)
    s = SS(maxw + 8, h + 8)
    if kicker:
        x = 0; kf = font(24, 820)
        for ch in kicker:
            s.text((x, 24), ch, 24, 820, fill=acc + (255,), anchor="ls"); x += kf.getlength(ch) + 4
    else:
        s.rect((0, 2, 46, 6.5), fill=acc + (255,))
    y = kh
    sp_w = f.getlength(" ") + trk * size
    for l in lines:
        x = 0
        for wd in l.split(" "):
            colr = acc if hot and norm_word(wd) == hot else (255, 255, 255)
            for ch in (wd if trk else [wd]):
                s.text((x, y + size * 0.8), ch, size, wt, fill=colr + (255,), anchor="ls", path=path, index=idx)
                x += f.getlength(ch) + trk * size
            x += sp_w - (trk * size if trk else 0)
        y += lh
    im = s.out()
    return im.crop((0, 0, im.width, int(y + 4)))

def _wrap(t, f, maxw, trk=0.0):
    words, lines, cur = t.split(), [], ""
    for w in words:
        n = (cur + " " + w).strip()
        if cur and f.getlength(n) + trk * f.size * (len(n) - 1) > maxw: lines.append(cur); cur = w
        else: cur = n
    if cur: lines.append(cur)
    return lines

def _date_img(txt, width, acc):
    """The date line: letter-spaced caps between two hairlines."""
    sz = 24
    f = font(sz, 700)
    t = txt.upper()
    trk = sz * 0.28
    tw = sum(f.getlength(ch) + trk for ch in t) - trk
    s = SS(width, 44)
    x0 = (width - tw) / 2
    x = x0
    for ch in t:
        s.text((x, 22), ch, sz, 700, fill=(255, 255, 255, 240), anchor="lm")
        x += f.getlength(ch) + trk
    s.rect((0, 21.5, x0 - 22, 23), fill=(255, 255, 255, 200))
    s.rect((x0 + tw + 22, 21.5, width, 23), fill=(255, 255, 255, 200))
    return s.out()

def _shadow(im, blur=10, a=0.45):
    al = im.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * a))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh.putalpha(al)
    return sh


# ------------------------------------------------------------------ render
def render(c):
    st = c.state
    d, u = c.d, c.u
    acc = hexc(c.p["accent"]) if c.p.get("accent") else tuple(c.skin.accent)
    if "mast" not in st:
        (fx, fy, fw, fh), (bx0, by0, bx1, by1) = face_stats(c)
        ht = min(head_top(c, '_ht0'), c.face[1] - c.face[3] * 0.8) - 0.25 * max(0, c.face[1] - (by0 + by1) / 2 + 30)  # top of the hair
        txt = _mast_text(c)
        letters, mw, cap, size = _masthead(txt, W - 2 * MARGIN, 300) if txt else ([], 0, 0, 0)
        # the baseline sits a third of the way down into your head, so your head covers the bottom of the letters
        base = clamp(ht + cap * 0.42, 300 + cap, 1100)
        st["mast"] = dict(letters=letters, x0=(W - mw) / 2, base=base, cap=cap)
        # the date line just above the masthead
        date = c.p.get("date")
        date = today_line() if date is None else str(date)
        st["date"] = (_date_img(date, W - 2 * MARGIN, acc), MARGIN, max(226, base - cap - 66)) if date else None
        # cover lines: left and right of the head, below the masthead
        hx0 = fx - fw * 0.5 - 0.35 * max(0, fx - fw / 2 - bx0) - 26
        hx1 = fx + fw * 0.5 + 0.35 * max(0, bx1 - fx - fw / 2) + 26
        cols = []
        lw, rw = hx0 - MARGIN, W - MARGIN - hx1
        if lw >= 170: cols.append(("L", MARGIN, lw))
        if rw >= 170: cols.append(("R", hx1, rw))
        blocks = _blocks(c)
        items = []
        y_start = base + 54
        if cols:
            per = [[] for _ in cols]
            for k, b in enumerate(blocks[:2 * len(cols)]): per[k % len(cols)].append(b)
            for (side, x, w_), bl in zip(cols, per):
                y = y_start + (70 if side == "R" else 0)
                for j, (kick, text) in enumerate(bl):
                    im = _block_img(kick, text, int(min(w_, 330)), acc, j % 2)
                    if y + im.height > 1460: break
                    xx = x if side == "L" else W - MARGIN - im.width
                    items.append(dict(im=im, sh=_shadow(im), x=xx, y=y, side=side))
                    y += im.height + 46
        for k, it in enumerate(items): it["t"] = 0.55 + 0.16 * k
        st["items"] = items
        st["topfade"] = vgrad(W, H, 150, 0, 0, max(500, base + 120))
    m = st["mast"]
    sp = min(1.0, d / 4.0)
    out_len = min(0.65, d * 0.24)
    t_out = d - out_len
    k_g = ease_out(prog(u, 0, 0.45)) * (1 - ease_in(prog(u, d - 0.4, 0.4))) * float(c.p.get("grade", 0.6))
    # editorial grade: a little contrast, warmth, and the top of the room darker so white type reads
    src = f32(np.asarray(c.img))
    if k_g > 0.002:
        g = (src - 118) * (1 + 0.12 * k_g) + 118
        g *= np.array([1 + 0.045 * k_g, 1 + 0.01 * k_g, 1 - 0.05 * k_g], np.float32)
        room = over(g, with_a(st["topfade"], k_g))
    else:
        g, room = src, src
    lay = c.canvas()
    col = hexc(c.p["color"]) if c.p.get("color") else (255, 255, 255)
    n = len(m["letters"])
    stag = min(0.075, (0.9 * sp) / max(1, n))
    drawn = False
    for k, (im, lx, top) in enumerate(m["letters"]):
        p = prog(u, 0.12 + k * stag, 0.5)
        q = prog(u, t_out + k * min(0.04, out_len * 0.4 / max(1, n)), out_len * 0.6)
        if p <= 0 or q >= 1: continue
        drawn = True
        dy = m["cap"] * 0.42 * (1 - ease_out(p)) - 90 * ease_in(q)
        a = ease_out(min(1, p * 1.6)) * (1 - ease_in(q))
        li = im if col == (255, 255, 255) else _tint(im, col)
        x = m["x0"] + lx; y = m["base"] + top + dy
        if a < 0.999: li = with_a(li, a)
        sh = _shadow(li, 16, 0.32)
        _comp(lay, sh, x, y + 8)
        _comp(lay, li, x, y)
    room = over(room, lay)
    out = mix(g, room, solid_mask(c))
    # cover lines and the date: in front, like printed type on the cover
    fr = c.canvas()
    if st["date"]:
        im, x, y = st["date"]
        p = prog(u, 0.05, 0.5); q = prog(u, t_out, out_len * 0.7)
        a = ease_out(p) * (1 - ease_in(q))
        if a > 0.003:
            drawn = True
            wcut = int(im.width * ease_io(p))                # the rules draw outward from the middle
            if wcut < im.width:
                x0c = (im.width - wcut) // 2
                im = im.crop((x0c, 0, x0c + max(1, wcut), im.height)); x += x0c
            _comp(fr, with_a(im, a), x, y - 40 * ease_in(q))
    for k, it in enumerate(st["items"]):
        p = prog(u, it["t"] * max(0.5, sp), 0.45)
        q = prog(u, t_out + min(0.05, out_len * 0.3 / max(1, len(st["items"]))) * k, out_len * 0.6)
        if p <= 0 or q >= 1: continue
        drawn = True
        a = ease_out(p) * (1 - ease_in(q))
        dx = (-1 if it["side"] == "L" else 1) * 26 * (1 - ease_out(p))
        dy = -50 * ease_in(q)
        _comp(fr, with_a(it["sh"], a), it["x"] + dx, it["y"] + dy + 3)
        _comp(fr, with_a(it["im"], a), it["x"] + dx, it["y"] + dy)
    if not drawn and k_g <= 0.002: return c.img
    return to_pil(over(out, fr))

def with_a(im, a):
    if a >= 0.999: return im
    im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * max(0.0, a)))); return im

def _tint(im, col):
    t = Image.new("RGBA", im.size, tuple(col) + (0,)); t.putalpha(im.getchannel("A")); return t

def _comp(cv, im, x, y):
    from core import comp
    comp(cv, im, x, y)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the masthead is your key word; cover lines are short phrases you say; the date is today's",
    "needs": ["face"],
}
