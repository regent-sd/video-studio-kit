"""Letter dive: the video zooms out into a giant serif word cut out of paper (you play inside the letters), then the
camera dives into one letter until the video fills the frame again."""
import math, re
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, f32, to_pil, font, text_img, ease_in, ease_out, ease_io, prog, lerp, clamp01, hexc,
                  DIDOT, BODONI, NEWYORK_IT)
from ._print import paper, smooth, sentence_with, key_word

NAME = "letter-dive"
KIND = "camera"
ABOUT = "A giant serif word on paper with the video playing inside the letters; the camera dives into a letter"
DUR = 3.2
PARAMS = dict(
    text=None,          # the word; default the key word you say in the window
    font="bodoni",      # bodoni | didot (both bold) | skin (the skin's title font: a brand's own, on the Brand skin)
    paper="#F3EEE4",    # paper colour
    mode="both",        # both (zoom out of a letter at the start, dive into one at the end) | in | out
    caption=True,       # your sentence in small italics under the word
)
FONTS = {"bodoni": (BODONI, 2), "didot": (DIDOT, 2)}
K = 2                    # the letter shapes are kept at 2x for clean edges when the camera is close
MG = 160                 # margin (1x px) around the layout, so the camera never samples past the edge

def _rows(word, path, idx):
    """Split the word into 1-3 rows and pick the size that makes the letters biggest. Returns (rows, size)."""
    n = len(word)
    best = None
    for r in (1, 2, 3):
        if r > 1 and n < r * 2: continue
        per = -(-n // r)
        rows = [word[i * per:(i + 1) * per] for i in range(r)]
        rows = [x for x in rows if x]
        f = font(200, 700, path, idx)
        wmax = max(f.getlength(x) for x in rows)
        cap = 200 * 0.70
        size = min(200 * W * 0.9 / wmax, 200 * (H * 0.6) / (cap * (len(rows) * 1.06)))
        score = size * (1 - 0.14 * (len(rows) - 1))
        if best is None or score > best[0]: best = (score, rows, size)
    return best[1], best[2]

def _layout(word, path, idx, cy):
    """The word's mask at 2x (uint8), and the box of each row."""
    from scipy.ndimage import distance_transform_edt, label
    rows, size = _rows(word, path, idx)
    f = font(size * K, 700, path, idx)
    bbs = [f.getbbox(r, anchor="ls") for r in rows]
    cap = max(-b[1] for b in bbs)
    gap = cap * 0.07
    total = cap * len(rows) + gap * (len(rows) - 1)
    m = Image.new("L", (W * K, H * K), 0)
    d = ImageDraw.Draw(m)
    y = cy * K - total / 2
    for r, b in zip(rows, bbs):
        wr = b[2] - b[0]
        d.text((W * K / 2 - wr / 2 - b[0], y + cap), r, font=f, fill=255, anchor="ls")
        y += cap + gap
    a = np.asarray(m, np.uint8)
    inside = a > 127
    sdf = (distance_transform_edt(inside) - distance_transform_edt(~inside)).astype(np.float32) / K   # 1x px
    # dive targets: the deepest point of each letter (connected pieces)
    lab, n = label(inside)
    pts = []
    for k in range(1, n + 1):
        sel = lab == k
        if sel.sum() < 400: continue
        v = np.where(sel, sdf, -1e9)
        j = int(np.argmax(v))
        yy, xx = divmod(j, W * K)
        pts.append((xx / K, yy / K, float(sdf.flat[j])))
    pts.sort(key=lambda p: (round(p[1] / 60), p[0]))
    bottom = cy + total / K / 2
    return sdf, pts, bottom

def _view(st, Z, P, a):
    """Screen-sized samples of the layout under the camera: zoom Z about layout point P, P moved a of the way to the
    centre. Returns (sdf in screen px, sdf shifted toward the light, paper RGB)."""
    Psx, Psy = lerp(P[0], W / 2, a), lerp(P[1], H / 2, a)
    # the screen rect the (margined) layout covers
    sx0 = max(0, int(math.ceil(Psx + (-MG + 12 - P[0]) * Z))); sy0 = max(0, int(math.ceil(Psy + (-MG + 12 - P[1]) * Z)))
    sx1 = min(W, int(math.floor(Psx + (W + MG - 12 - P[0]) * Z))); sy1 = min(H, int(math.floor(Psy + (H + MG - 12 - P[1]) * Z)))
    out = np.full((H, W), -999.0, np.float32)
    outs = np.full((H, W), -999.0, np.float32)
    pap = np.empty((H, W, 3), np.float32); pap[:] = st["paper_mean"]
    if sx1 > sx0 and sy1 > sy0:
        b = (P[0] + (sx0 - Psx) / Z + MG, P[1] + (sy0 - Psy) / Z + MG, P[0] + (sx1 - Psx) / Z + MG, P[1] + (sy1 - Psy) / Z + MG)
        sz = (sx1 - sx0, sy1 - sy0)
        bk = tuple(v * K for v in b)
        out[sy0:sy1, sx0:sx1] = np.asarray(st["sdf_img"].resize(sz, Image.BILINEAR, box=bk), np.float32) * Z
        # the paper's shadow falls down-right into the letters: sample the shape a little up-left
        dx, dy = -7.0 / Z * K, -10.0 / Z * K
        bs = (bk[0] + dx, bk[1] + dy, bk[2] + dx, bk[3] + dy)
        outs[sy0:sy1, sx0:sx1] = np.asarray(st["sdf_img"].resize(sz, Image.BILINEAR, box=bs), np.float32) * Z
        pap[sy0:sy1, sx0:sx1] = np.asarray(st["paper_img"].resize(sz, Image.BICUBIC, box=b), np.float32)
    return out, outs, pap

def render(c):
    st = c.state
    if "sdf_img" not in st:
        word = re.sub(r"[^\w'-]", "", key_word(c)).upper()
        if not word:
            from core import log
            log("letter-dive: no word to show (no transcript); set text=...")
            st["sdf_img"] = None
            return c.img
        path, idx = tuple(c.skin["title"][:2]) if c.p["font"] == "skin" else FONTS.get(c.p["font"], FONTS["bodoni"])
        sdf, pts, bottom = _layout(word, path, idx, H * 0.43)
        st["sdf_img"] = Image.fromarray(np.pad(sdf, MG * K, constant_values=-999.0), "F")
        pc = hexc(c.p["paper"])
        pp = paper(W + 2 * MG, H + 2 * MG, pc, seed=44, grain=5.0, mottle=7.0, fibers=0.6)
        st["paper_img"] = Image.fromarray(pp.astype(np.uint8), "RGB")
        st["paper_mean"] = np.array(pc, np.float32)
        if not pts: pts = [(W / 2, H * 0.43, 30.0)]
        mid = len(pts) // 2
        st["p_out"] = max(pts[max(0, mid - 1):mid + 2], key=lambda p: p[2]) if len(pts) > 2 else max(pts, key=lambda p: p[2])
        others = [p for p in pts if p is not st["p_out"]]
        st["p_in"] = max(others[:max(1, len(others) // 2)], key=lambda p: p[2]) if others else st["p_out"]
        # caption: the sentence you say, in small italics
        cap = sentence_with(c.words, word, c.t0, c.t1) if c.p.get("caption") else None
        if cap:
            t = text_img("— " + cap, 40, 400, (70, 64, 58), 0, NEWYORK_IT, 0)
            if t.width > W * 0.86: t = t.resize((int(W * 0.86), int(t.height * W * 0.86 / t.width)), Image.LANCZOS)
            st["cap"] = (t, min(bottom + 70, 1440 - t.height))
    if st["sdf_img"] is None: return c.img
    u, d = c.u, c.d
    mode = c.p.get("mode", "both")
    tin = min(1.0, d * 0.34); tout = min(0.95, d * 0.32)
    zin = max(8.0, 1150.0 / max(8.0, st["p_in"][2]) * 1.15)
    zout = max(8.0, 1150.0 / max(8.0, st["p_out"][2]) * 1.15)
    fade = 1.0
    hold_push = 1.0 + 0.035 * ease_io(prog(u, tin, max(0.1, d - tin - tout)))
    if mode in ("both", "in") and u < tin:
        e = ease_out(prog(u, 0, tin)) ** 0.9
        Z = math.exp(math.log(zin) * (1 - e)); P = st["p_in"]
        a = clamp01(math.log(Z) / math.log(zin)) ** 0.6
    elif mode in ("both", "out") and u > d - tout:
        e = ease_in(prog(u, d - tout, tout))
        Z = hold_push * math.exp(math.log(zout) * e); P = st["p_out"]
        a = clamp01(math.log(Z) / math.log(zout)) ** 0.6
    else:
        Z, P, a = hold_push, (W / 2, H * 0.43), 0.0
        if mode == "out": fade = ease_out(prog(u, 0, 0.35))
        if mode == "in": fade = 1 - ease_in(prog(u, d - 0.35, 0.35))
    sdf, sdfs, pap = _view(st, Z, P, a)
    inside = np.clip(0.5 + sdf, 0, 1)
    vid = f32(np.asarray(c.img))
    # a soft shadow from the paper's cut edge, and a faint light rim on the edge itself
    sh = smooth(18.0, 0.0, sdfs) * 0.38 + smooth(4.0, 0.0, sdf) * 0.12
    vid_in = vid * (1 - np.clip(sh, 0, 0.62)[..., None])
    rim = np.clip(1 - np.abs(sdf + 1.2) / 1.6, 0, 1) * 18
    pap = pap + rim[..., None]
    out = vid_in * inside[..., None] + pap * (1 - inside[..., None])
    # caption fades in once the word has landed and out before the dive
    if "cap" in st and Z < 1.2:
        ca = ease_out(prog(u, tin * 0.75, 0.4)) * (1 - ease_out(prog(u, d - tout - 0.1, 0.25)))
        if mode == "out": ca = ease_out(prog(u, 0.2, 0.4)) * (1 - ease_out(prog(u, d - tout - 0.1, 0.25)))
        if ca > 0.01:
            t, yc = st["cap"]
            ta = np.asarray(t, np.float32)
            x0 = int(W / 2 - t.width / 2); y0 = int(yc - 6 * (1 - ca))
            reg = out[y0:y0 + t.height, x0:x0 + t.width]
            al = ta[..., 3:4] / 255.0 * ca
            reg[:] = reg * (1 - al) + ta[..., :3] * al
    if fade < 1:
        out = vid * (1 - fade) + out * fade
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your own; the caption is your sentence",
}
