#!/usr/bin/env python3
"""Asset Library: split the tagging batches into agent-sized chunks, and merge the chunks back.

  .venv/bin/python assets/chunks.py make [--max 18]   <cache>/sheets/<batch>/ -> <cache>/chunks/<batch>.pNN/ (up to
                                      --max sheets each) and <cache>/chunks/<batch>.np/ (the files with no preview).
                                      Each chunk folder has its own batch.json and links to its sheets, so one
                                      tagging agent takes one chunk.
  .venv/bin/python assets/chunks.py status            which chunks have a work file, and how many entries
  .venv/bin/python assets/chunks.py merge             <cache>/tags-work/<chunk>.json -> <cache>/tags-work/<batch>.json
                                      for every batch whose chunks are all done. Then file each one with
                                      .venv/bin/python assets/tags.py apply <batch>

A tagging agent follows assets/tagging-agent-brief.md and checks its chunk with tags.py check <chunk>.
`previews.py sheets` rebuilds the sheets from scratch, so run `make` again after it, and never while tagging.
"""
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import assetlib as al  # noqa: E402


def make(args):
    mx = int(al.opt(args, "--max", "18"))
    idx = al.SHEETS / "index.json"
    if not idx.exists():
        sys.exit(f"No contact sheets yet ({idx}). Run: .venv/bin/python assets/previews.py sheets")
    shutil.rmtree(al.CHUNKS, ignore_errors=True)
    al.CHUNKS.mkdir(parents=True)
    out = []
    for b in json.loads(idx.read_text()):
        doc = json.loads((al.SHEETS / b["batch"] / "batch.json").read_text())
        sh = doc["sheets"]
        n = -(-len(sh) // mx) if sh else 0
        per = -(-len(sh) // n) if n else 0
        for i in range(n):
            part = sh[i * per:(i + 1) * per]
            name = f"{b['batch']}.p{i + 1:02d}"
            d = al.CHUNKS / name
            d.mkdir()
            for s in part:
                os.symlink((al.SHEETS / b["batch"] / s["file"]).resolve(), d / s["file"])
            cnt = sum(len(s["cells"]) for s in part)
            (d / "batch.json").write_text(json.dumps({**doc, "batch": name, "sheets": part, "no_preview": [],
                                                      "assets": cnt, "with_preview": cnt}, indent=1, ensure_ascii=False))
            out.append({"chunk": name, "batch": b["batch"], "sheets": len(part), "assets": cnt, "no_preview": 0})
        if doc["no_preview"]:
            name = f"{b['batch']}.np"
            d = al.CHUNKS / name
            d.mkdir()
            cnt = len(doc["no_preview"])
            (d / "batch.json").write_text(json.dumps({**doc, "batch": name, "sheets": [], "assets": cnt,
                                                      "with_preview": 0}, indent=1, ensure_ascii=False))
            out.append({"chunk": name, "batch": b["batch"], "sheets": 0, "assets": cnt, "no_preview": cnt})
    (al.CHUNKS / "chunks.json").write_text(json.dumps(out, indent=1))
    (al.CHUNKS / "index.json").write_text(json.dumps(
        [{"batch": c["chunk"], "assets": c["assets"], "with_preview": c["assets"] - c["no_preview"],
          "no_preview": c["no_preview"], "sheets": c["sheets"], "folders": 0} for c in out], indent=1))
    for c in out:
        print(f"{c['chunk']:<50}{c['sheets']:>4} sheets{c['assets']:>5} files")
    print(f"{len(out)} chunks, {sum(c['assets'] for c in out)} files. One tagging agent per chunk.")


def _chunks():
    p = al.CHUNKS / "chunks.json"
    if not p.exists():
        sys.exit("No chunks yet. Run: .venv/bin/python assets/chunks.py make")
    return json.loads(p.read_text())


def _entries(chunk):
    p = al.WORK / f"{chunk}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError as e:
        return f"unreadable: {e}"


def status(_):
    done = todo = 0
    for c in _chunks():
        e = _entries(c["chunk"])
        n = len(e) if isinstance(e, dict) else 0
        state = "no work file" if e is None else e if isinstance(e, str) else ("complete" if n >= c["assets"] else "partial")
        done += n
        todo += c["assets"]
        print(f"{c['chunk']:<50}{n:>5} / {c['assets']:<5} {state}")
    print(f"{done} of {todo} entries written")


def merge(_):
    by = {}
    for c in _chunks():
        by.setdefault(c["batch"], []).append(c)
    ready = []
    al.WORK.mkdir(parents=True, exist_ok=True)
    for batch, cs in by.items():
        parts = {c["chunk"]: _entries(c["chunk"]) for c in cs}
        need = {c["chunk"]: c["assets"] for c in cs}
        missing = [k for k, v in parts.items() if not isinstance(v, dict) or len(v) < need[k]]
        if missing:
            print(f"{batch}: waiting for {', '.join(missing)}")
            continue
        merged = {}
        for v in parts.values():
            merged.update(v)
        al.atomic_write(al.WORK / f"{batch}.json", json.dumps(merged, indent=1, ensure_ascii=False))
        ready.append(batch)
        print(f"{batch}: {len(merged)} entries from {len(cs)} chunks -> {al.WORK / (batch + '.json')}")
    print("ready to apply: " + (" ".join(ready) or "none"))


if __name__ == "__main__":
    a = sys.argv[1:]
    {"make": make, "status": status, "merge": merge}.get(a[0] if a else "", lambda _: print(__doc__))(a[1:])
