#!/usr/bin/env python3
"""Bring in a screen recording made outside the recorder (iOS Simulator, QuickTime, a phone)
so build_film.py can finish it like any take.

    .venv/bin/python walkthrough/rig/import_recording.py sim.mov --name app-signup --voice app-signup \\
        --starts 0.5,4.0,9.2,15.8 [--taps 3.1,8.8:0.5:0.82] [--trim 1.2:41] [--shape phone]

--voice     the voice folder (made by gen_voice.py) whose lines go on this recording
--starts    when each narration line starts, in seconds of the (trimmed) recording, in script order.
            Leave it out to lay the lines end to end with --gap seconds between them, then look at a
            contact sheet (check_film.py) and set real times.
--taps      when a tap or click happens, for click sounds and punch-ins: "t" or "t:x:y" (x, y from 0 to 1)
--trim      keep only start:end seconds of the recording
--shape     phone (1080x1920) or desktop (1920x1080); default: whichever the recording is closer to

Writes <work>/recordings/<name>/<name>.mp4 (30 fps, H.264, padded to the shape) and timeline.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import studio_config as sc  # noqa: E402

SIZES = {"phone": (1080, 1920), "desktop": (1920, 1080)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--name", required=True)
    ap.add_argument("--voice", required=True, help="voice folder name under <work>/voice/")
    ap.add_argument("--starts", default="")
    ap.add_argument("--gap", type=float, default=0.8)
    ap.add_argument("--taps", default="")
    ap.add_argument("--trim", default="")
    ap.add_argument("--shape", choices=list(SIZES))
    ap.add_argument("--bg", default="white", help="padding colour if the recording's shape doesn't fit exactly")
    a = ap.parse_args()

    work = Path((sc.get("walkthrough") or {}).get("work_dir") or "~/Movies/Walkthroughs").expanduser()
    vdir = work / "voice" / a.voice
    mpath = vdir / "manifest.json"
    if not mpath.exists():
        sys.exit(f"No voice at {vdir}. Make it first: gen_voice.py <script.md> --name {a.voice}")
    manifest = json.loads(mpath.read_text())
    lines = [(int(s), i, ln) for s, sc_ in sorted(manifest["scenes"].items(), key=lambda kv: int(kv[0]))
             for i, ln in enumerate(sc_["lines"], 1)]

    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                       "stream=width,height:format=duration", "-of", "json", str(a.video)],
                                      capture_output=True, text=True, check=True).stdout)
    w, h = probe["streams"][0]["width"], probe["streams"][0]["height"]
    shape = a.shape or ("phone" if h > w else "desktop")
    W, H = SIZES[shape]

    out = work / "recordings" / a.name
    out.mkdir(parents=True, exist_ok=True)
    mp4 = out / f"{a.name}.mp4"
    trim = []
    if a.trim:
        t0, t1 = (float(x) for x in a.trim.split(":"))
        trim = ["-ss", f"{t0}", "-to", f"{t1}"]
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *trim, "-i", str(a.video), "-an", "-vf",
                    f"fps=30,scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=decrease,"
                    f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color={a.bg},format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-movflags", "+faststart", str(mp4)], check=True)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                               capture_output=True, text=True, check=True).stdout)

    starts = [float(x) for x in a.starts.split(",") if x.strip()]
    if starts and len(starts) != len(lines):
        sys.exit(f"--starts has {len(starts)} times but the voice has {len(lines)} lines.")
    if not starts:
        t = 0.5
        for _, _, ln in lines:
            starts.append(round(t, 3))
            t += ln["seconds"] + a.gap
        print(f"lines laid end to end with {a.gap}s gaps (they need {t:.1f}s; the recording is {dur:.1f}s). "
              "Look at the recording and set --starts to when each action happens.")
    clicks = []
    for tap in [x for x in a.taps.split(",") if x.strip()]:
        p = tap.split(":")
        clicks.append({"t": float(p[0]), "x": float(p[1]) if len(p) > 2 else 0.5, "y": float(p[2]) if len(p) > 2 else 0.5})

    tl = {"name": a.name, "shape": shape, "size": {"width": W, "height": H}, "duration": round(dur, 3), "cuts": [],
          "clicks": clicks, "voice": {"engine": manifest.get("engine"), "profile": manifest.get("profile")},
          "imported_from": a.video.name,
          "lines": [{"scene": s, "line": i, "start": st, "seconds": ln["seconds"], "file": ln["file"], "text": ln["text"]}
                    for (s, i, ln), st in zip(lines, starts)]}
    late = [f"{x['scene']}.{x['line']}" for x in tl["lines"] if x["start"] + x["seconds"] > dur]
    (out / "timeline.json").write_text(json.dumps(tl, indent=2))
    print(f"imported {mp4}: {W}x{H}, {dur:.1f}s, {len(starts)} lines, {len(clicks)} taps")
    if late:
        print(f"warning: lines {', '.join(late)} run past the end of the recording and would play over the end card: trim less or start them earlier")
    print(f"next: build_film.py <film.json> --take {a.name}   (with \"voice\": \"voice/{a.voice}\" in the film.json)")


if __name__ == "__main__":
    main()
