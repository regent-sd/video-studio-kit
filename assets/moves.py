#!/usr/bin/env python3
"""Asset Library: move and rename folders and files from a plan, log every move, and put them back.

  .venv/bin/python assets/moves.py check <plan.csv>             simulate the whole plan against the catalog; refuse anything unsafe
  .venv/bin/python assets/moves.py apply <plan.csv> [--no-scan] re-scan, re-check, snapshot, then do each move and log it at once
  .venv/bin/python assets/moves.py undo [batch]                 move a batch back, last move first (default: the latest not undone)
  .venv/bin/python assets/moves.py verify [batch]               re-scan and compare with the snapshot taken before that batch
  .venv/bin/python assets/moves.py log                          list the batches in the move log

A plan is a CSV with the columns  order, from, to, kind, reason, id  (id may be empty). Paths are catalog paths,
"<root name>/<path inside it>", exactly as catalog.py find prints them. kind is folder or file. reason starts with a
word and a colon, e.g. "duplicate: same as Brand/Logos/logo.png" or "layout: one folder per year".
Nothing is ever deleted: things to get rid of are moved into a "_To Delete" folder (at the top of their root) for you
to clear yourself, and check refuses to put the only copy of a file there.
Every completed move goes into move-log.csv in the library folder the moment it happens.
Never touched: the asset_never_move folders, the asset_exclude folders, your shoots folder, the library folder itself.
"""
import csv
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assetlib as al  # noqa: E402

LOG_FIELDS = ["batch", "time", "order", "from", "to", "kind", "id", "reason"]
PLAN_FIELDS = ["order", "from", "to", "kind", "reason", "id"]
KEEP_IN_TO_DELETE = {"junk", "empty"}           # reasons for which a file may go to _To Delete without a copy elsewhere
PROTECTED = list(dict.fromkeys(al.NEVER_MOVE + al.EXCLUDED))
under = al.under


def protected(p):
    return any(under(p, x) for x in PROTECTED)


def holds_protected(p):
    """Moving p would carry a protected folder along."""
    return any(x.startswith(p + "/") for x in PROTECTED)


def bad_path(p):
    if not p or p.startswith("/") or p.endswith("/") or "\0" in p:
        return "must be a catalog path, '<root name>/...'"
    if any(part in ("", ".", "..") for part in p.split("/")):
        return "has an empty, '.' or '..' part"
    if p.split("/", 1)[0] not in al.ROOT_BY_LABEL:
        return f"doesn't start with a root name ({', '.join(al.ROOT_BY_LABEL)})"
    if "/" not in p:
        return "is a whole root; roots never move"
    return None


def category(reason):
    return (reason.split(":", 1)[0].strip().lower() or "other") if reason else "other"


def now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def device(label):
    try:
        return os.stat(al.ROOT_BY_LABEL[label]).st_dev
    except (OSError, KeyError):
        return None


# ---------------------------------------------------------------- the simulated tree

class Node:
    __slots__ = ("name", "parent", "kids", "fold", "kind", "id", "bytes", "md5", "locked", "orig", "opaque")

    def __init__(self, name, kind, parent=None, **kw):
        self.name, self.kind, self.parent = name, kind, None
        self.kids, self.fold = {}, {}
        self.id, self.bytes, self.md5 = kw.get("id"), kw.get("bytes", 0), kw.get("md5")
        self.locked, self.orig, self.opaque = kw.get("locked", False), kw.get("orig"), kw.get("opaque", False)
        if parent is not None:
            parent.attach(self)

    def attach(self, child):
        self.kids[child.name] = child
        self.fold[child.name.casefold()] = child
        child.parent = self

    def detach(self):
        p = self.parent
        del p.kids[self.name]
        del p.fold[self.name.casefold()]
        self.parent = None

    def path(self):
        parts, n = [], self
        while n.parent is not None:
            parts.append(n.name)
            n = n.parent
        return "/".join(reversed(parts))

    def walk(self):
        yield self
        for k in list(self.kids.values()):
            yield from k.walk()

    def files(self):
        return [n for n in self.walk() if n.kind == "file"]

    def is_within(self, other):
        n = self
        while n is not None:
            if n is other:
                return True
            n = n.parent
        return False


class Tree:
    """The roots as the catalog saw them, plus links, plus the folders the catalog leaves out (kept opaque)."""

    def __init__(self, doc):
        self.root = Node("", "folder")
        self.junk = {p["path"] for p in doc.get("problems", []) if p["type"] in ("alias", "temp-file")}
        for f in sorted(doc["folders"], key=lambda f: f["path"].count("/")):
            parent, name = self.split(f["path"])
            if self.find(parent) is not None:
                Node(name, "folder", self.find(parent), id=f["id"], locked=f["locked"], orig=f["path"])
        for a in doc["assets"]:
            parent, name = self.split(a["path"])
            if self.find(parent) is not None:
                Node(name, "file", self.find(parent), id=a["id"], bytes=a["bytes"], md5=a["md5"], locked=a["locked"],
                     orig=a["path"])
        for p in doc.get("problems", []):
            if p["type"] == "link":
                parent, name = self.split(p["path"])
                if self.find(parent) is not None and name not in self.find(parent).kids:
                    Node(name, "link", self.find(parent), orig=p["path"])
        for x in doc.get("excluded", []):
            parent, name = self.split(x)
            if self.find(parent) is not None and name not in self.find(parent).kids:
                Node(name, "folder", self.find(parent), opaque=True, orig=x, locked=True)

    @staticmethod
    def split(p):
        return p.rsplit("/", 1) if "/" in p else ("", p)

    def find(self, path):
        n = self.root
        for part in path.split("/") if path else []:
            n = n.kids.get(part)
            if n is None:
                return None
        return n


# ---------------------------------------------------------------- reading a plan

def read_plan(path):
    rows, errors = [], []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        r = csv.DictReader(fh)
        cols = r.fieldnames or []
        missing = [c for c in PLAN_FIELDS if c not in cols and not (c == "id" and "drive_id" in cols)]
        if missing:
            sys.exit(f"{path}: missing column(s) {', '.join(missing)}; need {', '.join(PLAN_FIELDS)}")
        for i, row in enumerate(r, 2):
            row = {"id": row.get("id") or row.get("drive_id") or "", **{k: (row.get(k) or "").strip() for k in PLAN_FIELDS if k != "id"}}
            try:
                row["order"] = int(row["order"])
            except ValueError:
                errors.append(f"line {i}: order {row['order']!r} is not a number")
                continue
            row["line"] = i
            rows.append(row)
    orders = [r["order"] for r in rows]
    if orders != sorted(orders) or len(set(orders)) != len(orders):
        errors.append("the order column must count up with no repeats, in file order")
    return rows, errors


# ---------------------------------------------------------------- check

def simulate(rows, doc):
    """Run the plan on a copy of the tree. Returns (errors, report)."""
    tree = Tree(doc)
    errors, created, touched = [], [], set()
    stats = {"by_reason": {}, "by_top": {}, "files_moved": set()}
    to_delete_reason = {}

    def err(row, msg):
        errors.append(f"row {row['order']} (line {row['line']}): {msg}\n      from: {row['from']}\n      to:   {row['to']}")

    for row in rows:
        src_p, dst_p, kind = row["from"], row["to"], row["kind"]
        bad = bad_path(src_p) or bad_path(dst_p)
        if bad:
            err(row, f"path {bad}")
            continue
        if kind not in ("folder", "file"):
            err(row, f"kind must be folder or file, not {kind!r}")
            continue
        if protected(src_p) or protected(dst_p):
            err(row, "touches a protected place (asset_never_move, asset_exclude, the shoots or library folder)")
            continue
        if holds_protected(src_p):
            err(row, "would carry a protected folder along with it")
            continue
        a_root, b_root = src_p.split("/", 1)[0], dst_p.split("/", 1)[0]
        if a_root != b_root and device(a_root) != device(b_root):
            err(row, "moves between roots on different disks; that would be a copy, not a move (do it by hand)")
            continue
        if not row["reason"]:
            err(row, "no reason given")
        src = tree.find(src_p)
        if src is None:
            err(row, "source is not there (at this point in the plan)")
            continue
        if src.locked or any(n.locked for n in src.walk()):
            err(row, "source is locked, or holds locked items")
            continue
        want = "folder" if src.kind == "folder" else "file"
        if kind != want:
            err(row, f"plan says {kind} but it is a {want}")
            continue
        if row["id"] and src.id and row["id"] != src.id:
            err(row, f"id {row['id']} in the plan, but the item there has {src.id}")
            continue
        if src.orig and src.orig not in touched:
            touched.add(src.orig)
            if not os.path.lexists(al.to_disk(src.orig)):
                err(row, f"source is in the catalog but not on disk now ({src.orig}); run catalog.py scan")
                continue
        parent_p, name = Tree.split(dst_p)
        n, made, ok = tree.root, [], True
        for part in parent_p.split("/"):
            k = n.kids.get(part)
            if k is None and part.casefold() in n.fold:
                err(row, f"a folder named {n.fold[part.casefold()].name!r} is already there; names differing only by "
                         "case clash on a Mac")
                ok = False
                break
            if k is None:
                k = Node(part, "folder", n)
                made.append(k)
            elif k.kind != "folder" or k.opaque:
                err(row, f"destination goes through {'a file' if k.kind != 'folder' else 'a protected folder'}: {k.path()}")
                ok = False
                break
            n = k
        if ok:
            clash = n.fold.get(name.casefold())
            if clash is src:
                err(row, "a case-only rename; do it in two steps through a temporary name")
                ok = False
            elif clash is not None:
                what = "exists" if clash.name == name else f"clashes with {clash.name!r} (names differing only by case clash on a Mac)"
                err(row, f"destination {what}; plans never overwrite or merge, move the children instead")
                ok = False
            elif n.is_within(src):
                err(row, "moves a folder into itself")
                ok = False
        if not ok:
            for m in reversed(made):
                m.detach()
            continue
        created += [m.path() for m in made]
        files = src.files()
        c = category(row["reason"])
        s = stats["by_reason"].setdefault(c, {"folder": 0, "file": 0, "files": 0, "bytes": 0})
        s[kind] += 1
        s["files"] += len(files)
        s["bytes"] += sum(f.bytes for f in files)
        for f in files:
            if f not in stats["files_moved"]:
                stats["files_moved"].add(f)
                parts = (f.orig or f.path()).split("/")
                t = stats["by_top"].setdefault("/".join(parts[:2]), {"files": 0, "bytes": 0})
                t["files"] += 1
                t["bytes"] += f.bytes
        src.detach()
        src.name = name
        n.attach(src)
        for f in src.walk():
            if al.in_to_delete(dst_p):
                to_delete_reason[f] = c
            else:
                to_delete_reason.pop(f, None)

    # What ends up in a _To Delete folder, and is any of it the last copy?
    report = {"tree": tree, "created": created, "stats": stats, "to_delete": {}, "unique": [], "to_delete_folders": 0}
    tdels = [n for n in tree.root.walk() if n.kind == "folder" and n.name == al.TO_DELETE]
    if tdels:
        outside_md5, outside_namesize = set(), set()
        for f in tree.root.walk():
            if f.kind == "file" and not f.locked and not any(f.is_within(t) for t in tdels):
                if f.md5:
                    outside_md5.add(f.md5)
                outside_namesize.add((f.name.casefold(), f.bytes))
        for t in tdels:
            for f in t.walk():
                if f.kind == "folder":
                    report["to_delete_folders"] += f is not t
                    continue
                c = to_delete_reason.get(f, "other")
                d = report["to_delete"].setdefault(c, {"files": 0, "bytes": 0})
                d["files"] += 1
                d["bytes"] += f.bytes
                if f.kind == "file" and c not in KEEP_IN_TO_DELETE and (f.orig or "") not in tree.junk and f in to_delete_reason:
                    if not ((f.md5 and f.md5 in outside_md5) or (f.name.casefold(), f.bytes) in outside_namesize):
                        report["unique"].append(f.orig or f.path())
    for u in report["unique"]:
        errors.append(f"would put the only unlocked copy of a file in {al.TO_DELETE}: {u} "
                      "(reason 'junk:' or 'empty:' if it really is junk)")
    return errors, report


def tree_lines(tree, depth=3):
    lines = []

    def visit(n, level):
        for k in sorted(n.kids.values(), key=lambda k: k.name.casefold()):
            if k.kind != "folder":
                continue
            if k.opaque:
                lines.append(f"{'  ' * level}{k.name}  (left out of the catalog; untouched)")
                continue
            fs = k.files()
            lines.append(f"{'  ' * level}{k.name:<{max(1, 46 - 2 * level)}} {len(fs):>6} files {al.gb(sum(f.bytes for f in fs)):>9}")
            if level + 1 < depth:
                visit(k, level + 1)
        loose = [k for k in n.kids.values() if k.kind != "folder"]
        if loose and 0 < level < depth:
            lines.append(f"{'  ' * level}(loose files here: {len(loose)}, {al.gb(sum(k.bytes for k in loose))})")
    visit(tree.root, 0)
    return lines


def print_report(rows, report):
    st = report["stats"]
    print(f"{len(rows)} moves: {sum(r['kind'] == 'folder' for r in rows)} folders, {sum(r['kind'] == 'file' for r in rows)} "
          f"files; {len(report['created'])} new folders made on the way")
    print("\nMoves by reason:")
    for c, s in sorted(st["by_reason"].items(), key=lambda kv: -kv[1]["bytes"]):
        print(f"  {c:<12} {s['folder']:>4} folder moves {s['file']:>5} file moves   carrying {s['files']:>6} files {al.gb(s['bytes']):>9}")
    print("\nFiles affected, by the folder they start in (each file counted once):")
    for t, s in sorted(st["by_top"].items(), key=lambda kv: -kv[1]["bytes"]):
        print(f"  {t:<46} {s['files']:>6} files {al.gb(s['bytes']):>9}")
    print("\nAfterwards (root and two levels):")
    for line in tree_lines(report["tree"]):
        print("  " + line)
    td = report["to_delete"]
    if td:
        print(f"\nIn {al.TO_DELETE} afterwards: {sum(d['files'] for d in td.values())} files, "
              f"{al.gb(sum(d['bytes'] for d in td.values()))}, {report['to_delete_folders']} folders")
        for c, d in sorted(td.items(), key=lambda kv: -kv[1]["bytes"]):
            print(f"  {c:<12} {d['files']:>6} files {al.gb(d['bytes']):>9}")


def check(args, quiet=False):
    if not args:
        sys.exit("usage: moves.py check <plan.csv>")
    al.need_roots()
    rows, errors = read_plan(args[0])
    doc = al.load_catalog()
    sim_errors, report = simulate(rows, doc)
    errors += sim_errors
    if not quiet:
        print(f"Plan {args[0]} against the catalog of {doc['generated']}\n")
        print_report(rows, report)
    if errors:
        print(f"\nCHECK FAILED: {len(errors)} problem(s)")
        for e in errors[:200]:
            print("  - " + e)
        if len(errors) > 200:
            print(f"  ... {len(errors) - 200} more")
        return rows, False
    print("\nCheck passed: every source is there, no destination exists, nothing protected is touched, "
          "and everything sent to _To Delete has a copy that stays.")
    return rows, True


# ---------------------------------------------------------------- the log

def log_row(batch, row, kind=None, reason=None, frm=None, to=None):
    rec = {"batch": batch, "time": now(), "order": row.get("order", ""), "from": row["from"] if frm is None else frm,
           "to": row["to"] if to is None else to, "kind": kind or row["kind"], "id": row.get("id", ""),
           "reason": row.get("reason", "") if reason is None else reason}
    al.MOVE_LOG.parent.mkdir(parents=True, exist_ok=True)
    new = not al.MOVE_LOG.exists()
    with open(al.MOVE_LOG, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, LOG_FIELDS)
        if new:
            w.writeheader()
        w.writerow(rec)
        fh.flush()
        os.fsync(fh.fileno())


def read_log():
    if not al.MOVE_LOG.exists():
        return []
    with open(al.MOVE_LOG, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def batches(rows):
    return list(dict.fromkeys(r["batch"] for r in rows))


# ---------------------------------------------------------------- apply

def scan_now():
    print("Re-scanning (catalog.py scan) ...")
    out = subprocess.run([sys.executable, str(HERE / "catalog.py"), "scan"], capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("catalog.py scan failed:\n" + out.stdout[-2000:] + out.stderr[-2000:])
    print(out.stdout.strip().splitlines()[0] if out.stdout.strip() else "")


def snapshot(batch, plan, doc):
    snap = {"batch": batch, "plan": str(plan), "catalog_generated": doc["generated"], "taken": now(),
            "files": len(doc["assets"]), "bytes": sum(a["bytes"] for a in doc["assets"]),
            "assets": [[a["id"], a["md5"], a["bytes"], a["path"], a["locked"]] for a in doc["assets"]],
            "folders": [[f["id"], f["path"]] for f in doc["folders"]]}
    path = al.SNAPS / f"{batch}.json"
    al.atomic_write(path, json.dumps(snap, ensure_ascii=False))
    return path


def apply(args):
    no_scan = al.flag(args, "--no-scan")
    if not args:
        sys.exit("usage: moves.py apply <plan.csv> [--no-scan]")
    plan = Path(args[0]).resolve()
    if not no_scan:
        scan_now()
    rows, ok = check([str(plan)], quiet=True)
    if not ok:
        sys.exit("Nothing was moved.")
    doc = al.load_catalog()
    batch = dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"[^A-Za-z0-9]+", "-", plan.stem).strip("-")
    snap = snapshot(batch, plan, doc)
    print(f"\nBatch {batch}: {len(rows)} moves. Snapshot: {snap}")
    print(f"Logging each move to {al.MOVE_LOG}\n")
    done = 0
    for row in rows:
        src, dst = al.to_disk(row["from"]), al.to_disk(row["to"])
        try:
            if not os.path.lexists(src):
                raise RuntimeError("source is not there")
            if os.path.lexists(dst):
                raise RuntimeError("destination already exists")
            missing, p = [], dst.parent
            while not os.path.lexists(p):
                missing.append(p)
                p = p.parent
            if not p.is_dir():
                raise RuntimeError(f"{p} is not a folder")
            for m in reversed(missing):
                os.mkdir(m)
                log_row(batch, {"order": row["order"], "from": "", "to": al.to_catalog(m), "id": "",
                                "reason": f"made for row {row['order']}"}, kind="mkdir")
            t0 = time.monotonic()
            os.rename(src, dst)
            log_row(batch, row)
            done += 1
            if len(rows) <= 20 or done % 25 == 0:
                print(f"  {row['order']:>5} done ({time.monotonic() - t0:.2f} s)  {row['from']}  ->  {row['to']}")
        except (OSError, RuntimeError) as e:
            print(f"\nSTOPPED at row {row['order']} (plan line {row['line']}): {e}\n  from: {row['from']}\n  to:   {row['to']}")
            print(f"{done} of {len(rows)} moves were done and logged before it. Nothing after it was tried.")
            print(f"To put the done ones back: .venv/bin/python assets/moves.py undo {batch}")
            sys.exit(1)
    print(f"\nAll {done} moves done (batch {batch}). Next: .venv/bin/python assets/moves.py verify {batch}")


# ---------------------------------------------------------------- undo

def undo(args):
    log = read_log()
    if not log:
        sys.exit("The move log is empty; nothing to undo.")
    names = batches(log)
    undone = {b[:-5] for b in names if b.endswith("-undo")}
    if args:
        batch = args[0]
        if batch not in names:
            sys.exit(f"No batch {batch} in {al.MOVE_LOG}. Batches: {', '.join(names)}")
    else:
        left = [b for b in names if not b.endswith("-undo") and b not in undone]
        if not left:
            sys.exit("Every batch in the log has already been undone.")
        batch = left[-1]
    if batch.endswith("-undo"):
        sys.exit("That batch is itself an undo; to redo the moves, apply the plan again.")
    if batch in undone:
        sys.exit(f"Batch {batch} has already been undone.")
    rows = [r for r in log if r["batch"] == batch]
    ub = batch + "-undo"
    print(f"Undoing batch {batch}: {sum(r['kind'] != 'mkdir' for r in rows)} moves, last first. Logged as {ub}.\n")
    kept = []
    for r in reversed(rows):
        try:
            if r["kind"] == "mkdir":
                if bad_path(r["to"]) or protected(r["to"]):
                    raise RuntimeError(f"unsafe path {r['to']}")
                d = al.to_disk(r["to"])
                if d.is_dir() and not os.listdir(d):
                    os.rmdir(d)
                    log_row(ub, {"order": r["order"], "from": r["to"], "to": "", "id": "",
                                 "reason": "undo: remove the folder the move made"}, kind="rmdir")
                else:
                    kept.append(r["to"])
                continue
            for p in (r["to"], r["from"]):
                if bad_path(p) or protected(p) or holds_protected(p):
                    raise RuntimeError(f"unsafe path {p}")
            src, dst = al.to_disk(r["to"]), al.to_disk(r["from"])
            if not os.path.lexists(src):
                raise RuntimeError("the moved item is no longer where the log says")
            if os.path.lexists(dst):
                raise RuntimeError("something is already back at the original place")
            if not dst.parent.is_dir():
                raise RuntimeError(f"the original folder {dst.parent} is gone")
            os.rename(src, dst)
            log_row(ub, {"order": r["order"], "from": r["to"], "to": r["from"], "id": r.get("id", ""),
                         "reason": "undo: " + r["reason"]}, kind=r["kind"])
            print(f"  {r['order']:>5} back  {r['to']}  ->  {r['from']}")
        except (OSError, RuntimeError) as e:
            print(f"\nSTOPPED undoing at row {r['order']}: {e}\n  now at:   {r['to']}\n  belongs:  {r['from']}")
            print("Everything after this row in the batch has been moved back and logged; this row and the ones before it have not.")
            sys.exit(1)
    if kept:
        print("\nLeft in place (not empty, or already gone): " + "; ".join(kept))
    print(f"\nBatch {batch} undone. Next: .venv/bin/python assets/moves.py verify {ub}")


# ---------------------------------------------------------------- verify

def verify(args):
    log = read_log()
    names = batches(log)
    if args:
        batch = args[0]
    elif names:
        batch = names[-1]
    else:
        sys.exit("The move log is empty.")
    base = batch[:-5] if batch.endswith("-undo") else batch
    snap_path = al.SNAPS / f"{base}.json"
    if not snap_path.exists():
        sys.exit(f"No snapshot {snap_path}")
    snap = json.loads(snap_path.read_text())
    scan_now()
    doc = al.load_catalog()
    problems, notes = [], []
    content = lambda md5, size, path: md5 or f"{path.rsplit('/', 1)[-1].casefold()}|{size}"  # noqa: E731
    before = Counter(content(m, b, p) for _, m, b, p, _ in snap["assets"])
    after = Counter(content(a["md5"], a["bytes"], a["path"]) for a in doc["assets"])
    for k in sorted((before - after).keys()):
        was = [p for _, m, b, p, _ in snap["assets"] if content(m, b, p) == k]
        problems.append(f"missing after: {was[0] if was else k}")
    for k in sorted((after - before).keys()):
        now_at = [a["path"] for a in doc["assets"] if content(a["md5"], a["bytes"], a["path"]) == k]
        problems.append(f"new since the snapshot: {now_at[0] if now_at else k}")
    nb, na = snap["files"], len(doc["assets"])
    bb, ba = snap["bytes"], sum(a["bytes"] for a in doc["assets"])
    if nb != na:
        problems.append(f"file count {nb} before, {na} after")
    if bb != ba:
        problems.append(f"total bytes {bb} before, {ba} after ({ba - bb:+d})")
    after_paths = {a["path"] for a in doc["assets"]}
    for _, _, _, path, was_locked in snap["assets"]:
        if was_locked and path not in after_paths:
            problems.append(f"LOCKED item moved or missing: {path}")
    folder_paths = {f["path"] for f in doc["folders"]}
    ids_before = {i: p for i, _, _, p, _ in snap["assets"]}
    ids_after = {a["id"]: a["path"] for a in doc["assets"]}
    for r in log:
        if r["batch"] != batch or r["kind"] not in ("file", "folder"):
            continue
        if r["to"] not in (folder_paths if r["kind"] == "folder" else after_paths):
            problems.append(f"{r['kind']} expected at {r['to']}, not there")
        elif r["kind"] == "file":
            moved_id = next((i for i, p in ids_before.items() if p == r["from"]), None)
            if moved_id and ids_after.get(moved_id) != r["to"]:
                notes.append(f"{r['to']}: the file system gave it a new id (content checked instead)")
    print(f"\nVerify {batch} against snapshot {snap_path.name} (taken {snap['taken']}):")
    print(f"  files {nb} -> {na}, bytes {al.gb(bb)} -> {al.gb(ba)}")
    for n in notes[:20]:
        print("  note: " + n)
    if problems:
        print(f"VERIFY FAILED: {len(problems)} problem(s)")
        for p in problems[:100]:
            print("  - " + p)
        sys.exit(1)
    print("  Verified: the same files with the same content and bytes, locked items untouched, "
          "every logged move where it should be.")


def show_log(args):
    log = read_log()
    if not log:
        print("The move log is empty.")
        return
    for b in batches(log):
        rs = [r for r in log if r["batch"] == b]
        print(f"{b:<48} {sum(r['kind'] in ('file', 'folder') for r in rs):>5} moves  {rs[0]['time']} .. {rs[-1]['time']}")
    print(f"(from {al.MOVE_LOG})")


def main():
    args = sys.argv[1:]
    cmd = args.pop(0) if args else ""
    if cmd == "check":
        _, ok = check(args)
        sys.exit(0 if ok else 1)
    {"apply": apply, "undo": undo, "verify": verify, "log": show_log}.get(cmd, lambda _: print(__doc__))(args)


if __name__ == "__main__":
    main()
