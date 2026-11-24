#!/usr/bin/env python3
"""Reel covers for any style: a 1080x1920 JPG from a frame of a video (or a photo), with a title.

    .venv/bin/python styles/cover.py <video or photo> --at 3.2 --title "MY BIG|TITLE" [options]
        --title "A|B"      the title; "|" breaks a line
        --hot N            which line is in the accent colour (default: the last; -1 for none)
        --sub "..."        a smaller line under the title
        --pill "..."       a label in a pill under that
        --skin dark|brand  dark: bold white type over a shade, accent line (default)
                           brand: the brand's title font on a block of its background colour
        --brand SLUG       which brand (default: the default brand)
        --place top|middle|bottom   where the words sit inside the grid band (default: top)
        --pop              the person stands in front of the title (Apple Vision cutout; needs a person)
        --out FILE         default: "<video> - cover.jpg" beside the video (never overwrites: "- cover 2.jpg"...)

Everything that matters sits inside the profile grid's 3:4 band (y 240 to 1680), which is all the grid shows.
It also writes a preview of the full cover beside its grid crop to the work folder (work/covers/), and prints both.
The cover's words are text someone wrote: flag them for approval like any on-screen text.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stylekit import draw, media, paths  # noqa: E402

sc = paths.sc
W, H = 1080, 1920
BAND = (240, 1680)


def look(skin, brand=None):
    b = sc.brand(brand)
    if skin == "brand":
        title = tuple(sc.font(b, "title")) + (800,)
        return dict(name="brand", title=title, body=tuple(sc.font(b, "body")) + (650,), ink=sc.color(b, "text"),
                    hot=sc.color(b, "accent"), panel=sc.color(b, "background"), pill_bg=sc.color(b, "accent"),
                    pill_fg=sc.color(b, "background"), grade=b.get("grade", "warm"))
    return dict(name="dark", title=(draw.SFP, 0, 900), body=(draw.SFP, 0, 760), ink=(255, 255, 255),
                hot=(255, 214, 10), panel=None, pill_bg=(255, 255, 255), pill_fg=(17, 17, 19), grade="punchy")


def words(txt, spec, size, col, maxw=980, stroke=0, stroke_col=(0, 0, 0)):
    f = draw.F(spec, size)
    tw = f.getlength(txt)
    asc, desc = f.getmetrics()
    pad = stroke + 20
    im = Image.new("RGBA", (int(tw) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((pad, pad), txt, font=f, fill=col, stroke_width=stroke, stroke_fill=stroke_col)
    im = im.crop(im.getbbox() or (0, 0, 1, 1))
    if im.width > maxw:
        im = im.resize((maxw, int(im.height * maxw / im.width)), Image.LANCZOS)
    return im


def shadowed(im, blur=18, alpha=0.65, dy=10):
    sh = Image.new("RGBA", (im.width + 80, im.height + 80), (0, 0, 0, 0))
    a = Image.new("L", sh.size, 0)
    a.paste(im.getchannel("A"), (40, 40 + dy))
    sh.putalpha(a.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * alpha)))
    sh.alpha_composite(im, (40, 40))
    return sh


def frame(src, at, lk, room=0.12):
    if Path(src).suffix.lower() in paths.IMAGE_EXT:
        im = Image.open(src).convert("RGB")
        r = max(W / im.width, H / im.height)
        im = im.resize((int(im.width * r + 0.5), int(im.height * r + 0.5)), Image.LANCZOS)
        x, y = (im.width - W) // 2, (im.height - H) // 2
        return im.crop((x, y, x + W, y + H)).convert("RGBA")
    box, _ = media.frame_for(src, "full", room=room)
    return media.still(src, at, box, (W, H), lk["grade"]).convert("RGBA")


def make(src, at=1.0, title="", hot=None, sub=None, pill=None, skin="dark", brand=None, place="top", pop=False):
    lk = look(skin, brand)
    fr = frame(src, at, lk, room=0.34 if pop else 0.12)   # pop-out: the head lower, so the title has room above it
    cv = fr.copy()
    lines = [x for x in title.split("|") if x.strip()] or [" "]
    hot = len(lines) - 1 if hot is None else hot
    size = 150 if max(len(x) for x in lines) <= 9 else 118 if max(len(x) for x in lines) <= 13 else 96
    layers = []
    for k, ln in enumerate(lines):
        col = lk["hot"] if k == hot else lk["ink"]
        if lk["name"] == "dark":
            layers.append(shadowed(words(ln.upper(), lk["title"], size, col)))
        else:
            layers.append(words(ln, lk["title"], size, col))
    if sub:
        layers.append(shadowed(words(sub, lk["body"], 54, lk["ink"]), alpha=0.9) if lk["name"] == "dark"
                      else words(sub, lk["body"], 50, lk["ink"]))
    block_h = sum(l.height for l in layers) + 12 * (len(layers) - 1) + (130 if pill else 0)
    y0 = {"top": BAND[0] + 60, "middle": (BAND[0] + BAND[1] - block_h) // 2, "bottom": BAND[1] - 60 - block_h}[place]
    m = None
    if pop:
        m = media.person_mask(fr.convert("RGB"), media.key("cover", str(src), at))
        if m is None:
            print("  --pop: no person found in that frame, so the title stays in front")
        else:   # the title's lower part tucks behind the top of the head
            import numpy as np
            rows = np.nonzero(np.asarray(m).max(axis=1) > 128)[0]
            if len(rows):
                y0 = max(BAND[0] + 10, int(rows[0]) - int(block_h * 0.45))
                if int(rows[0]) - y0 < block_h * 0.35:
                    print("  --pop: little room above the head in this frame, so the head covers much of the title. "
                          "Pick a frame with more space above the head, or a shorter title.")
    if lk["name"] == "dark":   # a shade behind the words
        if place == "bottom":
            cv.alpha_composite(draw.vgrad(W, H, 0, 220, y0 - 250, BAND[1]))
        else:
            cv.alpha_composite(draw.vgrad(W, H, 210, 0, 0, y0 + block_h + 250))
    else:                       # a block of the brand's background colour behind the words
        pw = min(W - 70, max(l.width for l in layers) + 110)
        blk = Image.new("RGBA", (pw + 80, block_h + 140), (0, 0, 0, 0))
        ImageDraw.Draw(blk).rounded_rectangle([40, 50, pw + 40, block_h + 110], radius=40, fill=(0, 0, 0, 80))
        cv.alpha_composite(blk.filter(ImageFilter.GaussianBlur(20)), ((W - pw) // 2 - 40, y0 - 70))
        p = Image.new("RGBA", (pw, block_h + 70), (0, 0, 0, 0))
        ImageDraw.Draw(p).rounded_rectangle([0, 0, pw - 1, block_h + 69], radius=40, fill=tuple(lk["panel"]) + (245,))
        cv.alpha_composite(p, ((W - pw) // 2, y0 - 35))
    y = y0
    title_bottom = y0
    for k, l in enumerate(layers):
        cv.alpha_composite(l, ((W - l.width) // 2, y))
        y += l.height + 12
        if k < len(lines):
            title_bottom = y
    if pill:
        c = draw.SS(W, 130)
        draw.pill(c, W / 2, 65, pill, lk["body"], 48, lk["pill_bg"], lk["pill_fg"], padx=40)
        cv.alpha_composite(c.out(), (0, y + 10))
    if m is not None:   # the person comes forward, in front of the title
        m = m.point(lambda v: 255 if v > 140 else (0 if v < 60 else int((v - 60) * 255 / 80)))
        band = Image.new("L", (W, H), 0)
        band.paste(255, (0, 0, W, title_bottom + 40))   # only the head and shoulders come forward
        m = Image.composite(m, Image.new("L", (W, H), 0), band.filter(ImageFilter.GaussianBlur(30)))
        sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sh.putalpha(m.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.55)))
        cv.alpha_composite(sh, (0, 10))
        head = fr.copy()
        head.putalpha(m)
        cv.alpha_composite(head)
    return cv.convert("RGB")


def grid_preview(im):
    """The full cover next to the profile grid's 3:4 crop."""
    full = im.resize((360, 640), Image.LANCZOS)
    grid = im.crop((0, BAND[0], W, BAND[1])).resize((360, 480), Image.LANCZOS)
    t = Image.new("RGB", (740, 640), (40, 40, 40))
    t.paste(full, (0, 0))
    t.paste(grid, (380, 80))
    return t


def out_path(src, out=None):
    if out:
        o = Path(out).expanduser()
        if o.exists():
            raise SystemExit(f"{o} already exists; pick another name.")
        return o
    src = Path(src)
    k, o = 1, src.with_name(f"{src.stem} - cover.jpg")
    while o.exists():
        k += 1
        o = src.with_name(f"{src.stem} - cover {k}.jpg")
    return o


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("--at", type=float, default=1.0)
    ap.add_argument("--title", required=True)
    ap.add_argument("--hot", type=int)
    ap.add_argument("--sub")
    ap.add_argument("--pill")
    ap.add_argument("--skin", default="dark", choices=["dark", "brand"])
    ap.add_argument("--brand")
    ap.add_argument("--place", default="top", choices=["top", "middle", "bottom"])
    ap.add_argument("--pop", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    im = make(a.src, a.at, a.title, a.hot, a.sub, a.pill, a.skin, a.brand, a.place, a.pop)
    o = out_path(a.src, a.out)
    im.save(o, quality=93)
    gp = paths.work_dir("covers") / f"{Path(o).stem} - grid preview.jpg"
    grid_preview(im).save(gp, quality=90)
    print(o)
    print(gp)


if __name__ == "__main__":
    main()
