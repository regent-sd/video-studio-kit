"""UI world: the top of the frame turns into a light, airy app. A cream surface slides down over the room above your
head (you stay in front of it), the footage eases down a little, and a rounded prompt box types your words letter by
letter with a caret. Then the send button is pressed (it dips, springs back and ripples) and the box clears."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import W, H, FPS, SS, font, ease_out, ease_io, ease_in, back, prog, lerp, clamp, clamp01
from ._ui import spoken, phases, put, stamp, clip_fade
from ._ui2 import head_top_low, type_schedule, match_times, wrap_idx, ripple, press, blink, SENT_END

NAME = "ui-world"
KIND = "cards"
ABOUT = "The top of the frame turns into a light app: a prompt box types your words, then sends"
DUR = 5.0
PARAMS = dict(
    prompt=None,      # what gets typed; default the words you say in the window (ums dropped), typed as you say them.
                      #   A prompt of your own types at your pace where its words match what you say, else evenly.
    app=None,         # a small app name above the box (never a real brand); None: no wordmark
    placeholder="",   # grey hint in the empty box before typing and after sending (e.g. "Ask anything"); default none
    lines=3,          # most lines of text in the box; older lines scroll up
    push=None,        # how far the footage eases down (px); default just enough to clear your head (70-300)
    surface=None,     # the UI colour, e.g. "#f9f7f2"; default warm cream (the Brand skin: its background colour)
)
BOX_X0, BOX_W, R = 72, 936, 36
PADX, PADT, PADB, LH, ROW, GAP = 44, 36, 20, 60, 64, 12
SIZE = 44
GRAD = 280
INK, MUTED, EDGE, OFF = (33, 32, 30), (156, 152, 145), (226, 222, 214), (214, 210, 202)

def _box_h(n):
    return PADT + n * LH + GAP + ROW + PADB

def _tokens(c, stop):
    if c.p.get("prompt"):
        words = str(c.p["prompt"]).split()
        lo = c.t0 + min(0.5, c.d * 0.2)
        return match_times(c, words, lo, max(lo + 0.2, stop))
    ws = [w for w in spoken(c) if w["s"] <= stop]
    ends = [i for i, w in enumerate(ws) if w["w"].rstrip()[-1:] in SENT_END]
    if ws and ends and ws[-1]["w"].rstrip()[-1:] not in SENT_END and ends[-1] + 1 >= 0.6 * len(ws):
        ws = ws[:ends[-1] + 1]          # finish on the end of a sentence when one is close
    toks = [(w["w"], w["s"]) for w in ws]
    if toks: toks[0] = (toks[0][0][:1].upper() + toks[0][0][1:], toks[0][1])
    return toks

def _setup(c):
    tin, tout = min(0.55, c.d * 0.28), min(0.45, c.d * 0.22)
    reserve = min(0.8, c.d * 0.24)                                  # time to press send before the UI leaves
    stop = c.t1 - tout - reserve
    toks = _tokens(c, stop)
    t_first = c.t0 + tin * 0.75
    text, times = type_schedule(toks, t_first) if toks else ("", np.zeros(0))
    sk = c.skin.fontspec("body", 460)
    f = font(SIZE, sk["weight"], sk["path"], sk["index"])
    lines = wrap_idx(text, f, BOX_W - 2 * PADX) if text else []
    maxl = max(1, int(c.p.get("lines") or 3))
    app = c.p.get("app")
    top0 = 316 if app else 262
    head = head_top_low(c)
    push = None
    for ml in sorted({maxl, min(maxl, 2), 1}, reverse=True):
        nl = max(1, min(ml, len(lines)))
        need = top0 + _box_h(nl) + 40 - head
        if need <= 300 or ml == 1:
            maxl = ml; push = clamp(need, 70, 300); break
    if c.p.get("push") is not None: push = float(c.p["push"])
    nl = max(1, min(maxl, len(lines)))
    solid = top0 + _box_h(nl) + 30
    # when the box clears: a beat after the last letter, ~1 s before the UI leaves (never past it)
    last = float(times[-1]) if len(times) else None
    if last is None:
        t_send = None
    else:
        t_send = max(last + 0.35, c.t1 - tout - 1.0)
        t_send = min(t_send, c.t1 - tout - 0.3)
        t_send = max(t_send, last + 0.12)
    # the start time of each line (for growing the box)
    lstart = [float(times[ls]) for ls, le in lines]
    surf = c.p.get("surface")
    if surf:
        from core import hexc
        base = hexc(surf)
    else:
        base = tuple(c.skin.light) if c.skin.name == "brand" else (249, 247, 242)
    y = np.arange(H, dtype=np.float32)
    g = np.clip(y / max(1, solid + GRAD), 0, 1)[:, None]
    top_col = np.array([min(255, v + 3) for v in base], np.float32)
    bot_col = np.array([max(0, v - 5) for v in base], np.float32)
    cream = (top_col * (1 - g) + bot_col * g)[:, None, :]           # H x 1 x 3
    return dict(text=text, times=times, lines=lines, f=f, maxl=maxl, top0=top0, push=push, solid=solid,
                t_send=t_send, last=last, lstart=lstart, cream=cream, tin=tin, tout=tout, app=app)

def _alpha_rows(L, slide):
    """Cream opacity per row: solid to the end of the UI, then a soft fade into the room. slide (px) lifts it."""
    y = np.arange(H, dtype=np.float32) + slide
    a = 1 - np.clip((y - L["solid"]) / GRAD, 0, 1)
    a = a * a * (3 - 2 * a)
    a[y < 0] = 1.0
    return a

def _icons(s, bh, t, L, send_k, tap_s, has_text):
    """The bottom row: '+' and settings on the left, the round send button on the right."""
    ym = bh - PADB - ROW / 2
    ic = (96, 93, 88, 255)
    # '+' button
    s.rr((PADX - 12, ym - 25, PADX - 12 + 50, ym + 25), 15, outline=EDGE + (255,), width=1.6)
    cx = PADX - 12 + 25
    s.line([(cx - 10, ym), (cx + 10, ym)], ic, 2.8); s.line([(cx, ym - 10), (cx, ym + 10)], ic, 2.8)
    # settings (two sliders)
    x0 = PADX - 12 + 64
    s.rr((x0, ym - 25, x0 + 50, ym + 25), 15, outline=EDGE + (255,), width=1.6)
    cx = x0 + 25
    for dy, kx in ((-7, -5), (7, 6)):
        s.line([(cx - 13, ym + dy), (cx + 13, ym + dy)], ic, 2.4)
        s.circ(cx + kx, ym + dy, 5.2, fill=(255, 255, 255, 255), outline=ic, width=2.2)
    # send: off-white while empty, dark once there's text, pressed at t_send
    r = 29 * tap_s
    bx = BOX_W - PADX + 8 - 29
    col = tuple(int(lerp(o, i, has_text)) for o, i in zip(OFF, (26, 25, 24)))
    s.circ(bx, ym, r, fill=col + (255,))
    k = r / 29
    w_ = 3.4 * k
    s.line([(bx, ym + 11 * k), (bx, ym - 11 * k)], (255, 255, 255, 255), w_)
    s.line([(bx - 9.5 * k, ym - 1.5 * k), (bx, ym - 11 * k), (bx + 9.5 * k, ym - 1.5 * k)], (255, 255, 255, 255), w_)
    return bx, ym

def render(c):
    st = c.state
    if "L" not in st: st["L"] = _setup(c)
    L = st["L"]
    ui, uo = phases(c, L["tin"], L["tout"])
    if ui <= 0 or uo >= 1: return c.img
    t = c.t
    # ---- the footage eases down; the cream surface slides down behind you
    kp = ease_io(ui) * (1 - ease_io(uo))
    p = int(round(L["push"] * kp))
    fr = np.asarray(c.img, np.uint8)
    m = c.mask
    if p > 0:
        sh = np.empty_like(fr); sh[p:] = fr[:H - p]; sh[:p] = fr[:1]
        mm = np.zeros_like(m); mm[p:] = m[:H - p]
    else:
        sh, mm = fr, m
    D = L["solid"] + GRAD
    slide = (1 - ease_out(ui)) * D + ease_in(uo) * D
    A = _alpha_rows(L, slide) * min(1.0, ease_out(ui * 2.2))
    rows = np.nonzero(A > 0.002)[0]
    out = sh.copy()
    if len(rows):
        y1 = int(rows.max()) + 1
        top = sh[:y1].astype(np.float32)
        a2 = (A[:y1, None] * (1 - mm[:y1]))[..., None]
        out[:y1] = np.clip(top + (L["cream"][:y1] - top) * a2, 0, 255).astype(np.uint8)
    img = Image.fromarray(out, "RGB")
    # ---- the prompt box
    bin_ = prog(c.u, L["tin"] * 0.25, L["tin"] * 0.75)
    if bin_ <= 0: return img
    lines, text, times, f = L["lines"], L["text"], L["times"], L["f"]
    maxl = L["maxl"]
    n = int(np.searchsorted(times, t, side="right")) if len(times) else 0
    t_send = L["t_send"]
    sent = ease_out(prog(t, t_send + 0.08, 0.3)) if t_send is not None else 0.0
    # line of the caret, and how many lines the box shows (grows line by line, shrinks back once sent)
    cl = 0
    for li, (ls, le) in enumerate(lines):
        if n > ls: cl = li
    shown = 1 + sum(ease_io(prog(t, L["lstart"][li] - 0.24, 0.22)) for li in range(1, len(lines)))   # grows just before
    shown_box = min(shown, maxl)
    shown_box = lerp(shown_box, 1, ease_io(prog(t, t_send + 0.12, 0.36))) if t_send is not None else shown_box
    off = sum(ease_io(prog(t, L["lstart"][li] - 0.26, 0.24)) for li in range(maxl, len(lines)))
    bh = int(round(_box_h(shown_box)))
    s = SS(BOX_W, bh)
    s.rr((0, 0, BOX_W, bh), R, fill=(255, 255, 255, 255))
    s.rr((0.5, 0.5, BOX_W - 0.5, bh - 0.5), R, outline=EDGE + (255,), width=1.5)
    has = 0.0
    if len(times):
        has = ease_out(prog(t, times[0], 0.18)) * (1 - ease_out(prog(t, t_send + 0.18, 0.3)))
    tap_s = press(t, t_send) if t_send is not None else 1.0
    bx, by = _icons(s, bh, t, L, sent, tap_s, has)
    box = s.out()
    # text: the typed part of each line, scrolled; it lifts away and fades once sent
    asc, desc = f.getmetrics()
    tw, th = BOX_W - 2 * PADX, int(round(shown_box * LH))
    tl = Image.new("RGBA", (tw, maxl * LH + 2), INK + (0,))
    d = ImageDraw.Draw(tl)
    ta = 1 - sent
    dy = -26 * sent
    yo = (LH - (asc + desc)) / 2 + 2
    caret = (0, yo)
    if ta > 0.01:
        for li, (ls, le) in enumerate(lines):
            if n <= ls: break
            y = (li - off) * LH + yo + dy
            seg = text[ls:min(le, n)]
            la = clamp01(1 + (li - off) * 1.8) * ta
            if la > 0.01 and -LH < y < tl.height:
                d.text((0, y), seg, font=f, fill=INK + (int(255 * la),))
            if li == cl: caret = (f.getlength(seg) + 3, y)
    ph = str(c.p.get("placeholder") or "")
    pa = 0.0
    if ph:
        pa = 1.0 if n == 0 else 0.0
        if t_send is not None: pa = max(pa, ease_out(prog(t, t_send + 0.3, 0.3)))
        if pa > 0.01:
            d.text((0, yo), ph, font=f, fill=MUTED + (int(255 * pa),))
    if sent > 0.5: caret = (0, yo)
    if off > 0.001:   # lines scrolling out of the top fade
        a = np.asarray(tl.getchannel("A"), np.float32)
        ramp = np.clip((np.arange(tl.height) + 4) / 18.0, 0, 1)
        tl.putalpha(Image.fromarray((a * ramp[:, None]).astype(np.uint8), "L"))
    last_typed = float(times[n - 1]) if n else c.t0
    idle = t - (t_send + 0.3 if (t_send is not None and t > t_send) else last_typed)
    ca = blink(idle)
    if ca > 0.01:
        cx, cy = caret
        d2 = ImageDraw.Draw(tl)
        d2.rounded_rectangle((cx, cy + asc * 0.1, cx + 3, cy + asc * 0.1 + asc * 1.02), 1.5, fill=INK + (int(235 * ca),))
    box.alpha_composite(tl.crop((0, 0, tw, max(1, min(th, tl.height)))), (PADX, PADT))
    # ---- place it: drops in with a little overshoot, lifts away with the surface
    top0 = L["top0"]
    y_in = (1 - back(bin_, 1.25)) * -150
    y_out = -ease_in(uo) * (top0 + bh + 80)
    a = min(1.0, ease_out(bin_ * 1.6)) * (1 - ease_out(prog(uo, 0.4, 0.6)))
    by0 = top0 + y_in + y_out
    stamp(img, box, BOX_X0 + BOX_W / 2, by0 + bh / 2, a=a, shadow=0.13, blur=30, dy=16)
    # the send ripple (outside the box's clip)
    if t_send is not None:
        rk = prog(t, t_send, 0.6)
        if 0 < rk < 1:
            rs = SS(220, 220)
            ripple(rs, 110, 110, 29, rk, (60, 58, 54), grow=72, a=0.32, width=2.2)
            put(img, rs.out(), BOX_X0 + bx - 110, by0 + by - 110, a)
    # the wordmark
    if L["app"]:
        wa = min(1.0, ease_out(prog(c.u, L["tin"] * 0.1, L["tin"] * 0.7) * 1.4)) * (1 - ease_out(prog(uo, 0.2, 0.6)))
        key = ("wm", L["app"])
        if key not in st:
            sp = c.skin.fontspec("serif", 560)
            fw = font(48, sp["weight"], sp["path"], sp["index"])
            tw_ = fw.getlength(str(L["app"]))
            ws = SS(int(tw_ + 60), 70)
            ws.circ(13, 37, 11, fill=tuple(c.skin.accent) + (255,))
            ws.text((40, 37), str(L["app"]), 48, sp["weight"], fill=INK + (255,), anchor="lm", path=sp["path"], index=sp["index"])
            st[key] = ws.out()
        wm = st[key]
        wy = 262 - wm.height / 2 + (1 - ease_out(prog(c.u, 0, L["tin"]))) * -90 + y_out
        put(img, wm, W / 2 - wm.width / 2, wy, wa)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "your own words as you say them; no wordmark, no placeholder",
    "needs": ["talk"],
}
