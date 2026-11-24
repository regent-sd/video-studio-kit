"""The slim catalog the Asset Library page reads: one record per unique content (exact duplicates collapsed, every copy
listed), folder paths in a shared table, short keys, nothing the page doesn't use. Shared by build.py (the Artifact
bundle) and serve.py (the local page in Video Review).

Record keys: k kind, x extension, b bytes, w/h pixels, d duration (s), p pages, tk date taken (YYYY-MM-DD),
ds description, tg tags, fl flags, bs brand status, c copies [[folder index, file name, id, modified, locked 0/1, link]],
t preview file name (local page) or s sprite cell [sheet, x, y, w, h] (Artifact bundle).
Top level: f folders [[path, folder link]], r root names, rp {root name: folder on disk} (local page only),
sh sprite sheets {n: [file, width, height]}, g generated, b brand name, mode.
The Artifact bundle never carries paths on this Mac or md5s.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import assetlib as al  # noqa: E402

THUMBS = al.THUMBS


def to_delete(folder):
    return al.in_to_delete(folder)


def load():
    """The catalog with the newest media.json laid over it (previews land there before the next scan).
    An empty catalog when there is none yet, so the page can say how to start."""
    if not al.CATALOG.exists():
        return {"assets": [], "folders": [], "roots": [], "generated": None,
                "empty": "No Asset Library yet: add folders to asset_roots in studio.json, then run "
                         ".venv/bin/python assets/catalog.py scan (assets/README.md)."}
    doc = al.load_catalog()
    media = al.load_json(al.MEDIA_FILE, {})
    media = media if isinstance(media, dict) else {}
    for a in doc["assets"]:
        m = media.get(al.key_of(a)) or media.get(a.get("id"))
        if isinstance(m, dict):
            for k in ("width", "height", "duration", "taken", "pages", "thumb"):
                if m.get(k) is not None:
                    a[k] = m[k]
    return doc


def groups(assets):
    """{content key (md5, else id): [assets]}."""
    g = {}
    for a in assets:
        g.setdefault(al.key_of(a), []).append(a)
    return g


def thumb_of(members):
    # A file flagged "sensitive" (card numbers, signed forms, contracts) never shows a preview, here or in the Artifact.
    if any("sensitive" in (m.get("flags") or []) for m in members):
        return None
    for m in members:
        t = m.get("thumb")
        if t and "/" not in t and (THUMBS / t).exists():
            return t
    return None


def slim(doc, sprite_of=None, local=True):
    """sprite_of(key, thumb) -> [sheet, x, y, w, h] or None, for the Artifact bundle."""
    folders, fidx, out = [], {}, []
    link_by_path = {f["path"]: f.get("link") for f in doc.get("folders", [])}
    for key, ms in sorted(groups(doc["assets"]).items()):
        ms = sorted(ms, key=lambda m: (to_delete(m["folder"]), m["locked"], m["top"].lower() in ("archive", "archives"),
                                       len(m["path"]), m["path"]))
        a = ms[0]
        r = {"k": a["kind"], "x": a.get("ext") or "", "b": a["bytes"]}
        for src, dst in (("width", "w"), ("height", "h"), ("pages", "p")):
            if a.get(src):
                r[dst] = a[src]
        if a.get("duration"):
            r["d"] = round(float(a["duration"]), 1)
        if a.get("taken"):
            r["tk"] = str(a["taken"])[:10]
        tagged = next((m for m in ms if m.get("description") or m.get("tags")), a)
        for src, dst in (("description", "ds"), ("tags", "tg"), ("flags", "fl"), ("brand_status", "bs")):
            if tagged.get(src):
                r[dst] = tagged[src]
        copies = []
        for m in ms:
            if m["folder"] not in fidx:
                fidx[m["folder"]] = len(folders)
                folders.append([m["folder"], link_by_path.get(m["folder"])])
            copies.append([fidx[m["folder"]], m["name"], m["id"], m.get("modified"), 1 if m["locked"] else 0, m.get("link")])
        r["c"] = copies
        t = thumb_of(ms)
        if t:
            if local:
                r["t"] = t
            elif sprite_of:
                s = sprite_of(key, t)
                if s:
                    r["s"] = s
        out.append(r)
    data = {"g": doc.get("generated"), "f": folders, "a": out, "b": al.brand_name(),
            "r": [x["name"] for x in doc.get("roots", [])]}
    if local:
        data["rp"] = {x["name"]: x["path"] for x in doc.get("roots", [])}
    if doc.get("empty"):
        data["empty"] = doc["empty"]
    return data
