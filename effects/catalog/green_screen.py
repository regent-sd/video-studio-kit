"""Green screen: the creator layout. You're cut out and set low in the frame (head and shoulders in the bottom half) over
a dark, softly lit backdrop, with a rounded card above you playing other footage (a moment of this video, or any image
or video you give it). A light rim on your outline and a soft shadow behind you sit you in the new scene. It wipes in
from the normal frame and wipes back out at the end. layout "full": the footage fills the frame behind you instead."""
import math
import numpy as np
from PIL import Image, ImageFilter
from core import (W, H, FPS, f32, to_pil, ease_io, back, prog, lerp, clamp, clamp01, hexc, soft_shadow, comp, vignette)
from catalog._cam import room, tighten, blur, pil
from catalog._b import face_stats, solid_mask
from catalog._cam2 import (move_layer, rr_sdf, place_map, edge_fade, soft, shift, rim, head_top_px, media_path,
                           media_size, Reader, load_still, cover)

NAME = "green-screen"
KIND = "behind"
ABOUT = "Creator green-screen layout: you cut out low in frame over a dark backdrop, a card of other footage above you"
DUR = 5.0
PARAMS = dict(
    media=None,       # an image or video for the card (a path; a relative one starts in the content folder); default this video
    at=None,          # seconds into the media (or this video) to show; default the start of this video
    live=True,        # True: the card plays from `at`; False: it holds a still
    layout="bottom",  # bottom: you sit low with the card above you | full: the footage fills the frame behind you, you stay as you are
    color=None,       # backdrop colour; default the skin's dark colours with a soft glow of its accent
    size=0.7,         # your size in the bottom layout (share of full size; made smaller if your head would rise past the middle)
    rim=0.55,         # light on your outline (0 = off)
)
CARD_TOP, CARD_W, CARD_R = 228, 944, 38

def _setup(c):
    p, subj = c.p, c.subj
    (fx, fy, fw, fh), _ = face_stats(c)
    ht = head_top_px(c, (fx, fy, fw, fh))
    full = str(p.get("layout", "bottom")).lower() == "full"
    sp = 1.0 if full else clamp(min(float(p["size"]), H * 0.52 / max(1.0, H - ht)), 0.35, 1.0)
    land_x = fx if full else W / 2
    head_s = H - (H - ht) * sp
    mp = media_path(p.get("media"))
    own = mp is None
    if own:
        path = subj.base
        at = float(p["at"]) if p.get("at") is not None else (0.0 if c.t0 > 1.0 else subj.dur / 2)
        msz, mcx, mcy = (W, H), fx / W, clamp(fy / H + 0.05, 0, 1)
    else:
        path, at = mp, float(p.get("at") or 0.0)
        msz, mcx, mcy = media_size(mp), 0.5, 0.5
    if full:
        box, size = (0, 0, W, H), (W, H)
    else:
        aspect = msz[0] / max(1, msz[1])
        avail = head_s + 70 - CARD_TOP
        ch = min(avail, CARD_W / clamp(aspect, 1.0, 2.2)) if aspect >= 1 else min(avail, CARD_W * 1.25)
        y0 = CARD_TOP + max(0.0, (avail - ch) * 0.35)
        ch = int(ch) // 2 * 2
        box = (W / 2 - CARD_W / 2, y0, W / 2 + CARD_W / 2, y0 + ch)
        size = (CARD_W // 2 * 2, ch)
    live = bool(p.get("live", True)) and (own or mp.lower().endswith(tuple(
        e for e in (".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts"))))
    n = int(math.ceil(c.d * FPS)) + 2
    src = Reader(path, at, size, mcx, mcy, n=n) if live else None
    still = None if live else (load_still(path, size, mcx, mcy) if not own else
                               Reader(path, at, size, mcx, mcy, n=1).get(0))
    return dict(fx=fx, sp=sp, land_x=land_x, head_s=head_s, full=full, box=box, size=size, src=src, still=still,
                fade=edge_fade((H, W), 70, "lrt"))

def _backdrop(c, S):
    """Dark gradient with soft light: the skin's dark colours (or the colour setting), an accent glow behind you."""
    p, sk = c.p, c.skin
    if p.get("color"):
        base = np.array(hexc(p["color"]), np.float32)
        top, bot, glow = base, base * 0.3, np.minimum(255, base * 1.6 + 30)
    else:
        top = np.array(sk.dark2, np.float32) * 1.25
        bot = np.array(sk.dark, np.float32) * 0.8
        glow = np.array(sk.accent, np.float32)
    q = 4
    h, w = H // q, W // q
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    col = top * (1 - y) + bot * y
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    hy = (S["head_s"] + 160) / q
    g1 = np.exp(-(((xx - w / 2) / (w * 0.55)) ** 2 + ((yy - hy) / (h * 0.2)) ** 2))[..., None]
    by = (S["box"][1] + S["box"][3]) / 2 / q
    g2 = np.exp(-(((xx - w / 2) / (w * 0.6)) ** 2 + ((yy - by) / (h * 0.16)) ** 2))[..., None]
    warm = np.array([235, 226, 214], np.float32) * 0.85 + glow * 0.15     # a soft studio light, a hint of accent
    col = col + g1 * warm * 0.11 + g2 * np.array([150, 160, 190], np.float32) * 0.07
    big = np.asarray(pil(col).resize((W, H), Image.BICUBIC), np.float32)
    rng = np.random.default_rng(3)
    big = big + rng.normal(0, 1.6, (H, W, 1)).astype(np.float32)          # fine grain: no banding
    return np.clip(big, 0, 255)

def _card(c, S, img, k):
    """The card as RGBA (rounded, a hairline of light round the edge) with its shadow, or None."""
    w, h = S["size"]
    im = (img if img.size == (w, h) else img.resize((w, h), Image.BILINEAR)).convert("RGBA")
    sd, org = rr_sdf((0, 0, w, h), CARD_R, pad=0, shape=(h, w))
    a = np.clip(0.5 - sd, 0, 1)
    ring = a * np.clip(sd + 2.4, 0, 1)
    arr = np.asarray(im, np.float32).copy()
    arr[..., :3] = arr[..., :3] + (255 - arr[..., :3]) * ring[..., None] * 0.55
    arr[..., 3] = a * 255
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")

def render(c):
    p, st = c.p, c.state
    d, u = c.d, c.u
    t_in = clamp(0.18 * d, 0.32, 0.6); t_out = clamp(0.15 * d, 0.3, 0.55)
    e = min(ease_io(prog(u, 0, t_in)), 1 - ease_io(prog(u, d - t_out, t_out)))
    if e < 1e-3:
        return c.img
    if "S" not in st:
        st["S"] = _setup(c)
    S = st["S"]
    img = f32(np.asarray(c.img))
    k_frame = int(round(u * FPS))
    media = S["src"].get(k_frame) if S["src"] is not None else S["still"]
    # the new scene
    if S["full"]:
        scene = f32(np.asarray(media))
        scene = blur(scene, 2.2) * 0.8 * vignette(0.55, 0.9, 0.45)[..., None]
    else:
        if "bg" not in st: st["bg"] = _backdrop(c, S)
        scene = st["bg"].copy()
    # you: scaled about the bottom under your face and moved to the middle
    m = solid_mask(c)
    sp = lerp(1.0, S["sp"], e)
    lx = lerp(S["fx"], S["land_x"], e)
    a_src = tighten(m, 0.12) * (S["fade"] if S["sp"] < 0.999 else 1.0)
    prgb, pa = move_layer(c.img, a_src, sp, S["fx"], H, lx, H)
    # soft shadow behind you on the backdrop and the card
    sh = shift(soft(pa, 26), 0, 30) * 0.55
    # the card, popping in a beat after the wipe and out a beat before it
    if not S["full"]:
        kc = min(back(prog(u, t_in * 0.45, t_in * 0.8), 1.4), 1 - ease_io(prog(u, d - t_out * 1.05, t_out * 0.6)))
        if kc > 1e-3:
            x0, y0, x1, y1 = S["box"]
            card = _card(c, S, media, kc)
            s = 0.82 + 0.18 * kc
            fx_now = c.face[0]
            dx = -(fx_now - S["fx"]) * 0.05 + 6 * math.sin(u * 0.7)       # a little parallax and drift
            dy = 5 * math.sin(u * 0.9 + 1.0) + (1 - kc) * 40
            cw, ch = card.size
            el = card.resize((max(1, int(cw * s)), max(1, int(ch * s))), Image.BILINEAR) if s < 0.999 else card
            al = min(1.0, kc * 2.5)
            if al < 0.999: el.putalpha(el.getchannel("A").point(lambda v: int(v * al)))
            cxc, cyc = (x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            comp(lay, soft_shadow(el, 0.6 * al, 16, pad=90, q=4), cxc - el.width / 2 - 90, cyc - el.height / 2 - 90 + 22)
            comp(lay, el, cxc - el.width / 2, cyc - el.height / 2)
            L = np.asarray(lay, np.float32)
            la = L[..., 3:4] / 255
            scene = scene * (1 - la) + L[..., :3] * la
    scene = scene * (1 - sh[..., None])
    # a dark floor at the bottom, so the edge of the picture under you melts away
    if not S["full"]:
        if "floor" not in st:
            yy = np.arange(H, dtype=np.float32)
            st["floor"] = (np.clip((yy - H * 0.8) / (H * 0.2), 0, 1) ** 1.5 * 0.7)[:, None, None]
        scene = scene * (1 - st["floor"])
    # wipe: the new scene sweeps down over the room (and back up at the end), a thin light line on its edge
    if e < 0.999:
        old, _ = room(c, img, m, grow_px=24, feather=24, dim=0.25, soften=6)
        if "xs" not in st: st["xs"] = (np.arange(W, dtype=np.float32) - W / 2)[None, :] * 0.22
        pos = lerp(-300, H + 300, e)
        dist = pos + st["xs"] - np.arange(H, dtype=np.float32)[:, None]        # > 0: wiped (new scene)
        wm = np.clip(dist / 26 + 0.5, 0, 1)
        bgm = old * (1 - wm[..., None]) + scene * wm[..., None]
        line = np.exp(-(dist / 5.0) ** 2) + 0.35 * np.exp(-(dist / 22.0) ** 2)
        lc = np.array(c.skin.accent, np.float32) * 0.5 + 127
        bgm = bgm + line[..., None] * lc * 0.8 * math.sin(math.pi * e)
    else:
        bgm = scene
    # you, with a light rim and a hair darker, so you sit in the darker scene
    if float(p["rim"]) > 0:
        rl = rim(pa, 7.0, 0.6) * float(p["rim"]) * e
        rc = np.array(c.skin.accent, np.float32) * 0.3 + 255 * 0.7
        prgb = prgb * (1 - 0.06 * e) + (rc - prgb * (1 - 0.06 * e)) * (rl[..., None] * 0.7)
    out = bgm * (1 - pa[..., None]) + prgb * pa[..., None]
    k = clamp01(e * 12)
    if k < 1: out = out * k + img * (1 - k)
    if S["src"] is not None and u >= d - 1.0 / FPS: S["src"].close()
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen; the card plays another clip from the footage folder",
    "still": 0.5,
    "needs": ["person", "other_clip"],
}
