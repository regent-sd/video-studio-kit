"""Hands-On Classic graphics: a transparent 1080x1920 PNG sequence that build_reel.py lays over the cut, drawn in
the brand's colours and fonts (brands/<slug>/brand.json).

Event types (times in seconds on the reel's timeline):
  caption      {text, style: "block"|"plain", y}   "|" breaks a line. block = text on a block of the brand's
                                                   background colour, wiping in; plain = white with a soft shadow.
  tag          {text}                              an accent pill that slides in from the left (ingredients, temps)
  lower_third  {title, subtitle, y}                a name and role on a background block
  counter      {to, label}                         a big number counting up, a label under it (real numbers only)
  hook         {text, sub, panel}                  the big title in the first second; panel=true puts it on a
                                                   background-colour panel (for bright footage)
  endcard      {lines, brand, cta}                 background wash, logo, a line, the brand's name and its end line

Positions keep the reel safe zones clear: 220 px at the top, 450 px at the bottom, 35 px each side.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit import paths  # noqa: E402

sc = paths.sc
W, H, FPS = 1080, 1920, 30
HOOK_Y = 420          # centre of the title zone
TAG_Y = 650           # top of the line-of-sight zone
CAPTION_Y = 1075      # centre of the captions zone
LOWER_THIRD_Y = 1330  # below the captions, above the bottom zone


class Brand:
    """The colours and fonts the graphics use, from a brand.json."""

    def __init__(self, slug=None):
        b = sc.brand(slug)
        self.b = b
        self.bg = sc.color(b, "background")
        self.ink = sc.color(b, "text")
        self.accent = sc.color(b, "accent")
        self.highlight = sc.color(b, "highlight")
        self.title = sc.font(b, "title")
        self.heading = sc.font(b, "heading")
        self.caption = sc.font(b, "caption")
        self.body = sc.font(b, "body")
        self.number = sc.font(b, "number")
        self.name = b.get("name", "")
        self.handle = b.get("handle", "")
        self.end_line = b.get("end_card_line", "")
        self.logo = sc.logo(b)
        self.caption_style = (b.get("captions") or {}).get("on_footage", "block")

    def font(self, role, size):
        path, index = getattr(self, role)
        return ImageFont.truetype(path, size, index=index)


def ease_out_cubic(p):
    return 1 - (1 - p) ** 3


def ease_out_back(p, s=1.5):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


def fade(img, a):
    if a >= 0.999:
        return img
    r, g, b, al = img.split()
    return Image.merge("RGBA", (r, g, b, al.point(lambda v: int(v * max(0.0, a)))))


def tracked_width(d, text, f, tracking):
    return sum(d.textlength(c, font=f) for c in text) + tracking * max(0, len(text) - 1)


def draw_tracked(d, xy, text, f, fill, tracking):
    x, y = xy
    for c in text:
        d.text((x, y), c, font=f, fill=fill)
        x += d.textlength(c, font=f) + tracking


def text_layer(lines, f, fill, line_h, tracking=0, shadow=170, align="center", max_w=W - 70):
    """Lines of text with a soft drop shadow, on a transparent canvas sized to fit (shrunk to max_w)."""
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    widths = [tracked_width(probe, ln, f, tracking) for ln in lines]
    pad = 24
    w, h = int(max(widths)) + pad * 2, line_h * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d, sd = ImageDraw.Draw(img), ImageDraw.Draw(sh)
    for i, ln in enumerate(lines):
        x = pad + ((w - 2 * pad - widths[i]) / 2 if align == "center" else 0)
        y = pad + i * line_h
        if shadow:
            draw_tracked(sd, (x, y + 4), ln, f, (0, 0, 0, shadow), tracking)
        draw_tracked(d, (x, y), ln, f, fill, tracking)
    out = Image.alpha_composite(sh.filter(ImageFilter.GaussianBlur(6)), img) if shadow else img
    box = out.getbbox()
    if box:
        out = out.crop((max(0, box[0] - pad // 2), 0, min(w, box[2] + pad // 2), h))
    if out.width > max_w:
        out = out.resize((max_w, int(out.height * max_w / out.width)), Image.LANCZOS)
    return out


def logo_img(path, size):
    src = Image.open(path).convert("RGBA")
    src.thumbnail((size, size), Image.LANCZOS)
    return src


def rounded_block(w, h, color, alpha, radius):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=tuple(color) + (alpha,))
    return img


class Event:
    def __init__(self, ev, br: Brand):
        self.ev, self.start, self.end, self.br = ev, ev["start"], ev["end"], br

    def layers(self, t):
        """[(image, x, y)] for reel time t (only called while active)."""
        raise NotImplementedError


class Caption(Event):
    def __init__(self, ev, br):
        super().__init__(ev, br)
        lines = ev["text"].split("|")
        self.style = ev.get("style") or br.caption_style
        if self.style != "block":
            self.img = text_layer(lines, br.font("caption", 104), (255, 255, 255, 255), 122)
            return
        txt = text_layer(lines, br.font("caption", 70), tuple(br.ink) + (255,), 86, shadow=0)
        bw, bh = txt.width + 36, txt.height + 6
        block = rounded_block(bw, bh, br.bg, 240, 22)
        block.alpha_composite(txt, ((bw - txt.width) // 2, (bh - txt.height) // 2 + 2))
        self.img = block

    def layers(self, t):
        x = (W - self.img.width) // 2
        cy = self.ev.get("y", CAPTION_Y)
        if self.style != "block":
            return [(self.img, x, int(self.ev.get("y", H * 0.64)) - self.img.height // 2)]
        p_out = min(1.0, max(0.0, (self.end - t) / 0.15))
        if self.ev.get("anim") == "pop":   # word-for-word subtitles change fast: a quick fade and settle
            p = min(1.0, (t - self.start) / 0.08)
            y = cy - self.img.height // 2 + int((1 - ease_out_cubic(p)) * 8)
            return [(fade(self.img, p * p_out), x, y)]
        e = ease_out_cubic(min(1.0, (t - self.start) / 0.22))
        img = self.img
        if e < 1:   # wipe in from the left while rising slightly
            img = img.crop((0, 0, max(1, int(img.width * e)), img.height))
        y = cy - self.img.height // 2 + int((1 - e) * 16)
        return [(fade(img, p_out), x, y)]


class Tag(Event):
    def __init__(self, ev, br):
        super().__init__(ev, br)
        txt = text_layer([ev["text"]], br.font("caption", 52), tuple(br.bg) + (255,), 64, shadow=0)
        pill = rounded_block(txt.width + 20, txt.height - 6, br.accent, 242, (txt.height - 6) // 2)
        pill.alpha_composite(txt, (10, -3))
        self.img = pill

    def layers(self, t):
        p_in = min(1.0, (t - self.start) / 0.35)
        p_out = min(1.0, max(0.0, (self.end - t) / 0.22))
        x = int(-self.img.width + (70 + self.img.width) * ease_out_back(p_in)) - int((1 - p_out) * 40)
        return [(fade(self.img, p_out), x, self.ev.get("y", TAG_Y))]


class LowerThird(Event):
    def __init__(self, ev, br):
        super().__init__(ev, br)
        title = text_layer([ev["title"]], br.font("title", 84), tuple(br.ink) + (255,), 100, shadow=0, align="left")
        sub = text_layer([ev.get("subtitle", "").upper() or " "], br.font("caption", 32), tuple(br.accent) + (255,), 40,
                         tracking=4, shadow=0, align="left")
        w = max(title.width, sub.width) + 30
        h = title.height + sub.height - 30
        block = rounded_block(w, h, br.bg, 242, 20)
        block.alpha_composite(title, (14, -6))
        block.alpha_composite(sub, (16, title.height - 40))
        self.img = block

    def layers(self, t):
        p_in = ease_out_cubic(min(1.0, (t - self.start) / 0.4))
        p_out = min(1.0, max(0.0, (self.end - t) / 0.25))
        img = self.img.crop((0, 0, max(1, int(self.img.width * p_in)), self.img.height))
        return [(fade(img, p_out), 70, self.ev.get("y", LOWER_THIRD_Y) - self.img.height // 2)]


class Counter(Event):
    def __init__(self, ev, br):
        super().__init__(ev, br)
        self.to = int(ev["to"])
        self.count_dur = ev.get("count_dur", 0.9)
        self.f = br.font("number", 360)
        self.cache = {}
        self.label = text_layer([ev.get("label", "").upper() or " "], br.font("caption", 46), tuple(br.accent) + (255,), 56,
                                tracking=6, shadow=0)
        pw = max(self.number(self.to).width, self.label.width) + 80
        self.panel = rounded_block(pw, 470, br.bg, 238, 36)

    def number(self, n):
        if n not in self.cache:
            self.cache[n] = text_layer([str(n)], self.f, tuple(self.br.ink) + (255,), 380, shadow=0)
        return self.cache[n]

    def layers(self, t):
        p = min(1.0, (t - self.start) / self.count_dur)
        n = max(1, round(self.to * ease_out_cubic(p)))
        a = min(1.0, (t - self.start) / 0.15) * min(1.0, max(0.0, (self.end - t) / 0.2))
        num = self.number(n)
        la = min(1.0, max(0.0, (t - self.start - self.count_dur * 0.6) / 0.25))
        return [(fade(self.panel, a), (W - self.panel.width) // 2, HOOK_Y - 255),
                (fade(num, a), (W - num.width) // 2, HOOK_Y - num.height // 2 - 50),
                (fade(self.label, a * la), (W - self.label.width) // 2, HOOK_Y + 135)]


class Hook(Event):
    def __init__(self, ev, br):
        super().__init__(ev, br)
        self.panel, self.sub = None, None
        lines = ev["text"].split("|")
        if ev.get("panel"):   # dark type on a background-colour panel, for bright footage where light type won't read
            self.img = text_layer(lines, br.font("title", 120), tuple(br.ink) + (255,), 136, shadow=0)
            if ev.get("sub"):
                self.sub = text_layer([ev["sub"].upper()], br.font("caption", 36), tuple(br.accent) + (255,), 46, tracking=5, shadow=0)
            ph = self.img.height + (self.sub.height + 4 if self.sub else 0) + 70
            self.panel = rounded_block(min(W - 70, max(self.img.width, self.sub.width if self.sub else 0) + 110), ph, br.bg, 238, 36)
            return
        self.img = text_layer(lines, br.font("title", 132), (255, 255, 255, 255), 148, shadow=190)
        if ev.get("sub"):
            self.sub = text_layer([ev["sub"].upper()], br.font("caption", 40), (255, 255, 255, 255), 50, tracking=5)

    def layers(self, t):
        p = ease_out_cubic(min(1.0, (t - self.start) / 0.35))
        a = min(1.0, (t - self.start) / 0.25) * min(1.0, max(0.0, (self.end - t) / 0.2))
        s = 0.92 + 0.08 * p
        img = self.img.resize((int(self.img.width * s), int(self.img.height * s)), Image.BICUBIC) if s < 0.999 else self.img
        out = [(fade(img, a), (W - img.width) // 2, HOOK_Y - img.height // 2)]
        if self.panel:
            out.insert(0, (fade(self.panel, a), (W - self.panel.width) // 2, HOOK_Y - self.img.height // 2 - 30))
        if self.sub:
            out.append((fade(self.sub, a), (W - self.sub.width) // 2, HOOK_Y + self.img.height // 2 + 4))
        return out


class EndCard(Event):
    def __init__(self, ev, br):
        super().__init__(ev, br)
        self.wash = Image.new("RGBA", (W, H), tuple(br.bg) + (250,))
        self.logo = logo_img(br.logo, 340) if br.logo else None
        self.title = text_layer(ev.get("lines", br.name or " ").split("|"), br.font("title", 118), tuple(br.ink) + (255,), 132, shadow=0)
        brand = ev.get("brand", br.name)
        self.brand = text_layer([brand.upper()], br.font("caption", 38), tuple(br.accent) + (255,), 48, tracking=6, shadow=0) if brand else None
        cta = ev.get("cta", br.end_line)
        self.cta = text_layer([cta], br.font("heading", 46), tuple(br.ink) + (255,), 58, shadow=0) if cta else None

    def layers(self, t):
        lt = t - self.start

        def a(delay, dur=0.35):
            return min(1.0, max(0.0, (lt - delay) / dur))
        out = [(fade(self.wash, a(0, 0.4)), 0, 0)]
        y = 470 if self.logo else 620
        if self.logo:
            out.append((fade(self.logo, a(0.2)), (W - self.logo.width) // 2, y + int((1 - ease_out_cubic(a(0.2))) * 20)))
            y += self.logo.height + 40
        out.append((fade(self.title, a(0.4)), (W - self.title.width) // 2, y))
        y += self.title.height + 10
        if self.brand:
            out.append((fade(self.brand, a(0.6)), (W - self.brand.width) // 2, y))
            y += self.brand.height + 20
        if self.cta:
            out.append((fade(self.cta, a(0.8)), (W - self.cta.width) // 2, y))
        return out


KINDS = {"caption": Caption, "tag": Tag, "lower_third": LowerThird, "counter": Counter, "hook": Hook, "endcard": EndCard}


def render(events, duration, out_dir, brand=None):
    """Write out_dir/00000.png ... one frame per 1/30 s. Returns the ffmpeg input pattern."""
    br = brand if isinstance(brand, Brand) else Brand(brand)
    os.makedirs(out_dir, exist_ok=True)
    objs = [KINDS[e["type"]](e, br) for e in events]
    blank = os.path.join(out_dir, "blank.png")
    Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank)
    n = int(round(duration * FPS)) + 1
    for i in range(n):
        t = i / FPS
        path = os.path.join(out_dir, f"{i:05d}.png")
        if os.path.exists(path):
            os.unlink(path)
        active = [o for o in objs if o.start <= t < o.end]
        if not active:
            os.link(blank, path)
            continue
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for o in active:
            for img, x, y in o.layers(t):
                frame.alpha_composite(img, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))
        frame.save(path, compress_level=1)
    return os.path.join(out_dir, "%05d.png")


def sfx_events(events):
    """Sound-effect moments for the effects pass: only where the picture is silent and a graphic moves."""
    out = []
    for e in events:
        k = e.get("type")
        if k == "hook":
            out.append(dict(t=e["start"], type="whoosh", len=0.4))
        elif k == "tag":
            out.append(dict(t=e["start"], type="pop"))
        elif k == "counter":
            out += [dict(t=e["start"] + i * 0.08, type="tick") for i in range(8)]
        elif k == "lower_third":
            out.append(dict(t=e["start"], type="whoosh", len=0.3, g=0.6))
        elif k == "endcard":
            out.append(dict(t=e["start"], type="whoosh", len=0.4))   # no chime: end cards stay quiet
    return sorted(({**x, "t": round(x["t"], 3)} for x in out), key=lambda x: x["t"])
