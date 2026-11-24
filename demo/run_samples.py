#!/usr/bin/env python3
"""Render the style samples and the effect previews from the demo shoot.

    .venv/bin/python demo/run_samples.py
    .venv/bin/python demo/run_samples.py --brand my-brand          # in your brand's colours and fonts
    .venv/bin/python demo/run_samples.py --effects-only --only spotlight,orbit

It runs, with the demo shoot's Raw folder as the footage:
  styles/make_samples.py   -> <demo shoot>/Style Tests/Samples   (a contact sheet per style and skin)
  effects/make_previews.py -> <demo shoot>/Style Tests/Effects   (a short preview MP4 per effect, and a contact sheet)

Options:
  --shoot DIR        the shoot folder (default: the newest '<date> Demo Shoot' in your content folder)
  --brand SLUG       passed to both: the Brand skin with brands/<slug>/brand.json
  --styles-only / --effects-only
  --only a,b         only these effects (passed to make_previews.py)
  --sheet-only       effects: only the contact sheet, no videos (much quicker)

If one of the two tools isn't in your kit yet, it says so and runs the other.
Run demo/fetch_stock.py and demo/make_narration.py first.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_common as dc  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}


def say(*a):
    print(*a, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render the style samples and effect previews from the demo shoot.")
    ap.add_argument("--shoot")
    ap.add_argument("--brand")
    ap.add_argument("--styles-only", action="store_true")
    ap.add_argument("--effects-only", action="store_true")
    ap.add_argument("--only", help="effects only: these effects, comma-separated")
    ap.add_argument("--sheet-only", action="store_true", help="effects only: just the contact sheet")
    a = ap.parse_args()

    shoot = dc.shoot_dir(a.shoot, create=False)
    raw = shoot / "Raw"
    clips = [p for p in raw.rglob("*") if p.suffix.lower() in VIDEO_EXT and dc.STOCK_DIR not in p.parts] if raw.is_dir() else []
    if not clips:
        say(f"No clips in {raw}.\nRun .venv/bin/python demo/fetch_stock.py first.")
        return 1
    say(f"Demo shoot: {shoot} ({len(clips)} clips)")
    if not (raw / "Camera" / "voiceover.wav.words.txt").exists():
        say("Note: no narration yet, so captions and word-timed effects have no words.\n"
            "      Run .venv/bin/python demo/make_narration.py first for the full demo.")

    jobs = []
    if not a.effects_only:
        jobs.append(("style samples", dc.KIT_ROOT / "styles" / "make_samples.py", shoot / "Style Tests" / "Samples", []))
    if not a.styles_only:
        extra = (["--only", a.only] if a.only else []) + (["--sheet-only"] if a.sheet_only else [])
        jobs.append(("effect previews", dc.KIT_ROOT / "effects" / "make_previews.py", shoot / "Style Tests" / "Effects", extra))

    made, missing, failed = [], [], []
    for name, script, out, extra in jobs:
        rel = script.relative_to(dc.KIT_ROOT)
        if not script.exists():
            say(f"\n{name}: {rel} isn't in this kit yet, so there's nothing to run. Skipped.")
            missing.append(str(rel))
            continue
        out.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(script), "--footage", str(raw), "--out", str(out)] + extra
        if a.brand:
            cmd += ["--brand", a.brand]
        say(f"\n{name}: {rel} --footage '{raw}' --out '{out}'" + (" " + " ".join(cmd[6:]) if len(cmd) > 6 else ""))
        r = subprocess.run(cmd, cwd=dc.KIT_ROOT)
        (made if r.returncode == 0 else failed).append((name, out, r.returncode))

    say("")
    for name, out, _ in made:
        say(f"Done: {name} in {out}")
    for name, out, code in failed:
        say(f"Failed: {name} (exit {code}); its messages are above.")
    if missing:
        say(f"Not run (not in the kit yet): {', '.join(missing)}")
    if made:
        say("Open them in Video Review: say \"open video review\" to Claude, or run the review server (review/README.md).")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
