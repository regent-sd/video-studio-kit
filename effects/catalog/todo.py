"""Todo: a dark checklist card under your chin. Each item ticks off with a green check as you say it."""
import math
import numpy as np
from PIL import Image
from core import W, H, FPS, SS, font, SFP, SFMONO, key_words, ease_out, ease_io, back, prog, lerp, clamp, norm_word
from ._ui import clean, when, phases, frost, stamp, spinner, check, fit_text

NAME = "todo"
KIND = "cards"
ABOUT = "A checklist card under your chin that ticks off each item as you say it"
DUR = 5.0
PARAMS = dict(
    title=None,       # header text, e.g. "Editing your clip"; None: no header (a progress line shows instead)
    items=None,       # [{"label": "Cut the intro", "tag": "every frame", "on": "intro"}, ...]
                      #   on: a word you say, or seconds into the video. tag: small green text on the right (optional).
                      #   Default: one item per key word you say in the window (the word, capitalised), ticking as you say it.
    tags="time",      # tag for default items: "time" (when the word is said, e.g. 0:05.6) | None
    max_items=6,      # most default items (picked evenly across the window)
    rows=4,           # most rows visible at once; longer lists scroll so the active row stays in view
    counter=True,     # "2 of 5" at the top right of the header (needs a title)
    y=None,           # top of the card (px); default just under your chin, or above your head if there's more room
    style="card",     # card (wide, under your chin) | compact (a small dark card at the top left: tiny caps header,
                      #   "1 of 3", a thin yellow progress line, yellow checks that fill as you say each item)
)
CARD_W, ROW_H, HEAD_H, PAD = 900, 68, 76, 16
BOTTOM = 1470          # Instagram's caption area starts about here

def _stamp(s):
    return f"{int(s // 60)}:{s % 60:04.1f}"

def _items(c):
    its = c.p.get("items")
    out = []
    if its:
        n = len(its)
        lo, hi = c.t0 + min(0.6, c.d * 0.2), c.t1 - min(0.6, c.d * 0.2)
        for k, it in enumerate(its):
            if isinstance(it, str): it = {"label": it}
            fb = lo + (hi - lo) * (k + 1) / (n + 1)
            t = when(c, it.get("on"), fb)
            out.append((str(it.get("label", "")), it.get("tag", _stamp(t) if c.p.get("tags") == "time" else None), t))
        return out
    seen, ws = set(), []
    for w in key_words(c.words_in()):
        n = norm_word(w["w"])
        if n not in seen: seen.add(n); ws.append(w)
    m = int(c.p.get("max_items") or 6)
    if len(ws) > m:
        ws = [ws[int(round(i * (len(ws) - 1) / (m - 1)))] for i in range(m)] if m > 1 else ws[:1]
    for w in ws:
        tag = _stamp(w["s"]) if c.p.get("tags") == "time" else None
        out.append((clean(w["w"]).capitalize(), tag, w["s"]))
    return out

def _layout(c, n):
    has_title = bool(c.p.get("title"))
    fixed = (HEAD_H if has_title else 10) + 2 * PAD
    i0 = int(c.t0 * FPS); i1 = max(i0 + 1, int(c.t1 * FPS))
    fs = c.subj.faces[i0:i1] if len(c.subj.faces) else np.array([c.face], np.float32)
    if len(fs) == 0: fs = np.array([c.face], np.float32)
    chin = float(np.percentile(fs[:, 1] + 0.62 * fs[:, 3], 75))
    head = float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], 10))
    fcx = float(np.median(fs[:, 0]))
    want = max(1, min(n, int(c.p.get("rows") or 4)))
    if c.p.get("y") is not None:
        top, vis = float(c.p["y"]), want
    else:
        below_top = chin + 12
        rb = int((BOTTOM + PAD - below_top - fixed) // ROW_H)
        ra = int((head - 14 - 226 - fixed) // ROW_H)
        if rb >= min(want, 3) or rb >= ra:
            vis = max(min(n, 2), min(want, rb)); top = below_top
        else:
            vis = max(min(n, 2), min(want, ra)); top = head - 14 - (fixed + vis * ROW_H)
            top = max(226, top)
    card_h = fixed + vis * ROW_H
    x0 = clamp(fcx - CARD_W / 2, 24, W - 24 - CARD_W)
    return dict(top=top, x0=x0, vis=vis, card_h=card_h, has_title=has_title)

def _row(s, y, label, tag, state, k, t, enter):
    """One row at y (top). state: done | active | queued. k: check progress. enter: 0-1 slide-in."""
    if enter <= 0: return
    dx = (1 - ease_out(enter)) * 40
    ea = ease_out(enter)
    mid = y + ROW_H / 2
    ix = 50 + dx
    if state == "done":
        check(s, ix, mid, 19, k)
    elif state == "active":
        spinner(s, ix, mid, 18, t, (255, 255, 255), ea)
    else:
        s.circ(ix, mid, 16, outline=(255, 255, 255, int(80 * ea)), width=2.4)
    a_lab = {"done": 235, "active": 255, "queued": 105}[state]
    tagw = 0
    if tag:
        f = font(27, 600, SFMONO)
        tw = f.getlength(tag); tagw = tw + 28
        x1 = CARD_W - 28 + dx; x0 = x1 - tagw
        green = (48, 209, 88)
        bg = green + (int(42 * ea),) if state == "done" else (255, 255, 255, int(16 * ea))
        s.rr((x0, mid - 21, x1, mid + 21), 11, fill=bg)
        col = {"done": green + (int(255 * ea),), "active": green + (int(190 * ea),)}.get(state, (255, 255, 255, int(95 * ea)))
        s.text(((x0 + x1) / 2, mid + 1), tag, 27, 600, fill=col, anchor="mm", path=SFMONO)
    lab = fit_text(label, font(36, 620), CARD_W - 96 - tagw - 44)
    s.text((88 + dx, mid + 1), lab, 36, 620, fill=(255, 255, 255, int(a_lab * ea)), anchor="lm")

def render(c):
    if c.p.get("style") == "compact": return _render_compact(c)
    st = c.state
    if "items" not in st:
        st["items"] = _items(c)
        st["lay"] = _layout(c, len(st["items"]))
    items, L = st["items"], st["lay"]
    n = len(items)
    if not n: return c.img
    ui, uo = phases(c, 0.5, 0.4)
    if ui <= 0 or uo >= 1: return c.img
    t = c.t
    vis, card_h, has_title = L["vis"], L["card_h"], L["has_title"]
    times = [it[2] for it in items]
    done = [t >= ti for ti in times]
    ndone = sum(done)
    active = next((i for i in range(n) if not done[i]), None)
    # ---- the content (header + scrolling rows), drawn crisp at 2x
    s = SS(CARD_W, card_h)
    y_list = PAD + (HEAD_H if has_title else 0)
    if has_title:
        title = fit_text(str(c.p["title"]), font(40, 700), CARD_W - 64 - (170 if c.p.get("counter") else 0))
        s.text((32, PAD + HEAD_H / 2 - 4), title, 40, 700, fill=(255, 255, 255, 255), anchor="lm")
        if c.p.get("counter"):
            of = f" of {n}"
            xr = CARD_W - 32
            s.text((xr, PAD + HEAD_H / 2 - 4), of, 32, 600, fill=(255, 255, 255, 140), anchor="rm")
            xn = xr - s.textlen(of, 32, 600)
            # the count rolls up when it changes (drawn in its own clipped strip)
            tl = max([ti for ti in times if ti <= t], default=None)
            e = ease_out(prog(t, tl, 0.34)) if tl is not None else 1.0
            nw = 90
            roll = SS(nw, 44)
            roll.text((nw, 22 + (1 - e) * 40), str(ndone), 32, 700, fill=(255, 255, 255, 235), anchor="rm")
            if e < 1 and ndone > 0:
                roll.text((nw, 22 - e * 40), str(ndone - 1), 32, 700, fill=(255, 255, 255, 235), anchor="rm")
            ro = roll.out()
            ramp = np.minimum(1, np.minimum(np.arange(44), np.arange(44)[::-1]) / 12.0).astype(np.float32)
            ro.putalpha(Image.fromarray((np.asarray(ro.getchannel("A"), np.float32) * ramp[:, None]).astype(np.uint8), "L"))
            st["roll"] = (ro, int(round(xn - nw)), int(round(PAD + HEAD_H / 2 - 4 - 22)))
        # progress line under the header
        frac = sum(ease_io(prog(t, ti, 0.4)) for ti in times) / n
        ly = PAD + HEAD_H - 6
        s.rr((28, ly - 1.5, CARD_W - 28, ly + 1.5), 1.5, fill=(255, 255, 255, 30))
        if frac > 0.002: s.rr((28, ly - 1.5, 28 + (CARD_W - 56) * frac, ly + 1.5), 1.5, fill=(48, 209, 88, 255))
    else:
        frac = sum(ease_io(prog(t, ti, 0.4)) for ti in times) / n
        ly = card_h - 13
        s.rr((32, ly - 2, CARD_W - 32, ly + 2), 2, fill=(255, 255, 255, 30))
        if frac > 0.002: s.rr((32, ly - 2, 32 + (CARD_W - 64) * frac, ly + 2), 2, fill=(48, 209, 88, 255))
    # rows: scroll so the active row stays in view
    vh = vis * ROW_H
    rl = SS(CARD_W, vh)
    maxoff = max(0, n - vis)
    off = 0.0
    for i, ti in enumerate(times):
        step = clamp(i, 0, maxoff) - clamp(i - 1, 0, maxoff) if i > 0 else 0
        if step: off += step * ease_io(prog(t, ti + 0.25, 0.42))
    # highlight band behind the active row
    af = sum(ease_io(prog(t, ti + 0.05, 0.3)) for ti in times)
    if af < n - 0.02:
        by = af * ROW_H - off * ROW_H
        band_a = (1 - ease_out(prog(af, n - 1, 0.6))) * ease_out(prog(c.u, 0.3, 0.3))
        rl.rr((10, by + 5, CARD_W - 10, by + ROW_H - 5), 16, fill=(255, 255, 255, int(20 * band_a)))
    for i, (label, tag, ti) in enumerate(items):
        y = (i - off) * ROW_H
        if y > vh or y + ROW_H < 0: continue
        state = "done" if done[i] else ("active" if i == active else "queued")
        enter = prog(c.u, 0.18 + 0.07 * min(i, vis), 0.38)
        _row(rl, y, label, tag, state, prog(t, ti, 0.45), t, enter)
    rows = rl.out()
    if n > vis:   # fade rows at the edges of the viewport
        a = np.asarray(rows.getchannel("A"), np.float32)
        ramp = np.ones(vh, np.float32)
        fz = 26
        ramp[:fz] *= 1 - min(1.0, off) * (1 - np.linspace(0, 1, fz))
        ramp[-fz:] *= 1 - min(1.0, maxoff - off) * (1 - np.linspace(1, 0, fz))
        rows.putalpha(Image.fromarray((a * np.clip(ramp, 0, 1)[:, None]).astype(np.uint8), "L"))
    content = s.out()
    if has_title and c.p.get("counter"):
        im, rx, ry = st["roll"]; content.alpha_composite(im, (rx, ry))
    content.alpha_composite(rows, (0, int(y_list)))
    # ---- the card: frosted dark glass, rising in with a little overshoot
    rise = (1 - back(ui, 1.4)) * 80 + ease_out(uo) * 50
    sc = (0.92 + 0.08 * back(ui, 1.4)) * (1 - 0.04 * ease_out(uo))
    a = min(ease_out(ui * 1.6), 1 - ease_out(uo))
    x0, top = L["x0"], L["top"] + rise
    card = frost(c.img, (x0, top, x0 + CARD_W, top + card_h), 34, tint=(16, 16, 20), tint_a=0.78, blur=7)
    card.alpha_composite(content)
    img = c.img.copy()
    stamp(img, card, x0 + CARD_W / 2, top + card_h / 2, s=sc, a=a, shadow=0.45, blur=26, dy=18)
    return img

# ------------------------------------------------------------------ style="compact": a small dark card at the top left
CW, CROW, CHEAD, CPAD, CX, CY = 384, 56, 64, 14, 40, 252

def _compact_layout(c, n):
    i0 = int(c.t0 * FPS); i1 = max(i0 + 1, int(c.t1 * FPS))
    fs = c.subj.faces[i0:i1] if len(c.subj.faces) else np.array([c.face], np.float32)
    if len(fs) == 0: fs = np.array([c.face], np.float32)
    vis = max(1, min(n, int(c.p.get("rows") or 4)))
    card_h = CHEAD + vis * CROW + CPAD
    top = float(c.p["y"]) if c.p.get("y") is not None else CY
    # top left, unless your face is there and the top right is clear
    fx0 = float(np.percentile(fs[:, 0] - fs[:, 2] * 0.5, 10)); fx1 = float(np.percentile(fs[:, 0] + fs[:, 2] * 0.5, 90))
    fy0 = float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], 10))
    x0 = CX
    if fy0 < top + card_h and fx0 < CX + CW and W - CX - CW > fx1:
        x0 = W - CX - CW
    return dict(top=top, x0=x0, vis=vis, card_h=card_h)

def _caps(s, x, y, txt, maxw, fill, size=18, track=1.6):
    """Tiny letter-spaced caps, cut with an ellipsis to maxw."""
    w = lambda t: sum(s.textlen(ch, size, 760) for ch in t) + track * max(0, len(t) - 1)
    if w(txt) > maxw:
        while txt and w(txt + "…") > maxw: txt = txt[:-1]
        txt = txt.rstrip() + "…"
    for ch in txt:
        s.text((x, y), ch, size, 760, fill=fill, anchor="lm")
        x += s.textlen(ch, size, 760) + track

def _render_compact(c):
    st = c.state
    if "items" not in st:
        st["items"] = _items(c)
        st["lay"] = _compact_layout(c, len(st["items"]))
    items, L = st["items"], st["lay"]
    n = len(items)
    if not n: return c.img
    ui, uo = phases(c, 0.45, 0.4)
    if ui <= 0 or uo >= 1: return c.img
    t = c.t
    acc, ink = tuple(c.skin.accent), tuple(c.skin.accent_ink)
    vis, card_h = L["vis"], L["card_h"]
    times = [it[2] for it in items]
    ndone = sum(t >= ti for ti in times)
    active = next((i for i in range(n) if t < times[i]), None)
    s = SS(CW, card_h)
    # header: tiny caps title on the left, "1 of 3" on the right (on the left when there's no title)
    hy = CPAD + 22
    title = str(c.p.get("title") or "").upper()
    if title:
        _caps(s, 24, hy, title, CW - 48 - (100 if c.p.get("counter") else 0), (255, 255, 255, 150))
    if c.p.get("counter", True):
        txt = f"{ndone} of {n}"
        if title:
            s.text((CW - 24, hy), txt, 19, 700, fill=(255, 255, 255, 190), anchor="rm")
        else:
            _caps(s, 24, hy, txt.upper(), CW - 48, (255, 255, 255, 170))
    # thin progress line
    frac = sum(ease_io(prog(t, ti, 0.4)) for ti in times) / n
    ly = CHEAD - 12
    s.rr((24, ly - 1.5, CW - 24, ly + 1.5), 1.5, fill=(255, 255, 255, 30))
    if frac > 0.002: s.rr((24, ly - 1.5, 24 + (CW - 48) * frac, ly + 1.5), 1.5, fill=acc + (255,))
    # rows, scrolling so the next item stays in view
    vh = vis * CROW
    rl = SS(CW, vh)
    maxoff = max(0, n - vis)
    off = 0.0
    for i, ti in enumerate(times):
        step = clamp(i, 0, maxoff) - clamp(i - 1, 0, maxoff) if i > 0 else 0
        if step: off += step * ease_io(prog(t, ti + 0.25, 0.42))
    lf = font(28, 720)
    for i, (label, tag, ti) in enumerate(items):
        y = (i - off) * CROW
        if y > vh or y + CROW < 0: continue
        enter = prog(c.u, 0.16 + 0.06 * min(i, vis), 0.36)
        if enter <= 0: continue
        ea = ease_out(enter)
        dx = (1 - ea) * 30
        mid = y + CROW / 2
        cx = 38 + dx
        k = prog(t, ti, 0.45)
        if k <= 0:
            s_a = 230 if i == active else 150
            rl.circ(cx, mid, 13, outline=acc + (int(s_a * ea),), width=2.4)
        else:
            if k < 0.5: rl.circ(cx, mid, 13, outline=acc + (int(230 * ea * (1 - k / 0.5)),), width=2.4)
            check(rl, cx, mid, 14, k, acc, ink)
        a_lab = 255 if (k > 0 or i == active) else 140
        rl.text((68 + dx, mid + 1), fit_text(label, lf, CW - 68 - 24), 28, 720, fill=(255, 255, 255, int(a_lab * ea)),
                anchor="lm")
    rows = rl.out()
    if n > vis:
        a = np.asarray(rows.getchannel("A"), np.float32)
        ramp = np.ones(vh, np.float32)
        fz = 22
        ramp[:fz] *= 1 - min(1.0, off) * (1 - np.linspace(0, 1, fz))
        ramp[-fz:] *= 1 - min(1.0, maxoff - off) * (1 - np.linspace(1, 0, fz))
        rows.putalpha(Image.fromarray((a * np.clip(ramp, 0, 1)[:, None]).astype(np.uint8), "L"))
    content = s.out()
    content.alpha_composite(rows, (0, CHEAD))
    # the card slides in from its side with a little overshoot, and back out
    sgn = -1 if L["x0"] < W / 2 else 1
    dx = sgn * ((1 - back(ui, 1.3)) * 70 + ease_out(uo) * 60)
    sc = (0.94 + 0.06 * back(ui, 1.3)) * (1 - 0.03 * ease_out(uo))
    a = min(ease_out(ui * 1.6), 1 - ease_out(uo))
    x0, top = L["x0"] + dx, L["top"]
    card = frost(c.img, (x0, top, x0 + CW, top + card_h), 26, tint=(14, 14, 17), tint_a=0.84, blur=7)
    card.alpha_composite(content)
    img = c.img.copy()
    stamp(img, card, x0 + CW / 2, top + card_h / 2, s=sc, a=a, shadow=0.45, blur=24, dy=14)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "dur": 8.0,
    "params": {},
    "note": "the items are your own key words; the tags are the real times you say each one",
    "needs": ["talk"],
}
