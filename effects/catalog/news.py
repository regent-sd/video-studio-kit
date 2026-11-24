"""News: a front page (newspaper, dev blog or literary magazine) slides in; the headline is what you say, the photo is
you, live, and a yellow marker sweeps across your key word as you say it. Then the page drops away."""
import math, re, datetime
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, f32, to_pil, font, text_img, place, ease_out, ease_in, ease_io, back, prog, lerp, clamp, clamp01,
                  key_words, norm_word, hexc, rounded, SFP, SFMONO, NEWYORK, NEWYORK_IT, GEORGIA, DIDOT)
from ._print import paper, halftone, blur, stretch, grid, fbm, key_word

NAME = "news"
KIND = "cards"
ABOUT = "A newspaper / blog / magazine front page: your words as the headline, you as the photo, your key word highlighted"
DUR = 4.5
PARAMS = dict(
    style="newspaper",  # newspaper | blog | magazine
    masthead=None,      # the paper's (or magazine's) name; default none (the newspaper shows the date there instead)
    date=None,          # the date line; default today's date; "" for none
    headline=None,      # default: the sentence you say in the window (your own words)
    highlight=None,     # the word the marker sweeps over; default your key word in the headline
    path=None,          # blog only: the path line; default ~/<date>/<key word>
    color=None,         # marker colour; default the skin's accent (yellow)
)
S = "/System/Library/Fonts/Supplemental/"
IOWAN, PTSERIF, COPPER = S + "Iowan Old Style.ttc", S + "PTSerif.ttc", S + "Copperplate.ttc"
HOEFLER = S + "Hoefler Text.ttc"

# ------------------------------------------------------------------ words -> headline
def _sentences(words):
    out, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w["w"]): out.append(cur); cur = []
    if cur: out.append(cur)
    return out

def _headline(c):
    """(headline words, index of the highlighted word or -1, time the highlighted word is said)."""
    win = c.words_in()
    hl = c.p.get("highlight")
    if c.p.get("headline"):
        toks = str(c.p["headline"]).split()
        idx = -1
        target = norm_word(hl) if hl else None
        if not target:
            kws = key_words([{"w": t} for t in toks])
            target = norm_word(kws[0]["w"]) if kws else None
        for k, t in enumerate(toks):
            if target and norm_word(t) == target: idx = k; break
        w = next((x for x in win if target and norm_word(x["w"]) == target), None) or \
            (c.subj.find_word(hl or toks[idx], c.t0) if idx >= 0 else None)
        return toks, idx, (w["s"] if w else c.t0 + c.d * 0.4)
    if not win:                       # nothing said in the window: the sentence said nearest to it
        mid = (c.t0 + c.t1) / 2
        allw = c.words or []
        if allw:
            near = min(allw, key=lambda x: abs(x["s"] - mid))
            for snt in _sentences(allw):
                if near in snt: win = snt; break
    if not win: return [], -1, c.t0 + c.d * 0.4
    sents = _sentences(win)
    target = norm_word(hl) if hl else None
    kws = key_words(win)
    if not target and kws: target = norm_word(kws[0]["w"])
    pick = None
    for snt in sents:
        if target and any(norm_word(w["w"]) == target for w in snt): pick = snt; break
    if pick is None:
        full = [s_ for s_ in sents if re.search(r"[.!?]$", s_[-1]["w"])]
        pick = max(full or sents, key=len) if sents else []
    # drop leading fillers
    while pick and norm_word(pick[0]["w"]) in ("um", "uh", "so", "and", "but"):
        pick = pick[1:]
    pick = pick[:16]
    toks = [w["w"] for w in pick]
    if toks: toks[0] = toks[0][0].upper() + toks[0][1:]
    idx, t_hl = -1, c.t0 + c.d * 0.4
    for k, w in enumerate(pick):
        if target and norm_word(w["w"]) == target: idx, t_hl = k, w["s"]; break
    if not (c.t0 <= t_hl <= c.t1 - 0.3): t_hl = c.t0 + min(1.0, c.d * 0.4)
    return toks, idx, t_hl

def _wrap(toks, f, maxw):
    sp = f.getlength(" ")
    lines, cur, w = [], [], 0.0
    for t in toks:
        lw = f.getlength(t)
        if cur and w + sp + lw > maxw: lines.append(cur); cur, w = [t], lw
        else: w += (sp if cur else 0) + lw; cur.append(t)
    if cur: lines.append(cur)
    return lines

def _fit_head(toks, path, idx, weight, maxw, maxlines, smax, smin):
    """Biggest size that fits in maxlines, then the narrowest measure that keeps that many lines (balanced rag)."""
    pick = None
    for size in range(smax, smin - 1, -2):
        f = font(size, weight, path, idx)
        lines = _wrap(toks, f, maxw)
        if len(lines) <= maxlines and all(f.getlength(" ".join(l)) <= maxw for l in lines): pick = (size, lines); break
    if pick is None:
        f = font(smin, weight, path, idx); return smin, _wrap(toks, f, maxw)
    size, lines = pick
    f = font(size, weight, path, idx)
    n = len(lines); lo, hi = maxw * 0.4, maxw
    for _ in range(14):
        mid = (lo + hi) / 2
        if len(_wrap(toks, f, mid)) <= n and all(f.getlength(t) <= mid for t in toks): hi = mid
        else: lo = mid
    return size, _wrap(toks, f, hi + 1)

def _draw_head(size_lines, path, idx, weight, x0, y0, lead, color, hl_idx, align="left", maxw=0, wh=None):
    """Draw the headline on a transparent layer the page's size. Returns (layer, highlight box or None, bottom y)."""
    size, lines = size_lines
    f = font(size, weight, path, idx)
    lay = Image.new("RGBA", wh, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    sp = f.getlength(" ")
    box, k, y = None, 0, y0
    asc = size * 0.74
    for ln in lines:
        lw = f.getlength(" ".join(ln))
        x = x0 + ((maxw - lw) / 2 if align == "center" else 0)
        y_base = y + asc
        for t in ln:
            d.text((x, y_base), t, font=f, fill=color, anchor="ls")
            tw = f.getlength(t)
            if k == hl_idx:
                tw2 = f.getlength(t.rstrip(".,!?;:"))
                box = (x - size * 0.06, y_base - asc - size * 0.1, x + tw2 + size * 0.06, y_base + size * 0.14)
            x += tw + sp; k += 1
        y += size * lead
    return lay, box, y

def _columns(d, toks, f, x0, y0, colw, gap, ncol, y1, color, lead, drop=None):
    """Justified columns of body text, starting with an optional drop cap (font, colour). The text repeats as new
    paragraphs if it runs out."""
    sp0 = f.getlength(" ")
    lh = f.size * lead
    orig = list(toks)
    if not orig: return
    stream = list(orig)
    if drop is not None:
        df, dcol = drop
        ch = stream[0][0].upper()
        stream[0] = stream[0][1:]
    i = 0
    def nxt():
        nonlocal i
        if i >= len(stream):
            stream.extend(["\n"] + orig)
        t = stream[i]; i += 1
        return t
    pending = None
    for ci in range(ncol):
        x = x0 + ci * (colw + gap)
        y = y0
        indent_lines, indent_w = 0, 0
        if ci == 0 and drop is not None:
            d.text((x - 2, y + lh * 2.62), ch, font=df, fill=dcol, anchor="ls")
            indent_w = df.getlength(ch) + 10; indent_lines = 3
        ln = 0
        while y + lh <= y1:
            ind = indent_w if ln < indent_lines else 0
            avail = colw - ind
            line, w, brk = [], 0.0, False
            while True:
                t = pending if pending is not None else nxt()
                pending = None
                if t == "\n":
                    brk = True; break
                if not t: continue
                tw = f.getlength(t)
                if line and w + sp0 + tw > avail: pending = t; break
                w += (sp0 if line else 0) + tw; line.append(t)
            gaps = len(line) - 1
            extra = (avail - w) / gaps if gaps and not brk and (avail - w) / gaps < sp0 * 2.2 else 0
            xx = x + ind
            for t in line:
                d.text((xx, y + f.size), t, font=f, fill=color, anchor="ls")
                xx += f.getlength(t) + sp0 + extra
            y += lh; ln += 1
            if brk: y += lh * 0.4

# ------------------------------------------------------------------ pages
def _date_text(c):
    if c.p.get("date") is not None: return str(c.p["date"])
    t = datetime.date.today()
    return t.strftime("%A, %B ") + str(t.day) + t.strftime(", %Y")

def _body_tokens(c, head):
    toks = [w["w"] for w in c.words if norm_word(w["w"]) not in ("um", "uh")]
    return toks or head or ["—"]

def _newspaper(c, toks, hl, col):
    PW, PH = 980, 1740
    pg = paper(PW, PH, (238, 233, 220), seed=21, grain=5.0, mottle=8.0, fibers=0.5, edge=0.6).copy()
    im = Image.fromarray(pg.astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    ink = (22, 21, 20)
    M = 46
    # masthead
    mh = c.p.get("masthead")
    date = _date_text(c)
    y = 52
    if mh:
        sz = 132
        while sz > 40 and font(sz, 700, HOEFLER, 1).getlength(mh) > PW - 2 * M - 20: sz -= 4
        d.text((PW / 2, y + sz * 0.8), mh, font=font(sz, 700, HOEFLER, 1), fill=ink, anchor="ms")
        y += sz * 1.0
    elif date:
        sz = 76
        while sz > 30 and font(sz, 700, HOEFLER, 1).getlength(date) > PW - 2 * M - 20: sz -= 4
        d.text((PW / 2, y + sz * 0.9), date, font=font(sz, 700, HOEFLER, 1), fill=ink, anchor="ms")
        y += sz * 1.25
    y += 14
    d.line([(M, y), (PW - M, y)], fill=ink, width=4); d.line([(M, y + 8), (PW - M, y + 8)], fill=ink, width=1)
    y += 14
    if mh and date:
        f = font(19, 600, IOWAN, 0)
        d.text((PW / 2, y + 22), date.upper(), font=f, fill=ink, anchor="ms")
        y += 34
        d.line([(M, y), (PW - M, y)], fill=ink, width=1); d.line([(M, y + 6), (PW - M, y + 6)], fill=ink, width=3)
        y += 6
    y += 26
    # headline
    hs = _fit_head(toks, IOWAN, 4, 700, PW - 2 * M, 3, 112, 56)
    head, box, yb = _draw_head(hs, IOWAN, 4, 700, M, y, 1.02, ink, hl, maxw=PW - 2 * M, wh=(PW, PH))
    y = yb + 16
    # photo box
    ph = int(min(700, PH - y - 420))
    photo = (M, int(y), PW - M, int(y + ph))
    y = photo[3] + 10
    d.line([(M, y + 4), (PW * 0.42, y + 4)], fill=(120, 116, 108), width=1)
    y += 26
    # body: three justified columns of your words, with column rules
    ncol, gap = 3, 26
    colw = (PW - 2 * M - gap * (ncol - 1)) / ncol
    for k in range(1, ncol):
        xg = M + k * (colw + gap) - gap / 2
        d.line([(xg, y), (xg, PH - 60)], fill=(170, 165, 155), width=1)
    _columns(d, _body_tokens(c, toks), font(19, 400, GEORGIA), M, y, colw, gap, ncol, PH - 60, (88, 86, 82), 1.42,
             drop=(font(74, 700, IOWAN, 4), ink))
    return dict(page=im, head=head, head_hl=None, box=box, photo=photo, kind="newspaper", marker="multiply")

def _magazine(c, toks, hl, col):
    PW, PH = 980, 1740
    pg = paper(PW, PH, (246, 240, 226), seed=33, grain=3.5, mottle=6.0, fibers=0.3, edge=0.3).copy()
    im = Image.fromarray(pg.astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    ink = (34, 28, 24)
    M = 60
    y = 64
    mh = c.p.get("masthead"); date = _date_text(c)
    if mh:
        d.text((M, y + 30), mh.upper(), font=font(30, 700, DIDOT, 2), fill=ink, anchor="ls")
    if date:
        d.text((PW - M, y + 30), date.upper(), font=font(17, 600, IOWAN, 0), fill=(120, 108, 96), anchor="rs")
    if mh or date:
        y += 46
        d.line([(M, y), (PW - M, y)], fill=ink, width=1)
    y += 26
    photo = (M, int(y), PW - M, int(y + 760))
    y = photo[3] + 44
    kw = ""
    if hl >= 0 and toks:
        kw = re.sub(r"[^\w'-]", "", toks[hl]).upper()
    if kw:
        f = font(20, 700, IOWAN, 1)
        tr = "  ".join(kw)
        d.text((PW / 2, y), tr, font=f, fill=(150, 70, 40), anchor="ms")
        y += 26
    hs = _fit_head(toks, DIDOT, 0, 400, PW - 2 * M, 3, 96, 50)
    head, box, yb = _draw_head(hs, DIDOT, 0, 400, M, y, 1.08, ink, hl, align="center", maxw=PW - 2 * M, wh=(PW, PH))
    y = yb + 20
    d.line([(PW / 2 - 40, y), (PW / 2 + 40, y)], fill=ink, width=1)
    y += 28
    ncol, gap = 2, 40
    colw = (PW - 2 * M - gap) / 2
    _columns(d, _body_tokens(c, toks), font(21, 400, NEWYORK, 0), M, y, colw, gap, ncol, PH - 70, (96, 88, 80), 1.5,
             drop=(font(80, 400, DIDOT, 0), ink))
    return dict(page=im, head=head, head_hl=None, box=box, photo=photo, kind="magazine", marker="multiply")

def _blog(c, toks, hl, col):
    PW, PH = 960, 1560
    bg = (13, 15, 19)
    im = Image.new("RGBA", (PW, PH), bg + (255,))
    d = ImageDraw.Draw(im)
    M = 54
    # window chrome
    d.rectangle([0, 0, PW, 74], fill=(22, 25, 31))
    for k, cc in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
        d.ellipse([28 + k * 32, 26, 48 + k * 32, 46], fill=cc)
    t = datetime.date.today()
    date = _date_text(c) if c.p.get("date") is not None else t.isoformat()
    kw = re.sub(r"[^\w'-]", "", toks[hl]).lower() if 0 <= hl < len(toks) else key_word(c).lower()
    path = c.p.get("path") or "~/" + "/".join(p_ for p_ in (date, kw) if p_)
    y = 130
    f = font(26, 500, SFMONO)
    d.text((M, y), "$ ", font=f, fill=(40, 200, 64), anchor="ls")
    d.text((M + f.getlength("$ "), y), "cat " + path, font=f, fill=(150, 156, 168), anchor="ls")
    y += 44
    hs = _fit_head(toks, SFP, 0, 860, PW - 2 * M, 4, 92, 48)
    head, box, yb = _draw_head(hs, SFP, 0, 860, M, y, 1.08, (246, 246, 248), hl, maxw=PW - 2 * M, wh=(PW, PH))
    hl_lay, _, _ = _draw_head(hs, SFP, 0, 860, M, y, 1.08, (14, 14, 16), hl, maxw=PW - 2 * M, wh=(PW, PH))
    y = yb + 24
    photo = (M, int(y), PW - M, int(y + min(600, PH - y - 280)))
    y = photo[3] + 46
    f = font(22, 500, SFMONO)
    body = _body_tokens(c, toks)
    lines = _wrap(body, f, PW - 2 * M - 40)
    k = 0
    while y < PH - 50 and lines:
        ln = " ".join(lines[k % len(lines)])
        d.text((M, y), "//", font=f, fill=(70, 76, 88), anchor="ls")
        d.text((M + 40, y), ln, font=f, fill=(120, 126, 138), anchor="ls")
        y += 36; k += 1
    return dict(page=rounded(im, 30), head=head, head_hl=hl_lay, box=box, photo=photo, kind="blog", marker="over")

# ------------------------------------------------------------------ the photo (you, live)
def _photo(c, st, box, kind):
    x0, y0, x1, y1 = box
    pw, ph = x1 - x0, y1 - y0
    cx, cy, fw, fh = c.face
    if "fx" not in st: st["fx"], st["fy"], st["fh"] = cx, cy, fh
    st["fx"] += (cx - st["fx"]) * 0.08; st["fy"] += (cy - st["fy"]) * 0.08; st["fh"] += (fh - st["fh"]) * 0.05
    s = max(ph * 0.46 / max(60.0, st["fh"]), pw / W * 1.01)
    cw_, ch_ = pw / s, ph / s
    sx = clamp(st["fx"] - cw_ / 2, 0, max(0, W - cw_)) if cw_ <= W else (W - cw_) / 2
    sy = clamp(st["fy"] - ch_ * 0.42, 0, max(0, H - ch_)) if ch_ <= H else (H - ch_) / 2
    im = c.img.transform((pw, ph), Image.AFFINE, (1 / s, 0, sx, 0, 1 / s, sy), Image.BILINEAR)
    a = f32(np.asarray(im))
    if kind == "newspaper":
        L = (a @ np.array([0.3, 0.59, 0.11], np.float32)) / 255.0
        tone = np.clip(stretch(L, None, 1, 99, 0.9) * 0.92 + 0.06, 0, 1)
        ink = halftone(tone, cell=6.2, angle=45)
        pap = np.array([236, 231, 218], np.float32)
        out = pap * (1 - ink[..., None]) + np.array([26, 25, 24], np.float32) * ink[..., None]
        return out
    if kind == "magazine":
        g = a.mean(2, keepdims=True)
        a = np.clip((a - 128) * 1.08 + 128 + np.array([8, 3, -6], np.float32), 0, 255)
        a = a * 0.9 + g * 0.1
        return a
    return np.clip((a - 128) * 1.04 + 128 + np.array([-4, 0, 6], np.float32), 0, 255)

# ------------------------------------------------------------------ render
def render(c):
    st = c.state
    col = hexc(c.p["color"]) if c.p.get("color") else c.skin.accent
    if "pg" not in st:
        toks, hl, t_hl = _headline(c)
        if not toks: toks = [key_word(c) or "—"]
        style = c.p.get("style") or "newspaper"
        mk = {"blog": _blog, "magazine": _magazine}.get(style, _newspaper)
        pg = mk(c, toks, hl, col)
        pg["t_hl"] = t_hl
        pg["base"] = f32(np.asarray(pg["page"]))          # RGBA float
        st["pg"] = pg
    pg = st["pg"]
    u, d = c.u, c.d
    tin = min(0.8, d * 0.3); tout = min(0.6, d * 0.22)
    pi_, po = prog(u, 0, tin), prog(u, d - tout, tout)
    PH_, PW_ = pg["base"].shape[:2]
    a = pg["base"].copy()
    # the marker sweeps over the word as it's said
    box = pg["box"]
    mk = 0.0
    if box is not None:
        t_hl = pg["t_hl"]
        mk = ease_io(prog(c.t, max(c.t0 + tin * 0.7, t_hl - 0.05), 0.38))
    if box is not None and mk > 0:
        bx0, by0, bx1, by1 = [int(round(v)) for v in box]
        bx1m = bx0 + (bx1 - bx0) * mk
        lay = Image.new("L", (PW_, PH_), 0)
        dd = ImageDraw.Draw(lay)
        sk = (by1 - by0) * 0.08
        dd.polygon([(bx0 + sk, by0 + 2), (bx1m, by0), (bx1m - sk * 0.5, by1), (bx0, by1 - 2)], fill=255)
        mm = np.asarray(lay, np.float32) / 255.0
        if pg["marker"] == "multiply":
            # highlighter ink: a little uneven, multiplied into the paper
            mm = mm * (0.8 + 0.2 * fbm(PW_, PH_, 40, 3, 9))
            tint = np.array(col, np.float32) / 255.0
            a[..., :3] *= (1 - mm[..., None] * 0.92) + mm[..., None] * 0.92 * tint
        else:
            a[..., :3] = a[..., :3] * (1 - mm[..., None]) + np.array(col, np.float32) * mm[..., None]
    # headline text (in the blog, the highlighted part turns dark)
    hd = f32(np.asarray(pg["head"]))
    ha = hd[..., 3:4] / 255.0
    a[..., :3] = a[..., :3] * (1 - ha) + hd[..., :3] * ha
    if pg["head_hl"] is not None and box is not None and mk > 0:
        hh = f32(np.asarray(pg["head_hl"]))
        clip = np.zeros((PH_, PW_, 1), np.float32)
        bx0, by0, bx1, by1 = [int(round(v)) for v in box]
        clip[max(0, by0):by1, max(0, bx0):int(bx0 + (bx1 - bx0) * mk)] = 1
        hb = hh[..., 3:4] / 255.0 * clip
        a[..., :3] = a[..., :3] * (1 - hb) + hh[..., :3] * hb
    # the photo: you, live
    x0, y0, x1, y1 = pg["photo"]
    ph = _photo(c, st, pg["photo"], pg["kind"])
    if pg["kind"] == "blog":
        r = Image.fromarray(np.clip(ph, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
        r = rounded(r, 18)
        rr = f32(np.asarray(r)); ra = rr[..., 3:4] / 255.0
        a[y0:y1, x0:x1, :3] = a[y0:y1, x0:x1, :3] * (1 - ra) + rr[..., :3] * ra
    else:
        a[y0:y1, x0:x1, :3] = ph
        a[y0:y0 + 1, x0:x1, :3] = 40; a[y1 - 1:y1, x0:x1, :3] = 40; a[y0:y1, x0:x0 + 1, :3] = 40; a[y0:y1, x1 - 1:x1, :3] = 40
    page = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    # motion: slide up and in, slow push toward the photo, drop away at the end
    s0 = min(W * 0.93 / PW_, H * 0.9 / PH_)
    e_in = ease_out(pi_); e_b = back(pi_, 1.1); e_out = ease_in(po)
    push = 0.10 * ease_io(prog(u, tin * 0.6, max(0.1, d - tin * 0.6 - tout * 0.3)))
    sc = s0 * (lerp(0.86, 1.0, e_b) + push - 0.1 * e_out)
    ay = (y0 + y1) / 2 - PH_ / 2                       # the photo's centre, from the page centre
    cy_rest = H * 0.5
    cy = cy_rest - ay * (sc - s0) + lerp(H * 0.62 + PH_ * s0 * 0.5, 0, e_in) + e_out * (H * 0.6 + PH_ * s0 * 0.8)
    cx = W / 2 + 6 * math.sin(u * 0.9) * (1 - e_out)
    rz = lerp(-5, -0.8, e_in) + 0.4 * math.sin(u * 1.1) + 11 * e_out
    rx = lerp(26, 0, e_in) - 14 * e_out
    ry = 1.8 * math.sin(u * 0.7 + 0.4)
    pres = min(ease_out(pi_ * 1.5), 1 - e_out)
    bgim = c.img
    if pres > 0.01:
        b = f32(np.asarray(bgim))
        b = b * (1 - pres) + blur(b, 9, 4) * pres
        bgim = to_pil(b * (1 - 0.55 * pres))
    cv = bgim.convert("RGBA")
    place(cv, page, cx, cy, s=sc, rx=rx, ry=ry, rz=rz, shadow=0.5, f=2600)
    return cv.convert("RGB")

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {"masthead": "The Daily Reel"},
    "note": "CLAUDE-WROTE: the masthead name 'The Daily Reel'. Headline, highlight and body are your own words; the date line is today's date.",
    "needs": ["talk"],
}
