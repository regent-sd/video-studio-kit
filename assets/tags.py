#!/usr/bin/env python3
"""Asset Library: check and file the descriptions and tags the tagging agents write.

  .venv/bin/python assets/tags.py check <batch or chunk>     validate its work file against TAGGING.md; exit 1 on problems
  .venv/bin/python assets/tags.py apply <batch> [--no-scan]  check, write <library>/tags/<batch>.json, run catalog.py scan
  .venv/bin/python assets/tags.py status                     per batch: files, tagged, applied; coverage; counts per tag
  .venv/bin/python assets/tags.py sample <batch> [--n 20] [--seed S]   review sheets (preview + its tags) to spot-check
  .venv/bin/python assets/tags.py vocab                      the word lists as read from TAGGING.md
  .venv/bin/python assets/tags.py paths [<chunk>]            where a chunk's sheets are and where its work file goes

Work files are <cache>/tags-work/<batch or chunk>.json: one entry per unique file, keyed by its md5 (or by its id
when the batch lists no md5): {"<key>": {"description", "tags", "flags", "brand_status"}}. The word lists are read from
TAGGING.md (the fixed lists plus your "Your business" section) every time, so that page stays the one source.
A name that is a chunk (made by chunks.py) is looked up in <cache>/chunks/, a batch in <cache>/sheets/.
"""
import datetime as dt
import difflib
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assetlib as al  # noqa: E402

DOC = HERE / "TAGGING.md"
ENTRY_KEYS = ("description", "tags", "flags", "brand_status")
NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
BUSINESS = "your business"


# ---------------------------------------------------------------- the vocabulary, read from TAGGING.md

class DocError(Exception):
    pass


def ticks(s):
    return re.findall(r"`([^`]+)`", s)


def sections(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


def field_blocks(lines):
    """Each "**name** (...)" or "**name**:" opens a field block, which runs to the next blank line or heading; a line
    may open several (people / people_count). A bold word in running text ("the **location** word") opens nothing."""
    fields, order, cur = {}, [], None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            cur = None
            continue
        parts = re.split(r"\*\*([a-z_]+)\*\*(?=\s*[(:])", line)
        if len(parts) == 1:
            if cur:
                fields[cur]["text"].append(line)
            continue
        if parts[0].strip() and cur:
            fields[cur]["text"].append(parts[0])
        for i in range(1, len(parts), 2):
            cur = parts[i]
            if cur not in fields:
                order.append(cur)
                fields[cur] = {"head": parts[i + 1], "text": []}
            else:
                fields[cur]["text"].append(parts[i + 1])
    return order, fields


def block_words(f):
    head = f["head"].strip()
    paren = re.match(r"^\(([^)]*)\)", head)
    body = [head[paren.end():] if paren else head] + f["text"]
    bullets = [line for line in f["text"] if line.lstrip().startswith("- ")]
    if bullets and all(ticks(b.split(":", 1)[0]) for b in bullets):      # "- `word`: meaning" lines
        return [ticks(b)[0] for b in bullets]
    return [w for line in body for w in ticks(line)]


def field_spec(name, f):
    head = f["head"].strip()
    paren = re.match(r"^\(([^)]*)\)", head)
    rule = (paren.group(1) if paren else "").lower()
    spec = {"photo_video_only": "photos and video only" in rule}
    if "number" in rule:
        spec["kind"] = "number"
    elif re.match(r"\d\s*[–-]\s*\d", rule):
        lo, hi = map(int, re.findall(r"\d", rule)[:2])
        spec.update(kind="int", min=lo, max=hi)
    elif "free text" in rule and rule.startswith("list"):
        spec["kind"] = "text-list"
    elif "list of names" in rule:
        spec.update(kind="text-list", names_from_path=True)
    elif "free text" in rule:
        spec["kind"] = "text"
    else:
        m = re.match(r"(\w+)\s+to\s+(\w+)", rule)
        if m and m.group(1) in NUMS and m.group(2) in NUMS:
            spec.update(kind="list", min=NUMS[m.group(1)], max=NUMS[m.group(2)])
        elif rule.startswith("one") or not rule:
            spec["kind"] = "one"
        else:
            raise DocError(f'can\'t tell what kind of value **{name}** takes from "({rule})"')
        spec["words"] = block_words(f)
    return spec


def parse_vocab(path=DOC):
    """Fields, their kind (one / list / text / number / int) and allowed words, the flags, brand_status and the
    description limit. "## Your business" adds words to a field, flags or brand_status, or adds a whole new field."""
    try:
        text = path.read_text()
    except OSError as e:
        raise DocError(f"can't read {path}: {e}")
    secs = sections(text)

    def sec(prefix, required=True):
        for k, v in secs.items():
            if k.lower().startswith(prefix):
                return k, v
        if required:
            raise DocError(f'TAGGING.md has no "## {prefix}..." section')
        return None, []

    _, desc = sec("description")
    m = re.search(r"(\d+)\s+words\s+at\s+most", " ".join(desc))
    if not m:
        raise DocError('the Description section no longer says "<N> words at most"')

    order, blocks = field_blocks(sec("tags")[1])
    if not blocks:
        raise DocError("the Tags section lists no **field** entries")
    vocab = {name: field_spec(name, blocks[name]) for name in order}

    def bullet_words(prefix):
        title, ls = sec(prefix)
        words = [ticks(line)[0] for line in ls if line.lstrip().startswith("- ") and ticks(line)]
        if not words:
            raise DocError(f'"## {title}" lists no `words` in bullets')
        return words

    flags, brand_status = bullet_words("flags"), bullet_words("brand_status")
    b_order, b_blocks = field_blocks(sec(BUSINESS, required=False)[1])
    for name in b_order:
        if name == "flags":
            flags += [w for w in block_words(b_blocks[name]) if w not in flags]
        elif name == "brand_status":
            brand_status += [w for w in block_words(b_blocks[name]) if w not in brand_status]
        elif name in vocab:
            if "words" in vocab[name]:
                vocab[name]["words"] += block_words(b_blocks[name])
        else:
            vocab[name] = field_spec(name, b_blocks[name])
    for name, spec in vocab.items():
        if "words" in spec:
            spec["words"] = list(dict.fromkeys(spec["words"]))
            if not spec["words"]:
                raise DocError(f"**{name}** has no `words` listed (in Tags or in Your business)")
    return {"max_words": int(m.group(1)), "fields": vocab, "flags": flags, "brand_status": brand_status}


def vocab_or_exit():
    try:
        return parse_vocab()
    except DocError as e:
        sys.exit(f"tags.py: can't read the word lists from TAGGING.md: {e}\n"
                 "Fix TAGGING.md before checking any work.")


def suggest(word, choices):
    m = difflib.get_close_matches(str(word).lower(), [str(c) for c in choices], n=1, cutoff=0.55)
    if not m:
        m = [c for c in choices if str(word).lower() in str(c) or str(c) in str(word).lower()][:1]
    return f' (did you mean "{m[0]}"?)' if m else ""


# ---------------------------------------------------------------- batches, chunks and work files

def batch_dir(name):
    for base in (al.SHEETS, al.CHUNKS):
        if (base / name / "batch.json").exists():
            return base / name
    return None


def batch_doc(name):
    d = batch_dir(name)
    if d is None:
        known = sorted(p.name for base in (al.SHEETS, al.CHUNKS) if base.exists()
                       for p in base.iterdir() if (p / "batch.json").exists())
        sys.exit(f"No batch or chunk {name!r}." + (suggest(name, known) if known else " (none yet: run previews.py sheets)"))
    return json.loads((d / "batch.json").read_text())


def batch_items(doc):
    """{key: item} for every unique file in the batch; key = md5, else the file's id."""
    items = {}
    for s in doc.get("sheets", []):
        for c in s.get("cells", []):
            items[c.get("md5") or c["ids"][0]] = dict(c, _sheet=s.get("file"))
    for c in doc.get("no_preview", []):
        items[c.get("md5") or c["ids"][0]] = dict(c, _sheet=None)
    return items


def work_path(name):
    return al.WORK / f"{name}.json"


def load_work(name):
    p = work_path(name)
    if not p.exists():
        return None, f"no work file yet: {p}"
    try:
        d = json.loads(p.read_text())
    except ValueError as e:
        return None, f"{p.name} is not valid JSON: {e}"
    if not isinstance(d, dict):
        return None, f"{p.name} must be one JSON object {{key: entry}}, not a {type(d).__name__}"
    return d, None


# ---------------------------------------------------------------- check

def check_entry(key, e, item, V):
    probs, warns = [], []

    def P(msg):
        probs.append(f"{key}  {msg}")

    def W(msg):
        warns.append(f"{key}  {msg}")

    if not isinstance(e, dict):
        P(f"entry must be an object with {', '.join(ENTRY_KEYS)}")
        return probs, warns
    for k in e:
        if k not in ENTRY_KEYS:
            P(f'unknown key "{k}"{suggest(k, ENTRY_KEYS)}; allowed: {", ".join(ENTRY_KEYS)}')
    d = e.get("description")
    if not isinstance(d, str) or not d.strip():
        P("description is missing or empty")
    elif len(d.split()) > V["max_words"]:
        P(f"description is {len(d.split())} words; at most {V['max_words']}")
    tags = e.get("tags") or {}
    if not isinstance(tags, dict):
        P("tags must be an object {field: value}")
        tags = {}
    F = V["fields"]
    paths = " ".join(item.get("paths", [])).lower() if item else ""
    pv = item and (item.get("kind") in ("photo", "video") or tags.get("type") in ("photo", "video"))
    for k, v in tags.items():
        if k not in F:
            P(f'unknown tag "{k}"{suggest(k, F)}; tags are: {", ".join(F)}')
            continue
        s, where = F[k], f"tags.{k}"
        if v is None or v == [] or v == "":
            continue                                   # an explicit clear: allowed by the merge contract
        if s.get("photo_video_only") and item and not pv:
            W(f"{where} is for photos and video only; this is a {item.get('kind')}")
        kind = s["kind"]
        if kind == "one":
            if isinstance(v, list):
                P(f"{where} takes one word, not a list")
            elif not isinstance(v, str) or v not in s["words"]:
                P(f'{where}: "{v}" is not on the list{suggest(v, s["words"])}')
        elif kind == "list":
            if isinstance(v, str):
                P(f'{where} must be a list, e.g. ["{v}"]')
                continue
            if not isinstance(v, list):
                P(f"{where} must be a list of words")
                continue
            if not s["min"] <= len(v) <= s["max"]:
                P(f"{where} has {len(v)} values; {s['min']} to {s['max']}")
            for w in v:
                if w not in s["words"]:
                    P(f'{where}: "{w}" is not on the list{suggest(w, s["words"])}')
            if len(set(map(str, v))) < len(v):
                P(f"{where} repeats a value")
        elif kind == "text-list":
            if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
                P(f"{where} must be a list of names (strings)")
                continue
            if s.get("names_from_path") and item:
                for x in v:
                    if x.lower() not in paths:
                        P(f'{where}: "{x}" is not in the folder path or file name (names come only from there)')
        elif kind == "text":
            if not isinstance(v, str) or not v.strip():
                P(f"{where} must be text")
            elif item and v.lower() not in paths:
                W(f'{where}: "{v}" is not in the path (campaigns come from the path)')
        elif kind == "number":
            if isinstance(v, bool) or not isinstance(v, int):
                P(f"{where} must be a whole number like 2024, not {json.dumps(v)}")
            elif not 1900 <= v <= dt.date.today().year + 1:
                P(f"{where}: {v} doesn't look like a year")
            elif item and str(v) not in paths and not str(item.get("taken") or "").startswith(str(v)):
                W(f"{where}: {v} is neither in the path nor the photo's date ({item.get('taken') or 'none'})")
        elif kind == "int":
            if isinstance(v, bool) or not isinstance(v, int) or not s["min"] <= v <= s["max"]:
                P(f"{where} must be a whole number {s['min']} to {s['max']}, not {json.dumps(v)}")
    if not tags.get("subject") and "subject" in F:
        W("no tags.subject (one to three subjects make it findable)")
    fl = e.get("flags", [])
    if fl is not None:
        if not isinstance(fl, list):
            P(f'flags must be a list, e.g. ["{fl}"]' if isinstance(fl, str) else "flags must be a list")
        else:
            for f in fl:
                if f not in V["flags"]:
                    P(f'flags: "{f}" is not a flag{suggest(f, V["flags"])}')
            if len(set(map(str, fl))) < len(fl):
                P("flags repeats a value")
            if tags.get("people_count") == "none" and ({"people-visible", "customers-visible", "kids-visible"} & set(fl)):
                W('people_count is "none" but a people flag is set')
    bs = e.get("brand_status")
    if bs is None:
        W('no brand_status (use "unknown" if you can\'t tell)')
    elif bs not in V["brand_status"]:
        P(f'brand_status: "{bs}" is not allowed{suggest(bs, V["brand_status"])}; one of {", ".join(V["brand_status"])}')
    return probs, warns


def run_check(name, quiet=False):
    """(ok, work, items). Prints the problems."""
    V = vocab_or_exit()
    items = batch_items(batch_doc(name))
    work, err = load_work(name)
    if err:
        print(f"{name}: {err}")
        return False, None, items
    id_to_key = {i: k for k, it in items.items() for i in it.get("ids", [])}
    probs, warns = [], []
    for key, e in work.items():
        if key not in items:
            if key in id_to_key:
                probs.append(f"{key}  this is a file id; key this entry by its md5 {id_to_key[key]}")
            else:
                probs.append(f"{key}  not in {name} (no file with this md5 or id)")
            continue
        p, w = check_entry(key, e, items[key], V)
        probs += p
        warns += w
    missing = [k for k in items if k not in work]
    for k in missing:
        it = items[k]
        where = f"{it['_sheet']} {it.get('cell')}" if it.get("_sheet") else "no_preview"
        probs.append(f"{k}  missing entry ({where}: {it.get('name')})")
    ok = not probs
    if not quiet or not ok:
        for line in probs:
            print("PROBLEM  " + line)
        for line in warns:
            print("warning  " + line)
        print(f"{name}: {len(items)} files, {len(work)} entries, {len(missing)} missing, {len(probs)} problems, "
              f"{len(warns)} warnings - " + ("OK" if ok else "fix the problems and run check again"))
    return ok, work, items


def check(args):
    if not args:
        sys.exit("usage: tags.py check <batch or chunk>")
    ok, *_ = run_check(args[0])
    sys.exit(0 if ok else 1)


# ---------------------------------------------------------------- apply

def apply(args):
    no_scan = al.flag(args, "--no-scan")
    if not args:
        sys.exit("usage: tags.py apply <batch> [--no-scan]")
    name = args[0]
    ok, work, items = run_check(name, quiet=True)
    if not ok:
        sys.exit("Not applied: fix the problems above first.")
    out = {key: {k: e[k] for k in ENTRY_KEYS if k in e} for key, e in sorted(work.items())}
    dest = al.TAGS_DIR / f"{name}.json"
    al.atomic_write(dest, json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True))
    copies = sum(len(items[k].get("ids", [])) for k in out)
    print(f"Wrote {dest}: {len(out)} entries, covering {copies} copies (every copy of a file shares its tags)")
    if no_scan:
        print("--no-scan: run catalog.py scan to merge them into the catalog")
        return
    r = subprocess.run([sys.executable, str(HERE / "catalog.py"), "scan"], capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-2000:])
        sys.exit("catalog.py scan failed; the tags file is written, run the scan again by hand")
    assets = al.load_catalog()["assets"]
    print(f"catalog.py scan done: {sum(1 for a in assets if a.get('description'))} of {len(assets)} files now carry tags")


# ---------------------------------------------------------------- status

def status(args):
    V = vocab_or_exit()
    idx_p = al.SHEETS / "index.json"
    index = json.loads(idx_p.read_text()) if idx_p.exists() else []
    names = [b["batch"] for b in index] or sorted(p.stem for p in al.WORK.glob("*.json"))
    tot = [0, 0, 0]
    if names:
        print(f"{'batch':<46}{'files':>7}{'tagged':>8}  applied")
    for n in names:
        b = next((x for x in index if x["batch"] == n), {})
        work, err = load_work(n)
        done = len(work) if work else 0
        dest = al.TAGS_DIR / f"{n}.json"
        if dest.exists():
            stale = work_path(n).exists() and work_path(n).stat().st_mtime > dest.stat().st_mtime
            ap = dt.datetime.fromtimestamp(dest.stat().st_mtime).strftime("%m-%d %H:%M") + (" (work file changed since)" if stale else "")
        else:
            ap = "-"
        if err and work_path(n).exists():
            ap += f"  [{err}]"
        print(f"{n:<46}{b.get('assets', '?'):>7}{done:>8}  {ap}")
        tot[0] += b.get("assets", 0)
        tot[1] += done
        tot[2] += dest.exists()
    if names:
        print(f"{'total':<46}{tot[0]:>7}{tot[1]:>8}  {tot[2]} of {len(names)} batches applied")
    else:
        print("No batches yet (run previews.py sheets).")
    if not al.CATALOG.exists():
        return
    assets = al.load_catalog()["assets"]

    def cov(fn):
        t = {}
        for a in assets:
            c = t.setdefault(fn(a), [0, 0])
            c[0] += 1
            c[1] += bool(a.get("description"))
        return t
    for title, fn in (("By kind", lambda a: a["kind"]), ("By folder", lambda a: f"{a['root']}/{a['top']}" if a["top"] else a["root"])):
        print(f"\n{title} (tagged / all files):")
        for k, (n, d) in sorted(cov(fn).items(), key=lambda kv: -kv[1][0]):
            print(f"  {k[:40]:<42}{d:>6} / {n:<6} {100 * d / n:5.1f}%")
    uniq = {}
    for a in assets:
        if a.get("description"):
            uniq.setdefault(al.key_of(a), a)
    print(f"\nAll: {sum(1 for a in assets if a.get('description'))} of {len(assets)} files tagged ({len(uniq)} unique)")
    if not uniq:
        return
    print("\nCounts per value:")
    for f in V["fields"]:
        c = Counter()
        for a in uniq.values():
            v = (a.get("tags") or {}).get(f)
            for x in (v if isinstance(v, list) else [v] if v not in (None, "") else []):
                c[str(x)] += 1
        if c:
            top = c.most_common(40)
            unk = [w for w, _ in top if "words" in V["fields"][f] and w not in map(str, V["fields"][f]["words"])]
            print(f"  {f}: " + ", ".join(f"{w} {n}" for w, n in top) + (f"  (+{len(c) - 40} more)" if len(c) > 40 else "")
                  + (f"   NOT ON THE LIST: {', '.join(unk)}" if unk else ""))
    for title in ("flags", "brand_status"):
        c = Counter()
        for a in uniq.values():
            v = a.get(title)
            for x in (v if isinstance(v, list) else [v] if v else []):
                c[x] += 1
        print(f"  {title}: " + (", ".join(f"{w} {n}" for w, n in c.most_common()) or "none"))


# ---------------------------------------------------------------- sample review sheets

def wrap(d, text, f, width):
    out = []
    for para in str(text).split("\n"):
        line = ""
        for w in para.split(" "):
            t = (line + " " + w).strip()
            if d.textlength(t, font=f) <= width or not line:
                line = t
            else:
                out.append(line)
                line = w
        out.append(line)
    return out


def review_sheet(rows, out):
    from PIL import Image, ImageDraw
    W, BOX, PAD = 1700, 420, 28
    TX = W - BOX - 3 * PAD
    f_name, f_desc, f_lab, f_val, f_path = al.ui_font(30, True), al.ui_font(30), al.ui_font(25, True), al.ui_font(25), al.ui_font(21)
    ink, label_ink, faint = (24, 24, 24), (40, 70, 110), (110, 110, 110)
    scratch = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    blocks = []
    for r in rows:
        lines = [(f_name, ink, line) for line in wrap(scratch, f"{r['cell']}  {r['name']}", f_name, TX)]
        lines += [(f_path, faint, line) for line in wrap(scratch, r["where"], f_path, TX)]
        lines.append(None)
        lines += [(f_desc, ink, line) for line in wrap(scratch, r["description"] or "(no description)", f_desc, TX)]
        lines.append(None)
        for lab, val in r["fields"]:
            lw = scratch.textlength(lab + ": ", font=f_lab)
            vl = wrap(scratch, val, f_val, TX - lw)
            lines.append(("pair", lab + ": ", vl[0], lw))
            lines += [("cont", lw, line) for line in vl[1:]]
        h = sum(14 if line is None else 36 for line in lines)
        blocks.append((r, lines, max(BOX, h) + 2 * PAD))
    img = Image.new("RGB", (W, sum(b[2] for b in blocks) + PAD), (248, 248, 246))
    d = ImageDraw.Draw(img)
    y = PAD
    for r, lines, h in blocks:
        d.rectangle([PAD, y, PAD + BOX - 1, y + BOX - 1], fill=(225, 225, 222))
        if r["thumb"] and r["thumb"].exists():
            with Image.open(r["thumb"]) as t:
                t = t.convert("RGB")
                t.thumbnail((BOX, BOX), Image.LANCZOS)
                img.paste(t, (PAD + (BOX - t.width) // 2, y + (BOX - t.height) // 2))
        else:
            d.text((PAD + BOX // 2, y + BOX // 2), f"no preview\n{r['kind']}", font=f_lab, fill=faint, anchor="mm", align="center")
        x, ty = 2 * PAD + BOX, y
        for line in lines:
            if line is None:
                ty += 14
                continue
            if line[0] == "pair":
                d.text((x, ty), line[1], font=f_lab, fill=label_ink)
                d.text((x + line[3], ty), line[2], font=f_val, fill=ink)
            elif line[0] == "cont":
                d.text((x + line[1], ty), line[2], font=f_val, fill=ink)
            else:
                d.text((x, ty), line[2], font=line[0], fill=line[1])
            ty += 36
        y += h
        d.line([PAD, y - 1, W - PAD, y - 1], fill=(205, 205, 200), width=2)
    img.save(out, "JPEG", quality=85)


def sample(args):
    if not args:
        sys.exit("usage: tags.py sample <batch> [--n 20] [--seed S]")
    name = args.pop(0)
    n, seed = int(al.opt(args, "--n", "20")), al.opt(args, "--seed")
    items = batch_items(batch_doc(name))
    work, err = load_work(name)
    if err:
        sys.exit(f"{name}: {err}")
    keys = sorted(k for k in work if k in items)
    pick = sorted(random.Random(seed).sample(keys, min(n, len(keys))),
                  key=lambda k: (items[k].get("_sheet") or "~", items[k].get("cell") or "", k))
    rows = []
    for k in pick:
        it, e = items[k], work[k] if isinstance(work[k], dict) else {}
        tags = e.get("tags") if isinstance(e.get("tags"), dict) else {}
        fields = [(f, ", ".join(map(str, v)) if isinstance(v, list) else str(v)) for f, v in tags.items() if v not in (None, [], "")]
        fields.append(("flags", ", ".join(map(str, e.get("flags") or [])) or "none"))
        fields.append(("brand_status", str(e.get("brand_status") or "-")))
        paths = it.get("paths", [])
        rows.append({"cell": f"{(it.get('_sheet') or 'no preview').replace('.jpg', '')} {it.get('cell') or ''}".strip(),
                     "name": it.get("name"), "kind": it.get("kind"), "key": k,
                     "where": paths[0] + (f"  (+{len(paths) - 1} copies)" if len(paths) > 1 else ""),
                     "thumb": al.THUMBS / it["thumb"] if it.get("thumb") else None,
                     "description": e.get("description"), "fields": fields})
    dest = al.REVIEW / name
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("review-*.jpg"):
        old.unlink()
    files = []
    for i in range(0, len(rows), 5):
        fn = dest / f"review-{i // 5 + 1:02d}.jpg"
        review_sheet(rows[i:i + 5], fn)
        files.append(fn.name)
    (dest / "sample.json").write_text(json.dumps({"batch": name, "seed": seed, "n": len(rows),
                                                  "keys": [r["key"] for r in rows], "sheets": files}, indent=1))
    print(f"{len(rows)} of {len(keys)} entries sampled into {len(files)} sheets in {dest}")
    for f in files:
        print("  " + str(dest / f))


def vocab(args):
    V = vocab_or_exit()
    print(f"description: at most {V['max_words']} words")
    for k, s in V["fields"].items():
        extra = {x: y for x, y in s.items() if x not in ("kind", "words")}
        print(f"{k:<13} {s['kind']:<9} {' '.join(map(str, s.get('words', [])))} {extra if extra else ''}")
    print(f"flags         {' '.join(V['flags'])}\nbrand_status  {' '.join(V['brand_status'])}")


def paths(args):
    """Everything a tagging agent needs to know about where things are."""
    print(f"rulebook     {DOC}")
    print(f"brief        {HERE / 'tagging-agent-brief.md'}")
    refs = sorted(al.REFERENCE.glob("*.jpg")) if al.REFERENCE.exists() else []
    print("reference    " + (", ".join(str(p) for p in refs) if refs else "(none: no reference sheets made)"))
    if args:
        d = batch_dir(args[0])
        if d is None:
            sys.exit(f"No batch or chunk {args[0]!r}")
        print(f"chunk        {d}")
        print(f"batch.json   {d / 'batch.json'}")
        print(f"sheets       {', '.join(p.name for p in sorted(d.glob('sheet-*.jpg'))) or '(none: tag from batch.json)'}")
        print(f"write to     {work_path(args[0])}")
        print(f"check with   .venv/bin/python assets/tags.py check {args[0]}")


def main():
    args = sys.argv[1:]
    cmd = args.pop(0) if args else ""
    {"check": check, "apply": apply, "status": status, "sample": sample, "vocab": vocab,
     "paths": paths}.get(cmd, lambda _: print(__doc__))(args)


if __name__ == "__main__":
    main()
