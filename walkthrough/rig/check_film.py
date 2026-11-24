#!/usr/bin/env python3
"""Check a finished walkthrough before anyone sees it: frames, gaps, loudness.

    .venv/bin/python walkthrough/rig/check_film.py <work>/out/example.mp4 [--every 2] [--at 4.5,12]

Prints the size, length, loudness (integrated LUFS and true peak), any stretch of silence
longer than 1.5 s inside the film (dead air), and any black frames. Saves contact sheets
(one frame every --every seconds, 16 to a sheet) and single frames at --at times to
<work>/checks/<name>/, so Claude (or you) can look at every part of the picture.
It can't tell you how the voice sounds: a person listens before it goes out.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
import studio_config as sc  # noqa: E402


def ff(*args) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, text=True).stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", type=Path)
    ap.add_argument("--every", type=float, default=2.0, help="seconds between frames on the contact sheets")
    ap.add_argument("--at", default="", help="also save full frames at these times, e.g. 3.2,14")
    ap.add_argument("--out", type=Path, help="where to save the sheets (default <work>/checks/<name>)")
    a = ap.parse_args()
    v = a.video
    if not v.exists():
        sys.exit(f"No file at {v}")
    work = Path((sc.get("walkthrough") or {}).get("work_dir") or "~/Movies/Walkthroughs").expanduser()
    out = a.out or work / "checks" / v.stem
    out.mkdir(parents=True, exist_ok=True)

    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,r_frame_rate",
                                      "-of", "json", str(v)], capture_output=True, text=True, check=True).stdout)
    dur = float(info["format"]["duration"])
    vs = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    print(f"{v.name}: {vs.get('width')}x{vs.get('height')}, {dur:.2f}s, {vs.get('r_frame_rate')} fps, audio: {'yes' if has_audio else 'NO'}")

    problems = []
    if has_audio:
        e = ff("-i", str(v), "-af", "ebur128=peak=true", "-f", "null", "-")
        i_lufs = re.findall(r"I:\s+(-?[\d.]+) LUFS", e)
        peak = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", e)
        if i_lufs:
            lufs = float(i_lufs[-1])
            tp = float(peak[-1]) if peak else None
            print(f"loudness: {lufs:.1f} LUFS integrated, true peak {tp if tp is not None else '?'} dBTP (aim for about -14 to -16 LUFS, peak under -1)")
            if lufs < -20 or lufs > -12:
                problems.append(f"loudness {lufs:.1f} LUFS is outside -20..-12")
            if tp is not None and tp > -1.0:
                problems.append(f"true peak {tp} dBTP is above -1")
        s = ff("-i", str(v), "-af", "silencedetect=noise=-45dB:d=1.5", "-f", "null", "-")
        starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", s)]
        ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", s)]
        gaps = [(st, en) for st, en in zip(starts, ends + [dur]) if st > 3.5 and en < dur - 3.5]
        for st, en in gaps:
            problems.append(f"{en - st:.1f}s of silence at {st:.1f}-{en:.1f}s (dead air?)")
    else:
        problems.append("no audio track")

    b = ff("-i", str(v), "-vf", "blackdetect=d=0.25:pix_th=0.08", "-an", "-f", "null", "-")
    for st, en in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", b):
        problems.append(f"black frames {float(st):.2f}-{float(en):.2f}s")

    w = 480 if (vs.get("width", 1920) >= vs.get("height", 1080)) else 270
    n = max(1, int(dur / a.every))
    sheets = (n + 15) // 16
    for k in range(sheets):
        start = k * 16 * a.every
        sheet = out / f"sheet_{k + 1:02d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.2f}", "-i", str(v), "-vf",
                        f"fps=1/{a.every},scale={w}:-2,drawtext=text='%{{pts\\:hms\\:{start:.2f}}}':x=6:y=6:fontsize=16:fontcolor=white:box=1:boxcolor=black@0.6,tile=4x4",
                        "-frames:v", "1", str(sheet)], check=True)
        print(f"sheet: {sheet}  ({start:.0f}s-{min(dur, start + 16 * a.every):.0f}s)")
    for t in [x for x in a.at.split(",") if x.strip()]:
        f = out / f"frame_{float(t):06.2f}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", t, "-i", str(v), "-frames:v", "1", str(f)], check=True)
        print(f"frame: {f}")

    print("problems:" if problems else "no problems found in the numbers. Look at every sheet, then listen to the whole film.")
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
