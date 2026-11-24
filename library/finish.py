#!/usr/bin/env python3
"""Finish an export: put the file in its place in the content folder, write its sound and effects maps, and refresh
the video tracker. This is how a finished render gets into its shoot; it replaces copying it by hand.

    .venv/bin/python -I library/finish.py FILE.mp4 "<shoot>/Style Tests/NAME.mp4"   place it, both maps, tracker
    .venv/bin/python -I library/finish.py --maps VIDEO                               both maps for a video already in place
    options: --no-tracker (skip usage.py and footage.py index), --replace (with --maps: make the maps again)

The destination is a path in the content folder (studio.json content_root), relative or absolute. It refuses when a
file of that name is already there: a new version gets a new name (v2, v3…). The maps come from the build record the
builder kept at render time (library/buildrecord.py), found by the video's picture, so any render from a builder that
keeps records gets both rows with no other step. If one can't be made it says why in a line, and the file stays where
it was put. It also notes which render the file came from, so usage.py can list the raw seconds it used.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import buildrecord as BR  # noqa: E402


def say(msg):
    print(msg, flush=True)


def place(src, dest):
    root = BR.content_root()
    src = Path(src).expanduser().resolve()
    dest = Path(dest).expanduser()
    if not dest.is_absolute():
        dest = root / dest
    dest = dest.resolve()
    if not src.is_file():
        sys.exit(f"Refused: {src} isn't a file.")
    if root is None or not root.is_dir():
        sys.exit(f"Refused: the content folder ({root}) isn't there. Set content_root in studio.json.")
    if root not in dest.parents:
        sys.exit(f"Refused: {dest} isn't inside the content folder ({root}).")
    if dest.suffix.lower() not in (".mp4", ".mov", ".m4v"):
        sys.exit("Refused: the destination should be a video file name (.mp4).")
    if any(p.lower() == "raw" for p in dest.relative_to(root).parts):
        sys.exit("Refused: finished videos don't go in a Raw folder.")
    if dest.exists():
        sys.exit(f"Refused: {dest.name} is already there. A finished video is never overwritten; give the new one a new "
                 "name (v2, v3…).")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name("." + dest.name + ".part")
    shutil.copyfile(src, part)
    os.replace(part, dest)
    say(f"Placed {dest.relative_to(root)}")
    BR.note_placed(dest, src)
    return dest


def maps(video, replace=False):
    res = BR.make_maps(video, replace=replace, quiet=True)
    for name, msg in res.items():
        ok = msg.startswith("ok: ")
        say(f"  {name} map: " + (msg[4:] if ok else msg))
    return all(m.startswith("ok: ") for m in res.values())


def tracker():
    for args in (["usage.py"], ["footage.py", "index"]):
        r = subprocess.run([sys.executable, "-I", str(HERE / args[0]), *args[1:]], capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()
        say(f"  {args[0]}: " + ("done" if r.returncode == 0 else "failed: " + (tail[-1] if tail else "no message"))
            + ("".join("\n    " + ln for ln in tail if ln.startswith("Maps") or ln.startswith("  -")) if args[0] == "footage.py" else ""))


def main():
    ap = argparse.ArgumentParser(description="Place an export in the content folder, write both maps, refresh the tracker.")
    ap.add_argument("file")
    ap.add_argument("dest", nargs="?")
    ap.add_argument("--maps", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--no-tracker", action="store_true")
    a = ap.parse_args()
    if a.maps:
        video = Path(a.file).expanduser().resolve()
        if not video.is_file():
            sys.exit(f"Refused: {video} isn't a file.")
        maps(video, a.replace)
        return
    if not a.dest:
        sys.exit("Give the file and where it goes, for example: finish.py work/X_sfx.mp4 \"<shoot>/Style Tests/NAME-v1.mp4\"")
    dest = place(a.file, a.dest)
    maps(dest)
    if not a.no_tracker:
        tracker()


if __name__ == "__main__":
    main()
