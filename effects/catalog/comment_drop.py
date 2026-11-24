"""Comment drop: a comment box slides up and one of your words is typed and posted; comment cards then drop in
from the top one by one, and the word lands huge behind your head."""
import math
import numpy as np
from PIL import Image, ImageFilter, ImageDraw
from core import (W, H, FPS, SS, font, SFP, ease_out, ease_io, ease_in, back, prog, lerp, clamp, clamp01, text_img,
                  scaled, comp)
from ._ui import (phases, put, stamp, frost, avatar, initials_avatar, heart, clean, label_img, fit_text, wrap, seeded,
                  IOS_BLUE, IOS_RED)

NAME = "comment-drop"
KIND = "cards"
ABOUT = "A comment is typed and posted, comment cards drop in from the top, and the word lands huge behind your head"
DUR = 5.0
PARAMS = dict(
    comments=None,    # [{"user": "you", "text": "better"}, {"user": "...", "text": "...", "likes": 3}, ...]
                      #   the first is the one typed and posted; "you" gets your face as the avatar.
                      #   likes: shown under the heart only if given. Default: one comment by "you" with a key word you say.
    big_word=None,    # the huge word behind your head; default the typed word ("" for none)
    style="light",    # light (white cards) | dark
    placeholder="Add a comment…",
    max_cards=3,      # most cards on screen; older ones slide away
)
CW, AVD, GAP = 880, 68, 14
BLUE = (0, 149, 246)

def _setup(c):
    cs = c.p.get("comments")
    if cs:
        cs = [dict(user=str(x.get("user", "you")), text=str(x.get("text", "")), likes=x.get("likes")) for x in cs]
    else:
        w = c.word_text()
        cs = [dict(user="you", text=w.lower() if w else "", likes=None)] if w else []
    typed = cs[0]["text"] if cs else ""
    big = c.p.get("big_word")
    big = typed if big is None else str(big)
    big = clean(big.split()[0]).upper() if big.strip() else ""
    # schedule (seconds into the effect), squeezed for short windows
    d = c.d
    tin = min(0.45, d * 0.18)
    ty0 = tin + 0.08
    # if the word is said later in the window, type it so it lands as it's said
    said = next((w for w in c.words_in() if typed and clean(w["w"]).lower() == clean(typed.split()[0]).lower()), None)
    dt = clamp((d * 0.3) / max(1, len(typed)), 0.035, 0.085)
    if said: ty0 = clamp(said["s"] - c.t0 - dt * len(typed) * 0.6, ty0, max(ty0, d * 0.45))
    ty1 = ty0 + dt * len(typed)
    post = ty1 + min(0.3, d * 0.06)
    tout = min(0.45, d * 0.15)
    rest = max(0.2, d - tout - post - 0.4)
    step = min(0.9, rest / (len(cs) - 1)) if len(cs) > 1 else 0
    drops = [post + 0.12 + step * k for k in range(len(cs))]
    # layout: cards stack from the top, down to just above your head
    i0 = int(c.t0 * FPS); i1 = max(i0 + 1, int(c.t1 * FPS))
    fs = c.subj.faces[i0:i1] if len(c.subj.faces[i0:i1]) else np.array([c.face], np.float32)
    head = float(np.percentile(fs[:, 1] - 0.85 * fs[:, 3], 10))
    chin = float(np.percentile(fs[:, 1] + 0.62 * fs[:, 3], 80))
    fcy, ffh = float(np.median(fs[:, 1])), float(np.median(fs[:, 3]))
    cards = [_card(c, x) for x in cs]
    hmin = min([cd["h"] for cd in cards], default=114)
    if head + 10 - 236 >= hmin: top0, limit = 236, head + 10                 # above your head
    elif (1470 - 124 - 20) - (chin + 24) >= hmin: top0, limit = chin + 24, 1470 - 124 - 20   # under your chin
    else: top0, limit = 236, H
    return dict(cs=cs, typed=typed, big=big, tin=tin, ty0=ty0, dt=dt, post=post, drops=drops, tout=tout,
                cards=cards, head=head, fcy=fcy, ffh=ffh, word=None, top0=top0, limit=limit)

def _card(c, cm):
    """A comment card (RGBA) without the avatar (that's live for 'you')."""
    dark = c.p.get("style") == "dark"
    ink = (245, 245, 247) if dark else (18, 18, 20)
    sub = (160, 160, 168) if dark else (110, 110, 118)
    fnt = font(33, 500)
    tx = 24 + AVD + 18
    maxw = CW - tx - 92
    words = cm["text"].split()
    lines = [" ".join(words[i] for i in ln) for ln in wrap(words, fnt, maxw)][:3] or [""]
    h = 22 + 36 + len(lines) * 42 + 18
    s = SS(CW, h)
    s.rr((0, 0, CW, h), 32, fill=((30, 30, 33, 238) if dark else (255, 255, 255, 250)))
    s.text((tx, 22 + 16), fit_text(cm["user"], font(28, 700), maxw), 28, 700, fill=ink + (255,), anchor="lm")
    for k, ln in enumerate(lines):
        s.text((tx, 22 + 36 + k * 42 + 21), ln, 33, 500, fill=ink + (255,), anchor="lm")
    return dict(im=s.out(), h=h, sub=sub, dark=dark)

def _big_layer(txt, fcy, ffh):
    t = text_img(txt, 300, 950, (255, 255, 255))
    s = min(1.0, (W * 0.96) / t.width, 330 / t.height)
    return scaled(t, s)

def render(c):
    st = c.state
    if "S" not in st: st["S"] = _setup(c)
    S = st["S"]
    if not S["cs"]: return c.img
    ui, uo = phases(c, S["tin"], S["tout"])
    if ui <= 0 or uo >= 1: return c.img
    u = c.u
    img = c.img
    # ---- the big word behind your head, slammed in on Post
    if S["big"]:
        bk = prog(u, S["post"] + 0.05, 0.4)
        if bk > 0:
            if S["word"] is None: S["word"] = _big_layer(S["big"], S["fcy"], S["ffh"])
            wl = S["word"]
            s = 1.35 - 0.35 * back(bk, 1.2)
            a = ease_out(bk * 1.6) * (1 - ease_out(uo))
            cy = S["fcy"] - S["ffh"] * 0.42
            lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            wl2 = scaled(wl, s)
            comp(lay, wl2, W / 2 - wl2.width / 2, cy - wl2.height / 2)
            if a < 0.999: lay.putalpha(lay.getchannel("A").point(lambda v: int(v * a)))
            # a soft contact shadow from you onto the word
            m8 = Image.fromarray((c.mask * 255).astype(np.uint8), "L").resize((W // 4, H // 4), Image.BILINEAR)
            sh = np.asarray(m8.filter(ImageFilter.GaussianBlur(7)).resize((W, H), Image.BILINEAR), np.float32) / 255
            la = np.asarray(lay, np.float32)
            la[..., :3] *= (1 - 0.45 * sh[..., None])
            img = c.behind(Image.fromarray(la.astype(np.uint8), "RGBA"))
    img = img.copy() if img is c.img else img
    dark = c.p.get("style") == "dark"
    # ---- the comment box: slides up, the word is typed, Post is tapped
    bh, bx0, bx1 = 124, 30, W - 30
    by = 1470 - bh
    rise = (1 - back(ui, 1.2)) * (H - by + 40) + ease_in(uo) * (H - by + 60)
    ytop = by + rise
    if ytop < H:
        panel = frost(img, (bx0, ytop, bx1, ytop + bh), 40, tint=(18, 18, 20), tint_a=0.8, blur=7)
        s = SS(bx1 - bx0, bh)
        fx0, fx1 = 120, bx1 - bx0 - 20
        s.rr((fx0, 20, fx1, bh - 20), (bh - 40) / 2, fill=(255, 255, 255, 18), outline=(255, 255, 255, 46), width=1.5)
        n = 0 if u < S["ty0"] else min(len(S["typed"]), int((u - S["ty0"]) / S["dt"]) + 1)
        posted = u >= S["post"] + 0.1
        txt = S["typed"][:n] if not posted else ""
        clear = prog(u, S["post"] + 0.02, 0.15)
        if posted or not txt:
            s.text((fx0 + 30, bh / 2 + 1), str(c.p.get("placeholder") or ""), 33, 500, fill=(150, 150, 158, 255), anchor="lm")
        else:
            s.text((fx0 + 30, bh / 2 + 1), txt, 34, 600, fill=(255, 255, 255, int(255 * (1 - clear))), anchor="lm")
        # caret
        if not posted:
            cxp = fx0 + 30 + (s.textlen(txt, 34, 600) + 3 if txt else 0)
            idle = u - (S["ty0"] + max(0, n - 1) * S["dt"]) if n else u
            on = 1.0 if (n and idle < 0.4) else (1.0 if (idle % 1.0) < 0.55 else 0.0)
            if on: s.rr((cxp, bh / 2 - 21, cxp + 3.5, bh / 2 + 21), 1.5, fill=BLUE + (255,))
        # Post: lights up once there's text, pressed on the tap
        lit = 1.0 if (n and not posted) else 0.4
        press = math.sin(math.pi * clamp01((u - S["post"]) / 0.22)) if S["post"] <= u <= S["post"] + 0.22 else 0.0
        ps = 1 - 0.14 * press
        pxr = fx1 - 30
        if press > 0.02:
            s.circ(pxr - 34, bh / 2, 44 + 16 * clamp01((u - S["post"]) / 0.22), fill=BLUE + (int(60 * press),))
        s.text((pxr - 34 + 34 * ps, bh / 2 + 1), "Post", 33 * ps, 700, fill=BLUE + (int(255 * lit),), anchor="rm")
        panel.alpha_composite(s.out())
        av = avatar(c, 76)
        panel.alpha_composite(av, (24, (bh - 76) // 2))
        put(img, panel, bx0, ytop)
    # ---- the cards drop in from the top; newer ones push the stack down
    drops, cards = S["drops"], S["cards"]
    top0, limit = S["top0"], S["limit"]
    maxc = max(1, int(c.p.get("max_cards") or 3))
    order = []
    for k in range(len(cards)):
        dk = prog(u, drops[k], 0.6)
        if dk <= 0: continue
        # space taken by newer cards above this one
        above = 0.0
        for m in range(k + 1, len(cards)):
            above += ease_io(prog(u, drops[m], 0.4)) * (cards[m]["h"] + GAP)
        ty = top0 + above
        y = lerp(-cards[k]["h"] - 80, ty, back(dk, 1.15))
        newer = sum(ease_io(prog(u, drops[m], 0.4)) for m in range(k + 1, len(cards)))
        fade = clamp01(1 - (newer - (maxc - 1))) if newer > maxc - 1 else 1.0
        if ty + cards[k]["h"] > limit: fade = min(fade, clamp01(1 - (ty + cards[k]["h"] - limit) / 70))
        rot = (1 - ease_out(dk)) * (-7 if k % 2 == 0 else 6)
        order.append((k, y, fade, rot, dk))
    exit_up = ease_in(uo) * 420
    for k, y, fade, rot, dk in order:
        cd = cards[k]; cm = S["cs"][k]
        im = cd["im"].copy()
        av = avatar(c, AVD) if cm["user"].lower() == "you" else initials_avatar(cm["user"], AVD)
        im.alpha_composite(av, (24, 22))
        # heart (with a count only if given)
        hs = SS(70, cd["h"])
        hc = (150, 150, 158) if not cd["dark"] else (170, 170, 178)
        heart(hs, 35, 46, 34, outline=hc, width=2.6)
        if cm.get("likes") is not None:
            hs.text((35, 84), str(cm["likes"]), 22, 600, fill=hc + (255,), anchor="mm")
        im.alpha_composite(hs.out(), (CW - 80, 0))
        a = fade * (1 - ease_out(uo)) * min(1, dk * 3)
        stamp(img, im, W / 2, y + cd["h"] / 2 - exit_up, a=a, shadow=0.35, blur=20, dy=12, rot=rot)
    return img

# preview on the test clip (samples.json): seconds into the stretch, settings, and who wrote any text
SAMPLE = {   # for make_previews.py: settings for the preview, and who wrote any text it shows
    "params": {},
    "note": "the typed word is your own; 'Add a comment…' and 'Post' are the app's standard UI text",
}
