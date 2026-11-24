#!/usr/bin/env python3
"""Which seconds of which raw clip every finished video used, for the Footage Log ("used in", "not used yet").

    .venv/bin/python library/usage.py                         work it out again, into <content>/Footage Log/usage.json
    .venv/bin/python library/usage.py add OUTPUT CLIP FROM TO [--by WHAT] [--approx]
                                                             OUTPUT (a video file name) used CLIP from FROM to TO seconds
    .venv/bin/python library/usage.py same OUTPUT OTHER [--by WHAT]
                                                             OUTPUT used the same moments as OTHER (a restyle, a cut-down)
    .venv/bin/python library/usage.py show [OUTPUT]           what's recorded, for every video or one

Where it comes from, most exact first:
  1. Build records (library/buildrecord.py). A builder that calls rec.used(clip, from, to) for each piece it shows
     keeps the raw seconds in "<render>.build.json". The render's own name counts, and so does every file finish.py
     placed from it, or any video in a shoot with the same picture (found by checksum, cached).
  2. Lines added by hand or by a builder that keeps no record: "add" and "same" above, or from Python
         import usage; usage.register("My-Video-v1.mp4", [("C0041.MP4", 9.7, 13.9)], built_by="my_builder.py")
     They're kept in <content>/Footage Log/usage-added.json, which this script never rewrites on its own.
  3. <content>/Footage Log/effects-applied.json, where effects/fx.py apply logs each export: effects on a raw clip
     count that clip's seconds, effects on a finished video count the same moments as that video.

footage.py index reads usage.json (finish.py runs both).
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
sys.path.insert(0, str(KIT / "lib"))
sys.path.insert(0, str(HERE))
import studio_config as sc  # noqa: E402
import buildrecord as BR  # noqa: E402

VIDEO_EXT = {".mp4", ".mov", ".m4v"}
OUTPUT_DIRS = {"Finished", "Style Tests", "Older Versions"}
MD5_CACHE = Path.home() / ".cache" / "video-studio" / "picture-md5.json"

usage = {}  # output file name -> {"built_by": str, "clips": [{clip, from, to, approx?}]}


def root():
    return BR.content_root() or sc.content_root()


def log_dir():
    return root() / "Footage Log"


def added_file():
    return log_dir() / "usage-added.json"


def add(out, built_by, clip, a, b, approx=False):
    a, b = float(a), float(b)
    if b - a <= 0.01:
        return
    u = usage.setdefault(out, {"built_by": built_by, "clips": []})
    u["clips"].append({"clip": Path(str(clip)).name, "from": round(a, 2), "to": round(b, 2), **({"approx": True} if approx else {})})


def merge():
    for u in usage.values():
        by = {}
        for c in sorted(u["clips"], key=lambda c: (c["clip"], c["from"])):
            L = by.setdefault(c["clip"], [])
            if L and c["from"] <= L[-1]["to"] + 0.5:
                L[-1]["to"] = max(L[-1]["to"], c["to"])
                if c.get("approx"):
                    L[-1]["approx"] = True
            else:
                L.append(dict(c))
        u["clips"] = [c for L in by.values() for c in L]


def same_as(out, other, built_by):
    if other in usage:
        usage[out] = {"built_by": built_by, "clips": [dict(c, approx=True) for c in usage[other]["clips"]]}


# ---------------------------------------------------------------- 1. build records

def outputs():
    """Every video in a shoot's Finished/, Style Tests/ or Older Versions/ folder."""
    r = root()
    out = []
    if not r.is_dir():
        return out
    for dirpath, dirnames, filenames in os.walk(r):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("_To Delete", "Footage Log")]
        parts = Path(dirpath).relative_to(r).parts
        if len(parts) < 2 or parts[1] not in OUTPUT_DIRS:
            continue
        out += [Path(dirpath) / f for f in filenames if Path(f).suffix.lower() in VIDEO_EXT and not f.startswith(".")]
    return out


def picture_md5(p, cache):
    st = p.stat()
    key = f"{p}|{st.st_size}|{st.st_mtime_ns}"
    if key not in cache:
        cache[key] = BR.stream_md5(p, "v")
    return cache[key]


def from_records():
    lines = BR.registry_lines()
    records = {}            # record file -> its doc, for the records that list clips
    by_render, by_picture = {}, {}
    for d in lines:
        f = d.get("record")
        if not f or f in records:
            continue
        try:
            doc = json.loads(Path(f).read_text())
        except (OSError, ValueError):
            continue
        if not doc.get("clips"):
            continue
        records[f] = doc
        by_render[str(Path(doc.get("render_path") or d.get("render") or "").resolve())] = f
        if doc.get("picture_md5"):
            by_picture[doc["picture_md5"]] = f   # newest wins (lines are oldest first)
    if not records:
        return 0

    def give(out_name, f, picture=None):
        doc = records[f]
        # a file placed from an earlier render of the same name: the record now describes the newer render
        older = bool(picture and doc.get("picture_md5") and picture != doc["picture_md5"])
        by = f"{doc.get('builder') or 'a builder'} (build record {Path(f).name})" + (", an earlier render" if older else "")
        usage.pop(out_name, None)
        for c in doc["clips"]:
            add(out_name, by, c.get("clip") or c.get("path"), c["from"], c["to"], older or c.get("approx", False))

    r = root()
    named = set()
    for render, f in by_render.items():            # renders made straight into a shoot keep their own name
        rp = Path(render)
        if r in rp.parents and rp.is_file():
            give(rp.name, f)
            named.add(rp.name)
    for d in lines:                                # files finish.py placed
        if not d.get("placed"):
            continue
        dest = Path(d["placed"])
        f = by_render.get(str(Path(d.get("from") or "").resolve())) or by_picture.get(d.get("picture_md5") or "")
        if f and dest.is_file():
            give(dest.name, f, d.get("picture_md5"))
            named.add(dest.name)
    try:
        cache = json.loads(MD5_CACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    for p in outputs():                            # anything else with the same picture as a record's render
        if p.name in named:
            continue
        try:
            f = by_picture.get(picture_md5(p, cache))
        except Exception:
            continue
        if f:
            give(p.name, f)
            named.add(p.name)
    try:
        MD5_CACHE.parent.mkdir(parents=True, exist_ok=True)
        MD5_CACHE.write_text(json.dumps(cache))
    except OSError:
        pass
    return len(named)


# ---------------------------------------------------------------- 2. added by hand or by a builder

def read_added():
    try:
        d = json.loads(added_file().read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_added(d):
    f = added_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    d["about"] = ("Raw seconds used by videos whose builder keeps no build record, added with library/usage.py add / "
                  "same or usage.register(). usage.py reads this file and never rewrites it on its own.")
    d["updated"] = datetime.now().isoformat(timespec="seconds")
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
    os.replace(tmp, f)


def register(out_name, clips, built_by=""):
    """For builders without a build record: OUTPUT used these raw seconds. clips: [(clip, from, to)] or
    [{"clip", "from", "to", "approx"?}]. Replaces what was registered for that output before."""
    d = read_added()
    rows = [r for r in d.get("clips", []) if r.get("out") != out_name]
    for c in clips:
        if isinstance(c, dict):
            clip, a, b, approx = c["clip"], c["from"], c["to"], bool(c.get("approx"))
        else:
            clip, a, b = c[:3]
            approx = bool(c[3]) if len(c) > 3 else False
        rows.append({"out": out_name, "clip": Path(str(clip)).name, "from": round(float(a), 2), "to": round(float(b), 2),
                     "by": built_by, **({"approx": True} if approx else {})})
    d["clips"] = rows
    write_added(d)


def from_added():
    d = read_added()
    for r in d.get("clips", []):
        try:
            add(r["out"], r.get("by") or "added by hand", r["clip"], r["from"], r["to"], r.get("approx", False))
        except (KeyError, TypeError, ValueError):
            continue
    return d.get("same", [])


# ---------------------------------------------------------------- 3. effects applied

def from_effects():
    f = log_dir() / "effects-applied.json"
    if not f.is_file():
        f = KIT / "effects" / "cache" / "applied.json"     # where fx.py logs while the content folder is away
    if not f.is_file():
        return
    try:
        for r in json.loads(f.read_text()):
            by = "effects/fx.py apply " + " ".join(r.get("effects", []))
            src = Path(r["src"]).name
            out = Path(r["out"]).name
            if src in usage:                      # effects on a finished video: the same moments as that video
                same_as(out, src, by)
            elif "start" in r and "end" in r:     # effects on a raw clip
                add(out, by, src, r["start"], r["end"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(f"{f.name}: {e}")


# ---------------------------------------------------------------- main

def build():
    usage.clear()
    n = from_records()
    same = from_added()
    from_effects()
    merge()
    for s in same:
        try:
            same_as(s["out"], s["as"], s.get("by") or f"the same moments as {s['as']}")
        except (KeyError, TypeError):
            continue
    return n


def save():
    f = log_dir() / "usage.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(usage, indent=1, ensure_ascii=False))
    os.replace(tmp, f)
    return f


def show(only=None):
    for out, u in sorted(usage.items()):
        if only and out != only:
            continue
        secs = sum(c["to"] - c["from"] for c in u["clips"])
        print(f"{out:56s} {len(u['clips']):3d} ranges {secs:7.1f}s  clips: {', '.join(sorted({c['clip'][:28] for c in u['clips']}))}")
        if only:
            print(f"  built by {u['built_by']}")
            for c in u["clips"]:
                print(f"  {c['clip']}  {c['from']:.2f}-{c['to']:.2f}{'  (approximate)' if c.get('approx') else ''}")


def main():
    ap = argparse.ArgumentParser(description="Which raw seconds every finished video used.")
    sub = ap.add_subparsers(dest="cmd")
    a1 = sub.add_parser("add", help="OUTPUT used CLIP from FROM to TO seconds")
    a1.add_argument("out"); a1.add_argument("clip"); a1.add_argument("start", type=float); a1.add_argument("end", type=float)
    a1.add_argument("--by", default="added by hand"); a1.add_argument("--approx", action="store_true")
    a2 = sub.add_parser("same", help="OUTPUT used the same moments as OTHER")
    a2.add_argument("out"); a2.add_argument("other"); a2.add_argument("--by", default="")
    a3 = sub.add_parser("show", help="what's recorded")
    a3.add_argument("out", nargs="?")
    a = ap.parse_args()
    if not root().is_dir():
        sys.exit(f"The content folder {root()} isn't there. Set content_root in studio.json.")
    if a.cmd == "add":
        if a.end <= a.start:
            sys.exit("Refused: the end must come after the start.")
        d = read_added()
        d.setdefault("clips", []).append({"out": Path(a.out).name, "clip": Path(a.clip).name, "from": round(a.start, 2),
                                          "to": round(a.end, 2), "by": a.by, **({"approx": True} if a.approx else {})})
        write_added(d)
        print(f"Added: {Path(a.out).name} used {Path(a.clip).name} {a.start:.2f}-{a.end:.2f}")
    elif a.cmd == "same":
        d = read_added()
        d["same"] = [s for s in d.get("same", []) if s.get("out") != Path(a.out).name]
        d["same"].append({"out": Path(a.out).name, "as": Path(a.other).name, "by": a.by})
        write_added(d)
        print(f"Added: {Path(a.out).name} used the same moments as {Path(a.other).name}")
    n = build()
    f = save()
    if a.cmd == "show":
        show(a.out)
        return
    print(f"{len(usage)} video(s) with raw seconds recorded ({n} from build records) -> {f}")
    if not a.cmd:
        show()


if __name__ == "__main__":
    main()
