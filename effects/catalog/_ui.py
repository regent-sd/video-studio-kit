"""Shared helpers for the UI-card effects: todo, timeline, typewriter, voice-note, comment-drop, predict-keys.
(Files starting with _ are not effects.)"""
import math, re, wave, functools, subprocess, zlib
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, FPS, SS, font, SFP, SFMONO, clamp, clamp01, ease_out, back, prog, lerp, lerpc, norm_word,
                  with_alpha)

IOS_BLUE = (10, 132, 255)
IOS_GREEN = (52, 199, 89)
IOS_RED = (255, 59, 48)
IOS_GREY = (142, 142, 147)
FILLERS = {"um", "uh", "uhm", "umm", "erm", "er", "ah", "hmm", "mm", "mhm"}

# ------------------------------------------------------------------ words + timing
def clean(w):
    """'quickly,' -> 'quickly' (keeps apostrophes and hyphens)."""
    return re.sub(r"[^\w'’-]", "", w)

def is_filler(w):
    return norm_word(w) in FILLERS

def spoken(c, a=None, b=None, fillers=False):
    """Words said in [a, b] (default the window), fillers (um, uh) dropped unless fillers=True."""
    return [w for w in c.words_in(a, b) if fillers or not is_filler(w["w"])]

def when(c, on, fallback):
    """'on' (a word you say, or seconds into the video) -> seconds. Unknown words fall back."""
    if on is None or on == "": return fallback
    if isinstance(on, (int, float)): return float(on)
    try: return float(on)
    except (TypeError, ValueError): pass
    n = norm_word(str(on))
    w = next((w for w in c.words_in() if norm_word(w["w"]) == n), None) or c.subj.find_word(str(on), c.t0)
    return w["s"] if w else fallback

def phases(c, tin=0.45, tout=0.35):
    """(in, out) progress 0-1 of the entrance and exit, shortened for short windows."""
    tin = min(tin, c.d * 0.28); tout = min(tout, c.d * 0.22)
    return prog(c.u, 0, tin), prog(c.u, c.d - tout, tout)

def chin(c):
    cx, cy, fw, fh = c.face
    return cy + fh * 0.62

def fmt_clock(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"

def seeded(name):
    return zlib.crc32(str(name).encode()) & 0xffffffff

# ------------------------------------------------------------------ compositing
@functools.lru_cache(128)
def rr_mask(w, h, r):
    """Antialiased rounded-rect alpha mask (L)."""
    w, h = max(1, int(w)), max(1, int(h))
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], radius=max(0, min(r, w / 2, h / 2)) * 2, fill=255)
    return m.resize((w, h), Image.LANCZOS)

def rr_mask_fast(w, h, r):
    """Rounded-rect alpha (L) for any size, antialiased corners worked out only where they are (cheap per frame)."""
    w, h = max(1, int(w)), max(1, int(h))
    r = int(max(0, min(r, w / 2, h / 2)))
    m = Image.new("L", (w, h), 255)
    if r < 1: return m
    y, x = np.mgrid[0:r, 0:r].astype(np.float32) + 0.5
    d = np.sqrt((x - r) ** 2 + (y - r) ** 2)
    q = Image.fromarray((np.clip(r - d + 0.5, 0, 1) * 255).astype(np.uint8), "L")
    m.paste(q, (0, 0)); m.paste(q.transpose(Image.FLIP_LEFT_RIGHT), (w - r, 0))
    m.paste(q.transpose(Image.FLIP_TOP_BOTTOM), (0, h - r)); m.paste(q.transpose(Image.ROTATE_180), (w - r, h - r))
    return m

@functools.lru_cache(16)
def circle_mask(d):
    d = max(1, int(d))
    m = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(m).ellipse([0, 0, d * 4 - 1, d * 4 - 1], fill=255)
    return m.resize((d, d), Image.LANCZOS)

def put(img, el, x, y, a=1.0):
    """Composite an RGBA element onto an RGB frame, in place, at its top-left x, y (clipped to the frame)."""
    if a <= 0.003: return
    if a < 0.999: el = with_alpha(el, a)
    img.paste(el, (int(round(x)), int(round(y))), el)

def shadow_of(el, blur=18, strength=0.35, q=4):
    """A soft shadow from an element's alpha. Returns (RGBA, pad): draw it at x - pad, y - pad (+ a drop)."""
    pad = int(blur * 2.6)
    al = el.getchannel("A")
    sw, sh = max(1, (el.width + 2 * pad) // q), max(1, (el.height + 2 * pad) // q)
    sm = Image.new("L", (sw, sh), 0)
    sm.paste(al.resize((max(1, el.width // q), max(1, el.height // q)), Image.BILINEAR), (pad // q, pad // q))
    sm = sm.filter(ImageFilter.GaussianBlur(blur / q)).resize((el.width + 2 * pad, el.height + 2 * pad), Image.BILINEAR)
    sm = sm.point(lambda v: int(v * strength))
    out = Image.new("RGBA", sm.size, (0, 0, 0, 0)); out.putalpha(sm)
    return out, pad

def stamp(img, el, cx, cy, s=1.0, a=1.0, shadow=0.35, blur=18, dy=14, rot=0.0):
    """Draw an RGBA element centred on (cx, cy), scaled by s, with a soft drop shadow. In place."""
    if a <= 0.003 or s <= 0.02: return
    if abs(s - 1) > 1e-3:
        el = el.resize((max(1, int(round(el.width * s))), max(1, int(round(el.height * s)))),
                       Image.LANCZOS if s < 1 else Image.BICUBIC)
    if rot: el = el.rotate(rot, Image.BICUBIC, expand=True)
    x, y = cx - el.width / 2, cy - el.height / 2
    if shadow > 0:
        sh, pad = shadow_of(el, blur * max(s, 0.3), shadow)
        put(img, sh, x - pad, y - pad + dy * s, a)
    put(img, el, x, y, a)

def frost(img, box, r, tint=(18, 18, 22), tint_a=0.72, blur=7, q=4, border=(255, 255, 255, 34)):
    """Frosted panel: what's behind box (img, PIL RGB), blurred from a downscaled copy and tinted.
    Returns the rounded RGBA panel to put() at box's top-left."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    w, h = max(2, x1 - x0), max(2, y1 - y0)
    pad = blur * q * 2
    bx0, by0 = max(0, x0 - pad), max(0, y0 - pad)
    bx1, by1 = min(img.width, x1 + pad), min(img.height, y1 + pad)
    panel = Image.new("RGB", (w, h), tint)
    if bx1 - bx0 > 4 and by1 - by0 > 4:
        reg = img.crop((bx0, by0, bx1, by1))
        small = reg.resize((max(1, reg.width // q), max(1, reg.height // q)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(blur))
        reg = small.resize(reg.size, Image.BILINEAR)
        panel.paste(reg, (bx0 - x0, by0 - y0))
    panel = Image.blend(panel, Image.new("RGB", (w, h), tint), tint_a).convert("RGBA")
    if border:
        s = SS(w, h); s.rr((0.5, 0.5, w - 0.5, h - 0.5), r, outline=border, width=1.5)
        panel.alpha_composite(s.out())
    panel.putalpha(rr_mask(w, h, r))
    return panel

def flat(w, h, r, fill):
    """A plain rounded-rect RGBA (fill may carry alpha)."""
    fill = tuple(fill) + ((255,) if len(fill) == 3 else ())
    im = Image.new("RGBA", (int(w), int(h)), fill[:3] + (0,))
    a = rr_mask(int(w), int(h), r)
    if fill[3] < 255: a = a.point(lambda v: v * fill[3] // 255)
    im.putalpha(a)
    return im

def avatar(c, d, zoom=1.55, ring=None, ring_w=0):
    """A round crop of the face from the source frame (live, every frame). d: diameter in px."""
    cx, cy, fw, fh = c.face
    side = max(40.0, fh * zoom)
    x0, y0 = cx - side / 2, cy - side * 0.52
    x0 = clamp(x0, 0, W - side); y0 = clamp(y0, 0, H - side)
    crop = Image.fromarray(c.src).crop((int(x0), int(y0), int(x0 + side), int(y0 + side))).resize((d, d), Image.LANCZOS)
    out = crop.convert("RGBA"); out.putalpha(circle_mask(d))
    if ring and ring_w:
        s = SS(d, d); s.circ(d / 2, d / 2, d / 2 - ring_w / 2, outline=tuple(ring) + (255,), width=ring_w)
        out.alpha_composite(s.out())
    return out

def initials_avatar(name, d):
    """A round gradient avatar with the name's first letter (for usernames that aren't you)."""
    rnd = np.random.default_rng(seeded(name))
    pal = [((255, 149, 0), (255, 45, 85)), ((88, 86, 214), (10, 132, 255)), ((52, 199, 89), (48, 176, 199)),
           ((175, 82, 222), (255, 45, 85)), ((255, 204, 0), (255, 149, 0)), ((90, 200, 250), (0, 122, 255))]
    c0, c1 = pal[int(rnd.integers(len(pal)))]
    y = np.linspace(0, 1, d, dtype=np.float32)[:, None, None]
    x = np.linspace(0, 1, d, dtype=np.float32)[None, :, None]
    g = (x + y) / 2
    arr = np.array(c0, np.float32) * (1 - g) + np.array(c1, np.float32) * g
    im = Image.fromarray(np.broadcast_to(arr, (d, d, 3)).astype(np.uint8), "RGB").convert("RGBA")
    ch = (clean(str(name)) or "?")[0].upper()
    t = Image.new("RGBA", (d, d), (255, 255, 255, 0))
    ImageDraw.Draw(t).text((d / 2, d / 2 + d * 0.02), ch, font=font(d * 0.48, 700), fill=(255, 255, 255, 255), anchor="mm")
    im.alpha_composite(t)
    im.putalpha(circle_mask(d))
    return im

# ------------------------------------------------------------------ small drawn icons (on an SS)
def spinner(s, cx, cy, r, t, col=(255, 255, 255), a=1.0, spokes=8, period=0.85):
    """iOS activity indicator: spokes whose brightness chases round."""
    head = int(t / period * spokes)
    for k in range(spokes):
        ang = 2 * math.pi * k / spokes - math.pi / 2
        age = (head - k) % spokes
        al = a * (1 - 0.8 * age / (spokes - 1))
        p0 = (cx + math.cos(ang) * r * 0.5, cy + math.sin(ang) * r * 0.5)
        p1 = (cx + math.cos(ang) * r, cy + math.sin(ang) * r)
        s.line([p0, p1], tuple(col) + (int(255 * clamp01(al)),), r * 0.24)

def check(s, cx, cy, r, k, col=IOS_GREEN, ink=(255, 255, 255)):
    """A filled circle with a tick. k 0-1: the circle pops (overshoot), then the tick draws itself."""
    if k <= 0: return
    rr = r * back(prog(k, 0, 0.55), 2.6)
    if rr > 0.5: s.circ(cx, cy, rr, fill=tuple(col) + (255,))
    kk = ease_out(prog(k, 0.3, 0.7))
    if kk <= 0: return
    pts = [(cx - r * 0.42, cy + r * 0.02), (cx - r * 0.12, cy + r * 0.32), (cx + r * 0.45, cy - r * 0.3)]
    l1 = math.dist(pts[0], pts[1]); l2 = math.dist(pts[1], pts[2])
    L = (l1 + l2) * kk
    if L <= l1:
        f = L / l1; path = [pts[0], (lerp(pts[0][0], pts[1][0], f), lerp(pts[0][1], pts[1][1], f))]
    else:
        f = (L - l1) / l2; path = [pts[0], pts[1], (lerp(pts[1][0], pts[2][0], f), lerp(pts[1][1], pts[2][1], f))]
    s.line(path, tuple(ink) + (255,), r * 0.2)

def heart_pts(cx, cy, size, n=60):
    pts = []
    for i in range(n):
        t = 2 * math.pi * i / n
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * size / 34, cy - y * size / 34 - size * 0.04))
    return pts

def heart(s, cx, cy, size, fill=None, outline=None, width=3):
    pts = heart_pts(cx, cy, size)
    if fill: s.poly(pts, fill=tuple(fill) + ((255,) if len(fill) == 3 else ()))
    if outline: s.line(pts + [pts[0]], tuple(outline) + ((255,) if len(outline) == 3 else ()), width)

def play_icon(s, cx, cy, r, col):
    s.poly([(cx - r * 0.38, cy - r * 0.62), (cx + r * 0.62, cy), (cx - r * 0.38, cy + r * 0.62)], fill=tuple(col) + (255,))

def pause_icon(s, cx, cy, r, col):
    bw = r * 0.3
    s.rr((cx - r * 0.5, cy - r * 0.6, cx - r * 0.5 + bw, cy + r * 0.6), bw * 0.3, fill=tuple(col) + (255,))
    s.rr((cx + r * 0.5 - bw, cy - r * 0.6, cx + r * 0.5, cy + r * 0.6), bw * 0.3, fill=tuple(col) + (255,))

# ------------------------------------------------------------------ text
def wrap(words, f, maxw, space=None):
    """Greedy wrap of a list of words with font f to maxw px. Returns [[word index, ...], ...]."""
    space = f.getlength(" ") if space is None else space
    lines, cur, cw = [], [], 0.0
    for i, w in enumerate(words):
        lw = f.getlength(w)
        if cur and cw + space + lw > maxw:
            lines.append(cur); cur, cw = [], 0.0
        cw = lw if not cur else cw + space + lw
        cur.append(i)
    if cur: lines.append(cur)
    return lines

@functools.lru_cache(512)
def label_img(txt, size, weight=700, fill=(255, 255, 255), path=SFP, index=0):
    """One line of text as RGBA, full line height (so labels share a baseline), cropped left-right only."""
    f = font(size, weight, path, index)
    asc, desc = f.getmetrics()
    w = int(math.ceil(f.getlength(txt))) + 4
    im = Image.new("RGBA", (max(1, w), asc + desc), tuple(fill[:3]) + (0,))
    ImageDraw.Draw(im).text((1, 0), txt, font=f, fill=tuple(fill[:3]) + (255,))
    return im

def clip_fade(im, maxw, fade=14):
    """im cut to maxw px wide, fading out over the last fade px if it was cut."""
    if im.width <= maxw: return im
    maxw = max(1, int(maxw))
    im = im.crop((0, 0, maxw, im.height))
    a = np.asarray(im.getchannel("A"), np.float32)
    ramp = np.clip((maxw - np.arange(maxw)) / float(fade), 0, 1)
    im.putalpha(Image.fromarray((a * ramp[None, :]).astype(np.uint8), "L"))
    return im

def fit_text(txt, f, maxw):
    """txt cut with an ellipsis to fit maxw px."""
    if f.getlength(txt) <= maxw: return txt
    while txt and f.getlength(txt + "…") > maxw: txt = txt[:-1]
    return (txt.rstrip() + "…") if txt else ""

# ------------------------------------------------------------------ audio + footage
@functools.lru_cache(4)
def _loudness(path, hop=0.01):
    with wave.open(path) as w:
        n, sr, ch, sw = w.getnframes(), w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    if sw != 2: return np.zeros(1, np.float32)
    a = np.frombuffer(raw, np.int16).astype(np.float32).reshape(-1, ch).mean(1) / 32768.0
    k = max(1, int(sr * hop)); m = len(a) // k
    if m < 1: return np.zeros(1, np.float32)
    rms = np.sqrt((a[:m * k].reshape(m, k) ** 2).mean(1) + 1e-12)
    db = 20 * np.log10(rms)
    ref = np.percentile(db, 98)
    return np.clip((db - (ref - 40)) / 40, 0, 1).astype(np.float32)

def loudness(c, a, b, n):
    """n loudness values (0-1, the real sound) for n equal slices of [a, b] seconds. Zeros with no audio."""
    if not c.subj.audio: return np.zeros(n, np.float32)
    env = _loudness(c.subj.audio)
    out = np.zeros(n, np.float32)
    for i in range(n):
        i0 = int((a + (b - a) * i / n) * 100); i1 = int((a + (b - a) * (i + 1) / n) * 100)
        seg = env[max(0, i0):max(i0 + 1, i1)]
        out[i] = float(seg.max()) * 0.6 + float(seg.mean()) * 0.4 if len(seg) else 0.0
    return out

def contrast(v, lo=5, hi=97, gamma=1.3):
    """Loudness values stretched to their own range (quietest -> 0, loudest -> 1), so the shape reads."""
    v = np.asarray(v, np.float32)
    if len(v) < 2: return v
    a, b = np.percentile(v, lo), np.percentile(v, hi)
    if b - a < 0.04: return v
    return np.clip((v - a) / (b - a), 0, 1) ** gamma

def thumbs(c, a, b, n, tw, th, box=None):
    """n thumbnails (PIL RGB tw x th) of the video, evenly over [a, b] seconds.
    box: the region of the frame to show (x0, y0, x1, y1 in px, same shape as tw x th); default the centre."""
    d = max(0.1, b - a)
    if box:
        x0, y0, x1, y1 = [int(round(v)) for v in box]
        crop = f"crop={(x1 - x0) // 2 * 2}:{(y1 - y0) // 2 * 2}:{x0}:{y0},"
        sw, sh = tw, th
    else:
        crop = ""
        sc = max(tw / W, th / H)
        sw, sh = int(math.ceil(W * sc / 2) * 2), int(math.ceil(H * sc / 2) * 2)
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{max(0, a):.3f}", "-t", f"{d:.3f}", "-i", c.subj.base,
           "-vf", f"fps={n / d:.5f},{crop}scale={sw}:{sh}:flags=area", "-frames:v", str(n), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    try:
        raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    except Exception:
        raw = b""
    out = []
    fsz = sw * sh * 3
    for i in range(n):
        if len(raw) >= (i + 1) * fsz:
            im = Image.frombytes("RGB", (sw, sh), raw[i * fsz:(i + 1) * fsz])
        elif out:
            im = out[-1]
        else:
            im = Image.fromarray(c.src).resize((sw, sh), Image.BILINEAR)
        x0, y0 = (im.width - tw) // 2, (im.height - th) // 2
        out.append(im.crop((x0, y0, x0 + tw, y0 + th)) if im.size != (tw, th) else im)
    return out
