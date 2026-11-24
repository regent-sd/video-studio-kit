"""Phone mockup: a phone pops in beside you (on the side with more room), tilted a little in 3D with a soft shadow,
and floats. Its screen plays your footage behind an app sheet: a title line and 3-4 rows with radio dots that check
off one by one as you say each item, then a yellow "Done" pill that gets tapped. A touch ring glides to each tap."""
import math
import numpy as np
from PIL import Image, ImageDraw
from core import (W, H, FPS, SS, font, place, ease_out, ease_io, ease_in, back, prog, lerp, clamp, clamp01)
from ._ui import phases, fit_text, rr_mask
from ._ui2 import faces_in, face_span, sentence, key_items, given_items, ripple, press, wrap_idx

NAME = "phone-mockup"
KIND = "cards"
ABOUT = "A phone floats beside you; its app sheet checks off your words one by one, then taps Done"
DUR = 5.0
PARAMS = dict(
    title=None,       # the sheet's title; default your first sentence in the window (cut to 12 words, 3 lines)
    items=None,       # rows: ["Sleep more", ...] or [{"label": "Sleep more", "on": "sleep"}, ...]
                      #   on: a word you say, or seconds into the video. Default: the key words you say, each
                      #   checking off as you say it.
    max_items=4,      # most rows (3-4 fit best)
    button="Done",    # the pill button's label
    side=None,        # left | right; default the side with more room
    footage=True,     # the screen shows your footage behind the sheet; False: a plain light screen
)
PW, PH, BZ, RO = 400, 850, 13, 66          # phone (px at scale 1), bezel, outer corner radius
SW, SH, RS = PW - 2 * BZ, PH - 2 * BZ, RO - BZ
PADX, TSZ, TLH, ROW_H, LSZ, BTN_H = 26, 31, 38, 70, 27, 62
FRAME, FRAME_HI = (22, 22, 25), (78, 78, 86)
INK, MUTED, LINE, RADIO = (17, 17, 19), (142, 142, 147), (226, 226, 231), (196, 196, 202)

def _content(c, st):
    tin, tout = st["tin"], st["tout"]
    limit = c.t1 - tout - 0.75                                 # last check, leaving time to tap Done
    if c.p.get("items"):
        its = given_items(c, list(c.p["items"])[:6], c.t0 + tin + 0.3, limit)
    else:
        its = [(l, s) for l, s in key_items(c, 12) if s <= limit]
        m = max(1, int(c.p.get("max_items") or 4))
        if len(its) > m: its = [its[int(round(i * (len(its) - 1) / (m - 1)))] for i in range(m)] if m > 1 else its[:1]
    its = [(l, clamp(s, c.t0 + tin + 0.15, limit)) for l, s in its]
    title = c.p.get("title")
    if title is None: title = sentence(c, 12)
    last = max([s for _, s in its], default=c.t0 + tin)
    t_done = clamp(max(last + 0.6, c.t1 - tout - 0.75), last + 0.3, c.t1 - tout - 0.3)
    return its, str(title or ""), t_done

def _layout(st, sk):
    """Sheet geometry in screen px: title lines, row tops, button box."""
    tf = font(TSZ, sk["title"]["weight"], sk["title"]["path"], sk["title"]["index"])
    lines = wrap_idx(st["title"], tf, SW - 2 * PADX) if st["title"] else []
    tl = [st["title"][a:b] for a, b in lines[:3]]
    if len(lines) > 3:                  # cut the third line at a word, with an ellipsis
        ws = tl[-1].split()
        while len(ws) > 1 and tf.getlength(" ".join(ws) + "…") > SW - 2 * PADX: ws.pop()
        tl[-1] = " ".join(ws).rstrip(",;:") + "…"
    n = len(st["items"])
    y = 40
    th = len(tl) * TLH
    rows_y = y + th + (18 if tl else 0)
    btn_y = rows_y + n * ROW_H + 26
    sheet_h = btn_y + BTN_H + 40
    return dict(tl=tl, title_y=y, rows_y=rows_y, btn_y=btn_y, sheet_h=min(SH - 120, sheet_h))

def _placement(c, st):
    x0, x1, y0, y1 = face_span(c)
    fs = faces_in(c)
    fw = float(np.median(fs[:, 2])); cy = float(np.median(fs[:, 1])); fh = float(np.median(fs[:, 3]))
    side = c.p.get("side")
    if side not in ("left", "right"):
        side = "right" if (W - x1) >= x0 else "left"
    room = (W - x1) if side == "right" else x0
    s = clamp((room + 0.12 * fw - 26) / PW, 0.8, 1.02)
    pw = PW * s
    cx = (x1 - 0.12 * fw + pw / 2) if side == "right" else (x0 + 0.12 * fw - pw / 2)
    cx = clamp(cx, 24 + pw / 2, W - 24 - pw / 2)
    ph = PH * s
    cy_ = clamp(cy + 0.32 * fh, 236 + ph / 2, 1480 - ph / 2)
    return side, s, cx, cy_

def _frame_img():
    """The phone body: dark frame, a lighter rim, side buttons, a hole for the screen (drawn on top)."""
    m = 6
    s = SS(PW + 2 * m, PH + 2 * m)
    # side buttons
    for y0, y1 in ((190, 236), (262, 336), (350, 424)):
        s.rr((1, y0, m + 6, y1), 3, fill=(40, 40, 44, 255))
    s.rr((PW + m - 6, 270, PW + 2 * m - 1, 380), 3, fill=(40, 40, 44, 255))
    s.rr((m, m, PW + m, PH + m), RO, fill=FRAME + (255,))
    s.rr((m + 1.2, m + 1.2, PW + m - 1.2, PH + m - 1.2), RO - 1, outline=FRAME_HI + (255,), width=2.4)
    s.rr((m + BZ - 2, m + BZ - 2, PW + m - BZ + 2, PH + m - BZ + 2), RS + 2, fill=(6, 6, 7, 255))
    return s.out(), m

def _static_sheet(st, sk, acc, ink_on_acc):
    """Sheet parts that don't move: white sheet, grabber, title, row labels and lines, the button's label."""
    L = st["lay"]
    sh = L["sheet_h"]
    s = SS(SW, sh)
    s.rr((0, 0, SW, sh + 60), 30, fill=(255, 255, 255, 255))
    s.rr((SW / 2 - 22, 11, SW / 2 + 22, 16), 2.5, fill=(210, 210, 215, 255))
    tsp, bsp = sk["title"], sk["body"]
    for k, ln in enumerate(L["tl"]):
        s.text((PADX, L["title_y"] + k * TLH + TLH / 2), ln, TSZ, tsp["weight"], fill=INK + (255,), anchor="lm",
               path=tsp["path"], index=tsp["index"])
    lf = font(LSZ, 640, bsp["path"], bsp["index"])
    for k, (label, _) in enumerate(st["items"]):
        y = L["rows_y"] + k * ROW_H
        if k: s.line([(PADX + 48, y), (SW - PADX + 6, y)], LINE + (255,), 1.2, round_caps=False)
        s.text((PADX + 52, y + ROW_H / 2 + 1), fit_text(label, lf, SW - 2 * PADX - 56), LSZ, 640, fill=INK + (255,),
               anchor="lm", path=bsp["path"], index=bsp["index"])
    return s.out()

def _screen(c, st, t, ui):
    """The screen image (SW x SH) on this frame."""
    L = st["lay"]
    acc, ink_acc = tuple(c.skin.accent), tuple(c.skin.accent_ink)
    scr = Image.new("RGBA", (SW, SH), (238, 238, 243, 255))
    if c.p.get("footage", True):
        fx, fy, fw_, fh_ = c.face
        ch = min(H, max(fh_ * 3.4, 900)); cw = ch * SW / SH
        x0 = clamp(fx - cw / 2, 0, W - cw); y0 = clamp(fy - ch * 0.3, 0, H - ch)
        foot = Image.fromarray(c.src).resize((SW, SH), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        scr.paste(foot, (0, 0))
        dim = Image.new("RGBA", (SW, SH), (0, 0, 0, int(255 * 0.18 + 255 * 0.22 * ease_out(prog(c.u, st["tin"] * 0.6, 0.4)))))
        scr.alpha_composite(dim)
    if not st["sheet_on"]: return _finish(st, scr)    # nothing to list: just the phone playing your footage
    # the sheet slides up just after the phone lands
    k_in = ease_out(prog(c.u, st["tin"] * 0.55, 0.42))
    sh = L["sheet_h"]
    sy = SH - sh + (1 - k_in) * (sh + 30)
    sheet = st["sheet"].copy()
    d = SS(SW, sh)
    rows_y = L["rows_y"]
    # tap highlight behind a row, radio dots that fill as each item is said
    for k, (label, ts) in enumerate(st["items"]):
        y = rows_y + k * ROW_H
        hk = prog(t, ts - 0.05, 0.5)
        if 0 < hk < 1:
            d.rr((8, y + 4, SW - 8, y + ROW_H - 4), 16, fill=(0, 0, 0, int(16 * math.sin(math.pi * hk))))
        cx, cy = PADX + 16, y + ROW_H / 2
        ck = prog(t, ts, 0.42)
        if ck <= 0:
            d.circ(cx, cy, 14, outline=RADIO + (255,), width=2.4)
        else:
            rr = 14 * back(prog(ck, 0, 0.6), 2.4)
            if ck < 0.6: d.circ(cx, cy, 14, outline=RADIO + (int(255 * (1 - ck / 0.6)),), width=2.4)
            d.circ(cx, cy, max(0.5, rr), fill=acc + (255,))
            kk = ease_out(prog(ck, 0.35, 0.65))
            if kk > 0:
                pts = [(cx - 6, cy + 0.5), (cx - 1.8, cy + 4.8), (cx + 6.4, cy - 4.6)]
                l1 = math.dist(pts[0], pts[1]); l2 = math.dist(pts[1], pts[2]); Lk = (l1 + l2) * kk
                path = [pts[0], (lerp(pts[0][0], pts[1][0], min(1, Lk / l1)), lerp(pts[0][1], pts[1][1], min(1, Lk / l1)))]
                if Lk > l1:
                    f = (Lk - l1) / l2; path.append((lerp(pts[1][0], pts[2][0], f), lerp(pts[1][1], pts[2][1], f)))
                d.line(path, ink_acc + (255,), 3.0)
    # the Done pill: pressed at t_done
    bs = press(t, st["t_done"], depth=0.07, over=0.025)
    bw, bh = (SW - 2 * PADX) * bs, BTN_H * bs
    bcx, bcy = SW / 2, L["btn_y"] + BTN_H / 2
    done_k = ease_out(prog(t, st["t_done"], 0.25))
    col = tuple(int(lerp(a, a * 0.86, done_k * (1 - prog(t, st["t_done"] + 0.35, 0.4)))) for a in acc)
    d.rr((bcx - bw / 2, bcy - bh / 2, bcx + bw / 2, bcy + bh / 2), bh / 2, fill=col + (255,))
    bsp = c.skin.fontspec("title", 760)
    d.text((bcx, bcy + 1), str(c.p.get("button") or "Done"), 27 * bs, bsp["weight"], fill=ink_acc + (255,), anchor="mm",
           path=bsp["path"], index=bsp["index"])
    sheet.alpha_composite(d.out())
    scr.alpha_composite(sheet, (0, int(round(sy))))
    # the touch ring: glides to each tap, dips, and ripples
    taps = [(ts, (PADX + 16, sy + rows_y + k * ROW_H + ROW_H / 2)) for k, (_, ts) in enumerate(st["items"])]
    taps.append((st["t_done"], (SW / 2 + 40, sy + L["btn_y"] + BTN_H / 2)))
    t_first = taps[0][0]
    ra = ease_out(prog(t, t_first - 0.7, 0.3)) * (1 - ease_out(prog(t, st["t_done"] + 0.25, 0.35)))
    if ra > 0.01:
        j = next((i for i, (ts, _) in enumerate(taps) if t < ts + 0.12), len(taps) - 1)
        p1 = taps[j][1]; p0 = taps[j - 1][1] if j > 0 else (p1[0] + 70, p1[1] + 90)
        t0 = taps[j - 1][0] + 0.12 if j > 0 else t_first - 0.7
        mk = ease_io(prog(t, max(t0, taps[j][0] - 0.42), min(0.36, max(0.12, taps[j][0] - t0 - 0.06))))
        px, py = lerp(p0[0], p1[0], mk), lerp(p0[1], p1[1], mk)
        rs = SS(SW, SH)
        dip = min(press(t, ts, 0.08, 0.3, 0.22, 0.04) for ts, _ in taps)
        for ts, (qx, qy) in taps:
            ripple(rs, qx, qy, 18, prog(t, ts, 0.5), (60, 60, 66), grow=34, a=0.35, width=2)
        r = 25 * dip
        rs.circ(px, py, r, fill=(120, 120, 128, int(70 * ra)))
        rs.circ(px, py, r, outline=(255, 255, 255, int(235 * ra)), width=3)
        scr.alpha_composite(rs.out())
    return _finish(st, scr)

def _finish(st, scr):
    """The island, the home bar and a soft glass sheen; the screen's rounded corners."""
    if "glass" not in st:
        g = SS(SW, SH)
        g.rr((SW / 2 - 58, 16, SW / 2 + 58, 50), 17, fill=(0, 0, 0, 255))
        g.rr((SW / 2 - 66, SH - 15, SW / 2 + 66, SH - 9), 3, fill=(20, 20, 22, 230))
        sheen = np.zeros((SH, SW), np.float32)
        yy, xx = np.mgrid[0:SH, 0:SW].astype(np.float32)
        band = (xx * 0.9 + yy * 0.45) / (SW * 0.9 + SH * 0.45)
        sheen = np.clip(1 - np.abs(band - 0.28) / 0.16, 0, 1) ** 2 * 26
        sh_im = Image.new("RGBA", (SW, SH), (255, 255, 255, 0))
        sh_im.putalpha(Image.fromarray(sheen.astype(np.uint8), "L"))
        gl = g.out(); gl.alpha_composite(sh_im)
        st["glass"] = gl
    scr.alpha_composite(st["glass"])
    scr.putalpha(rr_mask(SW, SH, RS))
    return scr

def render(c):
    st = c.state
    if "lay" not in st:
        st["tin"], st["tout"] = min(0.6, c.d * 0.28), min(0.5, c.d * 0.22)
        st["items"], st["title"], st["t_done"] = _content(c, st)
        sk = {r: c.skin.fontspec(r, 700 if r == "title" else None) for r in ("title", "body")}
        st["lay"] = _layout(st, sk)
        st["sheet_on"] = bool(st["items"] or st["title"])
        st["sheet"] = _static_sheet(st, sk, c.skin.accent, c.skin.accent_ink)
        st["frame"], st["fm"] = _frame_img()
        st["place"] = _placement(c, st)
    ui, uo = phases(c, st["tin"], st["tout"])
    if ui <= 0 or uo >= 1: return c.img
    side, s, cx, cy = st["place"]
    sgn = 1 if side == "right" else -1
    t = c.t
    phone = st["frame"].copy()
    m = st["fm"]
    phone.alpha_composite(_screen(c, st, t, ui), (m + BZ, m + BZ))
    # pop in with overshoot, float, slide out to its side
    e = back(ui, 1.7)
    sc = s * (0.55 + 0.45 * e) * (1 - 0.06 * ease_in(uo))
    fl = c.u
    bob = 9 * math.sin(2 * math.pi * 0.32 * fl) * ease_out(prog(c.u, 0.2, 0.8))
    ry = sgn * (11 + (1 - ease_out(ui)) * 34 + ease_in(uo) * 30) + 2.2 * math.sin(2 * math.pi * 0.21 * fl + 0.7)
    rz = sgn * (2.6 + 1.0 * math.sin(2 * math.pi * 0.17 * fl + 1.9)) + (1 - ease_out(ui)) * sgn * 8
    rx = 4 + 1.5 * math.sin(2 * math.pi * 0.23 * fl)
    x = cx + sgn * (1 - ease_out(ui)) * 60 + sgn * ease_in(uo) * (PW * s + 260)
    y = cy + (1 - ease_out(ui)) * 140 + bob
    a = min(1.0, ease_out(ui * 2.2)) * (1 - ease_out(prog(uo, 0.35, 0.65)))
    img = c.img.convert("RGBA")
    place(img, phone, x, y, s=sc, ry=ry, rx=rx, rz=rz, shadow=0.5 * a, a=a, f=2400)
    return img.convert("RGB")

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the title and rows are your own words; 'Done' is a standard UI label",
    "needs": ["talk"],
}
