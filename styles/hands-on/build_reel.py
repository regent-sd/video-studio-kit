#!/usr/bin/env python3
"""Hands-On Classic builder: a 9:16 reel from a JSON edit spec. Cuts segments from one or more cameras, grades
them in the brand's look, adds the graphics (hook, captions, tags, counter, end card), mixes the footage's own
sound and any voice with a music bed you picked, and keeps the build record.

    .venv/bin/python styles/hands-on/build_reel.py <spec.json> [--shoot "<shoot>"] [--music TRACK] [--out FILE]
    .venv/bin/python styles/hands-on/build_reel.py --starter "<shoot or folder>" [--brand SLUG] > my-spec.json

It writes <shoot>/Style Tests/<name>_vN.mp4 (never over an existing file), <video>.words.txt, the build record in
its work folder (work/<name>/) and the sound-effect moments (work/<name>/sfx_events.json). SPEC.md describes every
field; example-spec.json is a full example for the demo shoot.

Spec fields, in short:
  name           file name stem for the video
  shoot          the shoot folder ("2026-03-14 Kitchen Remodel"; a title alone, "Demo Shoot", finds the newest
                 shoot with that title). Clip paths are looked for in its Raw/ folders.
  brand          brands/<slug> (default: the default brand): colours, fonts, logo, end line, grade
  sources        {alias: {"path": "<clip>", "camera": "pov"|"cam", "grade": "window"|"none"|<look>}}
  source         one clip for every segment, instead of sources
  caption_style  "block" (brand block) or "plain" (white with a shadow); default: the brand's
  music_file     a track you picked (music library or a path); "file@12.5" starts 12.5 s in; a list plays in order.
                 No music_file: no music (every video gets its own track; none is made up).
  music_level    music volume under the footage sound (default 0.30); voice_duck: under a voice (default 0.12)
  word_fixes     {"heard": "meant"} for words the transcript gets wrong
  fx             reel-level graphics; a negative "start" counts back from the end
  effects        the effects library, in reel time, before the graphics; effects_skin (default the brand's)
  segments[]     a, b: source seconds (or "say": [first words, last words] to cut the sound by what's said)
                 src, speed, caps, subs, caption_y, fx, zoom [x, y, w, h], pullout, blur_top, face_light,
                 audio (seconds, or {"src", "t"} / {"src", "say"}), voice, low_cut, voice_clean, mute, hold
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import handson_graphics as gfx  # noqa: E402
from stylekit import audio as AU  # noqa: E402
from stylekit import fxhook, media, paths, record  # noqa: E402
from stylekit import words as W_  # noqa: E402

W, H, FPS = 1080, 1920, 30
STYLE = "hands-on"


def run(cmd):
    media.ff(cmd)


def grade_for(spec_brand, src):
    """The brand's look (brand.json "grade": warm, neutral or cool) for this source."""
    look = spec_brand.b.get("grade", "warm")
    g = src.get("grade")
    if g == "none":
        return "null"
    if g and g not in ("window", "pov", "cam"):
        return media.grade(g)
    return media.grade(look, src.get("camera") == "pov", window=(g == "window"))


def top_mask(path):
    """White over the top 22% of the frame, fading to clear by 40% (softens hair across a glasses lens)."""
    m = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(m)
    for y in range(int(H * 0.40)):
        v = 255 if y < H * 0.22 else int(255 * (1 - (y - H * 0.22) / (H * 0.18)))
        d.line([(0, y), (W, y)], fill=v)
    m.save(path)


def face_mask(path, fl):
    """A feathered ellipse: full strength at the centre, gone by about 1.6x the radius (output pixels)."""
    import numpy as np
    y, x = np.mgrid[0:H, 0:W].astype(float)
    d2 = ((x - fl["x"]) / fl["rx"]) ** 2 + ((y - fl["y"]) / fl["ry"]) ** 2
    a = fl.get("amount", 0.6) * np.exp(-0.9 * d2)
    Image.fromarray((a * 255).clip(0, 255).astype("uint8"), "L").save(path)


def subtitle_events(ws, t0, dur, offset, fixes, max_chars=22):
    """Word-for-word captions: the words said from t0 for dur seconds, chunked short, on the reel timeline."""
    words = []
    for w in ws:
        if t0 - 0.05 <= w["s"] < t0 + dur - 0.1:
            words.append((w["s"] - t0, fixes.get(w["w"], w["w"])))
    chunks, cur = [], []
    for a, w in words:
        if cur and len(" ".join(x for _, x in cur + [(a, w)])) > max_chars:
            chunks.append(cur)
            cur = []
        cur.append((a, w))
        if w[-1:] in ".,?!" and len(cur) >= 2:
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    events = []
    for i, ch in enumerate(chunks):
        s = max(0.0, ch[0][0] - 0.12)
        e = chunks[i + 1][0][0] - 0.12 if i + 1 < len(chunks) else dur
        text = " ".join(w for _, w in ch).rstrip(",")
        events.append({"type": "caption", "text": text, "anim": "pop", "start": offset + s,
                       "end": offset + min(dur, max(e, s + 0.4))})   # never past its own shot
    return events


def resolve_shoot(spec, override=None):
    s = override or spec.get("shoot")
    if not s:
        return None
    p = paths.shoot_dir(s)
    if p.exists():
        return p
    root = paths.content_root()
    hits = sorted(root.glob(f"* {s}")) if root.exists() else []
    if hits:
        return hits[-1]
    raise SystemExit(f"No shoot folder '{s}' in {root}.")


def said(src_path, words_pair):
    """(start, end) of the sound from the first words through the last words, cut in pauses."""
    ws = W_.words_for(src_path)
    if not ws:
        raise SystemExit(f"{Path(src_path).name} has no transcript words to cut by.")
    first, last = words_pair
    i0 = W_.find(ws, first)
    i1 = W_.find(ws, last, ws[i0]["s"]) + len(last.split()) - 1
    return W_.cut_points(src_path, ws, i0, i1)


def main(spec_path, out=None, shoot_override=None, music=None):
    spec = json.load(open(spec_path))
    if music:
        spec["music_file"] = music
    shoot = resolve_shoot(spec, shoot_override)
    br = gfx.Brand(spec.get("brand"))

    def clip_path(p):
        return str(paths.find_clip(p, shoot) if shoot else paths.find_clip(Path(spec_path).parent / p if not os.path.isabs(os.path.expanduser(p)) else p))

    sources = {k: dict(v, path=clip_path(v["path"])) for k, v in spec.get("sources", {}).items()}
    if "source" in spec:
        sources["source"] = {"path": clip_path(spec["source"])}
    style = spec.get("caption_style", br.caption_style)
    fixes = spec.get("word_fixes", {})
    name = spec.get("name") or Path(spec_path).stem
    work = paths.work_dir(STYLE, name)
    tmp = Path(tempfile.mkdtemp(prefix="handson-", dir=work))
    mask = tmp / "topmask.png"
    top_mask(mask)

    parts, clips, events, voice_windows, used, t = [], [], [], [], [], 0.0
    reel_words = []
    for i, seg in enumerate(spec["segments"]):
        src = sources[seg.get("src", "source")]
        speed = seg.get("speed", 1.0)
        aud = seg.get("audio")
        audio_src = sources[aud["src"]] if isinstance(aud, dict) and aud.get("src") else src
        # cut by what's said: the sound runs from the first words through the last, the picture for as long
        say = seg.get("say") or (aud.get("say") if isinstance(aud, dict) else None)
        if say:
            sa, sb = said(audio_src["path"], say)
            if aud is None or not isinstance(aud, dict):
                seg = dict(seg, a=sa, b=sb)
            else:
                seg = dict(seg, b=seg.get("a", 0.0) + (sb - sa) * speed, audio=dict(aud, t=sa))
                aud = seg["audio"]
        span = seg["b"] - seg["a"]
        hold = seg.get("hold", 0)
        n = int(round((span / speed + hold) * FPS))      # whole frames, so the timeline never drifts
        dur = n / FPS - hold
        grade = grade_for(br, src)
        retime = f",setpts=(PTS-STARTPTS)/{speed}" if speed != 1 else ""
        tail = f",tpad=stop_mode=clone:stop_duration={hold + 1}" if hold else ",tpad=stop_mode=clone:stop_duration=1"
        cmd = ["-ss", f"{seg['a']}", "-t", f"{span + 0.5}", "-i", src["path"]]
        n_in = 1
        if seg.get("pullout"):
            vf = (f"[0:v]{grade},split[a][b];[b]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                  f"gblur=sigma=28,eq=brightness=-0.07:saturation=0.85[bg];[a]scale={W}:-2[fg];"
                  f"[bg][fg]overlay=0:(H-h)/2{retime},fps={FPS}{tail}[v]")
        else:
            if "zoom" in seg:
                crop = f"crop={seg['zoom'][2]}:{seg['zoom'][3]}:{seg['zoom'][0]}:{seg['zoom'][1]}"
            else:   # 9:16, following the person when there is one (else the centre)
                bx = media.frame_for(src["path"], "full")[0]
                crop = f"crop={bx[2]}:{bx[3]}:{bx[0]}:{bx[1]}"
            base = f"[0:v]{grade},{crop},scale={W}:{H}:flags=lanczos{retime},fps={FPS}"
            if seg.get("blur_top"):
                cmd += ["-loop", "1", "-t", f"{dur + 1}", "-i", mask]
                vf = (f"{base},split[a][b];[b]gblur=sigma=28[bb];[{n_in}:v]format=gray[m];"
                      f"[bb][m]alphamerge[bl];[a][bl]overlay=0:0:shortest=1{tail}[v]")
            elif "face_light" in seg:
                fmask = tmp / f"face{i:02d}.png"
                face_mask(fmask, seg["face_light"])
                cmd += ["-loop", "1", "-t", f"{dur + 1}", "-i", fmask]
                vf = (f"{base},split[a][b];[b]{media.FACE_LIFT}[lb];[{n_in}:v]format=gray[m];"
                      f"[lb][m]alphamerge[lit];[a][lit]overlay=0:0:shortest=1{tail}[v]")
            else:
                vf = f"{base}{tail}[v]"
        # the sound under this shot
        audio_t, aspeed = seg["a"], speed
        if aud is not None:
            audio_t = aud["t"] if isinstance(aud, dict) else aud
            aspeed = 1.0
        if seg.get("voice"):
            voice_windows.append((t, t + dur))
        if not seg.get("mute"):   # every word heard, in reel time (captions, effects on a word, verify.py)
            for w in W_.words_for(audio_src["path"]):
                if audio_t - 0.08 <= w["s"] < audio_t + dur * aspeed - 0.05:
                    reel_words.append({"w": w["w"], "s": t + (w["s"] - audio_t) / aspeed, "e": t + (w["e"] - audio_t) / aspeed})
        clips.append({"path": audio_src["path"], "start": audio_t, "len": dur * aspeed, "speed": aspeed,
                      "voice": bool(seg.get("voice")), "hold": hold, "t0": t, "hp": seg.get("low_cut"),
                      "clean": bool(seg.get("voice_clean")), "mute": bool(seg.get("mute"))})
        used.append((src["path"], seg["a"], seg["a"] + dur * speed))
        if not seg.get("mute") and (audio_src is not src or abs(audio_t - seg["a"]) > 0.01):
            used.append((audio_src["path"], audio_t, audio_t + dur * aspeed))
        vf = vf[:-3] + ",setpts=PTS-STARTPTS,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"
        part = tmp / f"seg{i:02d}.mp4"
        run(cmd + ["-filter_complex", vf, "-map", "[v]", "-an", "-frames:v", n,
                   "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-pix_fmt", "yuv420p", part])
        parts.append(str(part))
        seg_end = n / FPS
        cap_pos = {"y": seg["caption_y"]} if "caption_y" in seg else {}
        for text, s, e in seg.get("caps", []):
            events.append({"type": "caption", "text": text, "style": style, **cap_pos,
                           "start": t + s + 0.05, "end": t + (e if e is not None else seg_end) - 0.05})
        if seg.get("subs"):
            events += [dict(ev, style=style, **cap_pos)
                       for ev in subtitle_events(W_.words_for(audio_src["path"]), audio_t, dur, t, fixes)]
        for fx in seg.get("fx", []):
            events.append(dict(fx, start=t + fx.get("start", 0), end=t + (fx["end"] if fx.get("end") is not None else seg_end)))
        t += seg_end

    for fx in spec.get("fx", []):
        s = fx["start"] if fx["start"] >= 0 else t + fx["start"]
        e = fx.get("end")
        events.append(dict(fx, start=s, end=t + 0.1 if e is None else (e if e >= 0 else t + e)))

    overlay = gfx.render(events, t, str(work / "gfx"), br)
    # the sound: muted shots are silence; each run is laid with short handles, so neighbours crossfade at a cut
    live = [c for c in clips if not c.get("mute")]
    runs = AU.runs(live, str(tmp / "runs"))
    level = spec.get("music_level", 0.30) if spec.get("music_file") else 0
    voice_wav = AU.lay(runs, t, str(work / "voice.wav"), "loudnorm=I=-17:TP=-3" if level else "")
    if spec.get("effects"):   # effects go on the joined picture, before the graphics
        clean = tmp / "clean.mp4"
        run([x for p in parts for x in ("-i", p)] +
            ["-filter_complex", "".join(f"[{k}:v]" for k in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[cv]",
             "-map", "[cv]", "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", clean])
        skin = spec.get("effects_skin") or f"brand:{br.b.get('slug', '')}"
        parts = [fxhook.effects_pass(clean, spec["effects"], words=reel_words, audio=voice_wav, skin=skin,
                                     out=tmp / "clean_fx.mp4")]
    tracks = [(voice_wav, 1.0)]
    music = None
    if level > 0:
        raw = AU.fit_music(spec["music_file"], t, str(work / "music_fit.wav"))
        music = AU.duck(raw, t, voice_windows, str(work / "music.wav"), level, spec.get("voice_duck", 0.12))
        tracks.append((music, 1.0))
    elif not spec.get("music_file"):
        print("  no music_file in the spec: no music bed (pick a track for this video; never reuse one)")
    mix = AU.mix(tracks, str(work / "sound.wav"), t)
    dest = paths.output_for(name, shoot, out, near=next(iter(sources.values()))["path"])
    n = len(parts)
    vk = max(1500, min(6000, int(28 * 8192 / max(1.0, t)) - 220))   # under ~28 MB so it can go to a phone
    run([x for p in parts for x in ("-i", p)] + ["-framerate", str(FPS), "-i", overlay, "-i", mix, "-filter_complex",
         "".join(f"[{k}:v]" for k in range(n)) + f"concat=n={n}:v=1:a=0[cv];"
         f"[cv][{n}:v]overlay=0:0:format=auto:shortest=1,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[vout]",
         "-map", "[vout]", "-map", f"{n + 1}:a", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
         "-c:v", "libx264", "-preset", "slow", "-b:v", f"{vk}k", "-maxrate", f"{int(vk * 1.2)}k", "-bufsize", f"{vk * 2}k",
         "-pix_fmt", "yuv420p", "-r", FPS, "-c:a", "aac", "-b:a", "192k", "-ar", 48000, "-t", f"{t:.3f}",
         "-movflags", "+faststart", dest])
    W_.write_words(str(dest) + ".words.txt", sorted(reel_words, key=lambda w: w["s"]))
    (work / "cuts.json").write_text(json.dumps({"video": str(dest), "voice": str(voice_wav),
                                                "cuts": [round(c["t0"], 3) for c in clips[1:]]}, indent=1))
    (work / "sfx_events.json").write_text(json.dumps(gfx.sfx_events(events), indent=1))
    print(f"{dest}  {t:.1f} s, {len([e for e in events if e['type'] != 'caption'])} graphics")
    print(f"  sound-effect moments: {work / 'sfx_events.json'} (the picture's silent moments only)")
    keep_record(spec_path, spec, dest, t, events, voice_wav, music, used, work)
    return dest


def keep_record(spec_path, spec, out, total, events, voice_wav, music, used, work):
    """The build record: every graphic and library effect with its times, sped-up shots, the raw seconds used,
    the song, and the sound as two tracks (footage sound and voice; music). A problem prints one line."""
    rec = record.new("styles/hands-on/build_reel.py", [spec_path])
    if rec is None:
        return
    try:
        for ev in events:
            if ev.get("type") != "caption":
                rec.graphic(dict(ev, end=min(ev["end"], total)))
        t = 0.0
        for seg in spec["segments"]:
            speed, hold = seg.get("speed", 1.0), seg.get("hold", 0)
            dur = (seg["b"] - seg["a"]) / speed if "b" in seg else 0
            if speed > 1:
                record.layout(rec, "hands-on", "fast", t, t + dur, f"{speed:g}x speed")
            elif speed < 1:
                record.layout(rec, "hands-on", "slow", t, t + dur, f"{speed:g}x speed")
            t += dur + hold
        for name, a, b in fxhook.applied():
            rec.effect(name, a, b)
        for clip, a, b in used:
            record.used(rec, clip, a, b)
        rec.track("voice_nat", [(voice_wav, 1.0)])
        if music:
            rec.song(AU.music_files(spec["music_file"])[0][0])
            rec.track("music", [(music, 1.0)])
    except Exception as e:
        print(f"  [build record] {e}")
    record.save(rec, out, keep_in=work)


# ---------------------------------------------------------------- a starter spec from any footage
def starter(footage, brand=None, seconds=14.0):
    """A starter spec from whatever clips are in a shoot or folder: hands-at-work shots about 2 s each, the
    footage's own sound, a hook, short captions and the end card. Captions and hook are placeholders to rewrite."""
    folder = paths.shoot_dir(footage)
    clips = paths.raw_clips(folder)
    if not clips:
        raise SystemExit(f"No video clips in {folder}")
    shoot = paths.shoot_of(clips[0])
    srcs, segs, t = {}, [], 0.0
    # hands at work first: clips with no words said (by their transcripts, if they have one) come first
    clips = sorted(clips, key=lambda c: len(W_.words_for(c, make=False)) > 3)
    pick = clips[: max(4, min(6, len(clips)))]
    per = max(1.6, min(2.6, seconds / max(1, len(pick))))
    for k, c in enumerate(pick):
        alias = f"c{k + 1}"
        d = media.probe(c)["duration"]
        if d < 1.0:
            continue
        rel = str(c.relative_to(shoot / "Raw")) if shoot else str(c)
        cam = "pov" if any(p.lower() in ("pov", "glasses") for p in c.parts) else "cam"
        srcs[alias] = {"path": rel, "camera": cam}
        a = round(max(0.0, min(d * 0.3, d - per - 0.1)), 2)
        seg = {"src": alias, "a": a, "b": round(a + min(per, d - a - 0.05), 2)}
        if k == 0:
            seg["fx"] = [{"type": "hook", "text": "Made|by hand", "start": 0.0, "panel": True}]
        elif k % 2 == 1:
            seg["caps"] = [["step " + str((k + 1) // 2), 0, None]]
        elif k == 2:
            seg["fx"] = [{"type": "tag", "text": "by hand", "start": 0.2}]
        segs.append(seg)
        t += seg["b"] - seg["a"]
    segs[-1]["hold"] = 2.6
    spec = {"name": paths.safe_name(f"{(shoot or folder).name}_HandsOn"),
            "notes": "Starter spec: rewrite the hook, captions and tag from what the footage shows (these are placeholders).",
            "shoot": str(shoot) if shoot else None, "brand": brand, "sources": srcs, "music_level": 0.30,
            "segments": segs, "fx": [{"type": "endcard", "lines": "Made by hand", "start": -2.5}]}
    return {k: v for k, v in spec.items() if v is not None}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--shoot", help="use this shoot instead of the spec's")
    ap.add_argument("--music", help="use this track instead of the spec's music_file")
    ap.add_argument("--starter", metavar="FOOTAGE", help="print a starter spec for a shoot or folder of clips")
    ap.add_argument("--brand")
    a = ap.parse_args()
    if a.starter:
        print(json.dumps(starter(a.starter, a.brand), indent=1))
    elif a.spec:
        main(a.spec, a.out, a.shoot, a.music)
    else:
        ap.print_help()
