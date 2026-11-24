#!/usr/bin/env python3
"""Check a cut reel's words: re-transcribe it and list every word that differs from the plan, and check that no
cut lands on a sound (a clipped word).

    .venv/bin/python styles/talking-head/verify.py <video.mp4> [<planned words.txt>] [--model <whisper model>]

The plan is <video>.words.txt (the builders write it: every word the reel should say, in reel time). The cuts are
read from the builder's work folder (work/<name>/cuts.json) when it's there.

What it prints:
  - words planned but not heard, or heard but not planned (a missing word is often clipped at a cut)
  - cuts where the sound is still going at the cut point: listen there; a word may be cut short

A shortened word that the transcript still recognises ("tank" for "tanked") is clipped too: the sound check
catches those. Use a bigger whisper model for a stricter listen (settings: whisper_model, or --model).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stylekit import paths  # noqa: E402
from stylekit import words as W_  # noqa: E402


def heard_words(video, model=None):
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "heard.words.txt"
        if model:   # this run only; the settings stay as they are
            old = W_.model_path
            W_.model_path = lambda: model
            try:
                W_.transcribe(video, out)
            finally:
                W_.model_path = old
        else:
            W_.transcribe(video, out)
        return W_.read_words(out)


def cut_check(video, cuts, voice=None):
    """Cuts where the sound never drops to its pause level around the cut. voice: the voice track alone
    (the builders keep it in the work folder), so music under the voice doesn't hide the pauses."""
    src = voice if voice and Path(voice).exists() else video
    env = W_.level(src)
    thr = W_.pause_level(src, [])
    loud = []
    for c in cuts:
        i = int(round(c * 100))
        win = env[max(0, i - 6):i + 3]   # a pause somewhere from 60 ms before the cut to 30 ms after it
        if len(win) and float(win.min()) > thr:
            loud.append(c)
    return loud


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--model")
    ap.add_argument("--cuts", help="a cuts.json from the builder's work folder")
    a = ap.parse_args()
    video = Path(a.video)
    plan_file = Path(a.plan) if a.plan else Path(str(video) + ".words.txt")
    if not plan_file.exists():
        raise SystemExit(f"No plan: {plan_file} (the builders write it beside the video).")
    plan = W_.norm_words(" ".join(w["w"] for w in W_.read_words(plan_file)))
    heard = W_.norm_words(" ".join(w["w"] for w in heard_words(video, a.model)))
    print(f"{video.name}: {len(plan)} planned words, {len(heard)} heard")
    diffs = 0
    for op, a1, a2, b1, b2 in difflib.SequenceMatcher(None, plan, heard, autojunk=False).get_opcodes():
        if op != "equal":
            diffs += 1
            print(f"  {op:8s} planned: {' '.join(plan[max(0, a1 - 2):a2 + 2])!r:58s} heard: {' '.join(heard[max(0, b1 - 2):b2 + 2])!r}")
    if not diffs:
        print("  every planned word was heard")
    cuts_file = Path(a.cuts) if a.cuts else None
    if cuts_file is None:
        stem = re.sub(r"_v\d+$", "", video.stem)
        for style in ("talking-head", "hands-on", "fastcut"):
            c = paths.work_dir(style) / paths.safe_name(stem) / "cuts.json"
            if c.exists():
                d = json.loads(c.read_text())
                if Path(d.get("video", "")).name == video.name:
                    cuts_file = c
                    break
    if cuts_file and cuts_file.exists():
        info = json.loads(cuts_file.read_text())
        cuts = info.get("cuts", [])
        loud = cut_check(video, cuts, info.get("voice"))
        print(f"  {len(cuts)} cuts checked against the sound: " + ("all land in a pause" if not loud else
              "these land on sound (listen; a word may be cut short): " + ", ".join(f"{c:.2f} s" for c in loud)))
    else:
        print("  (no cuts.json for this video, so the cuts weren't checked against the sound)")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
