#!/usr/bin/env python3
"""Effects you can put on any video. See effects/README.md for the list and what each needs.

  python3 fx.py list
  python3 fx.py apply <video> <effect>@<when> [<effect>@<when> ...] [options]
      <when>:  2.5-6        seconds into the (trimmed) video
               2.5          a start; the effect's own length
               better       starts on that word (first time it's said); add +4 for a length: better+4
               (nothing)    the whole video
      --from S --to E     use only this stretch of the source (seconds)
      --set key=value     a setting (for one effect), or effect.key=value; repeatable. Values can be JSON.
      --skin dark|brand   dark (default): neutral dark panels, white text, yellow keywords
                          brand: the colours and fonts of a brand (brands/<slug>/brand.json)
      --brand SLUG        which brand for --skin brand (default: studio.json's default_brand)
      --grade none|camera|pov    a light colour grade, for camera originals
      --cx PX --zoom Z    where to crop a horizontal source (default: follow the face)
      --out FILE          default: <shoot>/Style Tests/<name>_<effects>_vN.mp4 (never overwrites)
  python3 fx.py sheet <video> <effect>@<when> ... [--times 1.2 3.4]   a contact sheet instead of a video (fast check)
  python3 fx.py prep <video> [--from S --to E ...]                     cutout, face and words only
  python3 fx.py commands                                               a slash command per effect (/spotlight, /orbit...)

Previews of every effect on your own footage: python3 make_previews.py --footage <folder> --out <folder>
"""
import os, sys, json, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import core
import catalog


def parse_val(v):
    try: return json.loads(v)
    except Exception: return v


def build_specs(subj, specs, sets):
    return core.make_specs(subj, specs, sets)


def default_out(src, names):
    """<shoot>/Style Tests/<name>_<effects>_vN.mp4 for a video in the content folder, else beside the video."""
    src = os.path.abspath(src)
    stem = os.path.splitext(os.path.basename(src))[0]
    tag = "+".join(names)
    folder = os.path.dirname(src)
    if core.CONTENT and src.startswith(os.path.abspath(core.CONTENT) + os.sep):
        shoot = os.path.relpath(src, core.CONTENT).split(os.sep)[0]
        folder = os.path.join(core.CONTENT, shoot, "Style Tests")
    os.makedirs(folder, exist_ok=True)
    v = 1
    while True:
        p = os.path.join(folder, f"{stem}_{tag}_v{v}.mp4")
        if not os.path.exists(p): return p
        v += 1


def skin_arg(a):
    """The skin a command line asked for: 'dark', or 'brand:<slug>'."""
    if a.brand:
        return "brand:" + a.brand
    return a.skin


def subject_from(a):
    return core.prep(a.video, a.start, a.end, a.cx, a.zoom, a.grade)


def cmd_list(a):
    rows = []
    for n in catalog.names():
        m = catalog.get(n)
        rows.append((m.KIND, n, m.ABOUT))
    if getattr(a, "md", False):
        for kind in catalog.KIND_ORDER:
            print(f"\n### {catalog.KIND_HEADINGS[kind]}\n\n| Effect | What it does | Length | Settings |\n|---|---|---|---|")
            for k, n, ab in rows:
                if k != kind: continue
                m = catalog.get(n)
                st = ", ".join(f"`{p}`" for p in m.PARAMS)
                tr = " (transition)" if n in catalog.TRANSITIONS else ""
                print(f"| `{n}`{tr} | {ab} | {m.DUR:g} s | {st} |")
        return
    for kind in catalog.KIND_ORDER:
        print(f"\n{catalog.KIND_HEADINGS[kind]}")
        for k, n, ab in rows:
            if k == kind:
                print(f"  {n:16s} {ab}" + ("  [transition]" if n in catalog.TRANSITIONS else ""))


def cmd_apply(a):
    subj = subject_from(a)
    specs = build_specs(subj, a.effects, a.set)
    names = [m.NAME for m, *_ in specs]
    out = a.out or default_out(a.video, names)
    for m, t0, t1, p in specs:
        core.log(f"  {m.NAME:14s} {t0:6.2f}-{t1:6.2f}s")
    core.render(subj, specs, out, skin_arg(a))
    # remember what went into it, for the video tracker (which raw seconds a test used)
    rec = core.APPLIED_LOG
    try:
        os.makedirs(os.path.dirname(rec), exist_ok=True)
        log = json.load(open(rec)) if os.path.exists(rec) else []
        log = [r for r in log if r["out"] != os.path.basename(out)]
        log.append(dict(out=os.path.basename(out), src=os.path.abspath(a.video), start=subj.meta["start"],
                        end=subj.meta["end"], effects=[f"{m.NAME}@{t0:.2f}-{t1:.2f}" for m, t0, t1, _ in specs],
                        skin=skin_arg(a)))
        json.dump(log, open(rec, "w"), indent=1)
    except Exception as e:
        core.log(f"  (couldn't log the export in {rec}: {e})")
    print(out)


def cmd_sheet(a):
    subj = subject_from(a)
    specs = build_specs(subj, a.effects, a.set)
    if a.times:
        frames = [int(round(t * core.FPS)) for t in a.times]
    else:
        frames = []
        for m, t0, t1, p in specs:
            frames += [int(round((t0 + (t1 - t0) * k) * core.FPS)) for k in (0.04, 0.2, 0.4, 0.6, 0.8, 0.97)]
    frames = sorted(set(min(subj.n - 1, max(0, f)) for f in frames))
    got = core.render(subj, specs, None, skin_arg(a), frames_only=frames)
    stem = os.path.splitext(os.path.basename(a.video))[0]
    out = a.out or os.path.join(core.CACHE, "sheets", f"{stem}_{'+'.join(m.NAME for m, *_ in specs)}.jpg")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    core.sheet([got[f] for f in frames], out, cols=min(6, len(frames)), labels=[f"{f / core.FPS:.2f}s" for f in frames])
    print(out)


# ------------------------------------------------------------------ slash commands (.claude/skills/<effect>/SKILL.md)
KINDS = {"cards": "on top of you", "behind": "behind you (uses the cutout)", "restyle": "you, restyled",
         "camera": "a camera or body trick"}


def param_docs(m):
    """[(name, default, comment)] from the effect's PARAMS = dict(...) and its comments."""
    import ast, io, tokenize
    src = open(m.__file__).read()
    tree = ast.parse(src)
    keys, end = [], 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "PARAMS" for t in node.targets):
            v = node.value
            if isinstance(v, ast.Call):
                keys = [(kw.arg, kw.value.lineno, kw.value.end_lineno) for kw in v.keywords]
            elif isinstance(v, ast.Dict):
                keys = [(k.value, k.lineno, vv.end_lineno) for k, vv in zip(v.keys, v.values)]
            end = node.end_lineno
    comments = {}
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            comments.setdefault(tok.start[0], []).append(tok.string.lstrip("#").strip())
    out = []
    for k, (name, l0, l1) in enumerate(keys):
        nxt = keys[k + 1][1] if k + 1 < len(keys) else end
        txt = [c for ln in range(l0, nxt) for c in comments.get(ln, [])]
        d = m.PARAMS.get(name)
        dv = "none" if d is None else json.dumps(d) if not isinstance(d, str) else d
        if len(dv) > 40: dv = dv[:37] + "..."
        out.append((name, dv, " ".join(txt)))
    return out


def skill_text(n, m):
    rows = "\n".join(f"| `{k}` | {d} | {c.replace('|', '/')} |" for k, d, c in param_docs(m))
    trans = ("\n- Works as a **transition**: put its window across a cut in an edit, and the cut lands at its peak "
             f"(about {catalog.TRANSITIONS[n]:.0%} of the way in)." if n in catalog.TRANSITIONS else "")
    quiet = ("\n- Quiet enough for a restrained brand." if n in catalog.QUIET else
             "\n- Not for a brand set to restrained (`\"effects\": {\"restrained\": true}` in its brand.json) "
             "unless you ask for it.")
    return f"""---
name: {n}
description: "Effect: {m.ABOUT}. Put it on a video: /{n} <video> at <word or seconds> [setting=value ...]"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /{n}

{m.ABOUT}.
- Kind: {KINDS.get(m.KIND, m.KIND)}. Default length {m.DUR:g} s.{trans}{quiet}
- Code: `effects/catalog/{n.replace('-', '_')}.py`
- Preview on your own footage: `.venv/bin/python effects/make_previews.py --footage <folder> --out <folder> --only {n}`

**You asked:** $ARGUMENTS

Put this effect on the video named. Follow `.claude/skills/effects/SKILL.md`: find the video, pick the moment from its
transcript if none was given, check a sheet, render, open it in Video Review, update the tracker.

```
.venv/bin/python effects/fx.py sheet "<video>" {n}@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
.venv/bin/python effects/fx.py apply "<video>" {n}@<when> [--from S --to E] [--grade camera|pov] [--skin brand --brand <slug>] [--set key=value]
```

`<when>`: `7.2-10.6` (seconds), `7.2` (a start), `better` (on that word), `better+4` (on that word, 4 s long).
If no video was named, ask which (suggest recent clips or reels). If it's for an edit you're building, add it to that
builder's effects list instead (the effects skill says how).

## Settings (`--set key=value`)

| Setting | Default | What it does |
|---|---|---|
{rows}

Text defaults to the speaker's own words. Any wording you write in a setting, flag it before the video is posted.
Numbers on screen must be real: never invent one.
"""


def alias_text(al, tgt, m, pre):
    sets = " ".join(f"--set {k}={json.dumps(v) if not isinstance(v, str) else v}" for k, v in pre.items())
    return f"""---
name: {al}
description: "Effect: {m.ABOUT}{' (' + ', '.join(f'{k} {v}' for k, v in pre.items()) + ')' if pre else ''}. Same as /{tgt}{' with ' + sets if sets else ''}. /{al} <video> at <word or seconds>"
argument-hint: <video> [at "<word>" | at <start>-<end>] [setting=value ...]
disable-model-invocation: true
---

# /{al}

Another name for `/{tgt}`{' with ' + sets if sets else ''}: read `.claude/skills/{tgt}/SKILL.md` and follow it, using
`{al}@<when>` (fx.py applies {'the preset' if pre else 'the same effect'}) or `{tgt}@<when> {sets}`.

**You asked:** $ARGUMENTS
"""


def cmd_commands(a):
    """Write one slash command per effect into <kit>/.claude/skills/<effect>/SKILL.md."""
    root = os.path.join(core.STUDIO, ".claude", "skills")
    made = []
    for n in catalog.names():
        m = catalog.get(n)
        d = os.path.join(root, n)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "SKILL.md"), "w").write(skill_text(n, m))
        made.append(n)
    for al in getattr(catalog, "COMMAND_ALIASES", []):
        tgt = catalog.ALIASES[al]; pre = getattr(catalog, "PRESETS", {}).get(al, {})
        d = os.path.join(root, al); os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "SKILL.md"), "w").write(alias_text(al, tgt, catalog.get(tgt), pre))
        made.append(al)
    print(f"{len(made)} commands in {root}: " + " ".join("/" + n for n in made))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").add_argument("--md", action="store_true", help="as Markdown tables (for README.md)")
    def common(p):
        p.add_argument("video")
        p.add_argument("--from", dest="start", type=float); p.add_argument("--to", dest="end", type=float)
        p.add_argument("--cx", type=float); p.add_argument("--zoom", type=float, default=1.0)
        p.add_argument("--grade", default="none", choices=sorted(set(core.GRADES) | set(core.GRADE_ALIASES)))
        p.add_argument("--skin", default="dark", choices=core.SKIN_NAMES)
        p.add_argument("--brand", help="brand slug for --skin brand (brands/<slug>/)")
        p.add_argument("--set", action="append", default=[])
        p.add_argument("--out")
    p = sub.add_parser("apply"); common(p); p.add_argument("effects", nargs="+")
    p = sub.add_parser("sheet"); common(p); p.add_argument("effects", nargs="+"); p.add_argument("--times", type=float, nargs="*")
    p = sub.add_parser("prep"); common(p)
    sub.add_parser("commands", help="write a slash command per effect (.claude/skills/<effect>)")
    a = ap.parse_args()
    if a.cmd == "list": cmd_list(a)
    elif a.cmd == "apply": cmd_apply(a)
    elif a.cmd == "sheet": cmd_sheet(a)
    elif a.cmd == "prep":
        s = subject_from(a); print(s.dir); print(json.dumps(s.meta, indent=1))
    elif a.cmd == "commands": cmd_commands(a)


if __name__ == "__main__":
    main()
