"""Doodle boil: a hand-drawn chalk outline traced around you, a little outside your edge, that "boils" (it is redrawn
with a new wobble every few frames, like hand-drawn animation). Crayon doodles pop in around your head one by one
and wiggle (a heart, stars, a sparkle, a squiggle, a crown, an arrow), with your key word written by hand.
It all draws itself on quickly and is wiped off at the end."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import (W, H, f32, to_pil, mix, text_img, ease_out, ease_in, ease_io, back, prog, clamp, hexc, HAND, CHALK)
from catalog._b import face_stats, solid_mask, head_top
from catalog._print import key_word, noise
from catalog._wall import solid_small

NAME = "doodle-boil"
KIND = "behind"
ABOUT = "A boiling hand-drawn chalk outline around you, with crayon doodles and your word around your head"
DUR = 4.0
PARAMS = dict(
    color=None,      # outline colour; default white
    accent=None,     # doodle colour; default the skin's accent (yellow)
    offset=22,       # how far outside your edge the outline runs (px)
    width=7,         # line thickness (px)
    stickers=["heart", "star", "sparkle", "crown", "squiggle", "arrow"],   # doodles round your head, in pop order (heart | star | sparkle | squiggle | crown | arrow)
    word=None,       # a hand-written word by your head; default your key word; "" for none
    font="hand",     # hand (Bradley Hand) | chalk (Chalkduster)
    boil=3,          # frames between redraws (3 = the classic 10-a-second boil)
)
Q = 4                # the outline is traced on a 1/Q size cutout


# ------------------------------------------------------------------ the outline
CASES = {1: [("l", "b")], 2: [("b", "r")], 3: [("l", "r")], 4: [("t", "r")], 5: [("l", "t"), ("b", "r")],
         6: [("t", "b")], 7: [("l", "t")], 8: [("l", "t")], 9: [("t", "b")], 10: [("l", "b"), ("t", "r")],
         11: [("t", "r")], 12: [("l", "r")], 13: [("b", "r")], 14: [("l", "b")]}

def _contours(f, iso=0.5):
    """Marching squares on a float field: closed polylines [(x, y), ...] in field pixels."""
    h, w = f.shape
    b = f > iso
    case = (b[:-1, :-1] * 8 + b[:-1, 1:] * 4 + b[1:, 1:] * 2 + b[1:, :-1] * 1).astype(np.int8)
    ys, xs = np.nonzero((case > 0) & (case < 15))
    def pt(e, y, x):
        if e == "t": a, c_ = f[y, x], f[y, x + 1]; t = (iso - a) / (c_ - a + 1e-9); return ("h", y, x), (x + t, y)
        if e == "b": a, c_ = f[y + 1, x], f[y + 1, x + 1]; t = (iso - a) / (c_ - a + 1e-9); return ("h", y + 1, x), (x + t, y + 1)
        if e == "l": a, c_ = f[y, x], f[y + 1, x]; t = (iso - a) / (c_ - a + 1e-9); return ("v", y, x), (x, y + t)
        a, c_ = f[y, x + 1], f[y + 1, x + 1]; t = (iso - a) / (c_ - a + 1e-9); return ("v", y, x + 1), (x + 1, y + t)
    adj, pos = {}, {}
    for y, x in zip(ys.tolist(), xs.tolist()):
        for e1, e2 in CASES[int(case[y, x])]:
            k1, p1 = pt(e1, y, x); k2, p2 = pt(e2, y, x)
            pos[k1], pos[k2] = p1, p2
            adj.setdefault(k1, []).append(k2); adj.setdefault(k2, []).append(k1)
    seen, loops = set(), []
    for start in adj:
        if start in seen: continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [n for n in adj[cur] if n != prev and n not in seen]
            if not nxt: break
            prev, cur = cur, nxt[0]
            seen.add(cur); loop.append(cur)
        if len(loop) > 8: loops.append([pos[k] for k in loop])
    return loops

def _outline(c, off):
    """Your outline grown by off px, as open runs [(x, y)...] in frame px (the parts along the frame edge dropped),
    simplified and evenly spaced."""
    from scipy.ndimage import distance_transform_edt, gaussian_filter
    m = solid_small(c, Q)
    if m.sum() < 50: return []
    dist = distance_transform_edt(~m)
    grown = (dist <= off / Q).astype(np.float32)
    fld = gaussian_filter(grown, 2.2)
    fld = np.pad(fld, 2)                                     # closed loops, even where you touch the frame edge
    h, w = fld.shape
    runs = []
    for loop in _contours(fld):
        if len(loop) < 40: continue
        cur = []
        for x, y in loop:
            inside = 3.2 < x < w - 4.2 and 3.2 < y < h - 4.2
            if inside: cur.append(((x - 2) * Q, (y - 2) * Q))
            elif cur:
                runs.append(cur); cur = []
        if cur:
            if runs and loop and 3.2 < loop[0][0] < w - 4.2 and 3.2 < loop[0][1] < h - 4.2 and runs[0]:
                runs[0] = cur + runs[0]                      # the loop started mid-run: join the two halves
            else:
                runs.append(cur)
    out = []
    for r in runs:
        if len(r) < 10: continue
        out.append(_resample(_smooth(np.asarray(r, np.float32), 5), 11.0))
    return [r for r in out if len(r) >= 6]

def _smooth(p, k):
    if len(p) < k * 2 + 2: return p
    ker = np.ones(k) / k
    pad = np.pad(p, ((k // 2, k // 2), (0, 0)), mode="edge")
    return np.stack([np.convolve(pad[:, j], ker, mode="valid") for j in range(2)], 1)

def _resample(p, step):
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    if d[-1] < step * 2: return p
    s = np.arange(0, d[-1], step)
    return np.stack([np.interp(s, d, p[:, 0]), np.interp(s, d, p[:, 1])], 1)

def _boil(p, rng, amp, closed=False):
    """Wobble a polyline along its normals: a smooth wander plus a little hand shake."""
    n = len(p)
    if n < 3: return p
    t = np.diff(p, axis=0, append=p[-1:] + (p[-1:] - p[-2:-1]))
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-6)[:, None]
    nrm = np.stack([-t[:, 1], t[:, 0]], 1)
    s = np.arange(n, dtype=np.float32)
    wob = np.zeros(n, np.float32)
    for per, a in ((rng.uniform(18, 30), 1.0), (rng.uniform(6, 10), 0.45)):
        wob += a * np.sin(2 * math.pi * s / per + rng.uniform(0, 6.28))
    wob = wob * amp / 1.45 + rng.normal(0, amp * 0.18, n)
    return p + nrm * wob[:, None] + rng.normal(0, amp * 0.12, (n, 2))


# ------------------------------------------------------------------ doodles (local coordinates, unit size ~1)
def _doodle(kind, rng):
    """[polyline (Nx2 array)] for a doodle about 1 unit across, centred on 0."""
    if kind == "heart":
        t = np.linspace(0, 2 * math.pi, 64)
        x = 16 * np.sin(t) ** 3; y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))
        out = [np.stack([x, y], 1) / 34]
        for k in range(4):                       # a few hatch strokes inside
            yy = -0.18 + k * 0.12
            out.append(np.array([[-0.28 + abs(yy) * 0.25, yy + 0.06], [0.28 - abs(yy) * 0.25, yy - 0.06]]) * (1 - 0.5 * (k == 3)))
        return out
    if kind == "star":
        pts = []
        for k in range(11):
            a = -math.pi / 2 + k * math.pi / 5
            r = 0.5 if k % 2 == 0 else 0.21
            pts.append((r * math.cos(a), r * math.sin(a)))
        return [np.array(pts)]
    if kind == "sparkle":
        out = []
        for k in range(4):
            a = k * math.pi / 2
            out.append(np.array([[0.08 * math.cos(a), 0.08 * math.sin(a)], [0.46 * math.cos(a), 0.46 * math.sin(a)]]))
        for k in range(4):
            a = math.pi / 4 + k * math.pi / 2
            out.append(np.array([[0.1 * math.cos(a), 0.1 * math.sin(a)], [0.24 * math.cos(a), 0.24 * math.sin(a)]]))
        return out
    if kind == "squiggle":
        s = np.linspace(0, 1, 60)
        return [np.stack([s - 0.5, 0.13 * np.sin(s * 2 * math.pi * 2.5)], 1)]
    if kind == "crown":
        return [np.array([[-0.42, 0.22], [-0.46, -0.2], [-0.2, 0.02], [0.0, -0.3], [0.2, 0.02], [0.46, -0.2], [0.42, 0.22],
                          [-0.42, 0.22]]),
                np.array([[-0.38, 0.1], [0.38, 0.1]])]
    # arrow: a curved shaft and a head (pointing toward +x, rotated into place later)
    s = np.linspace(0, 1, 30)
    shaft = np.stack([s - 0.5, -0.18 * np.sin(s * math.pi)], 1)
    return [shaft, np.array([[0.3, -0.12], [0.5, 0.0], [0.32, 0.14]])]

def _sub(p, k):
    """The first fraction k of a polyline (by length)."""
    if k >= 1: return p
    if k <= 0 or len(p) < 2: return p[:1]
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    L = d[-1] * k
    j = int(np.searchsorted(d, L))
    j = clamp(j, 1, len(p) - 1)
    f = (L - d[j - 1]) / max(1e-6, d[j] - d[j - 1])
    return np.vstack([p[:j], p[j - 1] + (p[j] - p[j - 1]) * f])


# ------------------------------------------------------------------ chalk
def _grain(seed):
    g = noise(W, H, 2.2, seed) * 0.6 + noise(W, H, 7.0, seed + 1) * 0.4
    return g

def _chalk(mask_l, grain, ox, oy):
    """L mask -> chalky alpha (float32): broken, grainy edges. The grain shifts with each boil."""
    a = np.asarray(mask_l, np.float32) / 255
    g = np.roll(grain, (oy, ox), (0, 1))[:a.shape[0], :a.shape[1]]
    tex = np.clip((g - 0.22) / 0.2, 0, 1) * (0.72 + 0.28 * g)
    return a * tex


def render(c):
    st = c.state
    d, u = c.d, c.u
    boil = int(clamp(int(c.p.get("boil") or 3), 1, 12))
    step = c.i // boil
    col = hexc(c.p["color"]) if c.p.get("color") else (255, 255, 255)
    acc = hexc(c.p["accent"]) if c.p.get("accent") else tuple(c.skin.accent)
    lw = float(c.p.get("width", 7))
    if "items" not in st:
        (fx, fy, fw, fh), box = face_stats(c)
        ht = min(head_top(c, "_ht0"), fy - fh * 0.8)
        hr = max(fw, fh) * 0.62                                     # head radius, roughly
        hcx, hcy = fx, (ht + fy + fh * 0.5) / 2
        kinds = [k for k in (c.p.get("stickers") or []) if k in ("heart", "star", "sparkle", "squiggle", "crown", "arrow")][:8]
        # the hand-written word first: up beside the top of your head, on the roomier side
        word = c.p.get("word")
        word = key_word(c) if word is None else str(word)
        st["word"] = None
        taken = []
        if word:
            path = CHALK if c.p.get("font") == "chalk" else HAND
            im = text_img(word.lower(), 120, 400, (255, 255, 255), 0, path, 0)
            hx0, hx1 = fx - fw * 0.55, fx + fw * 0.55
            room_l, room_r = hx0 - 30, W - hx1 - 30
            side = 1 if room_r >= room_l else -1
            maxw = max(room_l, room_r, 200)
            s = min(1.0, maxw / im.width, 140 / im.height)
            im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
            wx = (hx1 + 10) if side > 0 else (hx0 - 10 - im.width)
            wx = clamp(wx, 30, W - 30 - im.width)
            wy = clamp(ht - im.height * 0.55, 240, 1400)
            st["word"] = dict(im=im, x=wx, y=wy, t=0.75, rot=-6 * side)
            taken.append((wx - 10, wy - 10, wx + im.width + 10, wy + im.height + 10))
        # doodles: the first free spot round your head (angle in degrees, distance in head radii) for each;
        # the crown sits on top of your head
        spots = [(-150, 1.5), (-32, 1.5), (-118, 1.9), (-62, 1.95), (180, 1.55), (0, 1.55), (-90, 2.3), (150, 1.75),
                 (-170, 1.9), (-12, 1.9), (30, 1.7)]
        items = []
        rng = np.random.default_rng(5)
        free = list(spots)
        def hits(bx):
            return any(not (bx[2] <= t[0] or t[2] <= bx[0] or bx[3] <= t[1] or t[3] <= bx[1]) for t in taken)
        for k, kind in enumerate(kinds):
            size = rng.uniform(95, 130) * clamp(fh / 370, 0.75, 1.3)
            rot = rng.uniform(-18, 18)
            if kind == "crown":
                size = clamp(fw * 0.5, 110, 220)
                x, y, rot = hcx, ht - size * 0.32, 0.0
            else:
                if kind == "arrow": size *= 1.5
                pick = None
                for a, r in free:
                    x = clamp(hcx + math.cos(math.radians(a)) * hr * r, 26 + size / 2, W - 26 - size / 2)
                    y = clamp(hcy + math.sin(math.radians(a)) * hr * r, 236 + size / 2, 1450 - size / 2)
                    bx = (x - size * 0.5, y - size * 0.5, x + size * 0.5, y + size * 0.5)
                    if not hits(bx): pick = (a, r, x, y); break
                if pick is None: continue
                free.remove(pick[:2]); x, y = pick[2], pick[3]
                if kind == "arrow":                    # points in at your head
                    rot = math.degrees(math.atan2(hcy - y, hcx - x))
            taken.append((x - size * 0.5, y - size * 0.5, x + size * 0.5, y + size * 0.5))
            items.append(dict(kind=kind, x=x, y=y, size=size, rot=rot, t=0.45 + 0.16 * len(items), seed=101 + 17 * k,
                              col=acc if k % 3 != 2 else col, ph=rng.uniform(0, 6.28)))
        st["items"] = items
        st["f0"] = (c.face[0], c.face[1])
        st["grain"] = _grain(7)
        st["cache"] = {}
    # timing: draw on, boil, wipe off
    t_in = 0.05
    draw_len = min(0.55, d * 0.22)
    er_len = min(0.4, d * 0.18)
    t_er = d - er_len
    pdraw = ease_io(prog(u, t_in, draw_len))
    perase = ease_in(prog(u, t_er, er_len))
    if pdraw <= 0 or perase >= 1: return c.img
    rng = np.random.default_rng(step * 7919 + 13)
    gox, goy = int(rng.integers(0, 64)), int(rng.integers(0, 64))
    lineL = Image.new("L", (W, H), 0)
    dl = ImageDraw.Draw(lineL)
    # the outline: retraced every boil step from where you are now
    key = ("ol", step)
    if key not in st["cache"]:
        st["cache"] = {k: v for k, v in st["cache"].items() if k[0] != "ol"}
        st["cache"][key] = _outline(c, float(c.p.get("offset", 22)))
    runs = st["cache"][key]
    for j, r in enumerate(runs):
        a = _boil(r, np.random.default_rng(step * 31 + j), 3.4)
        b = _boil(r, np.random.default_rng(step * 31 + j + 977), 4.2) + np.array([1.5, -2.0])
        for pts, wd, k0 in ((a, lw, 0.0), (b, lw * 0.55, 0.06)):
            # drawn on from one end, wiped off from the same end
            k_on = clamp((pdraw - k0) / (1 - k0), 0, 1)
            seg = _sub(pts, k_on)
            if perase > 0:
                n0 = int(len(seg) * perase)
                seg = seg[n0:]
            if len(seg) >= 2:
                dl.line([tuple(q) for q in seg.tolist()], fill=255, width=int(round(wd)), joint="curve")
    # doodles
    accL = Image.new("L", (W, H), 0)
    da = ImageDraw.Draw(accL)
    for it in st["items"]:
        p = prog(u, it["t"], 0.32)
        q = prog(u, t_er - 0.05 + 0.04 * st["items"].index(it) * 0, er_len)
        if p <= 0 or q >= 1: continue
        s = it["size"] * back(min(1, p * 1.15), 2.4) * (1 - ease_in(q))
        fdx, fdy = (c.face[0] - st["f0"][0]) * 0.85, (c.face[1] - st["f0"][1]) * 0.85     # doodles ride along with you
        wig = 9 * math.sin(2 * math.pi * 1.4 * u + it["ph"])        # wiggle
        rot = math.radians(it["rot"] + wig)
        bob = 4 * math.sin(2 * math.pi * 0.9 * u + it["ph"])
        rr = np.random.default_rng(it["seed"] * 1000 + step)
        shapes = _doodle(it["kind"], rr)
        drawL = da if it["col"] == acc else dl
        for sh in shapes:
            pts = sh * s
            if len(pts) > 2: pts = _resample(pts, 6.0) if len(pts) < 200 else pts
            pts = pts + rr.normal(0, 2.0, pts.shape)                 # boil
            ca, sa = math.cos(rot), math.sin(rot)
            pts = np.stack([pts[:, 0] * ca - pts[:, 1] * sa + it["x"] + fdx, pts[:, 0] * sa + pts[:, 1] * ca + it["y"] + bob + fdy], 1)
            seg = _sub(pts, ease_out(min(1, p * 1.4)))
            if len(seg) >= 2:
                drawL.line([tuple(v) for v in seg.tolist()], fill=255, width=int(round(lw * 0.85)), joint="curve")
    # the word, written on left to right, jittering with the boil
    wd_ = st["word"]
    wordL = None
    if wd_:
        p = prog(u, wd_["t"], 0.55)
        if p > 0:
            im = wd_["im"]
            jx, jy, jr = rng.normal(0, 1.4), rng.normal(0, 1.4), rng.normal(0, 0.6)
            a = np.asarray(im.getchannel("A"), np.float32)
            if p < 1:
                xs = np.arange(im.width, dtype=np.float32)
                a = a * np.clip((im.width * ease_io(p) - xs) / 14 + 0.5, 0, 1)[None, :]
            if perase > 0:
                xs = np.arange(im.width, dtype=np.float32)
                a = a * np.clip((xs - im.width * perase) / 14 + 0.5, 0, 1)[None, :]
            m = Image.fromarray(a.astype(np.uint8), "L").rotate(wd_["rot"] + jr, Image.BICUBIC, expand=True)
            wordL = Image.new("L", (W, H), 0)
            fdx, fdy = (c.face[0] - st["f0"][0]) * 0.85, (c.face[1] - st["f0"][1]) * 0.85
            wordL.paste(m, (int(wd_["x"] + fdx + jx - (m.width - im.width) / 2), int(wd_["y"] + fdy + jy - (m.height - im.height) / 2)))
    # chalk it: soften a hair, then the grain (which shifts every boil step)
    lineL = lineL.filter(ImageFilter.GaussianBlur(0.7))
    accL = accL.filter(ImageFilter.GaussianBlur(0.7))
    A1 = _chalk(lineL, st["grain"], gox, goy)
    A2 = _chalk(accL, st["grain"], goy, gox)
    if wordL is not None:
        A1 = np.maximum(A1, _chalk(wordL, st["grain"], gox + 17, goy + 5))
    base = f32(np.asarray(c.img))
    # a soft dark shadow under every stroke, so white chalk still reads on a white wall
    shl = Image.fromarray((np.maximum(A1, A2) * 255).astype(np.uint8), "L").resize((W // 2, H // 2), Image.BILINEAR)
    shl = shl.filter(ImageFilter.GaussianBlur(2.2)).resize((W, H), Image.BILINEAR)
    sh = np.roll(np.asarray(shl, np.float32) / 255, (5, 3), (0, 1))
    room = base * (1 - 0.5 * np.clip(sh * 1.6, 0, 1)[..., None])
    room = room * (1 - A1[..., None]) + np.array(col, np.float32) * A1[..., None]
    room = room * (1 - A2[..., None]) + np.array(acc, np.float32) * A2[..., None]
    return to_pil(mix(base, room, solid_mask(c)))

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the word is your key word; the doodles have no text",
    "needs": ["person"],
}
