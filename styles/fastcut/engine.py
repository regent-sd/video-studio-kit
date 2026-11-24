"""The Fast Cut engine: an edit (pieces of clips laid end to end), scenes that change the layout every 1-2 s,
captions from the transcript, effects, sound and the build record. A Fast Cut script describes one reel with it:

    from fastcut import engine as fc, graphics as g, skins
    edit = fc.Edit([fc.piece(talk, 1.2, 6.8), fc.piece(talk, 7.4, 12.0), fc.piece(broll, 3.0, 5.5, audio=(talk, 12.3))])
    reel = fc.Reel("Kitchen_Tips_FastCut", edit, skins.get("brand"), shoot="2026-03-14 Kitchen Remodel")
    reel.split(0.0, 1.9, g.Hook(reel.skin, ["Three things", "nobody tells you"]))
    reel.full(1.9, 3.1)
    reel.card(3.1, 5.0, g.Checklist(reel.skin, "The list", [("Measure twice", 3.4), ("Cut once", 4.2)]))
    ...
    reel.end(edit.total - 2.5, edit.total, ["Kitchen tips"])
    reel.main()          # --sheet [t ...] | --mux | --out FILE | (nothing: full render)

Times are reel seconds. Put each cut on the first sound of a word (a caption start: reel.caption_starts()).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit import audio, draw, fxhook, media, paths, record  # noqa: E402
from stylekit import words as W_  # noqa: E402
from stylekit.draw import SS, back, clamp01, comp, comp_c, decay, ease_out, lerp, place, prog  # noqa: E402

from . import graphics as G  # noqa: E402

W, H, FPS, SR = 1080, 1920, 30, 48000
FULL, HALF = (W, H), (W, 960)
# Caption centre lines. Nothing important above y 220 or below y 1470 (the app's own bars cover them).
CAP_Y = dict(seam=960, chest=1240, face=1380, low=1420, center=960, high=640)


def piece(src, a, b, audio=None, voice=True, hp=None, clean=False, at=None):
    """One stretch of a clip on the timeline. audio: take the sound from elsewhere instead, (clip, start) or a
    start in the same clip (voice over B-roll). voice: it's speech (captions, clean-up, music ducks under it).
    hp: low cut in Hz for a hummy room. clean: the sound is already cleaned. at: (cx, cy, zoom) crop by hand."""
    return dict(src=str(src), a=float(a), b=float(b), audio=audio, voice=voice, hp=hp, clean=clean, at=at)


class Edit:
    """Pieces laid end to end in whole frames, plus `tail` seconds after them (for an end card)."""

    def __init__(self, pieces, tail=0.0):
        self.pieces, f = [], 0
        for p in pieces:
            p = dict(p)
            n = int(round((p["b"] - p["a"]) * FPS))
            asrc, at = p["src"], p["a"]
            if p.get("audio") is not None:
                aud = p["audio"]
                asrc, at = (str(aud[0]), float(aud[1])) if isinstance(aud, (list, tuple)) else (p["src"], float(aud))
            p.update(f0=f, f1=f + n, t0=f / FPS, t1=(f + n) / FPS, asrc=asrc, at_=at)
            self.pieces.append(p)
            f += n
        self.speech_end = f / FPS
        self.nf = f + int(round(tail * FPS))
        self.total = self.nf / FPS

    def at_frame(self, f):
        for p in self.pieces:
            if p["f0"] <= f < p["f1"]:
                return p
        return self.pieces[-1]

    def sources(self):
        return sorted({p["src"] for p in self.pieces} | {p["asrc"] for p in self.pieces})

    def words(self, make=True):
        """Every word said, in reel time (each word capped at 0.7 s, so a stretched word can't hold a caption)."""
        out = []
        for p in self.pieces:
            if not p.get("voice"):
                continue
            dur = p["t1"] - p["t0"]
            for w in W_.words_for(p["asrc"], make=make):
                if p["at_"] - 0.05 <= w["s"] < p["at_"] + dur - 0.1:
                    s = p["t0"] + w["s"] - p["at_"]
                    e = min(p["t1"], p["t0"] + min(w["e"], w["s"] + 0.7) - p["at_"])
                    out.append(dict(s=round(max(p["t0"], s), 3), e=round(max(e, s + 0.05), 3), w=w["w"]))
        return out

    def reel_time(self, src, t):
        """Reel time of a moment in a source clip's sound (first piece that holds it), or None."""
        for p in self.pieces:
            if p["asrc"] == str(src) and p["at_"] <= t < p["at_"] + (p["t1"] - p["t0"]):
                return p["t0"] + t - p["at_"]
        return None

    def voice_windows(self):
        return [(p["t0"], p["t1"]) for p in self.pieces if p.get("voice")]


class Scene:
    def __init__(self, t0, t1, fn, cap, theme, layers, kind, detail="", events=(), texts=()):
        self.t0, self.t1, self.fn, self.cap, self.theme, self.layers = t0, t1, fn, cap, theme, layers or {}
        self.kind, self.detail, self.events, self.texts = kind, detail, list(events), list(texts)
        self.f0 = self.f1 = 0

    def __repr__(self):
        return f"{self.t0:6.2f}-{self.t1:6.2f}  {self.kind:10s} {self.detail}"


def is_pov(src):
    return any(part.lower() in ("pov", "glasses") for part in Path(src).parts)


class Reel:
    """One Fast Cut reel. name: the file name stem (a version number is added). shoot: where it goes
    (<shoot>/Style Tests/); by default the shoot the first clip sits in. keywords: words to highlight in captions
    (default: picked from the transcript). effects: the effects library list (fxhook). music: a track you picked,
    "file" or "file@start" (fitted to the length, ducked under the voice); none by default."""

    def __init__(self, name, edit, skin, shoot=None, keywords=None, effects=(), music=None, music_level=0.30,
                 music_under_voice=0.10, words=None, crops=None, script=None):
        self.name, self.edit, self.skin, self.shoot = name, edit, skin, shoot
        self.effects, self.music = list(effects or []), music
        self.music_level, self.music_under_voice = music_level, music_under_voice
        self.words = words if words is not None else edit.words()
        self.keywords = list(keywords) if keywords is not None else W_.keywords_from(self.words)
        self.caps = W_.captions(self.words, self.keywords)
        self.crops = crops or {}
        self.scenes: list[Scene] = []
        self.script = script or (os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0].endswith(".py") else None)
        self.look = skin.grade
        self.work = paths.work_dir("fastcut", name)

    # ------------------------------------------------------------ footage layers
    def _box(self, src, kind, zoom=None, at=None, t=None):
        hand = at or (self.crops.get(Path(src).name) or {}).get(kind)
        return media.frame_for(src, "full" if kind == "punch" else kind, zoom or (1.3 if kind == "punch" else None),
                               t=t, at=hand)

    def own(self, kind="full", zoom=None):
        """The edit's own picture (whatever clip covers these frames), cropped full / half / punch."""
        def make(f0, f1):
            parts, f = [], f0
            while f < f1:
                p = self.edit.at_frame(f)
                g = min(f1, p["f1"]) if f < p["f1"] else f1
                box, size = self._box(p["src"], kind, zoom, p.get("at"), t=p["a"])
                parts.append(media.footage(p["src"], p["a"] + (f - p["f0"]) / FPS, g - f, box, size, self.look,
                                           is_pov(p["src"]), style="fastcut"))
                f = g
            return media.Reader(parts)
        make.kind, make.zoom = kind, zoom
        return make

    def clip(self, src, t, kind="full", zoom=None, at=None):
        """Other footage: src from t seconds (the edit's sound carries on under it)."""
        src = str(src)

        def make(f0, f1):
            box, size = self._box(src, kind, zoom, at, t=t)
            return media.Reader([media.footage(src, t, f1 - f0, box, size, self.look, is_pov(src), style="fastcut")])
        make.kind, make.zoom, make.src, make.t = kind, zoom, src, t
        return make

    # ------------------------------------------------------------ scenes
    def add(self, sc):
        self.scenes.append(sc)
        return sc

    def full(self, t0, t1, cap="chest", src=None, at=0.0, hit_at=None, zoom=None):
        """Full-screen footage: the talking head (default) or src from `at`. hit_at: a hard word gets a shake
        and a colour flash at that moment."""
        layer = self.clip(src, at, "full", zoom) if src else self.own("full", zoom)
        skin = self.skin

        def fn(t, L, i):
            fr = L["v"].get(i)
            if hit_at is None or t < hit_at:
                return fr.convert("RGBA")
            k = decay(t, hit_at, 6)
            dx = 22 * math.sin((t - hit_at) * 70) * k
            dy = 12 * math.cos((t - hit_at) * 55) * k
            big = fr.resize((int(W * 1.05), int(H * 1.05)), draw.Image.BICUBIC)
            cv = draw.Image.new("RGBA", (W, H))
            cv.paste(big, (int(-W * 0.025 + dx), int(-H * 0.025 + dy)))
            cv.alpha_composite(draw.Image.new("RGBA", (W, H), tuple(skin.flash) + (int((30 + 70 * k) * (1 if skin.name == "dark" else 0.5)),)))
            return cv
        kind = "broll" if src else "full"
        ev = [dict(t=hit_at, type="hit")] if hit_at is not None else []
        return self.add(Scene(t0, t1, fn, cap, "footage", {"v": layer}, kind, Path(src).name if src else "", ev))

    def punch(self, t0, t1, zoom=1.35, cap="chest", src=None, at=0.0):
        """The same moving footage, tighter: a quick change of view (use it instead of still photos)."""
        layer = self.clip(src, at, "punch", zoom) if src else self.own("punch", zoom)
        return self.add(Scene(t0, t1, lambda t, L, i: L["v"].get(i).convert("RGBA"), cap, "footage", {"v": layer},
                              "punch", f"{zoom:g}x"))

    def broll(self, t0, t1, src, at=0.0, zoom=None, cap="low", crop=None):
        """Other footage over the voice."""
        return self.add(Scene(t0, t1, lambda t, L, i: L["v"].get(i).convert("RGBA"), cap, "footage",
                              {"v": self.clip(src, at, "full", zoom, crop)}, "broll", Path(src).name))

    def tag(self, t0, t1, text, at, src=None, src_at=0.0, y=330, cap="chest"):
        """Footage with a short tag that pops in at `at` (the moment it's said). A tag stays up at least 1.5 s
        and matches what's on screen, or it isn't used."""
        if t1 - at < 1.5:
            print(f"  note: the tag “{text}” at {at:.2f} s is up only {t1 - at:.2f} s (keep tags up 1.5 s or more)")
        layer = self.clip(src, src_at, "full") if src else self.own("full")
        s = self.skin

        def fn(t, L, i):
            cv = L["v"].get(i).convert("RGBA")
            c = SS(W, 160)
            draw.pill(c, 540, 80, text, s.body, 42, s.tag_bg, s.tag_fg, back(prog(t, at, 0.32)))
            comp(cv, c.out(), 0, y - 80)
            return cv
        return self.add(Scene(t0, t1, fn, cap, "footage", {"v": layer}, "tag", f"“{text}”",
                              [dict(t=at, type="pop")], [text]))

    def split(self, t0, t1, panel, bottom=None, cap="seam"):
        """A panel on top (1080 x 960), footage below: the talking head, or bottom=(clip, start)."""
        assert getattr(panel, "shape", "panel") == "panel", "split() takes a panel graphic (Hook, ListPanel)"
        layer = self.clip(bottom[0], bottom[1], "half") if bottom else self.own("half")

        def fn(t, L, i):
            cv = draw.Image.new("RGBA", (W, H))
            cv.paste(L["h"].get(i), (0, 960))
            cv.alpha_composite(panel(t), (0, 0))
            return cv
        return self.add(Scene(t0, t1, fn, cap, "footage", {"h": layer}, "split", type(panel).__name__,
                              getattr(panel, "events", []), getattr(panel, "texts", [])))

    def card(self, t0, t1, card, cy=820, cap="low"):
        """One floating card on a plain background. It rises in about 0.45 s tilted, settles to about 6 degrees
        with a soft shadow, and drifts slowly."""
        assert getattr(card, "shape", "card") == "card", "card() takes a card graphic (Checklist, StatCard)"
        s = self.skin

        def fn(t, L, i):
            cv = s.bg.copy()
            e = ease_out(prog(t, t0, 0.45))
            place(cv, card(t), 540, lerp(1150, cy, e), lerp(0.86, 1, e), ry=lerp(26, 6, e) - 3 * prog(t, t0 + 0.4, 2.5),
                  rx=lerp(10, 3, e), shadow=0.3)
            return cv
        return self.add(Scene(t0, t1, fn, cap, "plain", {}, "card", type(card).__name__,
                              [dict(t=t0 - 0.12, type="whoosh", len=0.35)] + list(getattr(card, "events", [])),
                              getattr(card, "texts", [])))

    def card_split(self, t0, t1, card, bottom=None, cap="seam"):
        """A card in the top panel, footage below."""
        s = self.skin
        layer = self.clip(bottom[0], bottom[1], "half") if bottom else self.own("half")

        def fn(t, L, i):
            top = s.bg_top.copy()
            e = ease_out(prog(t, t0, 0.45))
            im = card(t)
            k = min(1.0, 860 / im.height, 960 / im.width)
            place(top, im, 540, lerp(700, 480, e), lerp(0.86, 0.96, e) * k, ry=lerp(-20, -5, e), rx=lerp(10, 2, e),
                  shadow=0.25, a=clamp01(e * 1.5))
            cv = draw.Image.new("RGBA", (W, H))
            cv.paste(L["h"].get(i), (0, 960))
            cv.alpha_composite(top, (0, 0))
            return cv
        return self.add(Scene(t0, t1, fn, cap, "footage", {"h": layer}, "card_split", type(card).__name__,
                              [dict(t=t0 - 0.12, type="whoosh", len=0.35)] + list(getattr(card, "events", [])),
                              getattr(card, "texts", [])))

    def graphic(self, t0, t1, g, cap="low"):
        """A full-screen graphic in place of the footage (BigNumber, Compare, Slam, Mosaic, EndCard)."""
        assert getattr(g, "shape", "full") == "full", "graphic() takes a full-screen graphic"
        kind = {"Mosaic": "mosaic", "EndCard": "end", "BigNumber": "big", "Compare": "explainer"}.get(type(g).__name__, "graphic")
        ev = list(getattr(g, "events", []))
        if not any(abs(e["t"] - t0) < 0.2 and e["type"] == "whoosh" for e in ev) and kind not in ("mosaic",):
            ev.insert(0, dict(t=t0 - 0.12, type="whoosh", len=0.3))
        theme = "plain" if not (self.skin.name == "dark" and kind in ("mosaic", "end")) and not getattr(g, "dark", False) else "footage"
        return self.add(Scene(t0, t1, lambda t, L, i: g(t), cap, theme, {}, kind, type(g).__name__, ev, getattr(g, "texts", [])))

    def end(self, t0, t1, lines=None, **kw):
        """The end card (no captions over it)."""
        return self.graphic(t0, t1, G.EndCard(self.skin, lines, t0, **kw), cap="none")

    # ------------------------------------------------------------ timeline
    def caption_starts(self):
        """Reel times where a caption starts: good places to cut (the first sound of a word)."""
        return [round(c[0] + 0.06, 3) for c in self.caps]

    def word_time(self, text, after=0.0):
        """Reel time of a word or phrase as it's said (for when a row ticks or a number counts up)."""
        i = W_.find(self.words, text, after)
        return self.words[i]["s"]

    def _finish_scenes(self):
        if not self.scenes:
            raise SystemExit("No scenes: add some with reel.full(), reel.split(), reel.card()...")
        self.scenes.sort(key=lambda s: s.t0)
        for k, s in enumerate(self.scenes):
            s.f0 = int(round(s.t0 * FPS))
            s.f1 = int(round(s.t1 * FPS)) if k + 1 < len(self.scenes) else self.edit.nf
        for a, b in zip(self.scenes, self.scenes[1:]):
            if b.f0 != a.f1:
                raise SystemExit(f"Scenes must meet: one ends at {a.t1:.2f} s, the next starts at {b.t0:.2f} s.")
        if self.scenes[0].f0 != 0:
            raise SystemExit("The first scene must start at 0.")

    def check(self):
        """Plain notes on the plan: the rhythm rules and text on screen that nobody said."""
        self._finish_scenes()
        notes = []
        for a, b in zip(self.scenes, self.scenes[1:]):
            if a.kind == b.kind and a.kind not in ("full", "broll"):
                notes.append(f"same layout twice in a row at {b.t0:.2f} s ({a.kind})")
        for s in self.scenes:
            d = s.t1 - s.t0
            if d > 2.6 and s.kind not in ("end", "card", "card_split"):
                notes.append(f"{s.t0:.2f} s: {s.kind} holds {d:.1f} s (the layout changes every 1-2 s)")
        said = set(W_.norm_words(" ".join(w["w"] for w in self.words)))
        b = self.skin.brand
        approved = {str(b.get(k) or "") for k in ("name", "handle", "end_card_line")}   # the brand's own lines
        unsaid = []
        for s in self.scenes:
            for txt in s.texts:
                if txt in approved:
                    continue
                extra = [w for w in W_.norm_words(txt) if w not in said and not w.isdigit()]
                if extra:
                    unsaid.append(f"{s.t0:.2f} s: “{txt}”")
        return notes, unsaid

    def scene_at(self, f):
        for s in self.scenes:
            if s.f0 <= f < s.f1:
                return s
        return self.scenes[-1]

    def open_layers(self, s):
        return {k: mk(s.f0, s.f1) for k, mk in s.layers.items()}

    # ------------------------------------------------------------ captions
    def cap_img(self, toks, theme, size):
        s = self.skin
        f = s.font("caption", size)
        sp = f.getlength(" ")
        ws = [f.getlength(w) for w, _ in toks]
        tw = sum(ws) + sp * (len(toks) - 1)
        asc, desc = f.getmetrics()
        pad = 44
        im = draw.Image.new("RGBA", (int(tw) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
        d = draw.ImageDraw.Draw(im)
        style = s.cap_footage if theme == "footage" else "plain"
        kw = s.get("cap_keyword", s.cap_plain)
        if style == "block":
            d.rounded_rectangle([pad - 30, pad - 10, pad + tw + 30, pad + asc + desc + 6], radius=24,
                                fill=tuple(s.get("background", s.card)) + (245,))
        box_keys = (style in ("block", "plain") and kw == "highlight")
        x = pad
        for (w, hl), ww in zip(toks, ws):
            if hl and box_keys:
                d.rounded_rectangle([x - 8, pad + asc * 0.45, x + ww + 8, pad + asc + desc * 0.2], radius=8, fill=s.highlight)
            x += ww + sp
        x = pad
        for (w, hl), ww in zip(toks, ws):
            if style in ("shadow", "outline"):
                fill = s.accent if (hl and s.name == "dark") else (s.hot if hl else (255, 255, 255))
            else:
                fill = s.hot if (hl and not box_keys) else s.ink
            if style == "outline":
                d.text((x, pad), w, font=f, fill=fill, stroke_width=max(3, size // 16), stroke_fill=(0, 0, 0))
            else:
                d.text((x, pad), w, font=f, fill=fill)
            x += ww + sp
        if style == "shadow":
            im = draw.soft_shadow(im)
        if im.width > W - 40:
            im = draw.scaled(im, (W - 40) / im.width)
        return im

    def draw_caption(self, cv, t, sc):
        """A caption belongs to one scene: one that starts in the last 0.4 s before a cut waits for the next
        scene, and one that started earlier ends at the cut, so it never shows twice in two places."""
        if sc.cap == "none":
            return cv
        s0, s1 = sc.t0, sc.t1
        for s, e, toks in self.caps:
            if s < s0:
                if s0 - s >= 0.4:
                    continue
                s = s0
            elif s1 - s < 0.4 and s1 < self.edit.total - 0.01:
                continue
            if s <= t < min(e, s1):
                size = 96 if sc.cap == "center" else (78 if self.skin.name == "dark" else 82)
                im = self.cap_img(tuple(toks), sc.theme, size)
                p = prog(t, s, 0.14)
                comp_c(cv, im, W / 2, CAP_Y[sc.cap], lerp(0.84, 1.0, back(p, 2.2)) if p < 1 else 1.0, clamp01(p * 2.5))
                break
        return cv

    # ------------------------------------------------------------ frames
    def picture(self, f, readers):
        s = self.scene_at(f)
        return s.fn(f / FPS, readers, f - s.f0)

    def frame(self, f, readers):
        s = self.scene_at(f)
        return self.draw_caption(self.picture(f, readers), f / FPS, s)

    def sheet(self, times=None, path=None, title=None, cols=8):
        """A contact sheet: one frame per scene (near its end, when its graphics have built up), or at `times`."""
        self._finish_scenes()
        nf = self.edit.nf
        if not times:
            times = [min(self.edit.total - 0.05, max(s.t0 + 0.05, s.t1 - 0.15)) for s in self.scenes]
        frames = []
        for t in times:
            f = min(nf - 1, int(round(t * FPS)))
            s = self.scene_at(f)
            rd = self.open_layers(s)
            try:
                im = self.frame(f, rd).convert("RGB")
            finally:
                for r in rd.values():
                    r.close()
            frames.append(draw.label(im, f"{t:.2f}"))
        p = Path(path) if path else self.work / "sheet.jpg"
        draw.contact_sheet(frames, cols=cols, title=title).save(p, quality=90)
        print(p)
        return p

    # ------------------------------------------------------------ render and sound
    def _encode_frames(self, vpath):
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                                "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "14", "-preset", "medium",
                                "-pix_fmt", "yuv420p", str(vpath)], stdin=subprocess.PIPE)
        cur, readers = None, {}
        try:
            for f in range(self.edit.nf):
                s = self.scene_at(f)
                if s is not cur:
                    for r in readers.values():
                        r.close()
                    readers = self.open_layers(s)
                    cur = s
                    print(f"  {s.t0:5.2f}s  {s.kind}", flush=True)
                enc.stdin.write(self.frame(f, readers).convert("RGB").tobytes())
        finally:
            for r in readers.values():
                r.close()
            enc.stdin.close()
            enc.wait()

    def _encode_with_effects(self, vpath, voice_wav):
        st = {"cur": None, "rd": {}}

        def picture(f):
            s = self.scene_at(f)
            if s is not st["cur"]:
                for r in st["rd"].values():
                    r.close()
                st["rd"] = self.open_layers(s)
                st["cur"] = s
                print(f"  {s.t0:5.2f}s  {s.kind}", flush=True)
            return s.fn(f / FPS, st["rd"], f - s.f0)
        try:
            fxhook.render_with_effects(self.edit.nf, picture,
                                       lambda cv, f: self.draw_caption(cv, f / FPS, self.scene_at(f)),
                                       self.effects, vpath, words=self.words, audio=str(voice_wav), skin=self.fx_skin())
        finally:
            for r in st["rd"].values():
                r.close()

    def fx_skin(self):
        """The effects library's name for this reel's skin."""
        return "dark" if self.skin.name == "dark" else f"brand:{self.skin.brand.get('slug', '')}"

    def sound(self):
        """voice.wav (the edit's sound, crossfaded at each cut), music.wav (if any, ducked under the voice) and
        sound.wav (the mix at -14 LUFS). Returns {name: path}."""
        e = self.edit
        clips = [dict(path=p["asrc"], start=p["at_"], len=p["t1"] - p["t0"], t0=p["t0"], voice=bool(p.get("voice")),
                      hp=p.get("hp"), clean=bool(p.get("clean"))) for p in e.pieces]
        runs = audio.runs(clips, self.work / "runs")
        out = {"voice": str(self.work / "voice.wav")}
        audio.lay(runs, e.total, out["voice"], "loudnorm=I=-17:TP=-3" if self.music else "")
        tracks = [(out["voice"], 1.0)]
        if self.music:
            raw = audio.fit_music(self.music, e.total, str(self.work / "music_fit.wav"))
            out["music"] = audio.duck(raw, e.total, e.voice_windows(), str(self.work / "music.wav"),
                                      self.music_level, self.music_under_voice)
            tracks.append((out["music"], 1.0))
        out["mix"] = audio.mix(tracks, str(self.work / "sound.wav"), e.total)
        return out

    def render(self, out=None):
        self._finish_scenes()
        notes, unsaid = self.check()
        for n in notes:
            print("  note:", n)
        vpath = self.work / "video.mp4"
        if self.effects:
            snd = self.sound()
            self._encode_with_effects(vpath, snd["voice"])
            return self.mux(vpath, out, snd, unsaid)
        self._encode_frames(vpath)
        return self.mux(vpath, out, None, unsaid)

    def events(self):
        ev = []
        for s in self.scenes:
            ev += [dict(e, scene=s.kind) for e in s.events if e.get("t") is not None and 0 <= e["t"] < self.edit.total]
        return sorted(ev, key=lambda e: e["t"])

    def mux(self, vpath, out=None, snd=None, unsaid=None):
        self._finish_scenes()
        if not Path(vpath).exists():
            raise SystemExit(f"No picture at {vpath}: run the full render first.")
        if unsaid is None:
            unsaid = self.check()[1]
        snd = snd or self.sound()
        first = self.edit.pieces[0]["src"]
        dest = paths.output_for(self.name, self.shoot, out, near=first)
        audio.mux(vpath, snd["mix"], dest, self.edit.total)
        W_.write_words(str(dest) + ".words.txt", self.words)
        (self.work / "cuts.json").write_text(json.dumps(   # where one piece of sound meets the next (verify.py)
            {"video": str(dest), "voice": snd["voice"], "cuts": [round(p["t0"], 3) for p in self.edit.pieces[1:]]}, indent=1))
        ev_path = self.work / "sfx_events.json"
        ev_path.write_text(json.dumps(self.events(), indent=1))
        print(f"{dest}  {self.edit.total:.2f} s, {self.edit.nf} frames")
        print(f"  sound-effect moments: {ev_path} ({len(self.events())}), for the effects pass (sound/README.md)")
        if unsaid:
            print("  text on screen that nobody said (flag it before posting):")
            for u in unsaid:
                print("   ", u)
        self.keep_record(dest, snd)
        return dest

    def keep_record(self, dest, snd):
        rec = record.new("styles/fastcut/engine.py", [self.script] + self.edit.sources())
        if rec is None:
            return
        for s in self.scenes:
            record.layout(rec, "fastcut", s.kind, s.t0, s.t1 if s is not self.scenes[-1] else self.edit.total, s.detail)
        for name, a, b in fxhook.applied():
            rec.effect(name, a, b)
        for p in self.edit.pieces:   # the raw seconds used: the edit's picture and its sound
            n = p["t1"] - p["t0"]
            record.used(rec, p["src"], p["a"], p["a"] + n)
            if p["asrc"] != p["src"] or abs(p["at_"] - p["a"]) > 0.01:
                record.used(rec, p["asrc"], p["at_"], p["at_"] + n)
        for s in self.scenes:        # other footage shown over the voice
            for layer in s.layers.values():
                if getattr(layer, "src", None):
                    record.used(rec, layer.src, layer.t, layer.t + (s.f1 - s.f0) / FPS)
        rec.track("voice_nat", [(snd["voice"], 1.0)])
        if snd.get("music"):
            rec.song(audio.music_files(self.music)[0][0])
            rec.track("music", [(snd["music"], 1.0)])
        record.save(rec, dest, keep_in=self.work)   # the record stays in the work folder; the maps go beside the video

    # ------------------------------------------------------------ command line
    def main(self, argv=None):
        """--sheet [t ...]  contact sheet (one frame per scene, or at these times)
           --mux            redo only the sound and the final file, from the last render's picture
           --out FILE       write here instead of <shoot>/Style Tests/<name>_vN.mp4 (never overwrites)
           --plan           list the scenes and the notes, render nothing"""
        argv = sys.argv[1:] if argv is None else argv
        out = None
        if "--out" in argv:
            out = argv[argv.index("--out") + 1]
        if "--plan" in argv:
            notes, unsaid = self.check()
            for s in self.scenes:
                print(s)
            for n in notes:
                print("note:", n)
            for u in unsaid:
                print("not said:", u)
            return None
        if "--sheet" in argv:
            ts = []
            for x in argv[argv.index("--sheet") + 1:]:
                try:
                    ts.append(float(x))
                except ValueError:
                    break
            return self.sheet(ts or None)
        if "--mux" in argv:
            return self.mux(self.work / "video.mp4", out)
        return self.render(out)
