"""Fast Cut graphics: the animated pieces the layouts show. Each is drawn in a skin, takes reel times for when
things appear (the moment the word is said), and is called with the reel time: g(t) -> RGBA image.

    shape "panel"  1080 x 960, the top of a split screen:      Hook, ListPanel
    shape "card"   a floating card, placed in 3D by the engine: Checklist, StatCard
    shape "full"   1080 x 1920, in place of the footage:       BigNumber, Compare, Slam, Mosaic, EndCard

g.events lists sound-effect moments [{"t", "type"}] (pop, whoosh, tick, hit, click) for the effects pass.
g.texts lists every word put on screen, so the engine can flag text nobody said.

Honesty: numbers on screen are only real ones (said in the video or confirmed). With no real number, show a flag
("LOW", "up", a check) instead of a made-up value.
"""
from __future__ import annotations

import functools
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit import draw  # noqa: E402
from stylekit.draw import (SS, back, clamp01, comp, comp_c, decay, ease_io, ease_out, lerp, place, prog,  # noqa: E402
                           text_img)

W, H = 1080, 1920


class Graphic:
    shape = "full"

    def __init__(self, skin):
        self.skin = skin
        self.events: list[dict] = []
        self.texts: list[str] = []

    def ev(self, t, kind, **kw):
        self.events.append(dict(t=round(float(t), 3), type=kind, **kw))

    def say(self, *txt):
        self.texts += [str(x) for x in txt if x]

    def __call__(self, t):
        raise NotImplementedError


def T(skin, role, txt, size, fill, track=0):
    return text_img(txt, skin[role], size, fill, track)


# ---------------------------------------------------------------- panels (top of a split screen)
class Hook(Graphic):
    """The opening title: up to three short lines popping in one after another. hot = the line in the accent
    colour (0-based). sub = a small pill under it (the brand's name, a place)."""
    shape = "panel"

    def __init__(self, skin, lines, at=0.0, hot=1, sub=None):
        super().__init__(skin)
        self.lines, self.at, self.hot, self.sub = list(lines)[:3], at, hot, sub
        self.say(*self.lines, sub)
        self.ev(at, "whoosh", len=0.4)

    def __call__(self, t):
        s = self.skin
        cv = s.bg_top.copy()
        n = len(self.lines)
        size = 150 if max(len(x) for x in self.lines) <= 10 else 118 if max(len(x) for x in self.lines) <= 14 else 96
        y0 = 480 - (n - 1) * size * 0.58
        for k, txt in enumerate(self.lines):
            p = ease_out(prog(t, self.at - 0.25 + 0.08 * k, 0.3))
            col = s.hot if k == self.hot and n > 1 else s.panel_text
            im = draw.fit_text(txt, s.title, size, col, 980)
            pulse = 1 + 0.05 * math.sin(math.pi * prog(t, self.at + 0.8, 0.3)) if k == self.hot else 1
            comp_c(cv, im, W / 2, y0 + k * size * 1.16 + 50 * (1 - p), pulse, p)
        if self.sub:
            c = SS(W, 140)
            draw.pill(c, W / 2, 70, self.sub, s.body, 34, s.tag_bg, s.tag_fg, back(prog(t, self.at + 0.5, 0.32)))
            comp(cv, c.out(), 0, y0 + n * size * 1.16 + 10)
        return cv


class ListPanel(Graphic):
    """A heading and up to four rows that slide in as each is said: rows [(text, at)]."""
    shape = "panel"

    def __init__(self, skin, heading, rows, at):
        super().__init__(skin)
        self.heading, self.rows, self.at = heading, list(rows)[:4], at
        self.say(heading, *[r[0] for r in self.rows])
        for txt, a in self.rows:
            self.ev(a, "pop")

    def __call__(self, t):
        s = self.skin
        c = SS(W, 960)
        c.im.paste(s.bg_top.resize((W * 2, 960 * 2)), (0, 0))
        a = ease_out(prog(t, self.at, 0.3))
        c.text((80 - 40 * (1 - a), 150), self.heading, s.heading, 66, s.panel_text)
        c.rr((80, 236, 80 + 120 * a, 244), 4, fill=s.hot)
        n = len(self.rows)
        for i, (txt, at) in enumerate(self.rows):
            e = ease_out(prog(t, at - 0.05, 0.4))
            dx = (1 - e) * 1100
            y = 300 + i * (560 / max(n, 1))
            hgt = min(150, 560 / max(n, 1) - 24)
            c.rr((80 + dx, y, 1000 + dx, y + hgt), 34, fill=s.panel_card, outline=s.panel_line, width=2)
            draw.check(c, 160 + dx, y + hgt / 2, 34, s.hot, s.card if s.name == "dark" else s.background, back(prog(t, at, 0.3)))
            c.text((228 + dx, y + hgt / 2), txt, s.heading, 48, s.panel_text, anchor="lm")
        return c.out()


# ---------------------------------------------------------------- cards (floating, placed in 3D by the engine)
class Checklist(Graphic):
    """A card whose rows fill in as they're said: grey placeholder rows until then, then the words and a check.
    rows [(text, at)] or [(text, at, value)]: value only when it's a real number that was said."""
    shape = "card"

    def __init__(self, skin, title, rows, sub=None, badge=None, badge_at=None):
        super().__init__(skin)
        self.title, self.sub, self.rows, self.badge, self.badge_at = title, sub, list(rows)[:5], badge, badge_at
        self.say(title, sub, badge, *[r[0] for r in self.rows], *[r[2] for r in self.rows if len(r) > 2])
        for r in self.rows:
            self.ev(r[1], "click")

    def __call__(self, t):
        s = self.skin
        n = len(self.rows)
        w, h = 900, 230 + n * 150
        c = SS(w, h)
        c.rr((0, 0, w, h), 44, fill=s.card)
        c.text((56, 54), self.title, s.heading, 54, s.ink)
        if self.sub:
            c.text((58, 124), self.sub, s.body, 30, s.muted)
        if self.badge:
            on = self.badge_at is None or t >= self.badge_at
            draw.pill(c, w - 140, 92, self.badge, s.body, 28, s.good_soft if on else s.skel, s.good_ink if on else s.muted,
                      back(prog(t, self.badge_at or 0, 0.3)) if on else 1.0)
        c.rr((40, 180, w - 40, 182), 0, fill=s.card_line)
        for i, r in enumerate(self.rows):
            txt, at = r[0], r[1]
            val = r[2] if len(r) > 2 else None
            y = 200 + i * 150
            if t < at - 0.04:
                draw_skeleton(c, s, 56, y + 50, w - 200, y + 80, t, i * 0.37)
                c.circ(w - 100, y + 65, 32, outline=s.card_line, width=6)
            else:
                e = ease_out(prog(t, at - 0.04, 0.25))
                c.text((56 + 30 * (1 - e), y + 65), txt, s.heading, 50, s.ink, anchor="lm")
                if val:
                    c.text((w - 160, y + 65), str(val), s.body, 40, s.muted, anchor="rm")
                draw.check(c, w - 100, y + 65, 32, s.hot, s.card, back(prog(t, at - 0.04, 0.3)))
            if i < n - 1:
                c.rr((40, y + 140, w - 40, y + 141), 0, fill=s.card_line)
        return c.out()


def draw_skeleton(c, s, x0, y0, x1, y1, t, phase=0.0):
    c.rr((x0, y0, x1, y1), (y1 - y0) / 2, fill=s.skel)
    u = ((t * 0.8 + phase) % 1.6) - 0.3
    sx = x0 + u * (x1 - x0)
    a, b = max(x0, sx - 70), min(x1, sx + 70)
    if b > a:
        c.rr((a, y0, b, y1), (y1 - y0) / 2, fill=s.skel_hi)


class StatCard(Graphic):
    """A card with one value that counts up and a bar that fills: StatCard(skin, "Real progress", "100%", at).
    Only a real, said number."""
    shape = "card"

    def __init__(self, skin, title, value, at, done_at=None):
        super().__init__(skin)
        self.title, self.value, self.at, self.done_at = title, str(value), at, done_at
        self.say(title, value)
        self.ev(at, "whoosh", len=0.3)
        if done_at:
            self.ev(done_at, "pop")

    def __call__(self, t):
        s = self.skin
        w, h = 900, 600
        c = SS(w, h)
        c.rr((0, 0, w, h), 44, fill=s.card)
        c.text((56, 56), self.title, s.heading, 54, s.ink)
        u = ease_io(prog(t, self.at, 0.62))
        c.text((52, 168), count_text(self.value, u), s.number, 176, s.good if u >= 1 else s.ink)
        c.rr((56, 470, w - 56, 506), 18, fill=s.skel)
        c.rr((56, 470, 56 + (w - 112) * max(0.04, u), 506), 18, fill=s.good)
        if self.done_at:
            draw.check(c, w - 120, 110, 58, s.good, s.card, back(prog(t, self.done_at, 0.32)))
        return c.out()


def count_text(value, u):
    """The value with its leading number counted up to u (0..1): "880 g" at 0.5 -> "440 g"."""
    m = re.match(r"^([^\d]*)(\d[\d,]*(?:\.\d+)?)(.*)$", str(value))
    if not m:
        return str(value)
    raw = m[2].replace(",", "")
    target = float(raw)
    dec = len(raw.split(".")[1]) if "." in raw else 0
    v = target * u
    num = f"{v:,.{dec}f}" if "," in m[2] else f"{v:.{dec}f}"
    if u >= 1:
        num = m[2]
    return f"{m[1]}{num}{m[3]}"


# ---------------------------------------------------------------- full-screen graphics
class BigNumber(Graphic):
    """A big number that counts up as it's said, with a ring that fills, and a label under it.
    BigNumber(skin, "375°F", at, "in the oven"). Only a real number."""

    def __init__(self, skin, value, at, label=None, ring=True, dark=False):
        super().__init__(skin)
        self.value, self.at, self.label, self.ring, self.dark = str(value), at, label, ring, dark
        self.say(value, label)
        for k in range(6):
            self.ev(at + k * 0.06, "tick")

    def __call__(self, t):
        s = self.skin
        dark = self.dark and s.name == "dark"
        cv = (s.bg_alt if dark else s.bg).copy()
        ink = s.end_text if dark else s.ink
        u = ease_out(prog(t, self.at, 0.5))
        txt = count_text(self.value, u)
        size = 420 if len(self.value) <= 2 else 300 if len(self.value) <= 4 else 220 if len(self.value) <= 6 else 160
        pop = 1 + 0.10 * (1 - ease_out(prog(t, self.at + 0.5, 0.16)))
        if self.ring:
            comp_c(cv, draw.ring(330, u, 26, s.card_line if not dark else (60, 63, 70), s.hot), 540, 800)
        comp_c(cv, draw.fit_text(txt, s.number, size, ink, 600 if self.ring else 960), 540, 800, pop)
        if self.label:
            comp_c(cv, draw.fit_text(self.label.upper(), s.body, 62, ink, 900, track=10), 540, 1250, 1.0,
                   ease_out(prog(t, self.at + 0.15, 0.25)))
        return cv


class Compare(Graphic):
    """A tiny explainer: two tiles side by side, one gets a check and the other a cross, as each is said.
    Compare(skin, ("Fold", 3.1), ("Mix", 3.6), winner=0)."""

    def __init__(self, skin, left, right, winner=0, heading=None, at=None):
        super().__init__(skin)
        self.left, self.right, self.winner, self.heading = left, right, winner, heading
        self.at = at if at is not None else min(left[1], right[1]) - 0.3
        self.say(left[0], right[0], heading)
        self.ev(left[1], "pop")
        self.ev(right[1], "pop")

    def __call__(self, t):
        s = self.skin
        cv = s.bg.copy()
        if self.heading:
            comp_c(cv, draw.fit_text(self.heading, s.heading, 70, s.ink, 960), 540, 560, 1, ease_out(prog(t, self.at, 0.3)))
        for k, (txt, at) in enumerate((self.left, self.right)):
            e = back(prog(t, at - 0.25, 0.35))
            if prog(t, at - 0.25, 0.35) <= 0:
                continue
            c = SS(420, 470)
            c.rr((0, 0, 420, 470), 40, fill=s.card)
            c.text((210, 120), txt, s.heading, 72, s.ink, anchor="mm")
            win = k == self.winner
            p = back(prog(t, at, 0.3))
            (draw.check if win else draw.cross)(c, 210, 310, 74, s.ink if win else s.bad, s.card, p)
            place(cv, c.out(), 290 + k * 500, 960, 0.6 + 0.4 * e, rz=(-3 if k else 3) * (1 - clamp01(e)), shadow=0.25,
                  a=clamp01(prog(t, at - 0.25, 0.1)))
        return cv


class Slam(Graphic):
    """One or two big words that slam in with a shake: for a hard word ("tanked") or a title between parts."""

    def __init__(self, skin, text, at, sub=None, dark=False):
        super().__init__(skin)
        self.text, self.at, self.sub, self.dark = text, at, sub, dark
        self.say(text, sub)
        self.ev(at, "hit")

    def __call__(self, t):
        s = self.skin
        dark = self.dark and s.name == "dark"
        cv = (s.bg_alt if dark else s.bg).copy()
        ink = s.end_text if dark else s.ink
        p = ease_out(prog(t, self.at, 0.16))
        sh = 14 * math.sin((t - self.at) * 60) * decay(t, self.at + 0.16, 8) if t > self.at + 0.16 else 0
        if t >= self.at - 0.02:
            comp_c(cv, draw.fit_text(self.text, s.title, 230, ink, 980), 540 + sh, 880, lerp(1.45, 1.0, p), clamp01(p * 2))
        if self.sub:
            comp_c(cv, draw.fit_text(self.sub, s.body, 60, s.hot, 900), 540, 1100, 1, ease_out(prog(t, self.at + 0.2, 0.25)))
        return cv


class Mosaic(Graphic):
    """A 3 x 4 grid of stills popping in about 0.06 s apart, then a soft flash: "everything came together".
    tiles: up to 12 PIL images (any size; cropped to fill)."""
    TW, TH = 328, 450
    ORDER = [4, 9, 1, 6, 11, 2, 7, 0, 10, 3, 8, 5]

    def __init__(self, skin, tiles, at):
        super().__init__(skin)
        self.at = at
        self.tiles = [draw.rounded(_fill(im, self.TW, self.TH), 26) for im in list(tiles)[:12]]
        for rank in range(len(self.tiles)):
            self.ev(at + rank * 0.055, "pop", g=0.4)

    def __call__(self, t):
        s = self.skin
        cv = s.bg_alt.copy()
        end = self.at + len(self.tiles) * 0.055 + 0.2
        q = prog(t, end, 0.4)
        pulse = -0.06 * math.sin(math.pi * q) if 0 < q < 1 else 0
        order = [k for k in self.ORDER if k < len(self.tiles)]
        for rank, k in enumerate(order):
            t0 = self.at + rank * 0.055
            if t < t0:
                continue
            p = back(prog(t, t0, 0.3))
            col, row = k % 3, k // 3
            cx = 24 + self.TW / 2 + col * (self.TW + 24)
            cy = 24 + self.TH / 2 + row * (self.TH + 24)
            place(cv, self.tiles[k], cx, cy, (0.55 + 0.45 * p) * (1 + pulse), rz=(rank % 3 - 1) * 4 * (1 - clamp01(p)),
                  shadow=0, a=clamp01(prog(t, t0, 0.1)))
        if 0 < q < 1:
            cv.alpha_composite(draw.Image.new("RGBA", (W, H), (255, 255, 255, int(60 * math.sin(math.pi * q)))))
        return cv


def _fill(im, w, h):
    im = im.convert("RGB")
    r = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * r + 0.5)), max(h, int(im.height * r + 0.5))), draw.Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


@functools.lru_cache(None)
def _logo(path, size, tint):
    im = draw.Image.open(path).convert("RGBA")
    im.thumbnail((size, size), draw.Image.LANCZOS)
    if tint:
        out = draw.Image.new("RGBA", im.size, tuple(tint) + (255,))
        out.putalpha(im.getchannel("A"))
        return out
    return im


class EndCard(Graphic):
    """The close: logo (the brand's, if it has one), a line or two, the handle and the brand's end line.
    Quiet: no chime under it by default."""

    def __init__(self, skin, lines=None, at=0.0, handle=True, end_line=True, logo=True):
        super().__init__(skin)
        b = skin.brand
        self.at = at
        self.lines = list(lines or [])
        self.handle = b.get("handle") if handle else None
        self.end_line = b.get("end_card_line") if end_line else None
        self.logo = None
        if logo:
            lp = Path(b["dir"]) / b["logo"] if b.get("logo") else None
            if lp and lp.exists():
                self.logo = str(lp)
        self.say(*self.lines, self.handle, self.end_line)
        self.ev(at, "whoosh", len=0.4)

    def __call__(self, t):
        s = self.skin
        cv = s.bg_alt.copy()
        ink = s.end_text
        y = 620
        if self.logo:
            im = _logo(self.logo, 300, None)
            comp_c(cv, im, 540, 500, lerp(0.7, 1, back(prog(t, self.at, 0.35))), clamp01(prog(t, self.at, 0.15)))
            y = 760
        elif s.brand.get("name") and s.name == "brand":
            comp_c(cv, draw.fit_text(s.brand["name"].upper(), s.body, 40, s.hot, 900, track=8), 540, 520, 1,
                   ease_out(prog(t, self.at, 0.3)))
        for k, ln in enumerate(self.lines[:2]):
            p = ease_out(prog(t, self.at + 0.15 + 0.1 * k, 0.3))
            comp_c(cv, draw.fit_text(ln, s.title, 120, ink, 960), 540, y + k * 150 + 30 * (1 - p), 1, p)
        y += max(1, len(self.lines[:2])) * 150 + 40
        if self.handle:
            c = SS(W, 140)
            draw.pill(c, 540, 70, self.handle, s.body, 42, s.tag_bg if s.name == "brand" else s.accent,
                      s.tag_fg if s.name == "brand" else s.on_accent, back(prog(t, self.at + 0.45, 0.3)))
            comp(cv, c.out(), 0, y)
            y += 150
        if self.end_line:
            comp_c(cv, draw.fit_text(self.end_line, s.body, 46, s.end_muted, 900), 540, y + 30, 1,
                   ease_out(prog(t, self.at + 0.7, 0.3)))
        return cv
