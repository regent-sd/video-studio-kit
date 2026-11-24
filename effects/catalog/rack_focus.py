"""Rack focus: a shallow-depth-of-field look, then the focus pulls from you to the room and back, like a cinema lens."""
import numpy as np
from PIL import Image
from core import W, H, f32, to_pil, ease_io, prog, clamp
from catalog._cam import room, stable_mask, defocus, lens_blur, blur, affine, pil

NAME = "rack-focus"
KIND = "camera"
ABOUT = "Focus pull: room blurred behind you, then the focus shifts to the room (you blur), then back"
DUR = 4.0
PARAMS = dict(
    room_blur=24,     # how out of focus the room gets while you're sharp (px, at 1080 wide)
    you_blur=16,      # how out of focus you get while the room is sharp (px)
    breathe=0.016,    # focus breathing: the picture grows this much (1.6 %) as focus goes to the room
    pull=0.5,         # seconds each focus pull takes (shortened on short windows)
    bokeh=2.0,        # how much bright spots bloom into discs when blurred (1 = plain blur)
)

def _curves(c):
    """dof: 0 -> 1 -> 0 (shallow depth of field on/off); focus: 0 on you, 1 on the room."""
    d = c.d
    ramp = min(0.45, d * 0.16)                         # depth of field fades in / out
    pull = clamp(float(c.p["pull"]), 0.15, max(0.15, (d - 2 * ramp) * 0.3))
    room_t = max(0.0, d - 2 * ramp - 2 * pull)         # time spent with the room sharp, plus time on you
    a = ramp + room_t * 0.22                           # focus starts moving to the room
    b = a + pull
    c2 = b + room_t * 0.56                             # ... and back to you
    dof = min(ease_io(c.u / ramp), ease_io((d - c.u) / ramp)) if ramp > 0 else 1.0
    focus = ease_io(prog(c.u, a, pull)) - ease_io(prog(c.u, c2, pull))
    return dof, focus

def render(c):
    p = c.p
    dof, focus = _curves(c)
    if dof < 1e-3:
        return c.img
    img = f32(np.asarray(c.img))
    m = stable_mask(c)
    rm, _ = room(c, img, m, grow_px=18, feather=18, dim=0.18, soften=6)
    rr = float(p["room_blur"]) * dof * (1 - focus)
    pr = float(p["you_blur"]) * dof * focus
    g = max(1.0, float(p["bokeh"]))
    # the room: a lens blur with blooming highlights (the person is already taken out, so no halo)
    room_b = defocus(rm, rr, g) if rr > 0.4 else rm
    # you: blurred with your own alpha (premultiplied), so the edge spreads softly over the room instead of
    # dragging the room's colours into you
    if pr > 0.4:
        lay = np.concatenate([img * m[..., None], m[..., None] * 255], 2)
        lb = defocus(lay, pr, 1.0)
        a = np.clip(lb[..., 3:4] / 255, 0, 1)
        out = room_b * (1 - a) + lb[..., :3]
    else:
        mm = m[..., None]
        out = room_b * (1 - mm) + img * mm
    # focus breathing: focusing farther makes the picture grow a touch (about the face)
    s = 1 + float(p["breathe"]) * focus * dof
    if s > 1.0005:
        cx, cy, fw, fh = c.face
        cx = clamp(cx, W * 0.3, W * 0.7); cy = clamp(cy, H * 0.3, H * 0.7)
        out = np.asarray(affine(pil(out), s, cx, cy), np.float32)
    # ease in from / out to the untouched frame (the very first and last frames match the video)
    k = min(1.0, dof * 4)
    if k < 1: out = out * k + img * (1 - k)
    return to_pil(out)

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "no text on screen",
    "still": 0.5,
    "needs": ["person"],
}
