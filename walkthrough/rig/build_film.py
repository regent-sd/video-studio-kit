#!/usr/bin/env python3
"""Turn a recorded take and its narration into a finished walkthrough film (a HyperFrames project).

    .venv/bin/python walkthrough/rig/build_film.py walkthrough/films/example.film.json            # build the project
    .venv/bin/python walkthrough/rig/build_film.py walkthrough/films/example.film.json --render   # build, check and render the MP4
    ... --take example-phone        the same film from another take of it (a phone-shaped one, say)

film.json:
{
  "name": "example",                 recordings/<name>, voice/<name>, films/<name>, out/<name>.mp4 in the work folder
  "brand": "example-brand",          optional; colours, fonts and logo come from brands/<brand>/brand.json
  "wordmark": "Mossy",               optional; shown on the cards when the brand has no logo (default: the brand's name)
  "title": "Add a plant and keep it watered",
  "kicker": "Mossy walkthrough · 1",
  "steps": {"2": "Add a plant", ...}, scene number -> the step label shown when that scene starts
  "end_line": "Questions? Reply to any email from us.",
  "end_sub": "",                     optional smaller line under it
  "captions": true,                  burn captions in (an .srt is always written next to the MP4)
  "caption_position": "bottom",      or "top", when the app shows something important at the bottom
  "punch": [{"scene": 3, "line": 1, "delay": 0.4, "hold": 2.0, "scale": 1.4}],
                                     zoom toward that line's last click ("origin": [x, y] in film pixels to aim elsewhere)
  "click_sound": "",                 optional; a file, or a path inside the sound library. Default: the first "click"
                                     sound in the sound library, else a soft tick made here
  "click_volume": 0.22,
  "music": "",                       optional; a licensed track (a path, or a file in the music library)
  "music_db": null                   music level under the voice, in dB (default: the brand's music.under_voice_db)
}
Paths "recording", "voice", "film_dir" and "out" can be set to override the defaults.

Writes films/<name>/: assets/ (recording, narration.wav, clicks.wav, music.wav, logo, fonts),
compositions/ (intro, steps, captions, outro) and index.html, plus out/<name>.srt.
Narration is levelled to -16 LUFS; clicks sit well under it.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE))
import studio_config as sc  # noqa: E402
import brandcss  # noqa: E402

INTRO, OUTRO, XF = 3.2, 3.0, 0.4   # title card, end card, crossfade overlap (s)
GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"  # HyperFrames serves this version from its own copy
AUDIO_EXT = {".wav", ".mp3", ".aif", ".aiff", ".m4a", ".flac", ".ogg", ".caf"}
esc = html.escape


def sh(*a):
    subprocess.run(a, check=True)


def probe(path) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                capture_output=True, text=True, check=True).stdout.strip())


def work_dir() -> Path:
    wt = sc.get("walkthrough") or {}
    return Path(wt.get("work_dir") or "~/Movies/Walkthroughs").expanduser()


def resolve(p: str, base: Path) -> Path:
    q = Path(os.path.expanduser(p))
    return q if q.is_absolute() else base / q


# ---------- sounds ----------

def find_click(cfg: dict, assets: Path) -> Path:
    """The click sound: film.json's, else a 'click' in the sound library, else a soft tick made here."""
    lib = None
    try:
        lib = sc.path("sound_library")
    except KeyError:
        pass
    if cfg.get("click_sound"):
        p = Path(os.path.expanduser(cfg["click_sound"]))
        if not p.is_absolute() and lib:
            p = lib / p
        if p.exists():
            return p
        print(f"note: click_sound {p} not found; looking in the sound library")
    if lib and lib.exists():
        made = ("made in code", "fallback", "synth")  # recorded sounds first; code-made banks last
        found = sorted((f for f in lib.rglob("*") if f.suffix.lower() in AUDIO_EXT and "click" in f.name.lower()
                        and "double" not in f.name.lower()),
                       key=lambda f: (any(m in str(f).lower() for m in made), "mouse" not in f.name.lower(), str(f)))
        if found:
            return found[0]
    return make_tick(assets / "tick.wav")


def make_tick(out: Path) -> Path:
    """A short, soft tick (filtered noise) for when there's no recorded click. A real one sounds better."""
    import numpy as np
    sr = 48000
    n = int(sr * 0.045)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    noise = np.convolve(noise, np.ones(6) / 6, mode="same")          # take the hiss off
    env = np.exp(-np.arange(n) / (sr * 0.006))
    body = np.sin(2 * np.pi * 1800 * np.arange(n) / sr) * np.exp(-np.arange(n) / (sr * 0.004))
    x = (0.6 * noise * env + 0.5 * body)
    x = (x / np.max(np.abs(x)) * 0.7 * 32767).astype(np.int16)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(x.tobytes())
    print("note: no click sound in the sound library; using a soft tick made in code (a recorded click sounds better)")
    return out


def click_onset(path: Path) -> float:
    """Seconds from the file's start to the click's attack (first sample over -30 dBFS)."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    import array
    a = array.array("h"); a.frombytes(raw)
    thr = int(32767 * 10 ** (-30 / 20))
    for i, v in enumerate(a):
        if abs(v) > thr:
            return i / 48000
    return 0.0


def mix_track(items, total, out: Path, loudnorm=None, volume=1.0):
    """items: [(audio_path, start_seconds)] -> one mono 48 kHz WAV `total` seconds long."""
    if not items:
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{total:.3f}", str(out))
        return
    args = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=mono"]
    for p, _ in items:
        args += ["-i", str(p)]
    parts = []
    for i, (_, st) in enumerate(items, 1):
        ms = max(0, int(round(st * 1000)))
        parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=mono,adelay={ms}:all=1[d{i}]")
    mixin = "[0:a]" + "".join(f"[d{i}]" for i in range(1, len(items) + 1))
    chain = ";".join(parts) + f";{mixin}amix=inputs={len(items) + 1}:normalize=0:duration=first,volume={volume}"
    if loudnorm:
        chain += f",loudnorm=I={loudnorm}:TP=-1.5:LRA=11"
    chain += ",aresample=48000[out]"
    sh(*args, "-filter_complex", chain, "-map", "[out]", "-ar", "48000", "-c:a", "pcm_s16le", "-t", f"{total:.3f}", str(out))


def music_bed(src: Path, total: float, out: Path, lufs: float):
    """A licensed track cut to the film's length, levelled under the voice, faded in and out."""
    sh("ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(src), "-t", f"{total:.3f}", "-af",
       f"aresample=48000,aformat=channel_layouts=mono,loudnorm=I={lufs}:TP=-3:LRA=11,"
       f"afade=t=in:d=0.6,afade=t=out:st={max(0, total - 1.8):.3f}:d=1.8", "-c:a", "pcm_s16le", str(out))


# ---------- captions ----------

def chunk(text: str, max_chars: int) -> list[str]:
    """Split a line into caption-sized pieces: sentence by sentence, each long sentence cut into
    even pieces (after a comma when one is near the middle), so no word is left on its own."""
    out = []
    for sent in re.split(r"(?<=[.?!])\s+", text.strip()):
        words = sent.split()
        if not words:
            continue
        k = max(1, -(-len(sent) // max_chars))          # pieces this sentence needs
        while words:
            if k == 1:
                out.append(" ".join(words)); break
            target = len(" ".join(words)) / k
            best, run = 1, 0
            for n in range(1, len(words)):
                run = len(" ".join(words[:n]))
                score = abs(run - target) - (target * 0.25 if words[n - 1].endswith(",") else 0)
                if n == 1 or score < best_score:
                    best, best_score = n, score
            out.append(" ".join(words[:best])); words = words[best:]; k -= 1
    return out


def captions(lines, t0: float, max_chars: int):
    """[(start, end, text)] in film time. Each line's pieces share its spoken time by length."""
    caps = []
    for ln in lines:
        text = (ln.get("text") or "").strip()
        if not text:
            continue
        pieces = chunk(text, max_chars)
        speak = max(0.6, float(ln.get("seconds") or 3) - 0.2)
        total = sum(len(p) for p in pieces)
        t = t0 + ln["start"]
        for p in pieces:
            d = speak * len(p) / total
            caps.append([round(t, 3), round(t + max(0.6, d), 3), p])
            t += d
    for i in range(len(caps) - 1):           # never overlap the next caption
        caps[i][1] = min(caps[i][1], caps[i + 1][0] - 0.02)
    return [tuple(c) for c in caps]


def srt(caps, path: Path):
    def ts(s):
        ms = int(round(s * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    path.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(caps, 1)))


# ---------- the film ----------

def main():
    ap = argparse.ArgumentParser(description="Build a walkthrough film from a take and its narration.")
    ap.add_argument("film", type=Path)
    ap.add_argument("--render", action="store_true", help="also run `hyperframes check` and render the MP4")
    ap.add_argument("--take", help="use recordings/<take> (e.g. example-phone) with this film's voice and cards; "
                                   "the project and MP4 are named after the take")
    a = ap.parse_args()

    cfg = json.loads(a.film.read_text())
    W_ = work_dir()
    name = cfg.get("name") or a.film.name.replace(".film.json", "")
    voice = resolve(cfg.get("voice") or f"voice/{name}", W_)
    if a.take:
        name = a.take
        rec, film, out_mp4 = W_ / "recordings" / name, W_ / "films" / name, W_ / "out" / f"{name}.mp4"
    else:
        rec = resolve(cfg.get("recording") or f"recordings/{name}", W_)
        film = resolve(cfg.get("film_dir") or f"films/{name}", W_)
        out_mp4 = resolve(cfg.get("out") or f"out/{name}.mp4", W_)
    tl_path = rec / "timeline.json"
    if not tl_path.exists():
        sys.exit(f"No take at {rec} (looked for timeline.json). Record the take first (walkthrough/README.md, step 6).")
    tl = json.loads(tl_path.read_text())
    mp4 = rec / f"{tl['name']}.mp4"
    W, H = (tl.get("size") or {}).get("width", 1920), (tl.get("size") or {}).get("height", 1080)
    tall = H > W
    D = probe(mp4)
    T0 = round(INTRO - XF, 3)           # the recording starts under the fading title card
    total = round(T0 + D + OUTRO - XF, 3)

    b = sc.brand(cfg.get("brand"))
    C = lambda role: sc.hex_color(b, role)  # noqa: E731
    A = film / "assets"
    A.mkdir(parents=True, exist_ok=True)
    (film / "compositions").mkdir(exist_ok=True)
    shutil.copy(mp4, A / "recording.mp4")
    font_css = brandcss.fonts_css(b, A / "fonts", "assets/fonts")

    logo_src = Path(os.path.expanduser(cfg["logo"])) if cfg.get("logo") else sc.logo(b)
    if logo_src and Path(logo_src).exists():
        shutil.copy(logo_src, A / f"logo{Path(logo_src).suffix.lower()}")
        mark = lambda cls: f'<img class="{cls}" src="assets/logo{Path(logo_src).suffix.lower()}" alt="" />'  # noqa: E731
    else:
        word = esc(cfg.get("wordmark") or b.get("name") or "")
        mark = lambda cls: f'<div class="{cls} wordmark font-title">{word}</div>'  # noqa: E731

    # ---- sound ----
    lines = [(voice / l["file"], T0 + l["start"]) for l in tl["lines"] if l.get("file")]
    missing = [str(p) for p, _ in lines if not p.exists()]
    if missing:
        sys.exit(f"Voice clips missing (was the take recorded with a different voice?): {', '.join(missing[:3])}")
    if not lines:
        print("note: this take has no narration (a dry run?); the film will be silent apart from clicks")
    mix_track(lines, total, A / "narration.wav", loudnorm=-16)
    click = find_click(cfg, A)
    on = click_onset(click)
    clicks_t = [c["t"] if isinstance(c, dict) else c for c in tl.get("clicks", [])]
    mix_track([(click, T0 + t - on) for t in clicks_t], total, A / "clicks.wav", volume=float(cfg.get("click_volume", 0.22)))
    music = None
    if cfg.get("music"):
        mp = Path(os.path.expanduser(cfg["music"]))
        if not mp.is_absolute():
            try:
                mp = sc.path("music_library") / mp
            except KeyError:
                pass
        if not mp.exists():
            sys.exit(f"Music not found: {mp}")
        under = cfg.get("music_db")
        if under is None:
            under = (b.get("music") or {}).get("under_voice_db", -20)
        music_bed(mp, total, A / "music.wav", -16 + float(under))
        music = A / "music.wav"
    nar_d, clk_d = round(probe(A / "narration.wav"), 3), round(probe(A / "clicks.wav"), 3)

    # ---- punch-ins: zoom toward a line's last click ----
    starts = [(l["scene"], l["line"], l["start"]) for l in tl["lines"]]
    clicks = [c if isinstance(c, dict) else {"t": c, "x": 0.5, "y": 0.5} for c in tl.get("clicks", [])]
    punches = []
    for pz in cfg.get("punch", []):
        try:
            i = next(k for k, (s_, l_, _) in enumerate(starts) if s_ == pz["scene"] and l_ == pz["line"])
        except StopIteration:
            sys.exit(f"punch: there's no line {pz['scene']}.{pz['line']} in the take")
        t_a = starts[i][2]
        t_b = starts[i + 1][2] if i + 1 < len(starts) else D
        cs = [c for c in clicks if t_a <= c["t"] < t_b]
        at = (cs[-1]["t"] if cs else t_a) + pz.get("delay", 0.4)
        origin = pz.get("origin") or ([round(cs[-1]["x"] * W), round(cs[-1]["y"] * H)] if cs else [W // 2, H // 2])
        punches.append({"at": round(T0 + at, 3), "hold": pz.get("hold", 2.5), "scale": pz.get("scale", 1.5), "origin": origin})

    scene_start = {}
    for l in tl["lines"]:
        scene_start.setdefault(str(l["scene"]), T0 + l["start"])

    # ---- layout (landscape 1920x1080 or tall 1080x1920) ----
    k = W / 1920 if not tall else W / 1080
    if tall:
        L = dict(pad=90, title=104, kicker=34, logo=220, end_line=58, end_sub=36,
                 step_pos=f"left: 50%; top: {round(150 * k)}px; transform: translateX(-50%);",
                 step_text=40, step_num=60, cap_bottom=380, cap_size=54, cap_max=920)
    else:
        L = dict(pad=160, title=92, kicker=30, logo=230, end_line=46, end_sub=30,
                 step_pos=f"left: {round(112 * k)}px; bottom: {round(150 * k)}px;",
                 step_text=34, step_num=54, cap_bottom=56, cap_size=40, cap_max=1500)
    L = {key: (round(v * k) if isinstance(v, (int, float)) else v) for key, v in L.items()}
    bg, text, muted, accent = C("background"), C("text"), C("muted"), C("accent")
    pill_bg, pill_text = brandcss.rgba(b, "dark_surface", 0.94), C("on_dark")
    num_text = brandcss.on(b, "accent")
    wm_size = round((64 if tall else 72) * k)

    common_css = f"""{font_css}
    .wordmark {{ color: {text}; font-size: {wm_size}px; letter-spacing: -0.02em; line-height: 1; }}"""

    # ---- intro ----
    (film / "compositions" / "intro.html").write_text(f"""<template>
  <style>
    {common_css}
    #root {{ position: absolute; inset: 0; background: {bg}; }}
    #intro-wrap {{ position: absolute; left: {L['pad']}px; right: {L['pad']}px; top: 0; bottom: 0; display: flex; flex-direction: column; justify-content: center; gap: {round(28 * k)}px; }}
    img.intro-logo {{ width: {L['logo']}px; height: auto; }}
    #intro-kicker {{ color: {muted}; font-size: {L['kicker']}px; letter-spacing: 0.04em; text-transform: uppercase; }}
    #intro-title {{ color: {text}; font-size: {L['title']}px; letter-spacing: -0.03em; line-height: 1.04; }}
    #intro-bar {{ width: {round(120 * k)}px; height: {round(10 * k)}px; border-radius: {round(5 * k)}px; background: {accent}; }}
  </style>
  <div id="root" data-composition-id="intro" data-width="{W}" data-height="{H}">
    <div id="intro-wrap" class="clip" data-start="0" data-duration="{INTRO}">
      {mark("intro-logo")}
      <div id="intro-kicker" class="font-heading" data-var-text="kicker">{esc(cfg.get('kicker', ''))}</div>
      <div id="intro-title" class="font-title" data-var-text="title">{esc(cfg['title'])}</div>
      <div id="intro-bar"></div>
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo(".intro-logo", {{ y: 10 }}, {{ y: 0, duration: 0.6, ease: "power3.out" }}, 0);
    tl.fromTo("#intro-kicker", {{ y: 14 }}, {{ y: 0, duration: 0.6, ease: "power3.out" }}, 0);
    tl.fromTo("#intro-title", {{ y: 18 }}, {{ y: 0, duration: 0.7, ease: "power3.out" }}, 0);
    tl.fromTo("#intro-bar", {{ scaleX: 0, transformOrigin: "left center" }}, {{ scaleX: 1, duration: 0.6, ease: "power3.out" }}, 0.7);
    tl.fromTo("#intro-wrap", {{ opacity: 1 }}, {{ opacity: 0, duration: {XF}, ease: "power1.in" }}, {INTRO - XF - 0.02});
    window.__timelines["intro"] = tl;
  </script>
</template>
""")

    # ---- step labels ----
    pills, tweens = [], []
    for n, (scene, label) in enumerate(sorted(cfg.get("steps", {}).items(), key=lambda kv: int(kv[0])), 1):
        if scene not in scene_start:
            print(f"note: step for scene {scene} skipped (no such scene in the take)")
            continue
        st = round(scene_start[scene] - T0, 3)
        nxt = [scene_start[s] - T0 for s in sorted(scene_start, key=int) if int(s) > int(scene)]
        dur = round(min(3.6, (nxt[0] - st - 0.1) if nxt else 3.6), 3)
        pid = f"step-{scene}"
        pills.append(f'    <div id="{pid}" class="clip step" data-start="{st}" data-duration="{dur}"><span class="step-num font-number">{n}</span><span class="step-text font-heading">{esc(label)}</span></div>')
        tweens.append(f'    tl.fromTo("#{pid}", {{ opacity: 0, y: {-16 if tall else 0}, x: {0 if tall else -24} }}, {{ opacity: 1, y: 0, x: 0, duration: 0.35, ease: "power3.out" }}, {st});')
        tweens.append(f'    tl.to("#{pid}", {{ opacity: 0, duration: 0.3, ease: "power1.in" }}, {round(st + dur - 0.32, 3)});')
    (film / "compositions" / "steps.html").write_text(f"""<template>
  <style>
    {font_css}
    #root {{ position: absolute; inset: 0; pointer-events: none; }}
    .step {{ position: absolute; {L['step_pos']} display: flex; align-items: center; gap: {round(18 * k)}px; padding: {round(16 * k)}px {round(30 * k)}px {round(16 * k)}px {round(16 * k)}px;
             background: {pill_bg}; border-radius: 999px; box-shadow: 0 {round(12 * k)}px {round(32 * k)}px rgba(0, 0, 0, 0.25); white-space: nowrap; }}
    .step-num {{ width: {L['step_num']}px; height: {L['step_num']}px; border-radius: 50%; background: {accent}; color: {num_text}; font-size: {round(L['step_num'] * 0.55)}px;
                 display: flex; align-items: center; justify-content: center; }}
    .step-text {{ color: {pill_text}; font-size: {L['step_text']}px; letter-spacing: -0.01em; }}
  </style>
  <div id="root" data-composition-id="steps" data-width="{W}" data-height="{H}">
{chr(10).join(pills)}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{chr(10).join(tweens)}
    window.__timelines["steps"] = tl;
  </script>
</template>
""")

    # ---- captions ----
    caps = captions(tl["lines"], T0, 30 if tall else 48)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    srt(caps, out_mp4.with_suffix(".srt"))
    burn = cfg.get("captions", True)
    cap_edge = "top" if cfg.get("caption_position") == "top" else "bottom"
    cap_divs, cap_tweens = [], []
    if burn:
        for i, (a0, a1, t) in enumerate(caps):
            st, du = round(a0 - T0, 3), round(a1 - a0, 3)
            cap_divs.append(f'    <div id="cap-{i}" class="clip cap" data-start="{st}" data-duration="{du}"><span class="font-caption">{esc(t)}</span></div>')
            cap_tweens.append(f'    tl.fromTo("#cap-{i}", {{ opacity: 0 }}, {{ opacity: 1, duration: 0.12 }}, {st});')
    (film / "compositions" / "captions.html").write_text(f"""<template>
  <style>
    {font_css}
    #root {{ position: absolute; inset: 0; pointer-events: none; }}
    .cap {{ position: absolute; left: 0; right: 0; {cap_edge}: {L['cap_bottom']}px; display: flex; justify-content: center; }}
    .cap span {{ max-width: {L['cap_max']}px; text-align: center; color: #FFFFFF; background: rgba(0, 0, 0, 0.72);
                 font-size: {L['cap_size']}px; line-height: 1.25; padding: {round(10 * k)}px {round(22 * k)}px; border-radius: {round(12 * k)}px; }}
  </style>
  <div id="root" data-composition-id="captions" data-width="{W}" data-height="{H}">
{chr(10).join(cap_divs)}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{chr(10).join(cap_tweens)}
    window.__timelines["captions"] = tl;
  </script>
</template>
""")

    # ---- outro ----
    end_sub = f'\n      <div id="outro-sub" class="font-body">{esc(cfg["end_sub"])}</div>' if cfg.get("end_sub") else ""
    (film / "compositions" / "outro.html").write_text(f"""<template>
  <style>
    {common_css}
    #root {{ position: absolute; inset: 0; }}
    #outro-bg {{ position: absolute; inset: 0; background: {bg}; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: {round(30 * k)}px; padding: 0 {L['pad']}px; text-align: center; }}
    img.outro-logo {{ width: {round(L['logo'] * 1.13)}px; height: auto; }}
    #outro-line {{ color: {text}; font-size: {L['end_line']}px; letter-spacing: -0.02em; line-height: 1.15; }}
    #outro-sub {{ color: {muted}; font-size: {L['end_sub']}px; }}
  </style>
  <div id="root" data-composition-id="outro" data-width="{W}" data-height="{H}">
    <div id="outro-bg" class="clip" data-start="0" data-duration="{OUTRO}">
      {mark("outro-logo")}
      <div id="outro-line" class="font-heading" data-var-text="endLine">{esc(cfg.get('end_line', ''))}</div>{end_sub}
    </div>
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    tl.fromTo("#outro-bg", {{ opacity: 0 }}, {{ opacity: 1, duration: {XF}, ease: "power1.out" }}, 0);
    tl.fromTo("#outro-line", {{ opacity: 0, y: 16 }}, {{ opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }}, 0.35);
    window.__timelines["outro"] = tl;
  </script>
</template>
""")

    # ---- root ----
    rec_dur = round(D, 3)
    punch_js = "\n".join(
        f'      tl.fromTo("#rec-wrap", {{ scale: 1, transformOrigin: "{p["origin"][0]}px {p["origin"][1]}px" }}, {{ scale: {p["scale"]}, duration: 0.55, ease: "power2.inOut" }}, {p["at"]});\n'
        f'      tl.to("#rec-wrap", {{ scale: 1, duration: 0.55, ease: "power2.inOut" }}, {round(p["at"] + 0.55 + p["hold"], 3)});'
        for p in punches)
    variables = json.dumps([
        {"id": "title", "type": "string", "label": "Title", "default": cfg["title"]},
        {"id": "kicker", "type": "string", "label": "Kicker", "default": cfg.get("kicker", "")},
        {"id": "endLine", "type": "string", "label": "End line", "default": cfg.get("end_line", "")},
    ])
    music_tag = (f'\n      <audio id="music" class="clip" src="assets/music.wav" data-start="0" data-duration="{round(probe(music), 3)}" data-track-index="7" data-volume="1"></audio>'
                 if music else "")
    (film / "index.html").write_text(f"""<!doctype html>
<html lang="en" data-composition-variables='{variables.replace("'", "&#39;")}'>
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="{GSAP}"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ margin: 0; width: {W}px; height: {H}px; overflow: hidden; background: {bg}; }}
      #root {{ position: relative; width: 100%; height: 100%; }}
      #rec-wrap {{ position: absolute; inset: 0; z-index: 1; overflow: hidden; }}
      #recording {{ position: absolute; inset: 0; width: {W}px; height: {H}px; object-fit: cover; }}
      #steps {{ z-index: 2; }}
      #captions {{ z-index: 3; }}
      #intro {{ z-index: 4; }}
      #outro {{ z-index: 5; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total}" data-width="{W}" data-height="{H}">
      <div id="rec-wrap">
        <video id="recording" class="clip" src="assets/recording.mp4" muted playsinline
               data-start="{T0}" data-duration="{rec_dur}" data-track-index="0"></video>
      </div>
      <div id="intro" data-composition-id="intro" data-composition-src="compositions/intro.html"
           data-start="0" data-duration="{INTRO}" data-track-index="1" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>
      <div id="steps" data-composition-id="steps" data-composition-src="compositions/steps.html"
           data-start="{T0}" data-duration="{rec_dur}" data-track-index="2" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html"
           data-start="{T0}" data-duration="{rec_dur}" data-track-index="3" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>
      <div id="outro" data-composition-id="outro" data-composition-src="compositions/outro.html"
           data-start="{round(T0 + D - XF, 3)}" data-duration="{OUTRO}" data-track-index="4" data-track-kind="graphics" data-width="{W}" data-height="{H}"></div>
      <audio id="narration" class="clip" src="assets/narration.wav" data-start="0" data-duration="{nar_d}" data-track-index="5" data-volume="1"></audio>
      <audio id="clicks" class="clip" src="assets/clicks.wav" data-start="0" data-duration="{clk_d}" data-track-index="6" data-volume="1"></audio>{music_tag}
    </div>
    <script>
      const tl = gsap.timeline({{ paused: true }});
      tl.set("#rec-wrap", {{ scale: 1, transformOrigin: "50% 50%" }}, 0);
{punch_js}
      window.__timelines["main"] = tl;
    </script>
  </body>
</html>
""")

    # ---- HyperFrames project files ----
    ver = (sc.get("walkthrough") or {}).get("hyperframes_version") or "0.9.40"
    if not (film / "hyperframes.json").exists():
        (film / "hyperframes.json").write_text(json.dumps({
            "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
            "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
            "media": {"autoProxy": True}}, indent=2) + "\n")
    (film / "package.json").write_text(json.dumps({
        "name": name, "private": True, "type": "module",
        "scripts": {k_: f"npx --yes hyperframes@{ver} {k_ if k_ != 'dev' else 'preview'}" for k_ in ("dev", "check", "render")}},
        indent=2) + "\n")

    print(f"film: {film}\n  {W}x{H}, {total}s (recording {D:.2f}s from {T0}s), {len(lines)} narration lines, "
          f"{len(clicks_t)} clicks ({click.name}), {len(caps)} captions{' burned in' if burn else ''}, "
          f"{len(punches)} punch-ins{', music' if music else ''}\n  captions file: {out_mp4.with_suffix('.srt')}")

    if a.render:
        env = {**os.environ, "HYPERFRAMES_NO_UPDATE_CHECK": "1"}
        hf = ["npx", "--yes", "--prefer-offline", f"hyperframes@{ver}"]
        r = subprocess.run(hf + ["check"], cwd=film, env=env)
        if r.returncode != 0:
            print("hyperframes check reported problems (above). A contrast warning on a frame that's mid-fade is usually "
                  "harmless; look at that frame before changing anything. Rendering anyway.")
        subprocess.run(hf + ["render", "-q", "delivery", "-o", str(out_mp4)], cwd=film, env=env, check=True)
        print(f"rendered {out_mp4}\nnext: .venv/bin/python walkthrough/rig/check_film.py {out_mp4}")
    else:
        print(f"next: cd \"{film}\" && npx --yes hyperframes@{ver} check && "
              f"npx --yes hyperframes@{ver} render -q delivery -o \"{out_mp4}\"   (or run this again with --render)")


if __name__ == "__main__":
    main()
