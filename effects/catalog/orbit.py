"""Orbit: a ring of rounded thumbnail cards circles your head on a tilted 3D ellipse,
passing behind you at the back and in front of your chest at the front."""
import math
from PIL import Image, ImageFilter
from core import W, H, SS, place, rounded, scaled, comp, ease_out, ease_in, back, prog, lerp, clamp, clamp01
from catalog._b import stills, load_images, crop_fill, face_stats, behind

NAME = "orbit"
KIND = "behind"
ABOUT = "A ring of thumbnail cards orbits your head in 3D, behind you at the back, in front at the front"
DUR = 5.0
PARAMS = dict(
    images=None,     # list of image paths for the cards; default stills from this video at spread-out times
    count=10,        # how many cards (8-12 looks best)
    speed=1.0,       # turns per 7 seconds; negative spins the other way
    size=1.0,        # card size
    ring=True,       # draw the faint orbit line
    tilt=1.0,        # how tilted the ring is (1 = the front passes below your chin)
)
CW, CH = 196, 348       # card size at the front of the ring (9:16)


def _cards(c, n):
    imgs = load_images(c.p.get("images"), (CW * 2, CH * 2))
    if not imgs:
        raw = stills(c.subj, n, (360, 640))
        idx = [int(round((0.04 + 0.92 * k / max(1, n - 1)) * (c.subj.n - 1))) for k in range(n)]
        imgs = []
        for k, (im, i) in enumerate(zip(raw, idx)):
            fx, fy, fw, fh = c.subj.face(i)
            zoom, cy = [(1.0, 0.5), (2.3, fy / H), (1.45, (fy + fh * 0.6) / H)][k % 3]
            imgs.append(crop_fill(im, (CW * 2, CH * 2), fx / W, cy, zoom))
    while len(imgs) < n: imgs = imgs + imgs
    out = []
    for k in range(n):
        im = imgs[k].resize((CW, CH), Image.LANCZOS).convert("RGBA")
        s = SS(CW, CH)
        s.rr((1.5, 1.5, CW - 1.5, CH - 1.5), 20, outline=(255, 255, 255, 235), width=3)
        # a soft sheen across the top, like a glossy card
        for j in range(8):
            s.rr((4 + j * 2, 4 + j * 2, CW - 4 - j * 2, CH * 0.35 - j * 6), 18, fill=(255, 255, 255, 4))
        im.alpha_composite(s.out())
        sharp = rounded(im, 20)
        far = sharp.filter(ImageFilter.GaussianBlur(2.2))
        dark = Image.new("RGBA", far.size, (8, 9, 12, 255)); dark.putalpha(far.getchannel("A"))
        far = Image.blend(far, dark, 0.5)
        out.append((sharp, far))
    return out

def _ring_layers(a, b):
    """The orbit line: (back half, front half) RGBA images centred on the ellipse centre."""
    pad = 20
    w, h = int(2 * a + 2 * pad), int(2 * b + 2 * pad)
    halves = []
    for front in (False, True):
        s = SS(w, h)
        pts = []
        for i in range(181):
            t = math.pi * i / 180 if front else math.pi + math.pi * i / 180
            pts.append((w / 2 + a * math.cos(t), h / 2 + b * math.sin(t)))
        s.line(pts, (255, 255, 255, 110), 3)
        halves.append(s.out())
    return halves

def render(c):
    st = c.state
    n = int(clamp(int(c.p.get("count") or 10), 3, 16))
    if "cards" not in st:
        st["cards"] = _cards(c, n)
        (fx, fy, fw, fh), u = face_stats(c)
        st["a"] = max(fw * 1.2, W * 0.4)
        st["b"] = fh * 1.15 * float(c.p.get("tilt") or 1.0)
        st["fh"] = fh
        st["rings"] = _ring_layers(st["a"], st["b"]) if c.p.get("ring", True) else None
    cards = st["cards"]
    fx, fy, fw, fh = c.face
    ocx, ocy = fx, fy + 0.1 * st["fh"]
    d, u = c.d, c.u
    t_in = min(0.8, d * 0.3); t_out = min(0.6, d * 0.25)
    p_in = prog(u, 0, t_in); p_out = prog(u, d - t_out, t_out)
    # the ring sweeps in from outside the frame and settles (so it never crosses your face), and leaves the same way
    R = lerp(1.75, 1.0, ease_out(p_in)) - 0.05 * math.sin(math.pi * clamp01((p_in - 0.55) / 0.45)) + 0.8 * ease_in(p_out)
    A = ease_out(p_in * 1.7) * (1 - ease_in(p_out))
    grow = lerp(0.35, 1.0, back(p_in, 1.6)) * lerp(1.0, 0.6, ease_in(p_out))
    if A <= 0.002: return c.img
    w_ = 2 * math.pi / 7.0 * float(c.p.get("speed", 1.0))
    # spins in fast and settles to a steady turn; whips away at the end
    th0 = w_ * u + math.copysign(2.4, w_ or 1) * (1 - ease_out(p_in)) * -1 + math.copysign(2.0, w_ or 1) * ease_in(p_out)
    a, b = st["a"] * R, st["b"] * R
    sz = float(c.p.get("size") or 1.0)
    items = []
    for k in range(n):
        th = th0 + 2 * math.pi * k / n
        z = math.sin(th)                      # +1 front (closest), -1 back
        x = ocx + a * math.cos(th)
        y = ocy + b * z
        dep = (z + 1) / 2
        s = lerp(0.56, 1.0, dep) * grow * sz
        ry = -math.cos(th) * 38
        items.append((z, k, x, y, s, ry, dep))
    items.sort()
    back_cv, front_cv = c.canvas(), c.canvas()
    if st["rings"]:
        rb, rf = st["rings"]
        if R < 0.999: rb, rf = scaled(rb, R), scaled(rf, R)
        al = A * 0.9
        for im, cv in ((rb, back_cv), (rf, front_cv)):
            if al < 0.999:
                im = im.copy(); im.putalpha(im.getchannel("A").point(lambda v: int(v * al)))
            comp(cv, im, ocx - im.width / 2, ocy - im.height / 2)
    for z, k, x, y, s, ry, dep in items:
        sharp, far = cards[k]
        # each card arrives a beat after the one before it
        ak = A * ease_out(prog(u, k * min(0.04, t_in * 0.4 / n), t_in * 0.6))
        if ak <= 0.003: continue
        im = Image.blend(far, sharp, clamp01(dep * 1.15)) if dep < 0.87 else sharp
        cv = front_cv if z >= 0 else back_cv
        place(cv, im, x, y, s=s, ry=ry, rx=-6 * z, shadow=0.22 + 0.18 * dep, a=ak)
    img = behind(c, back_cv)
    return c.front(front_cv, img)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the cards are stills from this same clip; no text",
    "needs": ["face"],
}
