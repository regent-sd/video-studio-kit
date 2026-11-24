"""Arch text: your line arcs over your head like a rainbow, behind you (you stay in front, raised hand and all).
It rises into place as your hand goes up, lands with a small overshoot, and each word lights as you say it.
"""
import math, re, subprocess
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, FPS, f32, to_pil, mix, over, font, hexc, ease_out, back, prog, clamp01, lerp, decay,
                  with_alpha, comp, norm_word, log)

NAME = "arch-text"
KIND = "behind"
ABOUT = "Your line arches over your head like a rainbow, behind you; rises as your hand goes up, words light as you say them"
DUR = 3.0
PARAMS = dict(
    text=None,          # the line; default the words you say in the window (your own words)
    fixes={},           # {"heard": "meant"}: words the transcript got wrong ("mane" -> "Main")
    lines=None,         # the arcs, top to bottom, e.g. ["Come along", "to the market", "with me"]; default: split for you
    big=None,           # which line is set big (index); default the longest
    sizes=None,         # or a size for every line, as a share of the big size, e.g. [0.55, 1.2, 1.0, 0.55] (0.8 and up are "big")
    color=None,         # the letters; default the skin's light colour
    small_color=None,   # the small lines; default the same as color
    size=1.0,           # overall type scale
    small_font="heading",   # the small lines' font: "heading" or "title" (the skin's fonts)
    radius=4.0,         # inner arc radius, in face heights (bigger = flatter arch)
    clear=0.12,         # gap between the top of your head and the inner arc, in face heights (negative tucks it behind)
    spread=118,         # widest an arc may open, degrees: a line that would open wider is set smaller
    width=0.92,         # widest an arc may be, as a share of the frame width
    dim=0.34,           # opacity of a word before it's said (1 = no lighting)
    glow=0.45,          # brief glow when a word lights (0 = off)
    rise="hand",        # "hand": land as your raised hand peaks; "word": land on the first word; or [start, land] seconds into the effect
    rise_dur=0.55,      # seconds from start to landing
    land_at=0.94,       # with rise="hand": land when the hand is this close to its highest (0-1)
    land_delay=0.05,    # ... plus this many seconds
    rise_from=170,      # px below its spot it rises from (from behind your head)
    overshoot=1.6,      # how far it overshoots as it lands (0 = none)
    stagger=0.035,      # seconds between lines landing (innermost first)
    tilt=5.0,           # degrees each line swings in from
    shadow=0.7,         # soft shadow under the letters
    backdrop=0.16,      # how much the room darkens just behind the letters, so they read (0 = off)
    stroke=0.0,         # px of extra weight on the letters (thickens a thin display face's hairlines)
    hold_out=0.0,       # seconds at the end to fade out (0 = stays to the last frame, for a hard cut)
    case="upper",       # upper | as-is
)

# ------------------------------------------------------------------ text and timing
def _words_for(c):
    """[(display word, start seconds in video time or None)] for the line."""
    fixes = {norm_word(k): v for k, v in (c.p.get("fixes") or {}).items()}
    said = [w for w in c.words_in() if norm_word(w["w"])]
    if c.p.get("text"):
        toks = str(c.p["text"]).split()
    else:   # the first sentence said in the window, at most 9 words
        toks = []
        for w in said:
            toks.append(fixes.get(norm_word(w["w"]), w["w"]))
            if len(toks) >= 9 or (w["w"][-1:] in ".?!" and len(toks) >= 3): break
        if toks: toks[-1] = toks[-1].rstrip(".,")
        said = said[:len(toks)]
    out, j = [], 0
    for k, tok in enumerate(toks):
        n = norm_word(tok)
        hit = None
        for jj in range(j, len(said)):            # the next transcript word that matches (or was misheard as it)
            sw = norm_word(said[jj]["w"])
            if sw == n or norm_word(fixes.get(sw, "")) == n:
                hit = jj; break
        if hit is None and len(said) == len(toks):  # same count: line them up by position
            hit = k
        if hit is not None:
            out.append((tok, said[hit]["s"])); j = hit + 1
        else:
            out.append((tok, None))
    # words with no timing light with the word before them
    last = None
    for k, (tok, s) in enumerate(out):
        if s is None: out[k] = (tok, last)
        else: last = s
    return out

def _split(words, big):
    """Up to three arcs, top to bottom; the middle one the longest when there are three."""
    n = len(words)
    if n <= 3: return [words]
    total = sum(len(w) for w in words) + n - 1
    best = None
    for a in range(1, n - 1):
        for b in range(a + 1, n):
            parts = [words[:a], words[a:b], words[b:]]
            ls = [len(" ".join(p)) for p in parts]
            score = abs(ls[1] - total * 0.42) + abs(ls[0] - ls[2]) * 0.5 + (0 if ls[1] >= max(ls[0], ls[2]) else 6)
            if best is None or score < best[0]: best = (score, parts)
    if total < 22:
        a = max(1, n // 2); return [words[:a], words[a:]]
    return best[1]

# ------------------------------------------------------------------ drawing the arch (arch coordinates: arc centre at (C, C))
K = 2   # drawn at 2x, then downscaled

def _glyph(ch, f, fill, stroke=0):
    """One character as RGBA, its baseline-middle point at the image centre (so rotating keeps it in place)."""
    asc, desc = f.getmetrics()
    adv = f.getlength(ch)
    S = int(2 * max(adv, asc + desc)) + 8 + 4 * stroke
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    kw = dict(stroke_width=stroke, stroke_fill=fill + (255,)) if stroke else {}
    ImageDraw.Draw(im).text((S / 2, S / 2), ch, font=f, fill=fill + (255,), anchor="ms", **kw)
    return im, adv

def _cap_h(f):
    b = f.getbbox("H", anchor="ls")
    return b[3] - b[1] if b else f.size * 0.7

def _layout(c, lines, big_i, fh):
    """Font, size and radius for every line, innermost (last) first; returns per-line dicts."""
    sk = c.skin
    scale = c.p.get("size", 1.0)
    big_spec = sk["title"]
    small_spec = sk["title"] if c.p.get("small_font") == "title" else sk["heading"]
    r = min(c.p["radius"] * fh, 0.62 * W)        # a close-up face would make the arch nearly flat: cap it
    spread = math.radians(c.p["spread"])
    out = [None] * len(lines)
    for j in range(len(lines) - 1, -1, -1):
        txt = lines[j]
        szs = c.p.get("sizes")
        rel = float(szs[j]) if szs and j < len(szs) else (1.0 if j == big_i else 0.52)
        isbig = rel >= 0.8
        path, idx, wt = big_spec if isbig else small_spec
        size = rel * min(fh, 0.12 * W) * scale
        track = (0.03 if isbig else 0.12)
        maxw = W * c.p.get("width", 0.92)
        for _ in range(60):     # shrink until the arc fits the spread and the frame
            f = font(size * K, wt, path, idx)
            ch_h = _cap_h(f) / K
            rm = r + ch_h * 0.38                 # measure along the letters' lower-middle, so tops don't crowd
            length = sum(f.getlength(ch) / K + track * size for ch in txt) - track * size
            ang = length / rm
            chord = 2 * (r + ch_h) * math.sin(min(math.pi / 2, ang / 2)) + ch_h
            if (ang <= spread and chord <= maxw) or size < 12: break
            size *= max(0.5, min(0.97, spread / ang, maxw / chord))
        out[j] = dict(txt=txt, big=isbig, path=path, idx=idx, wt=wt, size=size, track=track * size, r=r, cap=ch_h, length=length)
        gap = (0.26 if isbig else 0.34) * ch_h + 0.06 * fh
        r = r + ch_h + gap
    return out

def _build(c, words, lines_txt, big_i, fh, col, scol):
    """Per word: an RGBA image of its letters, its shadow and its glow, cropped, with offsets from the arc centre."""
    L = _layout(c, lines_txt, big_i, fh)
    rmax = max(l["r"] + l["cap"] * 1.6 for l in L)
    C = int(rmax + 120)
    S = 2 * C
    wi = 0
    built = []
    for j, ln in enumerate(L):
        f = font(ln["size"] * K, ln["wt"], ln["path"], ln["idx"])
        rm = ln["r"] + ln["cap"] * 0.38
        th = -ln["length"] / rm / 2          # start angle (from straight up, clockwise +)
        fill = col if ln["big"] else scol
        for wtxt in ln["txt"].split(" "):
            canv = Image.new("RGBA", (S * K, S * K), (0, 0, 0, 0))
            for ch in wtxt:
                g, adv = _glyph(ch, f, fill, int(round(c.p.get("stroke", 0) * K * ln["size"] / 96)))
                adv = adv / K
                a = th + (adv / 2) / rm
                x = C + ln["r"] * math.sin(a); y = C - ln["r"] * math.cos(a)
                gr = g.rotate(-math.degrees(a), Image.BICUBIC)
                canv.alpha_composite(gr, (int(round(x * K - gr.width / 2)), int(round(y * K - gr.height / 2))))
                th += (adv + ln["track"]) / rm
            th += (f.getlength(" ") / K + ln["track"]) / rm     # the space after the word
            im = canv.resize((S, S), Image.LANCZOS)
            built.append(dict(line=j, word=wi, img=im))
            wi += 1
    # crop every layer to what's drawn (plus room for the shadow), keep its offset from the arc centre
    st = c.p["shadow"]
    for b in built:
        al = b["img"].getchannel("A")
        bx = al.getbbox() or (0, 0, 1, 1)
        pad = 40
        bx = (max(0, bx[0] - pad), max(0, bx[1] - pad), min(S, bx[2] + pad), min(S, bx[3] + pad))
        img = b["img"].crop(bx); a = img.getchannel("A")
        sh = Image.new("RGBA", img.size, (24, 14, 6, 0))
        wide = a.filter(ImageFilter.GaussianBlur(9)).point(lambda v: int(v * st))
        tight = a.filter(ImageFilter.GaussianBlur(2.2)).point(lambda v: int(v * st * 0.55))
        sh.putalpha(Image.fromarray(np.maximum(np.asarray(wide), np.asarray(tight)), "L"))
        sh = sh.transform(sh.size, Image.AFFINE, (1, 0, 0, 0, 1, -5), Image.BILINEAR)    # shadow falls 5 px down
        gl = Image.new("RGBA", img.size, tuple(col) + (0,))
        gl.putalpha(a.filter(ImageFilter.GaussianBlur(14)).point(lambda v: min(255, int(v * 1.8))))
        b.update(img=img, sh=sh, glow=gl, ox=bx[0] - C, oy=bx[1] - C)
    for b, (tok, s) in zip(built, words):
        b["s"] = s
    return built, L

# ------------------------------------------------------------------ when the hand goes up
def _hand_peak(c):
    """Seconds into the effect when a raised hand is near its highest above the head, or None."""
    sj = c.subj
    f0, f1 = int(round(c.t0 * FPS)), int(round(c.t1 * FPS))
    sw, sh = 270, 480
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-i", sj.mask_path, "-vf", f"scale={sw}:{sh}", "-f", "rawvideo",
                              "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    except Exception as e:
        log(f"arch-text: no mask for hand timing ({e})"); return None
    n = len(raw) // (sw * sh)
    ms = np.frombuffer(raw[:n * sw * sh], np.uint8).reshape(n, sh, sw)
    hs = []
    for i in range(f0, min(f1, n)):
        cx, cy, fw, fh = sj.face(i)
        top_head = (cy - fh * 0.85) / 4
        x0, x1 = int(max(0, (cx - 3 * fw) / 4)), int(min(sw, (cx + 3 * fw) / 4))
        band = ms[i, :, x0:x1] > 128
        rows = np.nonzero(band.any(1))[0]
        hs.append(((top_head - rows[0]) * 4 / fh) if len(rows) else 0.0)
    hs = np.array(hs)
    if not len(hs): return None
    base = float(np.percentile(hs, 20))          # the head (and cap) alone sit a little above the face box's guess
    if hs.max() - base < 0.6:
        return None
    k = int(np.argmax(hs - base >= c.p.get("land_at", 0.94) * (hs.max() - base)))     # the first raise, at (nearly) its top
    return k / FPS + c.p.get("land_delay", 0.05)

# ------------------------------------------------------------------ per frame
def render(c):
    st = c.state
    cx, cy, fw, fh = c.face
    if "built" not in st:
        sk = c.skin
        col = hexc(c.p["color"]) if c.p.get("color") else tuple(sk.light)
        scol = hexc(c.p["small_color"]) if c.p.get("small_color") else col
        words = _words_for(c)
        up = (lambda s: s.upper()) if c.p.get("case", "upper") == "upper" else (lambda s: s)
        if c.p.get("lines"):
            lines = [up(x) for x in c.p["lines"]]
        else:
            lines = [up(" ".join(p)) for p in _split([w for w, _ in words], c.p.get("big"))]
        if len(" ".join(lines).split()) != len(words):      # lines given with different wording: time them as one
            words = [(w, words[0][1] if words else None) for w in " ".join(lines).split()]
        big_i = c.p["big"] if c.p.get("big") is not None else max(range(len(lines)), key=lambda j: len(lines[j]))
        # the arch is placed once, centred on the head over the whole window (it lives in the scene, like a sign)
        i0, i1 = int(round(c.t0 * FPS)), int(round(c.t1 * FPS))
        fs = np.array([c.subj.face(i) for i in range(i0, max(i0 + 1, i1))])
        mcx, mcy, mfw, mfh = [float(np.median(fs[:, k])) for k in range(4)]
        st["built"], st["L"] = _build(c, words, lines, big_i, mfh, col, scol)
        log("arch-text: face h %.0f px; " % mfh + "; ".join(f"'{l['txt']}' {l['size']:.0f}px r{l['r']:.0f}" for l in st["L"]))
        head_top = mcy - mfh * 0.85
        r0 = st["L"][-1]["r"]
        st["ax"] = min(max(mcx, W * 0.30), W * 0.70)
        st["ay"] = head_top - c.p["clear"] * mfh + r0
        st["col"] = col
        # when it rises
        rz = c.p["rise"]
        land = None
        if isinstance(rz, (list, tuple)):
            st["t_rise"], land = float(rz[0]), float(rz[1])
        else:
            if rz == "hand":
                land = _hand_peak(c)
                if land is not None: log(f"arch-text: hand peaks {land:.2f}s into the effect")
            if land is None:
                first = next((s for _, s in words if s is not None), None)
                land = (first - c.t0 + 0.25) if first is not None else c.p["rise_dur"]
            st["t_rise"] = max(0.0, land - c.p["rise_dur"])
        st["t_land"] = land if land is not None else st["t_rise"] + c.p["rise_dur"]
        # keep the top line inside the safe zone (220 px)
        top = st["ay"] - max(l["r"] + l["cap"] for l in st["L"])
        if top < 240: st["ay"] += 240 - top
    u = c.u
    nl = len(st["L"])
    fade_out = 1.0
    if c.p.get("hold_out", 0) > 0:
        fade_out = clamp01((c.d - u) / c.p["hold_out"])
    lay = c.canvas()
    sh_lay = c.canvas()
    for j in range(nl):
        order = nl - 1 - j                                   # innermost line lands first
        t_r = st["t_rise"] + order * c.p["stagger"]
        dur = max(0.05, st["t_land"] - st["t_rise"])
        q = prog(u, t_r, dur)
        if q <= 0: continue
        os_ = c.p["overshoot"]
        e = back(q, os_) if os_ > 0 else ease_out(q)
        dy = c.p["rise_from"] * (1 - e)
        sc = lerp(0.86, 1.0, e)
        rot = c.p["tilt"] * (1 if j % 2 else -1) * (1 - e)
        a_line = clamp01(q * 3.0) * fade_out
        for b in st["built"]:
            if b["line"] != j: continue
            lit = 1.0 if b["s"] is None else ease_out(prog(c.t, b["s"] - 0.05, 0.14))
            a = a_line * (c.p["dim"] + (1 - c.p["dim"]) * lit)
            ox, oy = b["ox"], b["oy"]
            imgs = [(b["sh"], sh_lay, a), (b["img"], lay, a)]
            gk = c.p["glow"] * (decay(c.t, b["s"], 4.5) if b["s"] is not None and c.t >= b["s"] else 0.0)
            if gk > 0.01: imgs.insert(1, (b["glow"], lay, a_line * gk))
            for im, dst, al in imgs:
                if al <= 0.003: continue
                if abs(sc - 1) > 1e-3 or abs(rot) > 0.05:
                    # turn and scale about the arc centre: place the word's centre where the transform puts it
                    wcx, wcy = ox + im.width / 2, oy + im.height / 2
                    ang = math.radians(-rot)
                    px = sc * (wcx * math.cos(ang) - wcy * math.sin(ang)); py = sc * (wcx * math.sin(ang) + wcy * math.cos(ang))
                    im2 = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.BICUBIC)
                    if abs(rot) > 0.05: im2 = im2.rotate(rot, Image.BICUBIC, expand=True)
                    comp(dst, with_alpha(im2, al), st["ax"] + px - im2.width / 2, st["ay"] + dy + py - im2.height / 2)
                else:
                    comp(dst, with_alpha(im, al), st["ax"] + ox, st["ay"] + dy + oy)
    base = f32(np.asarray(c.img))
    room = base
    if c.p.get("backdrop", 0) > 0:
        # a soft dark breath behind the letters: their alpha, grown and blurred at quarter size
        al = lay.getchannel("A").resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(9))
        bd = np.asarray(al.resize((W, H), Image.BILINEAR), np.float32) / 255.0
        room = room * (1 - c.p["backdrop"] * np.clip(bd * 1.6, 0, 1))[..., None]
    room = over(over(room, sh_lay), lay)
    return to_pil(mix(base, room, c.mask))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {"rise": "word"},
    "note": "the line is your own words in the window",
    "needs": ["talk"],
}
