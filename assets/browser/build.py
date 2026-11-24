#!/usr/bin/env python3
"""Build the Asset Library page as a self-contained bundle, ready to publish as an Artifact.

  .venv/bin/python assets/browser/build.py [--out <folder>]      (default <cache>/bundle)

  index.html          the page (page.html with the bundle config; no data in it)
  data/assets.json    the slim catalog (slim.py): no md5s and no paths on this Mac
  sprites/s-NNN.jpg   previews packed 10 x 10 per sheet, 220 px on the long edge, JPEG q72
  _publish.json       which files go up in which publish (not itself published)

Safe to re-run as previews and tags grow. Sprite slots are kept in <cache>/sprite-layout.json: a file keeps its sheet
and cell, new previews go into new slots at the end, so a rebuild rewrites only the sheets whose contents changed.
Only files shown by default get a sprite (not files that exist only in _To Delete).
Limits it checks (the Artifact tool's): 15 MB per file, 511 files and 256 MB in all; one publish carries at most
255 files and 64 MB, so a bigger bundle goes up in rounds to the same link (_publish.json lists them).
To publish, build into a folder Claude can publish from (the session's scratchpad, or inside the kit), e.g.
  .venv/bin/python assets/browser/build.py --out <scratchpad>/asset-library
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import slim  # noqa: E402
from PIL import Image  # noqa: E402

al = slim.al
CELL, PITCH, COLS, ROWS, Q = 220, 224, 10, 10, 72
PER = COLS * ROWS
MAX_BIN, MAX_FILES, MAX_TOTAL = 15 * 1024 * 1024, 511, 256 * 1024 * 1024
ROUND_FILES, ROUND_BYTES = 250, 60 * 1024 * 1024
CFG = {"mode": "artifact", "data": "data/assets.json", "sprites": "sprites/"}


def main():
    args = sys.argv[1:]
    out = al.expand(al.opt(args, "--out") or al.BUNDLE)
    doc = slim.load()
    if doc.get("empty"):
        sys.exit(doc["empty"])
    g = slim.groups(doc["assets"])
    shown = {k: slim.thumb_of(ms) for k, ms in g.items() if any(not slim.to_delete(m["folder"]) for m in ms)}
    shown = {k: t for k, t in shown.items() if t}

    lay = al.load_json(al.LAYOUT, None) or {"slots": {}, "next": 0, "sheets": {}}
    for k in sorted(shown):                       # new content goes to the end, in key order
        if k not in lay["slots"]:
            lay["slots"][k] = lay["next"]
            lay["next"] += 1
    by_sheet = {}
    for k, slot in lay["slots"].items():
        if k in shown:
            by_sheet.setdefault(slot // PER, []).append((slot % PER, k))

    (out / "sprites").mkdir(parents=True, exist_ok=True)
    (out / "data").mkdir(parents=True, exist_ok=True)
    cells, made, kept, sheet_dims = {}, 0, 0, {}
    for sh in sorted(by_sheet):
        entries = sorted(by_sheet[sh])
        name = f"s-{sh:03d}.jpg"
        rows = max(c for c, _ in entries) // COLS + 1
        W, H = COLS * PITCH, rows * PITCH
        sig = hashlib.sha1(json.dumps([[c, k, shown[k]] for c, k in entries]).encode()).hexdigest()
        dest = out / "sprites" / name
        old = lay["sheets"].get(name, {})
        rebuild = old.get("sig") != sig or not dest.exists()
        img = Image.new("RGB", (W, H), (232, 232, 229)) if rebuild else None
        for c, k in entries:
            x, y = (c % COLS) * PITCH + 2, (c // COLS) * PITCH + 2
            if rebuild:
                with Image.open(slim.THUMBS / shown[k]) as t:
                    t = t.convert("RGB")
                    t.thumbnail((CELL, CELL), Image.LANCZOS)
                    img.paste(t, (x, y))
                    wh = t.size
            else:
                wh = tuple(old["cells"][k])
            cells[k] = [sh, x, y, wh[0], wh[1]]
        if rebuild:
            img.save(dest, "JPEG", quality=Q, optimize=True)
            made += 1
        else:
            kept += 1
        lay["sheets"][name] = {"sig": sig, "cells": {k: cells[k][3:] for _, k in entries}}
        sheet_dims[sh] = [name, W, H]
    live = {d[0] for d in sheet_dims.values()}
    for p in (out / "sprites").glob("*.jpg"):
        if p.name not in live:
            p.unlink()
    lay["sheets"] = {n: v for n, v in lay["sheets"].items() if n in live}
    al.atomic_write(al.LAYOUT, json.dumps(lay, separators=(",", ":"), sort_keys=True))

    data = slim.slim(doc, sprite_of=lambda k, t: cells.get(k), local=False)
    data["mode"] = "artifact"
    data["sh"] = {str(k): v for k, v in sheet_dims.items()}
    (out / "data" / "assets.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    (out / "index.html").write_text((HERE / "page.html").read_text().replace("/*CONFIG*/{}", json.dumps(CFG)))

    files = sorted(p for p in out.rglob("*") if p.is_file() and not p.name.startswith((".", "_")))
    total = sum(p.stat().st_size for p in files)
    support = [p for p in files if p.name != "index.html" or p.parent != out]
    rounds, cur, cur_b = [], [], 0
    for p in sorted(support, key=lambda p: (p.parent.name != "data", p.name)):
        size = p.stat().st_size
        if cur and (len(cur) >= ROUND_FILES or cur_b + size > ROUND_BYTES):
            rounds.append(cur)
            cur, cur_b = [], 0
        cur.append(p.relative_to(out).as_posix())
        cur_b += size
    if cur:
        rounds.append(cur)
    (out / "_publish.json").write_text(json.dumps({"page": "index.html", "rounds": rounds}, indent=1))
    n_with = sum(1 for r in data["a"] if "s" in r)
    print(f"{len(data['a'])} unique files ({sum(len(r['c']) for r in data['a'])} copies), {n_with} with a preview in a sprite; "
          f"{len(sheet_dims)} sheets ({made} written, {kept} unchanged)")
    print(f"Bundle {out}: {len(files)} files, {total / 1e6:.1f} MB (assets.json "
          f"{(out / 'data' / 'assets.json').stat().st_size / 1e6:.2f} MB); publish in {len(rounds) or 1} round(s), "
          f"listed in {out / '_publish.json'}")
    errs = []
    big = [p.name for p in files if p.stat().st_size > MAX_BIN]
    if big:
        errs.append(f"files over 15 MB: {', '.join(big)}")
    if len(files) > MAX_FILES:
        errs.append(f"{len(files)} files > {MAX_FILES}")
    if total > MAX_TOTAL:
        errs.append(f"{total / 1e6:.0f} MB > 256 MB")
    if errs:
        sys.exit("OVER THE ARTIFACT LIMITS: " + "; ".join(errs))
    print("Within the Artifact limits.")


if __name__ == "__main__":
    main()
