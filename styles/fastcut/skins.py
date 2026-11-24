"""Fast Cut skins: the colours, fonts and caption look the engine and graphics draw with.

    dark()            Dark skin: SF Pro, dark split-screen panels, white cards on light grey, yellow keywords.
                      For personal, talking-to-camera content. The same on every brand.
    brand("my-brand") Brand skin: everything from brands/<slug>/brand.json: background, text, accent tags,
                      highlight behind keywords, the brand's fonts, its caption style, its grade and logo.
                      Plain backgrounds are always the brand's light "background" colour.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit import draw, paths  # noqa: E402

sc = paths.sc
W, H = 1080, 1920
SFP = draw.SFP


class Skin(dict):
    """A dict with attribute access. Colours are RGB tuples; fonts are (path, index, weight) specs."""
    __getattr__ = dict.__getitem__

    def font(self, role, size, weight=None):
        return draw.F(self[role], size, weight)


def mix(a, b, u):
    return tuple(int(round(x + (y - x) * u)) for x, y in zip(a, b))


def _backgrounds(light, light2, top_in, top_out):
    return dict(bg=draw.radial(W, H, light, light2), bg_top=draw.radial(W, 960, top_in, top_out, cy=0.5))


def dark(brand_slug=None) -> Skin:
    """The Dark skin. The brand (for the end card's name, handle and logo) is the default one unless named."""
    b = sc.brand(brand_slug)
    s = Skin(
        name="dark", brand=b,
        ink=(17, 17, 19), muted=(138, 138, 146), card=(255, 255, 255), card_line=(232, 232, 236),
        skel=(236, 236, 240), skel_hi=(248, 248, 251), accent=(255, 214, 10), on_accent=(17, 17, 19),
        hot=(255, 59, 48), tag_bg=(255, 255, 255), tag_fg=(17, 17, 19), good=(40, 190, 105),
        good_soft=(225, 246, 234), good_ink=(30, 140, 80), bad=(255, 59, 48), bad_soft=(255, 224, 220),
        highlight=(255, 214, 10), panel_text=(255, 255, 255), panel_muted=(150, 153, 162),
        panel_card=(24, 26, 31), panel_line=(46, 49, 56), end_text=(255, 255, 255), end_muted=(150, 153, 162),
        title=(SFP, 0, 860), heading=(SFP, 0, 760), body=(SFP, 0, 600), number=(SFP, 0, 860), caption=(SFP, 0, 720),
        cap_footage="shadow", cap_plain="highlight", grade="punchy", flash=(255, 20, 10),
    )
    s.update(_backgrounds((252, 252, 250), (234, 233, 229), (30, 32, 38), (8, 9, 11)))
    s["bg_alt"] = draw.radial(W, H, (30, 32, 38), (8, 9, 11))      # big numbers, mosaic and end card
    return s


def brand(slug=None) -> Skin:
    """The Brand skin, from brands/<slug>/brand.json (the default brand when slug is None)."""
    b = sc.brand(slug)
    c = lambda role: sc.color(b, role)
    f = lambda role, wt: tuple(sc.font(b, role)) + (wt,)
    bg, text, surface = c("background"), c("text"), c("surface")
    caps = b.get("captions") or {}
    s = Skin(
        name="brand", brand=b,
        ink=text, muted=c("muted"), card=surface, card_line=mix(surface, text, 0.10),
        skel=mix(surface, text, 0.07), skel_hi=mix(surface, text, 0.02), accent=c("highlight"), on_accent=text,
        hot=c("accent"), tag_bg=c("accent"), tag_fg=bg, good=c("good"), good_soft=mix(surface, c("good"), 0.15),
        good_ink=c("good"), bad=c("bad"), bad_soft=mix(surface, c("bad"), 0.15), highlight=c("highlight"),
        panel_text=text, panel_muted=c("muted"), panel_card=surface, panel_line=mix(surface, text, 0.10),
        end_text=text, end_muted=c("muted"),
        title=f("title", 800), heading=f("heading", 700), body=f("body", 600), number=f("number", 800),
        caption=f("caption", 700),
        cap_footage=caps.get("on_footage", "block"), cap_plain=caps.get("keyword_style", "highlight"),
        cap_keyword=caps.get("keyword_style", "highlight"),
        grade=b.get("grade", "warm"), flash=c("accent"),
    )
    s.update(_backgrounds(mix(bg, (255, 255, 255), 0.25), mix(bg, text, 0.05), mix(bg, (255, 255, 255), 0.25), mix(bg, text, 0.05)))
    s["bg_alt"] = s["bg"]   # the brand's light background everywhere: never a dark or accent fill
    s["background"] = bg
    return s


def get(name="dark", brand_slug=None) -> Skin:
    """A skin by name: "dark" or "brand"."""
    if name == "brand":
        return brand(brand_slug)
    if name == "dark":
        return dark(brand_slug)
    raise SystemExit(f"No Fast Cut skin '{name}'. Skins: dark, brand.")
