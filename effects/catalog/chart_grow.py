"""Chart grow: a glowing line chart draws itself across the room behind you (you stay in front). Faint grid lines come
in, the line draws left to right, each data point pops with a soft glow halo as the line reaches it, and the last
point lights up in the accent colour with a vertical guide line. With no values it's a decorative rising curve."""
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from core import W, H, FPS, SS, font, SFMONO, ease_out, ease_io, ease_in, back, prog, lerp, clamp, clamp01, hexc
from ._ui import phases, seeded
from ._ui2 import faces_in, head_top_low

NAME = "chart-grow"
KIND = "behind"
ABOUT = "A glowing line chart draws itself across the room behind you, the last point lit up"
DUR = 4.5
PARAMS = dict(
    values=None,      # real numbers to plot, in order, e.g. [231, 226, 222, 219]; scaled to fit. None: a decorative
                      #   rising curve (decorative, not data): no numbers, no labels.
    labels=None,      # a short label under each point, e.g. ["Jun", "Jul", "Aug", "Sep"] (only with values)
    unit=None,        # added after the last value in its callout, e.g. "lb"
    callout=True,     # the last value in a pill by its point (only with values)
    color=None,       # line colour; default the skin's accent
    dim=0.28,         # how much the room darkens behind the chart (0-0.6) so the glow reads
    grid=5,           # horizontal grid lines
)
X0, X1, TOP = 64, 1016, 268

def _decorative(seed):
    rng = np.random.default_rng(seed)
    n = 7
    u = np.linspace(0, 1, n)
    v = 0.06 + 0.86 * u ** 1.3 + rng.uniform(-0.06, 0.06, n) * np.sin(np.pi * u)
    v[0], v[-1] = 0.07, 0.94
    for i in range(1, n - 1):   # a gentle dip or two, but always heading up
        v[i] = clamp(v[i], v[i - 1] - 0.08, v[-1] - 0.05)
    return list(v)

def _setup(c):
    fs = faces_in(c)
    fh = float(np.median(fs[:, 3]))
    bottom = clamp(head_top_low(c) + 0.3 * fh, TOP + 320, 1100)     # mostly the room above and beside your head
    vals = c.p.get("values")
    real = isinstance(vals, (list, tuple)) and len(vals) > 0
    if real:
        vals = [float(v) for v in vals]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9: lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.14
        norm = [(v - lo + pad) / (hi - lo + 2 * pad) for v in vals]
    else:
        norm = _decorative(seeded(c.subj.dir) ^ int(c.t0 * 100))
    n = len(norm)
    xl, xr = X0 + 34, X1 - 56
    xs = [lerp(xl, xr, i / max(1, n - 1)) for i in range(n)] if n > 1 else [(xl + xr) / 2]
    ys = [lerp(bottom - 10, TOP + 30, v) for v in norm]
    pts = list(zip(xs, ys))
    dense = _spline(pts) if n > 1 else pts
    seg = [math.dist(a, b) for a, b in zip(dense, dense[1:])]
    cum = np.concatenate([[0], np.cumsum(seg)]) if seg else np.zeros(1)
    total = float(cum[-1]) or 1.0
    # where each data point sits along the line (0-1)
    at = []
    for p in pts:
        j = int(np.argmin([math.dist(p, q) for q in dense]))
        at.append(float(cum[j]) / total)
    tin, tout = min(0.5, c.d * 0.25), min(0.45, c.d * 0.22)
    t_a = c.t0 + min(0.35, c.d * 0.12)
    t_b = t_a + clamp(c.d * 0.5, 0.8, min(3.0, max(0.8, c.d - tout - 0.7 - (t_a - c.t0))))
    col = hexc(c.p["color"]) if c.p.get("color") else tuple(c.skin.accent)
    labels = [str(l) for l in (c.p.get("labels") or [])] if real else []
    lab = None
    if real and c.p.get("callout", True):
        v = vals[-1]
        txt = f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}"
        if c.p.get("unit"): txt += f" {c.p['unit']}"
        lab = txt
    ry0, ry1 = int(max(0, TOP - 150)), int(min(H, bottom + 150))
    return dict(pts=pts, dense=dense, cum=cum, total=total, at=at, bottom=bottom, tin=tin, tout=tout, t_a=t_a, t_b=t_b,
                col=col, labels=labels, callout=lab, ry0=ry0, ry1=ry1, real=real, grid=_grid(c, bottom, ry0, ry1, xs))

def _spline(pts, k=28):
    """Catmull-Rom through pts, k samples per segment (no overshoot past the ends)."""
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = (np.array(P[j], float) for j in (i - 1, i, i + 1, i + 2))
        for s in range(k):
            u = s / k
            q = 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)
            out.append((float(q[0]), float(q[1])))
    out.append(tuple(pts[-1]))
    return out

def _grid(c, bottom, ry0, ry1, xs):
    """Faint grid (RGBA, rows ry0..ry1): horizontal lines across, a baseline, short ticks."""
    n = max(2, int(c.p.get("grid") or 5))
    s = SS(W, ry1 - ry0)
    for k in range(n):
        y = lerp(TOP, bottom, k / (n - 1)) - ry0
        a = 96 if k == n - 1 else 52
        s.line([(X0, y), (X1, y)], (255, 255, 255, a), 1.8 if k == n - 1 else 1.3, round_caps=False)
    for x in xs:
        s.line([(x, TOP - ry0), (x, bottom - ry0)], (255, 255, 255, 22), 1.2, round_caps=False)
    return s.out()

def _point_at(L, f):
    """(x, y) at fraction f along the line, and the index of the last dense vertex before it."""
    d = f * L["total"]
    cum, dense = L["cum"], L["dense"]
    j = int(np.searchsorted(cum, d, side="right")) - 1
    j = clamp(j, 0, len(dense) - 2) if len(dense) > 1 else 0
    if len(dense) < 2: return dense[0], 0
    seg = cum[j + 1] - cum[j]
    u = (d - cum[j]) / seg if seg > 0 else 0
    a, b = dense[j], dense[j + 1]
    return (lerp(a[0], b[0], u), lerp(a[1], b[1], u)), j

def render(c):
    st = c.state
    if "L" not in st: st["L"] = _setup(c)
    L = st["L"]
    ui, uo = phases(c, L["tin"], L["tout"])
    if ui <= 0 or uo >= 1: return c.img
    t = c.t
    env = min(ease_out(ui), 1 - ease_out(uo))
    col = L["col"]
    ry0, ry1 = L["ry0"], L["ry1"]
    rh = ry1 - ry0
    lift = -ease_in(uo) * 40
    # line progress (eased), and the grid's wipe-in
    p = ease_io(prog(t, L["t_a"], L["t_b"] - L["t_a"]))
    gw = ease_out(prog(c.u, 0, L["tin"] + 0.3))
    layer = Image.new("RGBA", (W, rh), (0, 0, 0, 0))
    # grid, wiped in from the left
    g = L["grid"]
    xw = int(X0 + (X1 - X0) * gw)
    if xw > X0:
        gc = g.crop((0, 0, min(W, xw + 40), rh))
        ga = np.asarray(gc.getchannel("A"), np.float32)
        ramp = np.clip((xw + 40 - np.arange(gc.width)) / 80.0, 0, 1)
        gc.putalpha(Image.fromarray((ga * ramp[None, :]).astype(np.uint8), "L"))
        layer.alpha_composite(gc, (0, 0))
    dense = L["dense"]
    pts = L["pts"]
    s = SS(W, rh)
    head = None
    drawn = []
    if p > 0 and len(dense) > 1:
        hp, j = _point_at(L, p)
        drawn = [(x, y - ry0) for x, y in dense[:j + 1]] + [(hp[0], hp[1] - ry0)]
        head = (hp[0], hp[1] - ry0)
    # area under the drawn line: a soft gradient of the line colour
    if len(drawn) > 1:
        q = 2
        m = Image.new("L", (W // q, rh // q), 0)
        poly = [(x / q, y / q) for x, y in drawn] + [(drawn[-1][0] / q, (L["bottom"] - ry0) / q), (drawn[0][0] / q, (L["bottom"] - ry0) / q)]
        ImageDraw.Draw(m).polygon(poly, fill=255)
        m = m.resize((W, rh), Image.BILINEAR)
        yy = np.arange(rh, dtype=np.float32)
        top_y = min(y for _, y in drawn)
        grad = np.clip(1 - (yy - top_y) / max(1.0, (L["bottom"] - ry0) - top_y), 0, 1) ** 1.5 * 0.26
        a = (np.asarray(m, np.float32) * grad[:, None]).astype(np.uint8)
        area = Image.new("RGBA", (W, rh), col + (0,)); area.putalpha(Image.fromarray(a, "L"))
        layer.alpha_composite(area)
    # glow: the line and points, thick and blurred at quarter size
    q = 4
    gl = Image.new("RGBA", (W // q, rh // q), col + (0,))
    gd = ImageDraw.Draw(gl)
    if len(drawn) > 1:
        gd.line([(x / q, y / q) for x, y in drawn], fill=col + (235,), width=5, joint="curve")
    pops = []
    for k, (pt, f) in enumerate(zip(pts, L["at"])):
        t_hit = L["t_a"] + (L["t_b"] - L["t_a"]) * _inv_ease(f)
        if t >= t_hit:
            pops.append((k, pt, t_hit))
    last = len(pts) - 1
    for k, pt, th in pops:
        halo = decay_pulse(t, th) + (0.55 + 0.25 * math.sin(2 * math.pi * 0.9 * (t - th)) if k == last else 0.0)
        r = (9 if k != last else 15) + 10 * decay_pulse(t, th)
        gd.ellipse(((pt[0]) / q - r / q * 2, (pt[1] - ry0) / q - r / q * 2, pt[0] / q + r / q * 2, (pt[1] - ry0) / q + r / q * 2),
                   fill=col + (int(255 * clamp01(0.35 + 0.5 * halo)),))
    wide = gl.filter(ImageFilter.GaussianBlur(11))
    gl = gl.filter(ImageFilter.GaussianBlur(3.5))
    wide.alpha_composite(gl)
    layer.alpha_composite(wide.resize((W, rh), Image.BILINEAR))
    # the line itself, crisp
    if len(drawn) > 1:
        s.line(drawn, col + (255,), 5.5)
        s.line(drawn, (255, 255, 255, 120), 1.6)
    # last point's vertical guide (dashed), once the line reaches it
    done_t = L["t_b"]
    gk = ease_out(prog(t, done_t - 0.05, 0.45))
    lx, ly = pts[last][0], pts[last][1] - ry0
    if gk > 0:
        yb = L["bottom"] - ry0
        y_end = ly + (yb - ly) * gk
        y = ly + 20
        while y < y_end:
            s.line([(lx, y), (lx, min(y + 10, y_end))], col + (190,), 2.2, round_caps=False)
            y += 18
    # points: pop with overshoot as the line passes
    for k, pt, th in pops:
        e = back(prog(t, th, 0.35), 2.2)
        if e <= 0: continue
        x, y = pt[0], pt[1] - ry0
        if k == last:
            r = 13 * e
            s.circ(x, y, r + 4, fill=(255, 255, 255, 235))
            s.circ(x, y, r, fill=col + (255,))
        else:
            s.circ(x, y, 8 * e, fill=col + (255,))
            s.circ(x, y, 4.2 * e, fill=(255, 255, 255, 255))
    if head is not None and p < 0.999:
        s.circ(head[0], head[1], 7, fill=(255, 255, 255, 255))
    over = s.out()
    layer.alpha_composite(over)
    # labels under points, and the last value's callout (only with real values)
    if L["real"]:
        tl = ImageDraw.Draw(layer)
        if L["labels"]:
            f = font(24, 620)
            for k, pt, th in pops:
                if k < len(L["labels"]):
                    a = ease_out(prog(t, th + 0.05, 0.3))
                    tl.text((pt[0], pt[1] - ry0 + 22), L["labels"][k], font=f, fill=(255, 255, 255, int(200 * a)), anchor="ma")
        if L["callout"]:
            ck = back(prog(t, done_t + 0.05, 0.4), 1.8)
            if ck > 0:
                f = font(36, 760)
                tw = f.getlength(L["callout"])
                bw, bh = tw + 40, 58
                cs = SS(int(bw) + 4, bh + 4)
                cs.rr((2, 2, bw + 2, bh + 2), bh / 2, fill=col + (255,))
                cs.text(((bw + 4) / 2, (bh + 4) / 2 + 1), L["callout"], 36, 760, fill=tuple(c.skin.accent_ink) + (255,), anchor="mm")
                pill = cs.out()
                if ck < 0.999:
                    pill = pill.resize((max(1, int(pill.width * ck)), max(1, int(pill.height * ck))), Image.BICUBIC)
                px = clamp(lx - pill.width - 26, 20, W - pill.width - 20)
                py = clamp(ly - pill.height - 18, 0, rh - pill.height)
                layer.alpha_composite(pill, (int(px), int(py)))
    # composite behind you: the room dims a little under the chart, then the chart, then you
    fr = np.asarray(c.img, np.uint8)
    out = fr.copy()
    oy = int(round(lift))
    y0, y1 = max(0, ry0 + oy), min(H, ry1 + oy)
    if y1 > y0:
        la = np.asarray(layer, np.float32)[y0 - ry0 - oy:y1 - ry0 - oy]
        room = fr[y0:y1].astype(np.float32)
        yy = np.arange(y0, y1, dtype=np.float32)
        dz = float(c.p.get("dim") or 0) * env
        dimr = 1 - dz * np.clip(np.minimum((yy - (TOP - 140)) / 140, ((L["bottom"] + 140) - yy) / 140), 0, 1)
        room = room * dimr[:, None, None]
        a = la[..., 3:4] / 255.0 * env
        comp = room * (1 - a) + la[..., :3] * a
        m = c.mask[y0:y1, :, None]
        out[y0:y1] = np.clip(fr[y0:y1] * m + comp * (1 - m), 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")

def decay_pulse(t, th, k=3.5):
    return math.exp(-(t - th) * k) if t >= th else 0.0

def _inv_ease(f):
    """The progress u at which ease_io(u) = f (so a point pops exactly when the line reaches it)."""
    lo, hi = 0.0, 1.0
    for _ in range(30):
        mid = (lo + hi) / 2
        if ease_io(mid) < f: lo = mid
        else: hi = mid
    return (lo + hi) / 2

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "a decorative rising curve: no numbers and no labels (no values given)",
}
