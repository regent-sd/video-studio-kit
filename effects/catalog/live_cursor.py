"""Live cursor: a design-app selection box draws itself around you, shows its real pixel size,
and a named collaborator cursor drags the corner into place, then hangs around."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, SS, comp, soft_shadow, with_alpha, ease_out, ease_in, ease_io, back, prog, lerp, clamp, clamp01, hexc, font
from catalog._b import face_stats, smooth_noise, font_args

NAME = "live-cursor"
KIND = "cards"
ABOUT = "Design-app selection box with its real pixel size, and a named cursor that drags it into place"
DUR = 4.0
PARAMS = dict(
    name="Editor",     # the collaborator's name on the cursor tag
    color=None,        # cursor colour; default the skin's accent (yellow on the Dark skin)
    box_color=None,    # selection colour; default the skin's blue
    label=None,        # optional layer name above the box's top-left corner (e.g. a word you say); default none
    size=1.0,          # box size around your head and upper body (1 = head to mid-chest)
)
LINE = 4          # selection line width (px)
HANDLE = 25       # corner handle size (px)


def _lum(c): return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]

def _cursor(col, name, left, skin):
    """Arrow pointer with a name tag. Returns (RGBA sprite, tip x, tip y) with a soft shadow baked in."""
    txt_col = (17, 17, 19) if _lum(col) > 150 else (255, 255, 255)
    F = font_args(skin, "heading", 720)
    tsz = 27
    tw = SS(1, 1).textlen(name, tsz, F["weight"], F["path"], F["index"]) if name else 0
    tagw, tagh = (tw + 30, 46) if name else (0, 0)
    pad = 30
    aw, ah = 34, 50
    w = int(aw + tagw + 40 + 2 * pad); h = int(ah + 36 + tagh + 2 * pad)
    tipx = pad + (tagw + 20 if left else 0)
    tipy = pad
    s = SS(w, h)
    sc = 1.4
    pts = [(0, 0), (0, 34), (9, 26.5), (14.5, 38.5), (20, 36), (14.8, 24.5), (25, 24.5)]
    pts = [(tipx + x * sc, tipy + y * sc) for x, y in pts]
    # white outline: the arrow drawn fatter underneath
    s.poly(pts, fill=(255, 255, 255, 255))
    s.line(pts + [pts[0]], (255, 255, 255, 255), 6)
    s.poly(pts, fill=col + (255,))
    if name:
        tx = tipx + (22 if not left else -22 - tagw)
        ty = tipy + 44
        s.rr((tx, ty, tx + tagw, ty + tagh), 12, fill=col + (255,))
        s.text((tx + 15, ty + tagh / 2 + 1), name, tsz, fill=txt_col + (255,), anchor="lm", **F)
    im = s.out()
    sh = soft_shadow(im, 0.45, blur=4, pad=0)
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, 0))
    sh2 = Image.new("RGBA", im.size, (0, 0, 0, 0)); sh2.alpha_composite(out, (3, 6))
    sh2.alpha_composite(im)
    return sh2, tipx, tipy

def _tag(txt, col, skin):
    F = font_args(skin, "heading", 700)
    tw = SS(1, 1).textlen(txt, 30, F["weight"], F["path"], F["index"])
    w, h = int(tw + 32), 50
    s = SS(w, h)
    s.rr((0, 0, w, h), 10, fill=col + (255,))
    s.text((w / 2, h / 2 + 1), txt, 30, fill=(255, 255, 255, 255), anchor="mm", **F)
    return s.out()

def _box_final(c):
    """Final box size (w, h) and its offsets from the face: from the window's median face, fixed for the whole effect."""
    (fx, fy, fw, fh), u = face_stats(c)
    k = float(c.p.get("size") or 1.0)
    bw = int(round(min(W - 60, fw * 1.78 * k) / 2)) * 2
    top_off = fh * 0.98 + 26                     # box top above the face centre
    bh = int(round(min(1400 - 236, fh * 2.1 * k) / 2)) * 2
    return bw, bh, top_off

def _box_at(c, st, w, h, anchor):
    """Box (x0, y0, x1, y1) of size w x h for this frame, following the face. anchor: which corner stays put."""
    bw, bh, top_off = st["final"]
    fx, fy, fw, fh = c.face
    x0 = clamp(fx - bw / 2, 24, W - 24 - bw)
    y0 = clamp(fy - top_off, 236, 1400 - bh)
    if anchor == "tl": return (x0, y0, x0 + w, y0 + h)
    return (x0 + bw - w, y0, x0 + bw, y0 + h)       # "tr": the right edge stays put

def _draw_box(cv, box, col, perim_p, handles, alpha):
    """Selection lines (drawn up to perim_p of the perimeter, clockwise from top-left) and corner handles."""
    d = ImageDraw.Draw(cv)
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    ca = col + (int(255 * alpha),)
    segs = [((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))]
    lens = [x1 - x0, y1 - y0, x1 - x0, y1 - y0]
    left = perim_p * sum(lens)
    for (a, b), L in zip(segs, lens):
        if left <= 0: break
        f = min(1.0, left / max(1, L)); left -= L
        ex, ey = a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        xa, xb = sorted((a[0], ex)); ya, yb = sorted((a[1], ey))
        h = LINE // 2
        d.rectangle((xa - h, ya - h, xb + LINE - h - 1, yb + LINE - h - 1), fill=ca)
    for (hx, hy), hs in zip(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), handles):
        if hs <= 0.01: continue
        r = HANDLE / 2 * hs
        d.rectangle((hx - r, hy - r, hx + r, hy + r), fill=(255, 255, 255, int(255 * alpha)), outline=ca, width=LINE)

def render(c):
    st = c.state
    col = hexc(c.p["color"]) if c.p.get("color") else tuple(c.skin.accent)
    bcol = hexc(c.p["box_color"]) if c.p.get("box_color") else tuple(c.skin.blue)
    d, u = c.d, c.u
    if "final" not in st:
        st["final"] = _box_final(c)
        bw, bh, _ = st["final"]
        (fx, fy, fw, fh), _u = face_stats(c)
        x0 = clamp(fx - bw / 2, 24, W - 24 - bw)
        st["side"] = 1 if (W - (x0 + bw)) >= x0 else -1        # the cursor works on the roomier side
        name = str(c.p.get("name") or "")
        st["cur"] = _cursor(col, name, False, c.skin)
        st["curL"] = _cursor(col, name, True, c.skin)
        st["tags"] = {}
    bw, bh, _ = st["final"]
    side = st["side"]
    anchor = "tl" if side > 0 else "tr"
    # timing, squeezed for short windows
    f = min(1.0, d / 3.2)                       # everything runs faster in a short window
    t_draw = 0.55 * f
    t_in0, t_in1 = 0.25 * f, 0.8 * f
    t_drag0, t_drag1 = t_in1 + 0.08 * f, t_in1 + 0.63 * f
    t_out = d - 0.5 * f
    p_draw = ease_io(prog(u, 0, t_draw))
    p_drag = prog(u, t_drag0, t_drag1 - t_drag0)
    p_out = prog(u, t_out, d - t_out)
    # box size: starts at 76% and is dragged out to full size (with a touch of overshoot)
    g = back(p_drag, 1.1) if p_drag < 1 else 1.0
    w = lerp(bw * 0.76, bw, g); h = lerp(bh * 0.76, bh, g)
    box = _box_at(c, st, w, h, anchor)
    cv = c.canvas()
    alpha = 1 - ease_in(p_out)
    perim = p_draw * (1 - ease_in(prog(u, t_out, (d - t_out) * 0.8)))
    hs = []
    for q in (0.0, (box[2] - box[0]) / (2 * (w + h)), 0.5, 0.5 + (box[2] - box[0]) / (2 * (w + h))):
        pin = back(prog(p_draw, q, 0.18), 2.4) if p_draw > q else 0.0
        hs.append(pin * (1 - ease_in(p_out)))
    # the corner being dragged swells a little while held
    held = 1 + 0.25 * math.sin(math.pi * clamp01((u - t_drag0 + 0.05) / (t_drag1 - t_drag0 + 0.1)))
    hi = 2 if side > 0 else 3
    hs[hi] *= held
    # a faint fill flashes when the drag is released
    fl = math.exp(-max(0, u - t_drag1) * 5) * (u >= t_drag1) * alpha
    if fl > 0.02:
        ImageDraw.Draw(cv).rectangle([int(v) for v in box], fill=bcol + (int(30 * fl),))
    _draw_box(cv, box, bcol, perim, hs, alpha)
    # size tag under the box: the box's real size in pixels
    if p_draw > 0.6 and alpha > 0.01:
        txt = f"{int(round(box[2] - box[0]))} × {int(round(box[3] - box[1]))}"
        if txt not in st["tags"]: st["tags"][txt] = _tag(txt, bcol, c.skin)
        tg = st["tags"][txt]
        ta = ease_out(prog(p_draw, 0.6, 0.4)) * alpha
        ty = box[3] + 16 + 8 * (1 - ease_out(prog(u, t_draw * 0.6, 0.3)))
        comp(cv, with_alpha(tg, ta), (box[0] + box[2]) / 2 - tg.width / 2, min(1466 - tg.height, ty))
    if c.p.get("label") and alpha > 0.01:
        F = font_args(c.skin, "heading", 650)
        ImageDraw.Draw(cv).text((box[0], box[1] - 12), str(c.p["label"]), font=font(28, F["weight"], F["path"], F["index"]),
                                fill=bcol + (int(255 * alpha * ease_out(prog(u, t_draw, 0.3))),), anchor="ld")
    # ---- the cursor
    corner = (box[2], box[3]) if side > 0 else (box[0], box[3])
    if u < t_drag0:
        # fly in from off-screen to the handle
        p = ease_out(prog(u, t_in0, t_in1 - t_in0))
        if p <= 0: pos = None
        else:
            sx, sy = (W + 80, min(H - 200, corner[1] + 420)) if side > 0 else (-80, min(H - 200, corner[1] + 420))
            cx_, cy_ = lerp(sx, corner[0] + 4 * side, p), lerp(sy, corner[1] + 4, p)
            cy_ -= math.sin(math.pi * p) * 60        # a slight arc
            pos = (cx_, cy_)
    elif u < t_drag1 + 0.15:
        pos = (corner[0] + 4 * side, corner[1] + 4)
    else:
        # idle: wander between spots on the cursor's side of the box, never over the face
        bx0, by0, bx1, by1 = box
        ex = bx1 if side > 0 else bx0
        spots = [(ex + 6 * side, by1 + 6), (ex + 46 * side, (by0 + by1) * 0.52), (ex + 8 * side, by0 + 8),
                 ((bx0 + bx1) / 2 + side * (bx1 - bx0) * 0.28, by1 + 64), (ex + 110 * side, by0 + (by1 - by0) * 0.78),
                 (ex + 30 * side, by0 + (by1 - by0) * 0.3)]
        rng = np.random.default_rng(5)
        order = [0] + list(rng.permutation(len(spots) - 1) + 1) * 3
        hop = 1.25
        tt = u - (t_drag1 + 0.15)
        k = int(tt // hop); fr = (tt % hop) / hop
        a_ = spots[order[k % len(order)]]; b_ = spots[order[(k + 1) % len(order)]]
        m = ease_io(clamp01(fr / 0.55))                      # move for ~0.7 s, rest the remainder
        pos = (lerp(a_[0], b_[0], m), lerp(a_[1], b_[1], m))
        # a curved path and a little hand tremor
        pos = (pos[0] + math.sin(math.pi * m) * 30 * (1 if k % 2 else -1),
               pos[1] + 3 * smooth_noise(u, 3, (0.7, 1.3, 2.1)))
        pos = (pos[0] + 3 * smooth_noise(u, 4, (0.6, 1.1, 1.9)), pos[1])
    if pos is not None and p_out > 0:
        # leave: off the side
        q = ease_in(p_out)
        far = max(st["cur"][0].width, st["curL"][0].width) + 60
        pos = (lerp(pos[0], (W + far) if side > 0 else -far, q), lerp(pos[1], pos[1] + 260, q))
    if pos is not None:
        # the name tag sits right of the arrow, or left of it near the right edge (with some hysteresis,
        # and no flipping while the cursor leaves)
        spr_r, txr, _ = st["cur"]
        if p_out <= 0:
            if pos[0] + spr_r.width - txr > W - 6: st["tagL"] = True
            elif pos[0] + spr_r.width - txr < W - 70: st["tagL"] = False
        spr, tx, ty = st["curL"] if st.get("tagL") else st["cur"]
        # click ripples: when the drag starts and ends
        for tc in (t_drag0, t_drag1):
            r = prog(u, tc, 0.4)
            if 0 < r < 1:
                rr = 12 + 34 * ease_out(r)
                s2 = SS(int(2 * rr + 8), int(2 * rr + 8))
                s2.circ(rr + 4, rr + 4, rr, outline=col + (int(220 * (1 - r)),), width=3)
                comp(cv, s2.out(), pos[0] - rr - 4, pos[1] - rr - 4)
        comp(cv, spr, pos[0] - tx, pos[1] - ty)
    return c.front(cv)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "CLAUDE-WROTE: the cursor's name tag 'Editor' (the default). The size tag is the selection box's real size in pixels.",
    "needs": ["face"],
}
