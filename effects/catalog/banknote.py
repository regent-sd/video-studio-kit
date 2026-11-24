"""Banknote: an ornate pale-green note slides in with a 3D tilt, your face engraved in its oval medallion."""
import math, re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, f32, to_pil, text_img, scaled, comp, place, font, ease_out, ease_in, ease_io, back, prog, lerp,
                  clamp01, key_words, hexc, DIDOT)
from ._print import (paper, engrave, blur, smooth, stretch, trochoid, wave_ring, rosette, grid, solid, key_word, sentence_with)

NAME = "banknote"
KIND = "restyle"
ABOUT = "Your face engraved into an ornate banknote that slides in with a 3D tilt"
DUR = 4.0
PARAMS = dict(
    denomination=None,  # what the corners say, e.g. "100" (must be a real amount); default: your key word
    title=None,         # the big line at the top; default your key word
    motto=None,         # the line under the portrait; default the sentence you say in the window
    paper="#DDE9D8",    # note colour (pale green)
    ink="#173F30",      # engraving ink (deep green)
    seal=None,          # seal colour; default a gold made from the skin's accent
    face=0.36,          # face height as a share of the oval's height
)
NW, NH = 980, 1700                  # the note, in its own pixels
OCX, OCY, ORX, ORY = 490, 712, 288, 382   # the portrait oval
COPPER = "/System/Library/Fonts/Supplemental/Copperplate.ttc"

def _fit(txt, maxw, maxsize, path, idx, track_k=0.0, minsize=14, weight=700):
    size = maxsize
    while size > minsize:
        f = font(size, weight, path, idx)
        w = f.getlength(txt) + track_k * size * max(0, len(txt) - 1)
        if w <= maxw: break
        size -= 2
    return size

def _line(d, pts, fill, w):
    d.line(pts, fill=fill, width=w)

def _band(d, x0, y0, x1, y1, col, k, n=7, waves=None):
    """A guilloche rope between two parallel rules (horizontal if wider than tall)."""
    horiz = (x1 - x0) >= (y1 - y0)
    L = (x1 - x0) if horiz else (y1 - y0)
    T = (y1 - y0) if horiz else (x1 - x0)
    lam = waves or T * 1.6
    s = np.linspace(0, L, int(L / 2) + 2)
    for i in range(n):
        for sgn in (1, -1):
            off = T / 2 + sgn * (T * 0.4) * np.sin(2 * math.pi * s / lam + 2 * math.pi * i / n)
            if horiz: pts = list(zip(((x0 + s) * k).tolist(), ((y0 + off) * k).tolist()))
            else: pts = list(zip(((x0 + off) * k).tolist(), ((y0 + s) * k).tolist()))
            _line(d, pts, col, max(1, int(k * 0.7)))
    for a, b in ((0, 0), (T, T)):
        if horiz: _line(d, [(x0 * k, (y0 + a) * k), (x1 * k, (y0 + b) * k)], col, int(k * 1.2))
        else: _line(d, [((x0 + a) * k, y0 * k), ((x0 + b) * k, y1 * k)], col, int(k * 1.2))

def _text(cv, txt, size, cx, cy, col, path, idx, track=0, stroke=0, stroke_fill=None, k=2):
    t = text_img(txt, size * k, 700, tuple(col), int(track * k), path, idx, int(stroke * k), tuple(stroke_fill or col))
    cv.alpha_composite(t, (int(cx * k - t.width / 2), int(cy * k - t.height / 2)))
    return t.width / k, t.height / k

def _seal(gold, ini, k):
    """A gold foil seal: scalloped edge, guilloche rings, an initial. RGBA (192k square)."""
    S = 192 * k; c0 = S / 2
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).polygon(wave_ring(c0, c0, 86 * k, 4 * k, 44, n=1400), fill=255)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    g = np.clip(0.5 + 0.5 * ((c0 - xx) * 0.6 + (c0 - yy) * 0.8) / (90 * k), 0, 1)
    rad = np.sqrt((xx - c0) ** 2 + (yy - c0) ** 2) / (86 * k)
    ring = 0.5 + 0.5 * np.cos(rad * 40)
    lt, dk = np.array(gold, np.float32) * 1.18 + 20, np.array(gold, np.float32) * 0.62
    col = dk + (lt - dk) * (g * 0.8 + 0.2 * ring)[..., None]
    im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    im.putalpha(m)
    d = ImageDraw.Draw(im)
    gdd = tuple(int(v * 0.5) for v in gold) + (255,)
    for j in range(12):
        d.line(wave_ring(c0, c0, 62 * k, 8 * k, 18, phase=j * 0.35, n=900), fill=gdd, width=max(1, k // 2 + 1))
    d.ellipse([c0 - 42 * k, c0 - 42 * k, c0 + 42 * k, c0 + 42 * k], fill=tuple(int(v * 0.95) for v in gold) + (255,),
              outline=gdd, width=2 * k)
    t = text_img(ini, 56 * k, 700, gdd[:3], 0, DIDOT, 2)
    im.alpha_composite(t, (int(c0 - t.width / 2), int(c0 - t.height / 2 + 2 * k)))
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh.putalpha(m.filter(ImageFilter.GaussianBlur(3 * k)).point(lambda v: int(v * 0.35)))
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 0)); out.alpha_composite(im, (-k, -2 * k))
    return out

def _motto(words, limit=60, prefer=""):
    """The sentence you say in the window, kept to one line's worth: the one with your key word if it fits, else the
    first full sentence that fits. Leading fillers (um, so, and...) are dropped."""
    from core import norm_word
    txt, cur = [], []
    for w in words:
        cur.append(w)
        if re.search(r"[.!?]$", w):
            txt.append(cur); cur = []
    if cur: txt.append(cur)
    out = []
    for snt in txt:
        while snt and norm_word(snt[0]) in ("um", "uh", "so", "and", "but", "like"): snt = snt[1:]
        if snt:
            t = " ".join(snt); out.append((t[0].upper() + t[1:], snt))
    fits = [(t, snt) for t, snt in out if 12 <= len(t) <= limit]
    pw = norm_word(prefer) if prefer else ""
    for t, snt in fits:
        if pw and any(norm_word(x) == pw for x in snt): return t
    if fits: return fits[0][0]
    s = " ".join(words)
    return s if len(s) <= limit else s[:limit].rsplit(" ", 1)[0]

def _note(c, title, corner, motto, micro, pap, ink, gold):
    """The static note (everything except the portrait): RGBA NW x NH."""
    k = 2
    ink_d = tuple(ink) + (255,)
    ink_m = tuple(int(lerp(a, b, 0.42)) for a, b in zip(ink, pap)) + (255,)
    ink_l = tuple(int(lerp(a, b, 0.66)) for a, b in zip(ink, pap)) + (255,)
    # paper: pale green, warmer in the middle, with a fine wavy security underprint
    base = paper(NW, NH, tuple(pap), seed=5, grain=4.0, mottle=6.0, fibers=0.35, edge=0.35).copy()
    yy, xx = grid(NH, NW)
    r = np.sqrt(((xx - NW / 2) / (NW * 0.62)) ** 2 + ((yy - OCY) / (NH * 0.55)) ** 2)
    warm = np.clip(1 - r, 0, 1)[..., None] * np.array([14, 6, -6], np.float32)
    base += warm
    ph1 = (yy + 11 * np.sin(xx / 47.0 + yy / 130.0)) / 6.0
    ph2 = (xx + 13 * np.sin(yy / 61.0)) / 7.0
    l1 = smooth(0.16, 0.05, 0.5 - np.abs(ph1 - np.floor(ph1) - 0.5))
    l2 = smooth(0.14, 0.04, 0.5 - np.abs(ph2 - np.floor(ph2) - 0.5))
    under = np.clip(l1 * 0.32 + l2 * 0.2, 0, 1)
    # sunburst behind the oval
    ang = np.arctan2(yy - OCY, xx - OCX)
    rays = smooth(0.25, 0.1, np.abs(((ang / (2 * math.pi) * 180) % 1) - 0.5))
    rr = np.sqrt(((xx - OCX) / ORX) ** 2 + ((yy - OCY) / ORY) ** 2)
    under = np.maximum(under, rays * smooth(1.05, 1.25, rr) * smooth(2.1, 1.5, rr) * 0.45)
    col_l = np.array(ink_l[:3], np.float32)
    base = base * (1 - under[..., None]) + col_l * under[..., None]
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    big = im.resize((NW * k, NH * k), Image.BICUBIC)
    d = ImageDraw.Draw(big)
    # frame: outer rules, guilloche ropes on all four sides
    m = 26
    d.rectangle([m * k, m * k, (NW - m) * k, (NH - m) * k], outline=ink_d, width=3 * k)
    d.rectangle([(m + 7) * k, (m + 7) * k, (NW - m - 7) * k, (NH - m - 7) * k], outline=ink_m, width=k)
    bw = 50; b0 = m + 14
    _band(d, b0, b0, NW - b0, b0 + bw, ink_m, k)
    _band(d, b0, NH - b0 - bw, NW - b0, NH - b0, ink_m, k)
    _band(d, b0, b0, b0 + bw, NH - b0, ink_m, k)
    _band(d, NW - b0 - bw, b0, NW - b0, NH - b0, ink_m, k)
    ib = b0 + bw + 8
    d.rectangle([ib * k, ib * k, (NW - ib) * k, (NH - ib) * k], outline=ink_d, width=2 * k)
    # microprint of your words just inside the frame
    if micro:
        mf = font(10 * k, 700, COPPER, 0)
        line = (micro + " • ") * 40
        for y in (ib + 4,):
            d.text(((ib + 6) * k, y * k), line, font=mf, fill=ink_m, anchor="la")
        strip = Image.new("RGBA", ((NH - 2 * ib - 12) * k, 14 * k), (0, 0, 0, 0))
        ImageDraw.Draw(strip).text((0, 2 * k), line, font=mf, fill=ink_m)
        big.alpha_composite(strip.rotate(90, expand=True), ((ib + 4) * k, (ib + 6) * k))
        big.alpha_composite(strip.rotate(-90, expand=True), ((NW - ib - 18) * k, (ib + 6) * k))
        d.text(((ib + 6) * k, (NH - ib - 16) * k), line, font=mf, fill=ink_m, anchor="la")
    # corner cartouches with the denomination (or your word)
    cr = 74
    for (cx, cy) in ((b0 + bw / 2 + 30, b0 + bw / 2 + 30), (NW - b0 - bw / 2 - 30, b0 + bw / 2 + 30),
                     (b0 + bw / 2 + 30, NH - b0 - bw / 2 - 30), (NW - b0 - bw / 2 - 30, NH - b0 - bw / 2 - 30)):
        d.ellipse([(cx - cr - 6) * k, (cy - cr - 6) * k, (cx + cr + 6) * k, (cy + cr + 6) * k], fill=tuple(pap) + (255,),
                  outline=ink_d, width=2 * k)
        rosette(d, cx * k, cy * k, cr * k, ink_l, width=max(1, k // 2), layers=2)
        d.ellipse([(cx - cr * 0.58) * k, (cy - cr * 0.58) * k, (cx + cr * 0.58) * k, (cy + cr * 0.58) * k],
                  fill=tuple(pap) + (255,), outline=ink_d, width=k)
        if corner:
            num = bool(re.fullmatch(r"[\d.,]+", corner))
            path, idx = (DIDOT, 2) if num else (COPPER, 2)
            sz = _fit(corner, cr * 1.05, 64 if num else 30, path, idx, minsize=10)
            _text(big, corner, sz, cx, cy + (2 if num else 1), ink_d[:3], path, idx, k=k)
    # title, between two fine rules
    if title:
        tsz = _fit(title, NW - 2 * ib - 120, 118, COPPER, 2, track_k=0.08)
        tsz = min(tsz, 104)
        tw, th = _text(big, title, tsz, NW / 2, 186, ink_d[:3], COPPER, 2, track=tsz * 0.08, k=k)
        for yy_ in (186 - th / 2 - 16, 186 + th / 2 + 16):
            d.line([((NW / 2 - tw / 2 - 10) * k, yy_ * k), ((NW / 2 + tw / 2 + 10) * k, yy_ * k)], fill=ink_m, width=k)
    # the oval frame: two rules, a guilloche wave ring, a beaded ring
    sy = ORY / ORX
    for rad, wd in ((ORX + 6, 3), (ORX + 52, 2), (ORX + 60, 1)):
        d.ellipse([(OCX - rad) * k, (OCY - rad * (ORY + rad - ORX) / rad) * k, (OCX + rad) * k,
                   (OCY + rad * (ORY + rad - ORX) / rad) * k], outline=ink_d, width=wd * k)
    for j in range(18):
        pts = wave_ring(OCX * k, OCY * k, (ORX + 29) * k, 17 * k, 44, phase=j * 2 * math.pi / 18, n=1800,
                        sx=1.0, sy=(ORY + 29) / (ORX + 29))
        d.line(pts, fill=ink_m, width=max(1, k // 2 + 1))
    nb = 120
    for j in range(nb):
        a = 2 * math.pi * j / nb
        bx, by = OCX + (ORX + 70) * math.cos(a), OCY + (ORY + 70) * math.sin(a)
        d.ellipse([(bx - 3.2) * k, (by - 3.2) * k, (bx + 3.2) * k, (by + 3.2) * k], fill=ink_d)
    # a ribbon under the portrait with the sentence you say
    if motto:
        ry0, ry1 = OCY + ORY + 92, OCY + ORY + 176
        rx0, rx1 = 150, NW - 150
        d.rectangle([rx0 * k, ry0 * k, rx1 * k, ry1 * k], fill=tuple(pap) + (255,), outline=ink_d, width=2 * k)
        d.rectangle([(rx0 + 6) * k, (ry0 + 6) * k, (rx1 - 6) * k, (ry1 - 6) * k], outline=ink_m, width=k)
        for sx_, dirn in ((rx0, -1), (rx1, 1)):
            tail = [(sx_ * k, ry0 * k), ((sx_ + dirn * 70) * k, (ry0 + 14) * k), ((sx_ + dirn * 46) * k, (ry0 + ry1) / 2 * k),
                    ((sx_ + dirn * 70) * k, (ry1 + 14) * k), (sx_ * k, ry1 * k)]
            d.polygon(tail, fill=ink_l, outline=ink_d)
        words = motto.split()
        lines = [motto]
        f1 = _fit(motto, rx1 - rx0 - 50, 34, COPPER, 0, track_k=0.05, minsize=22)
        if f1 <= 22 and len(words) > 3:
            h_ = len(words) // 2
            lines = [" ".join(words[:h_]), " ".join(words[h_:])]
            f1 = min(_fit(l_, rx1 - rx0 - 50, 30, COPPER, 0, track_k=0.05, minsize=14) for l_ in lines)
        for li, l_ in enumerate(lines):
            yc = (ry0 + ry1) / 2 + (li - (len(lines) - 1) / 2) * f1 * 1.15
            _text(big, l_, f1, NW / 2, yc, ink_d[:3], COPPER, 0, track=f1 * 0.05, k=k)
    # a guilloche panel at the bottom with the big hollow word (or amount) on it
    py0, py1, px0, px1 = OCY + ORY + 206, OCY + ORY + 372, 168, NW - 168
    d.rounded_rectangle([px0 * k, py0 * k, px1 * k, py1 * k], radius=26 * k, fill=tuple(pap) + (255,), outline=ink_d, width=2 * k)
    xs = np.linspace(px0 + 12, px1 - 12, 700)
    env = np.clip(np.sin(math.pi * (xs - px0 - 12) / (px1 - px0 - 24)), 0, 1) ** 0.25
    amp_ = (py1 - py0) * 0.34
    for j in range(22):
        for lam, sg in ((150, 1), (150, -1)):
            yv = (py0 + py1) / 2 + sg * amp_ * env * np.sin(2 * math.pi * (xs - px0) / lam + j * 2 * math.pi / 22)
            d.line(list(zip((xs * k).tolist(), (yv * k).tolist())), fill=ink_l, width=max(1, k // 2))
    d.rounded_rectangle([(px0 + 8) * k, (py0 + 8) * k, (px1 - 8) * k, (py1 - 8) * k], radius=20 * k, outline=ink_m, width=k)
    low = corner or title
    if low:
        num = bool(re.fullmatch(r"[\d.,]+", low))
        path, idx = (DIDOT, 2) if num else (COPPER, 2)
        bsz = _fit(low, px1 - px0 - 90, 130 if num else 92, path, idx, track_k=0.06)
        _text(big, low, bsz, NW / 2, (py0 + py1) / 2 + 3, pap, path, idx, track=bsz * 0.06, stroke=2.4, stroke_fill=ink_d[:3], k=k)
    # small rosettes left and right of the portrait, and the gold seal on the right
    rosette(d, (OCX - ORX - 30) * k, (OCY + ORY - 10) * k, 62 * k, ink_m, width=max(1, k // 2), layers=2)
    sx_, sy_ = OCX + ORX + 12, OCY + ORY - 40
    big.alpha_composite(_seal(gold, (title or corner or " ")[0], k), (int((sx_ - 96) * k), int((sy_ - 96) * k)))
    note = big.resize((NW, NH), Image.LANCZOS)
    # punch out the oval window (the portrait goes there)
    hole = Image.new("L", (NW * k, NH * k), 255)
    ImageDraw.Draw(hole).ellipse([(OCX - ORX) * k, (OCY - ORY) * k, (OCX + ORX) * k, (OCY + ORY) * k], fill=0)
    return note, hole.resize((NW, NH), Image.LANCZOS)

def _portrait(c, pap, ink, face_k):
    """Your face as a line engraving inside the oval: (2*ORX+40) x (2*ORY+40) RGB array."""
    ow, oh = 2 * ORX + 40, 2 * ORY + 40
    cx, cy, fw, fh = c.face
    s = (oh - 40) * face_k / max(40.0, fh)
    # where the face goes in the oval: a little above the middle
    tx, ty = ow / 2, oh * 0.43
    data = (1 / s, 0, cx - tx / s, 0, 1 / s, cy - ty / s)
    src = Image.fromarray(c.src).transform((ow, oh), Image.AFFINE, data, Image.BILINEAR, fillcolor=(90, 90, 90))
    msk = Image.fromarray((solid(c.mask) * 255).astype(np.uint8), "L").transform((ow, oh), Image.AFFINE, data, Image.BILINEAR, fillcolor=0)
    m = np.asarray(msk, np.float32) / 255.0
    L = (np.asarray(src, np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)) / 255.0
    tone = stretch(L, m, 2, 99, 1.05)
    # local contrast so the eyes and glasses hold
    tone = np.clip(tone + (tone - blur(tone, 9, 2)) * 0.9, 0, 1)
    form = blur(tone, 7, 2)
    a = engrave(tone, period=5.0, angle=-6, warp=form, warp_amp=1.6, thick=1.12, minw=0.1)
    hatch = engrave(np.clip(tone / 0.42, 0, 1), period=5.0, angle=58, warp=form, warp_amp=0.8, thick=0.9)
    hatch *= (tone < 0.42)
    ed = np.clip((blur(tone, 1.2) - blur(tone, 3.2)) * -9.0, 0, 1)
    person = np.clip(np.maximum(a, hatch) + ed * 0.8, 0, 1)
    # the room: fine horizontal line shading, darker toward the rim, light behind the head
    yy, xx = grid(oh, ow)
    rr = np.sqrt(((xx - ow / 2) / (ow / 2)) ** 2 + ((yy - oh / 2) / (oh / 2)) ** 2)
    halo = np.exp(-(((xx - tx) / (ow * 0.42)) ** 2 + ((yy - ty) / (oh * 0.36)) ** 2))
    bgt = np.clip(0.86 - 0.62 * rr ** 2 + 0.22 * halo, 0.15, 0.97)
    bg = engrave(bgt, period=4.4, angle=0, thick=1.0, minw=0.12)
    inkm = person * m + bg * (1 - m)
    cream = np.array(pap, np.float32) * 0.55 + np.array([248, 246, 232], np.float32) * 0.45
    out = cream[None, None, :] * (1 - inkm[..., None]) + np.array(ink, np.float32)[None, None, :] * inkm[..., None]
    return out

def render(c):
    st = c.state
    pap, ink = hexc(c.p["paper"]), hexc(c.p["ink"])
    if "note" not in st:
        kw = key_word(c).upper()
        title = str(c.p["title"]).upper() if c.p.get("title") else kw
        corner = str(c.p["denomination"]) if c.p.get("denomination") is not None else kw
        said = c.words_in()
        motto = c.p.get("motto") or _motto([w["w"] for w in said], prefer=kw) or \
            (sentence_with(c.words, kw, 0, 1e9, 60) if kw else "") or ""
        motto = " ".join(motto.upper().split()).rstrip(",;:")
        micro = " ".join(w["w"] for w in (c.words or [])).upper()[:400]
        acc = c.skin.accent
        gold = hexc(c.p["seal"]) if c.p.get("seal") else tuple(int(lerp(a, b, 0.32)) for a, b in zip(acc, (120, 90, 30)))
        st["note"], st["hole"] = _note(c, title, corner, motto, micro, pap, ink, gold)
        st["hole_np"] = np.asarray(st["hole"], np.float32)[..., None] / 255.0
        st["note_np"] = f32(np.asarray(st["note"].convert("RGB")))
    u, d = c.u, c.d
    tin = min(0.9, d * 0.32); tout = min(0.7, d * 0.25)
    pi_ = prog(u, 0, tin); po = prog(u, d - tout, tout)
    # the portrait into the oval window
    por = _portrait(c, pap, ink, c.p["face"])
    nt = st["note_np"].copy()
    ox, oy = OCX - ORX - 20, OCY - ORY - 20
    sub = nt[oy:oy + por.shape[0], ox:ox + por.shape[1]]
    hm = st["hole_np"][oy:oy + por.shape[0], ox:ox + por.shape[1]]
    sub[:] = sub * hm + por * (1 - hm)
    # a slow sheen across the note after it lands
    sh_t = prog(u, tin + 0.1, 1.1)
    if 0 < sh_t < 1:
        yy, xx = grid(NH, NW)
        band = (xx * 0.6 + yy * 0.8) / (NW * 0.6 + NH * 0.8)
        g = np.exp(-((band - lerp(-0.2, 1.2, ease_io(sh_t))) / 0.07) ** 2)
        nt += g[..., None] * 40
    note = Image.fromarray(np.clip(nt, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    # motion: slide up from below with a tilt and zoom, settle with overshoot, float, then fly out the top
    e_in = back(pi_, 1.2); e_out = ease_in(po)
    s_hold = min(W * 0.955 / NW, H * 0.92 / NH)
    cy_hold = H * 0.49
    float_t = u
    drift = 0.05 * ease_io(prog(u, tin, max(0.1, d - tin - tout)))
    cy = lerp(H + NH * 0.42, cy_hold, ease_out(pi_)) + lerp(0, -H * 0.95 - NH * 0.3, e_out)
    sc = s_hold * (lerp(0.74, 1.0, e_in) + drift - lerp(0, 0.12, e_out))
    rx = lerp(34, 0, ease_out(pi_)) + 1.6 * math.sin(float_t * 1.1) + lerp(0, -26, e_out)
    ry = 2.4 * math.sin(float_t * 0.8 + 0.6)
    rz = lerp(-9, 0, ease_out(pi_)) + 0.5 * math.sin(float_t * 1.3) + lerp(0, 9, e_out)
    # the room behind: darker and softer while the note is up
    pres = min(ease_out(pi_ * 1.6), 1 - ease_in(po))
    bgim = c.img
    if pres > 0.01:
        b = f32(np.asarray(bgim))
        bl = blur(b, 10, 4)
        b = b * (1 - pres) + bl * pres
        b *= (1 - 0.62 * pres)
        bgim = to_pil(b)
    cv = bgim.convert("RGBA")
    place(cv, note, W / 2, cy, s=sc, rx=rx, ry=ry, rz=rz, shadow=0.55, f=2600)
    return cv.convert("RGB")

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "title, corners and motto are your own words; no amount shown",
    "needs": ["face"],
}
