"""Frame break: the shot shrinks into a rounded portrait card floating over a blurred, darkened copy of itself, tilted a
little in 3D. Then you break out of the frame: you grow a touch and your head and shoulders come out past the card's
edges, in front of its rim and the backdrop. At the end you settle back in and the card opens back to full frame."""
import math
import numpy as np
from PIL import Image
from core import W, H, f32, ease_io, back, prog, lerp, clamp, clamp01, vignette, warp_to, soft_shadow, comp
from catalog._cam import room, tighten, affine, pil, blur
from catalog._b import face_stats, solid_mask
from catalog._cam2 import rr_sdf, place_map, edge_fade, soft, shift, tilt_pts

NAME = "frame-break"
KIND = "camera"
ABOUT = "The shot shrinks into a floating 3D card, then you break out of it: head and shoulders in front of its edges"
DUR = 4.0
PARAMS = dict(
    size=0.74,        # card size while you're out of it (share of full size; made smaller if your head would leave the frame)
    pop=0.18,         # how much bigger you get as you break out (0.18 = 18 %)
    headroom=0.06,    # space above your head inside the card, in face-heights (smaller = more of you comes out)
    width=0.92,       # card width, as a share of the frame's width (narrower = your shoulders come out the sides too)
    tilt=7,           # 3D tilt of the card (degrees; 0 = flat)
    radius=46,        # card corner radius (px)
    rim=0.7,          # thin light rim round the card (0 = off)
    dim=0.45,         # how dark the blurred backdrop gets (0-1)
    blur=30,          # backdrop blur (px)
)

def _curves(c):
    """e: the card (0 = full frame, 1 = floating card); pp: the break-out (0 = inside, 1 = out, overshoots a little)."""
    d, u = c.d, c.u
    t_in = clamp(0.2 * d, 0.24, 0.62)
    t_out = clamp(0.17 * d, 0.22, 0.55)
    e = min(ease_io(prog(u, 0, t_in)), 1 - ease_io(prog(u, d - t_out, t_out)))
    t_pop = clamp(0.15 * d, 0.2, 0.46)
    pin = prog(u, t_in * 0.7, t_pop)
    pp = back(pin, 1.5) if pin < 1 else 1.0
    pout = prog(u, d - t_out - t_pop * 0.75, t_pop * 0.85)
    pp = min(pp, 1 - ease_io(pout))
    return e, max(0.0, pp)

def _layout(c):
    """The card and the break-out, worked out once from the face over the whole window."""
    p = c.p
    (fx, fy, fw, fh), _ = face_stats(c)
    # top of the head from the cutout above the face (first frame), else from the face box
    x0_, x1_ = int(clamp(fx - fw * 0.2, 0, W - 2)), int(clamp(fx + fw * 0.2, 1, W - 1))
    ys = int(clamp(fy - fh * 1.6, 0, H - 2)); ye = int(clamp(fy, ys + 1, H))
    rows = np.where((c.mask[ys:ye, x0_:x1_] > 0.5).any(1))[0]
    ht = ys + rows[0] if len(rows) else fy - fh * 0.9
    if abs(ht - (fy - fh * 0.9)) > fh * 0.5: ht = fy - fh * 0.9
    pop = max(0.0, float(p["pop"]))
    y0 = clamp(ht - float(p["headroom"]) * fh, 0, H * 0.62)
    ch = H - y0
    cw = min(W * clamp(float(p["width"]), 0.3, 1.0), ch * 0.8)
    x0 = clamp(fx - cw / 2, 0, W - cw)
    ax = clamp(fx, x0 + cw * 0.3, x0 + cw * 0.7)            # break-out anchor: under the face, on the bottom edge
    top_pop = H - (H - ht) * (1 + pop * 1.08)                  # head top at the overshoot
    ext = H - min(y0, top_pop)                                 # source px from the highest point to the bottom
    s = min(float(p["size"]), H * 0.8 / ext, W * 0.9 / cw)
    top = (H - ext * s) / 2 + H * 0.015                       # centre the whole thing, a hair low
    Y1 = top + ext * s                                         # card bottom on screen
    # below the shoulders you stay inside the card (only head and shoulders come out)
    line = min(H - fh * 0.3, fy + fh * 1.35)
    return dict(crop=(x0, y0, x0 + cw, H), s=s, Y1=Y1, ax=ax, pop=pop, line=line)

def _backdrop(c, e):
    """The frame, blurred and darkened (worked at 1/8 size, then scaled up)."""
    p, st = c.p, c.state
    q = 8
    sm = c.img.resize((W // q, H // q), Image.BOX)
    from PIL import ImageFilter
    sm = np.asarray(sm.filter(ImageFilter.GaussianBlur(float(p["blur"]) / q)), np.float32)
    if "vig" not in st:
        st["vig"] = np.asarray(Image.fromarray((vignette(0.75, 0.9, 0.48) * 255).astype(np.uint8), "L")
                               .resize((W // q, H // q), Image.BOX), np.float32)[..., None] / 255
    k = 1 - float(p["dim"]) * e
    sm = sm * k * (1 - (1 - st["vig"]) * e)
    return pil(sm).resize((W, H), Image.BILINEAR)

def _rgba(rgb, a):
    """PIL RGB + float alpha (0-1) -> PIL RGBA."""
    im = rgb.convert("RGBA")
    im.putalpha(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "L"))
    return im

def render(c):
    p, st = c.p, c.state
    e, pp = _curves(c)
    if e < 1e-3:
        return c.img
    if "lay" not in st:
        st["lay"] = _layout(c)
        st["fade"] = edge_fade((H, W), 36, "lrt")
    L = st["lay"]
    x0, y0, x1, y1 = L["crop"]
    # source -> screen: scale se about the crop's bottom middle P, landing on the card's bottom middle Q
    se = lerp(1.0, L["s"], e)
    P = (lerp(W / 2, (x0 + x1) / 2, e), H)
    Q = (W / 2, lerp(H, L["Y1"], e))
    sx = lambda x: (x - P[0]) * se + Q[0]
    sy = lambda y: (y - P[1]) * se + Q[1]
    box = (sx(lerp(0, x0, e)), sy(lerp(0, y0, e)), sx(lerp(W, x1, e)), sy(H))
    r = float(p["radius"]) * e
    sd, org = rr_sdf(box, r)
    ca = place_map(np.clip(0.5 - sd, 0, 1), org)
    # the card: the room (you taken out once you start to come forward), scaled into place
    m = solid_mask(c)
    if pp > 1e-3:
        content, _ = room(c, None, m, grow_px=22, feather=22, dim=0.2, soften=6)
        content = pil(content)
    else:
        content = c.img
    card = _rgba(affine(content, se, P[0], P[1], Q[0], Q[1]), ca)
    # you: grown by kp about the anchor on the card's bottom edge
    kp = 1 + L["pop"] * pp
    ax = L["ax"]
    a_src = tighten(m, 0.1) * st["fade"]
    you = Image.fromarray(np.dstack([np.asarray(c.img), (a_src * 255).astype(np.uint8)]), "RGBA").convert("RGBa")
    you = affine(you, se * kp, ax, H, sx(ax), sy(H)).convert("RGBA")
    pa = np.asarray(you.getchannel("A"), np.float32) / 255
    # outside the card you show only down to your shoulders (fading out below them)
    ly = sy((L["line"] - H) * kp + H)
    above = np.clip((ly - np.arange(H, dtype=np.float32)) / 110.0, 0, 1)[:, None]
    above = above * above * (3 - 2 * above) * clamp01(pp * 3)
    pa = pa * np.maximum(ca, above)
    you.putalpha(Image.fromarray((pa * 255).astype(np.uint8), "L"))
    # you cast a soft shadow on the card as you come out of it
    if pp > 1e-3:
        sh = shift(soft(pa, 16), 8 * se, 18 * se) * ca * 0.42 * clamp01(pp)
        card.alpha_composite(_rgba(Image.new("RGB", (W, H), (0, 0, 0)), sh))
    # the rim: a thin line of light just inside the edge, a little brighter along the top
    if float(p["rim"]) > 0:
        ring_part = np.clip(0.5 - sd, 0, 1) * np.clip(sd + 3.1, 0, 1)
        Y0 = org[1]
        glint = 0.75 + 0.5 * np.clip(1 - (np.arange(sd.shape[0], dtype=np.float32) + Y0 - box[1]) / 260.0, 0, 1)[:, None]
        ring = place_map(ring_part * glint, org) * float(p["rim"]) * 0.8 * e
        card.alpha_composite(_rgba(Image.new("RGB", (W, H), (255, 255, 255)), ring))
    card.alpha_composite(you)
    bg = _backdrop(c, e).convert("RGBA")
    ry = -float(p["tilt"]) * e * (0.72 + 0.28 * math.sin(c.u * 1.3))
    rx = float(p["tilt"]) * 0.45 * e * (0.8 + 0.2 * math.cos(c.u * 1.1))
    bb = card.getchannel("A").getbbox()
    if bb:
        bx0, by0, bx1, by1 = max(0, bb[0] - 2), max(0, bb[1] - 2), min(W, bb[2] + 2), min(H, bb[3] + 2)
        piece = card.crop((bx0, by0, bx1, by1))
        if abs(ry) + abs(rx) > 0.05:
            cxp, cyp = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            dst = tilt_pts([(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)], cxp, cyp, ry, rx)
            warp_to(bg, piece, dst, 1.0, shadow=0.6 * e, shadow_dy=int(36 * e))
        else:
            comp(bg, soft_shadow(piece, 0.6 * e), bx0 - 100, by0 - 100 + int(36 * e))
            comp(bg, piece, bx0, by0)
    out = bg.convert("RGB")
    # the very first and last frames are the video itself
    k = clamp01(e * 20)
    if k < 1: out = Image.blend(c.img, out, k)
    return out

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.5,
    "needs": ["person"],
}
