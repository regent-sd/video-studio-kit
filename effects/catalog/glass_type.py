"""Glass type: big 3D acrylic letters (your key word) stand in the room behind your head and bend the room seen
through them: bevelled edges refract it, a bright rim catches the light, a sheen sweeps across, and the letters
have a little thickness that shifts as they drift. They rise in letter by letter and sink out at the end."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, f32, to_pil, mix, font, ease_out, ease_in, ease_io, back, prog, lerp, clamp, hexc, SFP, SFROUND,
                  DIDOT)
from catalog._b import face_stats, solid_mask, smooth_noise, head_top
from catalog._print import key_word
from catalog._wall import grow_mask

NAME = "glass-type"
KIND = "behind"
ABOUT = "Big 3D glass letters of your word stand behind your head and refract the room"
DUR = 4.0
PARAMS = dict(
    text=None,       # the word; default your key word in the window
    font="sf",       # sf (SF Pro Black, condensed) | rounded (SF Rounded) | didot
    case="upper",    # upper | lower | as-said
    frost=0.35,      # 0 = clear acrylic, 1 = fully frosted
    tint=None,       # glass tint colour; default a cool clear white
    dim=0.18,        # how much the room darkens so the glass reads (0-1)
    y=None,          # centre of the letters (px); default so your head covers their lower third
    lens=1.7,        # how much the glass shrinks the room seen through it (1 = a flat pane)
)
FONTS = {"sf": (SFP, 0, 1000, 68), "rounded": (SFROUND, 0, 900, 100), "didot": (DIDOT, 2, 700, 100)}


# ------------------------------------------------------------------ letters -> glass maps (once)
def _letters(txt, fname, maxw, cap_max):
    """Per letter: alpha (float32 hxw at 1x), its x, top relative to the word's left / baseline. Plus cap height."""
    path, idx, wt, wd = FONTS.get(fname, FONTS["sf"])
    probe = font(400, wt, path, idx, wd)
    trk = 0.05 * 400
    nat = sum(probe.getlength(ch) for ch in txt) + trk * (len(txt) - 1)
    bb = probe.getbbox("H")
    cap400 = bb[3] - bb[1]
    size = min(400 * maxw / max(1, nat), 400 * cap_max / cap400)
    f2 = font(size * 2, wt, path, idx, wd)
    asc, desc = f2.getmetrics()
    out, x = [], 0.0
    for ch in txt:
        adv = f2.getlength(ch)
        if ch.strip():
            im = Image.new("L", (int(adv + 80), asc + desc + 80), 0)
            ImageDraw.Draw(im).text((40, asc + 40), ch, font=f2, fill=255, anchor="ls")
            bbx = im.getbbox()
            if bbx:
                im = im.crop(bbx)
                a = np.asarray(im.resize((max(1, im.width // 2), max(1, im.height // 2)), Image.LANCZOS), np.float32) / 255
                out.append(dict(a=a, x=(x + bbx[0] - 40) / 2, top=(bbx[1] - asc - 40) / 2))
        x += adv + trk * size / 400 * 2
    width = (x - trk * size / 400 * 2) / 2
    return out, width, cap400 * size / 400, size

def _glass_maps(a, bevel):
    """From a letter's alpha: bevel normals (nx, ny), the distance in from the edge, padded by P on every side."""
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    P = int(bevel * 1.9) + 10
    A = np.pad(a, P)
    d = distance_transform_edt(A > 0.5).astype(np.float32)
    d = gaussian_filter(d, 1.2)
    hgt = np.sin(np.clip(d / bevel, 0, 1) * math.pi / 2)            # a rounded bevel up to a flat top
    gy, gx = np.gradient(hgt)
    k = bevel / (math.pi / 2)
    nx, ny = -gx * k, -gy * k                                       # about 1 at the steepest edge, 0 on the flat top
    return dict(A=A, d=d, nx=nx.astype(np.float32), ny=ny.astype(np.float32), P=P)


def _shift(A, dx, dy):
    """A moved by (dx, dy) whole pixels, zero-filled, same shape."""
    dx, dy = int(round(dx)), int(round(dy))
    out = np.zeros_like(A)
    h, w = A.shape
    if abs(dx) >= w or abs(dy) >= h: return out
    out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] = A[max(0, -dy):h - max(0, dy), max(0, -dx):w - max(0, dx)]
    return out


# ------------------------------------------------------------------ sampling
def _bilinear(img, X, Y):
    """img HxWx3 float32; X, Y float arrays -> samples (N x 3)."""
    h, w = img.shape[:2]
    X = np.clip(X, 0, w - 1.001); Y = np.clip(Y, 0, h - 1.001)
    x0 = X.astype(np.int32); y0 = Y.astype(np.int32)
    fx = (X - x0)[:, None]; fy = (Y - y0)[:, None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c_ = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c_ * (1 - fx) + d * fx) * fy


def render(c):
    st = c.state
    d, u = c.d, c.u
    if "L" not in st:
        txt = key_word(c)
        cs = c.p.get("case", "upper")
        txt = txt.upper() if cs == "upper" else txt.lower() if cs == "lower" else txt
        st["L"] = []
        if txt:
            (fx, fy, fw, fh), (bx0, by0, bx1, by1) = face_stats(c)
            letters, width, cap, size = _letters(txt, c.p.get("font", "sf"), W - 90, 400)
            bevel = clamp(size * 0.075, 8, 34)
            ht = min(head_top(c, "_ht0"), fy - fh * 0.8)
            cy = float(c.p["y"]) if c.p.get("y") is not None else clamp(ht + cap * 0.2, 236 + cap / 2, 1300)
            base = cy + cap / 2
            x0 = (W - width) / 2
            for L in letters:
                g = _glass_maps(L["a"], bevel)
                L.update(g)
                L["X"] = x0 + L["x"] - g["P"]; L["Y"] = base + L["top"] - g["P"]
            st["L"] = letters
            st["cap"], st["bevel"], st["size"] = cap, bevel, size
            # the region the letters can reach (rise, sink, drift, refraction offsets)
            m = int(cap * 0.7) + 60
            st["box"] = (int(max(0, x0 - 60)), int(max(0, base - cap - m)), int(min(W, x0 + width + 60)), int(min(H, base + m)))
            st["tint"] = np.array(hexc(c.p["tint"]) if c.p.get("tint") else (228, 238, 255), np.float32)
    if not st["L"]: return c.img
    n = len(st["L"])
    sp = min(1.0, d / 3.5)
    out_len = min(0.7, d * 0.26)
    t_out = d - out_len
    ostag = min(0.05, out_len * 0.35 / max(1, n))
    k_bg = ease_out(prog(u, 0, 0.4)) * (1 - ease_in(prog(u, d - 0.35, 0.35)))
    cap, bev = st["cap"], st["bevel"]
    bx0, by0, bx1, by1 = st["box"]
    rw, rh = bx1 - bx0, by1 - by0
    # the room without you (your outline filled from the empty-room plate), for what the glass shows
    src = f32(np.asarray(c.img))
    reg = src[by0:by1, bx0:bx1]
    hole = grow_mask(c.mask, 24, 18)[by0:by1, bx0:bx1, None]
    plate = f32(c.subj.plate()[by0:by1, bx0:bx1])
    room = reg * (1 - hole) + plate * hole
    # slow 3D drift: the light and the thickness swing a little, the word sways
    drift = ease_io(prog(u, 0, d))
    sway_x = 10 * smooth_noise(u * 0.35, 3) * k_bg
    sway_y = 6 * smooth_noise(u * 0.3, 7) * k_bg
    ang = math.radians(-125 + 28 * smooth_noise(u * 0.25, 11) + 30 * drift)     # light from the top left, swinging
    Lx, Ly = math.cos(ang), math.sin(ang)
    depth = bev * 1.5
    ex, ey = depth * (0.55 + 0.35 * math.sin(u * 0.7)), depth * (0.8 + 0.2 * math.cos(u * 0.55))
    ph = ((u - 0.75) % 2.4) / 1.1                                    # a sheen sweeps across every 2.4 s
    b0, b1 = bx0 * 0.55 + by0 * 0.85, bx1 * 0.55 + by1 * 0.85
    sweep = lerp(b0 - 120, b1 + 120, ph) if 0 <= ph <= 1 and u > 0.75 else -1e6
    dim = float(c.p.get("dim", 0.18)) * k_bg
    out = reg * (1 - dim)
    shade = np.zeros((rh, rw), np.float32)                          # the letters' soft shadow on the wall
    any_on = False
    lay = []
    for k, L in enumerate(st["L"]):
        p = prog(u, 0.08 + k * min(0.07, 0.5 * sp / max(1, n)), 0.55)
        q = prog(u, t_out + k * ostag, out_len - ostag * (n - 1))
        if p <= 0 or q >= 1: continue
        a = ease_out(min(1, p * 1.5)) * (1 - ease_in(q))
        dy = cap * 0.55 * (1 - back(p, 1.4)) + cap * 0.45 * ease_in(q)
        X = int(round(L["X"] + sway_x)) - bx0; Y = int(round(L["Y"] + sway_y + dy)) - by0
        lay.append((L, X, Y, a))
        any_on = True
    if not any_on and k_bg <= 0.002: return c.img
    for L, X, Y, a in lay:                # shadows first, then the glass on top
        A = L["A"]
        h, w = A.shape
        x0, y0 = max(0, X + 24), max(0, Y + 40)
        x1, y1 = min(rw, X + 24 + w), min(rh, Y + 40 + h)
        if x1 > x0 and y1 > y0:
            shade[y0:y1, x0:x1] = np.maximum(shade[y0:y1, x0:x1], A[y0 - Y - 40:y1 - Y - 40, x0 - X - 24:x1 - X - 24] * a)
    if shade.max() > 0:
        sh = Image.fromarray((shade * 255).astype(np.uint8), "L")
        sh = sh.resize((max(1, rw // 4), max(1, rh // 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(5)).resize((rw, rh), Image.BILINEAR)
        shk = (1 - 0.42 * np.asarray(sh, np.float32)[..., None] / 255)
        out *= shk
        room = room * shk
    # what the glass shows: the room behind it (with the letters' own shadow), sharp or frosted
    room = room * (1 - dim)
    sm = Image.fromarray(np.clip(room, 0, 255).astype(np.uint8), "RGB")
    soft = f32(np.asarray(sm.resize((max(1, rw // 4), max(1, rh // 4)), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.2))
                          .resize((rw, rh), Image.BILINEAR)))
    frost = float(c.p.get("frost", 0.35))
    look = room * (1 - frost) + soft * frost
    tint = st["tint"]
    for L, X, Y, a in lay:
        A, D, nx, ny = L["A"], L["d"], L["nx"], L["ny"]
        h, w = A.shape
        # where the letter lands in the region (clipped)
        x0, y0, x1, y1 = max(0, X), max(0, Y), min(rw, X + w), min(rh, Y + h)
        if x1 <= x0 or y1 <= y0: continue
        sl = (slice(y0 - Y, y1 - Y), slice(x0 - X, x1 - X))
        Ac, Dc, nxc, nyc = A[sl], D[sl], nx[sl], ny[sl]
        # the thickness: the letter swept back along the depth vector; what shows beyond the front face is the side
        E = A.copy()
        N = int(clamp(math.hypot(ex, ey) / 2, 4, 24))
        for j in range(1, N + 1):
            E = np.maximum(E, _shift(A, ex * j / N, ey * j / N))
        Ab = E[sl]
        side = np.clip(Ab - Ac, 0, 1)
        cov = np.maximum(Ac, Ab)
        sel = cov > 0.004
        if not sel.any(): continue
        yy, xx = np.nonzero(sel)
        gx, gy = xx + x0, yy + y0
        Av, Dv, nxv, nyv, sv = Ac[sel], Dc[sel], nxc[sel], nyc[sel], side[sel]
        # refraction: the bevel bends the view outward, the slab shifts it a little with the drift
        R = bev * 1.9
        # a thick block works like a lens: the room inside each letter is seen smaller and shifted down a little,
        # so lines behind it (a wall edge, a shelf) show up bent inside the letters
        lcx, lcy = X + w / 2, Y + h / 2
        lens = float(c.p.get("lens", 1.7))
        sx = lcx + (gx - lcx) * lens + 0.35 * ex
        sy = lcy + (gy - lcy) * lens + 0.35 * ey + cap * 0.36
        offx = nxv * R + 10 * nxv * (1 - Av)
        offy = nyv * R
        if np.abs(nxv).max() > 0 or np.abs(nyv).max() > 0:       # a touch of dispersion: colour fringes on the bevel
            cr = _bilinear(look, sx + offx * 1.12, sy + offy * 1.12)[:, 0]
            cg = _bilinear(look, sx + offx, sy + offy)[:, 1]
            cb = _bilinear(look, sx + offx * 0.88, sy + offy * 0.88)[:, 2]
            col = np.stack([cr, cg, cb], 1)
        else:
            col = _bilinear(look, sx + offx, sy + offy)
        col = col * 0.9 + tint[None, :] * 0.1 + 6
        # a soft reflection of a bright window across the top of each face
        gl = np.clip(1 - (gy - Y) / (h * 0.5), 0, 1) ** 1.6 * np.clip((Dv - bev * 0.6) / 4, 0, 1) * 0.16
        col = col + (255 - col) * gl[:, None]
        # glass light: the bevel is darker (it reflects the dark room and bends light away), with a sharp highlight
        # on the edges facing the light, a bright caustic inside the far edges, and a thin rim all round
        ndl = nxv * Lx + nyv * Ly
        edge = np.clip(1 - (Dv - 1) / bev, 0, 1) * Av
        flat = np.clip((Dv - bev) / 3, 0, 1)
        lit = np.clip(ndl, 0, 1); away = np.clip(-ndl, 0, 1)
        spec = lit ** 3 * np.exp(-((Dv - bev * 0.3) / (bev * 0.2)) ** 2)
        caus = away ** 1.5 * np.exp(-((Dv - bev * 0.82) / (bev * 0.14)) ** 2)
        rim = np.exp(-(Dv / 1.3) ** 2) * Av
        band = (gx + bx0) * 0.55 + (gy + by0) * 0.85
        sheen = np.exp(-((band - sweep) / 52) ** 2) * flat * 0.26 + np.exp(-((band - sweep - 80) / 13) ** 2) * flat * 0.2
        inner = np.exp(-((Dv - bev * 1.0) / (bev * 0.13)) ** 2) * Av          # a dark line where the bevel meets the face
        col = col * (1 - edge[:, None] * (0.12 + 0.42 * away[:, None])) * (1 - 0.24 * inner[:, None])
        col = col * (1 + 0.06 * flat[:, None]) + 14 * flat[:, None]
        col = col * (1 - 0.25 * edge[:, None]) + np.array([150, 205, 215], np.float32)[None, :] * 0.25 * edge[:, None]
        col = col + (255 - col) * np.clip(spec * 0.95 + caus * 0.5 + rim * 0.55 + sheen, 0, 1)[:, None]
        # side walls: the room seen through the thickness, darker, with a lit edge facing the light
        if sv.any():
            sc = _bilinear(look, gx + ex * 1.4, gy + ey * 1.4) * 0.68 + tint[None, :] * 0.1
            # lighter where the side meets the front face, a bright line along the back edge
            near = np.clip(1 - Av * 0 - sv, 0, 1)
            sc = sc + (255 - sc) * (0.18 * np.exp(-(Dv / 3.0) ** 2))[:, None]
            col = col * (1 - sv[:, None]) + sc * sv[:, None]
        al = (np.maximum(Av, sv * 0.9) * a)[:, None]
        cur = out[gy, gx]
        out[gy, gx] = cur * (1 - al) + col * al
    res = src * (1 - dim) if dim > 0 else src.copy()     # the room outside the region darkens the same
    res[by0:by1, bx0:bx1] = out
    return to_pil(mix(src, res, solid_mask(c)))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your own",
    "needs": ["face"],
}
