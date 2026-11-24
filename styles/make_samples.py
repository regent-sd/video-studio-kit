#!/usr/bin/env python3
"""Sample contact sheets: one JPG per style and skin, made from whatever clips are in a folder.

    .venv/bin/python styles/make_samples.py --footage <folder> --out <folder> [--brand SLUG] [--only a,b]

    --footage   a shoot, its Raw/ folder, or any folder of clips (searched through subfolders)
    --out       where the sheets go (made if missing); a sheet from an earlier run is replaced
    --brand     the brand for the Brand skin and Hands-On Classic (default: the default brand)
    --only      some of: fastcut-dark, fastcut-brand, talking-head, hands-on

It makes:
    Fast Cut - Dark.jpg          one frame per scene of the Fast Cut example, Dark skin
    Fast Cut - Brand.jpg         the same in the brand's skin
    Talking Head Classic.jpg     frames from a short Talking Head Classic reel
    Hands-On Classic.jpg         frames from a short Hands-On Classic reel (a starter spec from the clips)

The talking clip is the one with the most words said. When nothing in the folder has speech, captions show
placeholder words: these sheets show the look, not a real edit. Short test renders go to the work folder.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "talking-head"))
sys.path.insert(0, str(HERE / "hands-on"))
from stylekit import draw, media, paths  # noqa: E402

ALL = ["fastcut-dark", "fastcut-brand", "talking-head", "hands-on"]
NAMES = {"fastcut-dark": "Fast Cut - Dark", "fastcut-brand": "Fast Cut - Brand",
         "talking-head": "Talking Head Classic", "hands-on": "Hands-On Classic"}


def frames_of(video, n=8):
    """n frames spread over a video (skipping the first and last moments)."""
    d = media.probe(video)["duration"]
    out = []
    for k in range(n):
        t = 0.3 + (d - 0.6) * k / max(1, n - 1)
        p = Path(tempfile.mkdtemp()) / "f.png"
        media.ff(["-ss", f"{t:.3f}", "-i", video, "-frames:v", 1, p])
        out.append(draw.label(media.Image.open(p).convert("RGB"), f"{t:.2f}"))
    return out


def scratch_out(name):
    """A fresh file name in the work folder for a sample render."""
    return paths.work_dir("samples") / f"{name}_{time.strftime('%Y%m%d-%H%M%S')}.mp4"


def fastcut(footage, out_dir, skin, brand):
    from fastcut import example
    reel = example.build(footage, skin=skin, brand=brand, seconds=16.0, name=f"sample_fastcut_{skin}")
    title = f"Fast Cut, {'Dark' if skin == 'dark' else 'Brand'} skin" + (f" ({reel.skin.brand['name']})" if skin == "brand" else "")
    return reel.sheet(path=out_dir / f"{NAMES['fastcut-' + skin]}.jpg", title=title)


def talking_head(footage, out_dir, brand):
    import example_reel
    video, _, _ = example_reel.make(footage, seconds=9.0, name="sample_talking_head", out=scratch_out("talking_head"))
    p = out_dir / f"{NAMES['talking-head']}.jpg"
    draw.contact_sheet(frames_of(video), cols=8, title="Talking Head Classic").save(p, quality=90)
    print(p)
    return p


def hands_on(footage, out_dir, brand):
    import build_reel
    spec = build_reel.starter(footage, brand, seconds=10.0)
    spec["name"] = "sample_hands_on"
    f = paths.work_dir("samples") / "hands_on_spec.json"
    f.write_text(json.dumps(spec, indent=1))
    video = build_reel.main(str(f), out=scratch_out("hands_on"))
    p = out_dir / f"{NAMES['hands-on']}.jpg"
    b = paths.sc.brand(brand)
    draw.contact_sheet(frames_of(video), cols=8, title=f"Hands-On Classic ({b['name']})").save(p, quality=90)
    print(p)
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--footage", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--brand")
    ap.add_argument("--only")
    a = ap.parse_args()
    footage = paths.shoot_dir(a.footage)
    if not paths.raw_clips(footage):
        raise SystemExit(f"No video clips in {footage}")
    out_dir = Path(a.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    want = [x.strip() for x in a.only.split(",")] if a.only else ALL
    made, failed = [], []
    for job in want:
        if job not in ALL:
            raise SystemExit(f"--only takes: {', '.join(ALL)}")
        print(f"\n{NAMES[job]}", flush=True)
        try:
            if job.startswith("fastcut"):
                made.append(fastcut(footage, out_dir, job.split("-")[1], a.brand))
            elif job == "talking-head":
                made.append(talking_head(footage, out_dir, a.brand))
            else:
                made.append(hands_on(footage, out_dir, a.brand))
        except (Exception, SystemExit) as e:
            failed.append((job, e))
            print(f"  {NAMES[job]} failed: {e}", flush=True)
    print()
    for p in made:
        print("made", p)
    for job, e in failed:
        print("failed", NAMES[job], "-", e)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
