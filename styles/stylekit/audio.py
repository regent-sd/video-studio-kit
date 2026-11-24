"""Sound for the builders: lay clips' sound on the timeline as runs with short crossfades at each cut, clean up
speech, fit a music bed and duck it under the voice, and level the whole mix (voice at -14 LUFS).

A "clip" here is one stretch of sound on the reel's timeline:
    dict(path=..., start=<source seconds>, len=<seconds>, t0=<reel seconds>, voice=True|False,
         speed=1.0, hold=0, hp=<low cut Hz or None>, clean=<already cleaned: skip the voice chain>)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import media

SR = 48000
HANDLE = 0.05   # seconds of extra sound each side of a cut; neighbours crossfade over 2 x HANDLE
VOICE_FX = ("highpass=f=80,afftdn=nf=-25,acompressor=threshold=-22dB:ratio=3:attack=8:release=180:makeup=3,"
            "equalizer=f=3200:t=q:w=1.2:g=2.5")
# A hummy room: steeper low cut, stronger noise reduction, more presence so consonants survive the music.
HUM_FX = ("highpass=f={hp}:poles=2,highpass=f={hp}:poles=2,afftdn=nr=20:nf=-35,"
          "equalizer=f=2500:t=q:w=1.5:g=4,equalizer=f=5000:t=q:w=1.5:g=3,"
          "acompressor=threshold=-16dB:ratio=2:attack=10:release=200:makeup=2")
FINAL = "loudnorm=I=-14:TP=-1.5:LRA=11"


def atempo(speed):
    parts, s = [], speed
    while s > 2.0:
        parts.append("atempo=2.0")
        s /= 2.0
    while s < 0.5:
        parts.append("atempo=0.5")
        s /= 0.5
    return ",".join(parts + [f"atempo={s:.4f}"])


def runs(clips, work, voice_fx=True):
    """Merge clips whose sound carries straight on (same file, contiguous) into one run, so a sentence split
    across a picture cut plays as one take. Render each run with handles and fades. Returns [(wav, delay)]."""
    merged = []
    for c in clips:
        c = dict(dict(speed=1.0, hold=0, hp=None, clean=False, voice=False), **c)
        p = merged[-1] if merged else None
        if (p and p["path"] == c["path"] and p["speed"] == c["speed"] == 1 and not p["hold"]
                and p["voice"] == c["voice"] and p.get("hp") == c.get("hp") and p.get("clean") == c.get("clean")
                and abs(p["start"] + p["len"] - c["start"]) < 0.02 and abs(p["t0"] + p["len"] - c["t0"]) < 0.02):
            p["len"] += c["len"]
            p["hold"] = c["hold"]
        else:
            merged.append(c)
    out = []
    Path(work).mkdir(parents=True, exist_ok=True)
    for k, r in enumerate(merged):
        wav = os.path.join(work, f"run{k:02d}.wav")
        if not media.probe(r["path"])["has_audio"]:
            media.ff(["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{r['len'] / r['speed'] + r['hold']:.3f}", wav])
            out.append((wav, r["t0"]))
            continue
        af = []
        if r["speed"] != 1:
            h_in = h_out = 0.0
            af.append(atempo(r["speed"]))
        else:
            h_in, h_out = min(HANDLE, r["start"], r["t0"]), HANDLE
        tl_len = r["len"] / r["speed"] + h_in + h_out
        if r.get("clean") or not voice_fx:
            pass
        elif r.get("hp") and r["voice"]:
            af.append(HUM_FX.format(hp=r["hp"]))
        elif r.get("hp"):
            af.append(f"highpass=f={r['hp']}:poles=2")
        elif r["voice"]:
            af.append(VOICE_FX)
        fi, fo = max(0.02, 2 * h_in), max(0.02, 2 * h_out)
        af += [f"afade=t=in:d={fi:.3f}", f"afade=t=out:st={max(0.0, tl_len - fo):.3f}:d={fo:.3f}"]
        if r["hold"]:
            af.append(f"apad=pad_dur={r['hold']}")
        media.ff(["-ss", f"{r['start'] - h_in:.3f}", "-t", f"{r['len'] + h_in + h_out:.3f}", "-i", r["path"], "-vn",
                  "-af", ",".join(af), "-ar", SR, "-ac", 2, wav])
        out.append((wav, r["t0"] - h_in))
    return out


def lay(run_list, total, out, extra=""):
    """The runs on one timeline, total seconds long, as a wav (no levelling unless `extra` adds a filter)."""
    ins, chain = [], []
    for k, (wav, delay) in enumerate(run_list):
        ins += ["-i", wav]
        ms = int(round(max(0.0, delay) * 1000))
        chain.append(f"[{k}:a]adelay={ms}|{ms}[r{k}]")
    n = len(run_list)
    if not n:
        media.ff(["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=stereo", "-t", f"{total:.3f}", out])
        return out
    chain.append("".join(f"[r{k}]" for k in range(n)) + f"amix=inputs={n}:normalize=0:duration=longest,"
                 f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={total:.3f}{(',' + extra) if extra else ''}[a]")
    media.ff(ins + ["-filter_complex", ";".join(chain), "-map", "[a]", "-ar", SR, "-ac", 2, "-c:a", "pcm_s16le", out])
    return out


def music_files(spec):
    """[(absolute path, start seconds)] for a music spec: "path", "path@12.5" or a list of them. Relative paths
    are looked for in the music library (settings: music_library), then from the current folder."""
    from . import paths
    items = [spec] if isinstance(spec, str) else list(spec)
    lib = paths.sc.get("music_library")
    out = []
    for it in items:
        path, at, start = it.rpartition("@") if "@" in it and it.rsplit("@", 1)[1].replace(".", "", 1).isdigit() else (it, "", "")
        p = Path(os.path.expanduser(path))
        if not p.is_absolute() and lib and (Path(lib) / p).exists():
            p = Path(lib) / p
        if not p.exists():
            raise FileNotFoundError(f"music track not found: {path} (looked in the music library: {lib})")
        out.append((str(p.resolve()), float(start) if at else 0.0))
    return out


def fit_music(spec, seconds, out):
    """A music bed `seconds` long from a track you picked (see music_files), fitted by fit_music.py so it ends
    on its own ending."""
    args = [p + (f"@{st:g}" if st else "") for p, st in music_files(spec)]
    subprocess.run([sys.executable, "-I", str(Path(__file__).with_name("fit_music.py")), out, f"{seconds:.2f}", *args], check=True)
    return out


def duck(music_wav, total, voice_windows, out, level=0.30, under_voice=0.10, fade_out=0.3):
    """The music at `level`, dropping to `under_voice` while someone speaks (voice_windows: [(t0, t1)])."""
    vol = (f"if({'+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in voice_windows)},{under_voice},{level})"
           if voice_windows else f"{level}")
    media.ff(["-i", music_wav, "-af", f"atrim=0:{total:.3f},asetpts=PTS-STARTPTS,apad=whole_dur={total:.3f},"
              f"afade=t=out:st={max(0.0, total - fade_out):.3f}:d={fade_out},volume='{vol}':eval=frame",
              "-ar", SR, "-ac", 2, "-c:a", "pcm_s16le", out])
    return out


def db_to_gain(db):
    return 10 ** (float(db) / 20)


def mix(tracks, out, total):
    """Sum wav tracks [(path, gain)] and level the result to -14 LUFS (true peak -1.5). Returns out."""
    ins = [x for p, _ in tracks for x in ("-i", p)]
    g = ";".join(f"[{k}:a]aformat=channel_layouts=stereo,volume={c:.4f}[p{k}]" for k, (_, c) in enumerate(tracks))
    g += ";" + "".join(f"[p{k}]" for k in range(len(tracks))) + \
         f"amix=inputs={len(tracks)}:normalize=0:duration=longest,atrim=0:{total:.3f},{FINAL},aresample={SR}[a]"
    media.ff(ins + ["-filter_complex", g, "-map", "[a]", "-ar", SR, "-ac", 2, "-c:a", "pcm_s16le", out])
    return out


def mux(video, sound, out, total, max_mb=28):
    """Picture + sound -> the finished mp4 (H.264, AAC). Bitrate kept so the file stays under ~max_mb."""
    vk = max(1500, min(6000, int(max_mb * 8192 / max(1.0, total)) - 220))
    media.ff(["-i", video, "-i", sound, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "slow",
              "-b:v", f"{vk}k", "-maxrate", f"{int(vk * 1.2)}k", "-bufsize", f"{vk * 2}k", "-pix_fmt", "yuv420p",
              "-r", media.FPS, "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
              "-c:a", "aac", "-b:a", "192k", "-ar", SR, "-t", f"{total:.3f}", "-movflags", "+faststart", out])
    return out
