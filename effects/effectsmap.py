#!/usr/bin/env python3
"""Effects map: which visual effect is on screen over each stretch of a finished video, for Video Review's timeline.

Video Review can show a row above the frames that names what's on screen over each stretch: the Fast Cut layout of
each scene (split screen, card, big number, punch-in, mosaic, end card), any effect from the effects library
(letter-dive, spotlight, arch-text…), and the graphics a builder put on a stretch (hook title, end card, tag…).
The labels come from the build's own records, never from looking at the picture. They are saved beside the video as
"<video file>.effects.json", with the Glossary name and a one-line description where the thing has one.

    .venv/bin/python -I effects/effectsmap.py VIDEO              from the build record (the usual way)
    .venv/bin/python -I effects/effectsmap.py VIDEO --show       print a map that's already there
    .venv/bin/python -I effects/effectsmap.py VIDEO [records] [checks] [--dry-run] [--replace]

--auto (the default when no record below is given): every builder keeps a record at render time
(library/buildrecord.py, "<render>.build.json"): each scene's layout, every library effect and graphic with its start
and length, by the Glossary's names. The tool finds the record whose render has this video's picture, bit for bit
(library/builds.jsonl), and writes its blocks.

Records for a render made without a build record (one or more; their blocks are put together):
  --log FILE --vocab NAME   a Fast Cut render's printout: one "  12.34s <layout>" line per scene, then the file it
                            wrote. NAME is the builder's vocabulary in library/buildrecord.py (usually fastcut).
  --spec FILE               with --log, the edit spec whose segments are those scenes: it must list the same scenes in
                            the same order with the same layouts.
  --build-log FILE          a builder printout with "effect <name> a-b s" lines (library effects) and a
                            "wrote <file>.mp4 (<n>s" line.
  --reel-spec FILE          an edit spec with an end card ("fx": [{"type": "endcard", "start": -3}]) and the first
                            segment's graphics.
Checks:
  --render FILE     the version without sound effects this build wrote. The video's picture must be the same, bit for bit.
                    (--log and --build-log name it themselves.)
  --built-at FILE   a file the build wrote; the spec read must not be newer than it (it wasn't changed since).
  Always: every record's length matches the video (within 0.15 s), and where the records list scenes, the shot changes
  Video Review finds in the video must fall on scene changes (60% or more of them, within 0.07 s). The tool refuses,
  writing nothing, when the picture link fails, or when there's neither a picture link nor a passing shot check.

It only ever writes "<video file>.effects.json". It never changes a video, a spec or a work folder.

Python use (the review and library tools call these):
    map_path(video) -> Path of the map;  show(video);  auto_blocks(video) -> (blocks, record, source);
    glossary() -> {name: (kind, about)};  block(t0, t1, label, entry=None, detail="", key="", source="", group="")
"""
import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent            # <kit>/effects
STUDIO = HERE.parent                              # the kit's root folder
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
LEN_TOL = 0.15
CUT_TOL = 0.07          # seconds: a detected shot change counts as on a scene change within 2 frames
MIN_CUTS = 0.6          # share of detected shot changes that must fall on scene changes
FORMAT_VERSION = 1
ABOUT = ("Effects map for Video Review: what is on screen over each stretch of this video (layouts, library effects, "
         "graphics), from the build's own records. t and len are seconds in this file. entry is the Glossary name "
         "where there is one. Made by effects/effectsmap.py; safe to delete (the row then goes away).")

# What each builder's own names mean on screen, and plain lines for labels the Glossary doesn't have: the shared
# tables in library/buildrecord.py, so the builders' records and this tool use the same names.
sys.path.insert(0, str(STUDIO / "library"))
try:
    from buildrecord import VOCAB, PLAIN  # noqa: E402
except Exception:   # the library isn't there (yet): the Fast Cut layouts and the common graphics
    VOCAB = {
        "fastcut": {
            "split": ("Split screen", "Split screen", ""), "card": ("Card", "Card", ""),
            "card_split": ("Card", "Card", ""), "end": ("End card", "End card", ""), "mosaic": ("Mosaic", "Mosaic", ""),
            "punch": ("Punch-in", "Punch-in", ""), "big": ("Big number", "Big number", ""), "tag": ("Tag", None, ""),
            "graphic": ("Full-screen graphic", None, ""), "other": ("Graphic", None, ""), "full": None,
        },
        "graphics": {
            "hook": ("Hook title", None, ""), "endcard": ("End card", None, ""), "lower_third": ("Lower third", None, ""),
            "title": ("Title card", None, ""), "tag": ("Tag", None, ""), "counter": ("Counter", None, ""),
            "quote": ("Quote card", None, ""),
        },
    }
    PLAIN = {
        "Tag": "A short word or two that pops in over the footage.",
        "Tags": "Short words that pop in over the footage, one after another.",
        "Hook title": "The opening title over the first shot.",
        "End card": "The closing card: logo, a line and what to do next.",
        "Lower third": "A name and place in the lower part of the frame.",
        "Title card": "A full-screen title between chapters.",
        "Counter": "A number that counts up on screen.",
        "Quote card": "A quote in a floating card over the footage.",
        "Full-screen graphic": "A graphic on a plain background, in place of the footage.",
        "Graphic": "Something drawn over or in place of the footage.",
    }


class Refuse(Exception):
    pass


def run(cmd, timeout=900):
    r = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if r.returncode != 0:
        err = r.stderr.decode(errors="replace").strip().splitlines()
        raise RuntimeError(f"{Path(cmd[0]).name} failed: {err[-1] if err else 'no message'}")
    return r


def rel_studio(p):
    p = Path(p).resolve()
    try:
        return p.relative_to(STUDIO).as_posix()
    except ValueError:
        return str(p)


def duration(p):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], timeout=120)
    return float(r.stdout.decode().strip() or 0)


def picture_md5(p):
    r = run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(p), "-map", "0:v:0", "-c", "copy", "-f", "md5", "-"])
    return r.stdout.decode().strip()


def detect_cuts(p, dur):
    """Shot changes, found the way Video Review finds them: a picture change over 0.32."""
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-nostdin", "-i", str(p), "-an", "-vf",
             "scale=192:-2,select='gt(scene,0.32)',showinfo", "-f", "null", "-"], timeout=900)
    cuts = []
    for m in re.findall(rb"pts_time:\s*([\d.]+)", r.stderr):
        t = float(m)
        if 0.3 < t < dur - 0.3 and (not cuts or t - cuts[-1] > 0.4):
            cuts.append(round(t, 3))
    return cuts


# ---------------------------------------------------------------- the Glossary's own descriptions

_GLOSSARY = None


def _consts(p, names=("NAME", "ABOUT")):
    """Literal module constants, read without running the file."""
    out = {}
    try:
        tree = ast.parse(Path(p).read_text())
    except (OSError, SyntaxError):
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if getattr(t, "id", None) in names:
                    try:
                        out[t.id] = ast.literal_eval(node.value)
                    except Exception:
                        pass
    return out


def glossary():
    """name -> (kind, one line) from the files the Studio's Glossary is built from (review/studio.py), and every
    effect in effects/catalog. Without the Studio page it knows the effects and the builders' layout names."""
    global _GLOSSARY
    if _GLOSSARY is None:
        g = {}
        try:
            spec = importlib.util.spec_from_file_location("vs_studio", STUDIO / "review" / "studio.py")
            st = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(st)
            for e in st.style_entries() + st.word_entries([]):
                g.setdefault(e["name"], (e.get("kind") or "", e.get("about") or ""))
        except Exception:
            for table in VOCAB.values():
                for v in table.values():
                    if v and v[1]:
                        g.setdefault(v[1], ("Layout", ""))
        for f in sorted((HERE / "catalog").glob("*.py")):
            if f.name.startswith("_"):
                continue
            meta = _consts(f)
            if meta.get("NAME"):
                g[meta["NAME"]] = ("Effect", meta.get("ABOUT", ""))
        _GLOSSARY = g
    return _GLOSSARY


def _vocab_names():
    return {v[1] for table in VOCAB.values() for v in table.values() if v and v[1]}


def block(t0, t1, label, entry=None, detail="", key="", source="", group=""):
    about = ""
    if entry and entry not in glossary():
        if entry not in _vocab_names():
            raise Refuse(f"'{entry}' isn't in the Glossary, so it can't be named as one")
        entry = None            # a builder name the Glossary doesn't list (yet): keep the label, without a link
    if entry:
        g = glossary()[entry]
        about = g[1] if not g[1].startswith("(") else ""      # "(STYLES.md gives no description)" isn't a description
    if not about:
        about = PLAIN.get(label, "")
    b = {"t": round(t0, 3), "len": round(max(0.03, t1 - t0), 3), "label": label}
    if entry:
        b["entry"] = entry
    if detail:
        b["detail"] = detail
    if about:
        b["about"] = about.rstrip(".") + "."
    b["key"], b["from"] = key, source
    if group:
        b["group"] = group
    return b


# ---------------------------------------------------------------- readers

LOG_SCENE = re.compile(r"^\s*(\d+(?:\.\d+)?)s\s*(\S*)\s*$")
LOG_OUT = re.compile(r"(\S+\.mp4)\b.*?\s(\d+(?:\.\d+)?)s\b")


def read_log(path):
    """A Fast Cut render printout: [(t0, name)], the file it wrote, and its length."""
    scenes, out, total = [], None, None
    for line in Path(path).read_text(errors="replace").splitlines():
        m = LOG_SCENE.match(line)
        if m:
            scenes.append((float(m[1]), m[2]))
            continue
        m = LOG_OUT.search(line)
        if m and ("nofx" in m[1] or "nosfx" in m[1]):
            out, total = m[1], float(m[2])
    if not scenes or out is None:
        raise Refuse(f"{Path(path).name} isn't a render printout (no scene lines, or no file it wrote)")
    if out.startswith("wrote "):
        out = out[6:]
    return scenes, Path(out), total


def tags_block(t0, t1, tags, source):
    """The tags of one scene as one block, from the first tag until the scene ends. tags: [(seconds into the scene, text)]."""
    tags = sorted(tags)
    return block(t0 + tags[0][0], t1, "Tag" if len(tags) == 1 else "Tags", None,
                 ", ".join(f"“{txt}”" for _, txt in tags), "tags", source, "graphic")


def scene_blocks(scenes, total, vocab, source, extra=None):
    """Blocks for a scene list [(t0, t1, key, detail)]; consecutive scenes with the same label and detail join."""
    out = []
    for t0, t1, key, detail in scenes:
        v = VOCAB[vocab].get(key, "?")
        if v == "?":
            raise Refuse(f"the {vocab} records name a scene '{key}' the tool doesn't know; add it to VOCAB in "
                         "library/buildrecord.py after reading the builder's drawing code")
        if v is None:
            continue
        label, entry, d0 = v
        d = detail or d0
        if out and out[-1]["label"] == label and out[-1].get("detail", "") == d and abs(out[-1]["t"] + out[-1]["len"] - t0) < 0.02:
            out[-1]["len"] = round(t1 - out[-1]["t"], 3)
            continue
        out.append(block(t0, t1, label, entry, d, key, source, "scene"))
    return out


def reel_spec_blocks(spec_path, total):
    """An edit spec: the end card (counted from the end) and the first segment's graphics (it starts at 0)."""
    d = json.loads(Path(spec_path).read_text())
    out, src = [], f"{rel_studio(spec_path)}"
    segs = d.get("segments") or []
    if segs:
        s0 = segs[0]
        n0 = (float(s0["b"]) - float(s0["a"])) / float(s0.get("speed") or 1)
        for fx in s0.get("fx") or []:
            if fx.get("type") in VOCAB.get("graphics", {}):
                lab, ent, _ = VOCAB["graphics"][fx["type"]]
                e = fx.get("end")
                out.append(block(float(fx.get("start") or 0), n0 if e is None else float(e), lab, ent,
                                 graphic_detail(fx), fx["type"], src, "graphic"))
    for fx in d.get("fx") or []:
        if fx.get("type") == "endcard" and float(fx.get("start") or 0) < 0:
            out.append(block(total + float(fx["start"]), total, "End card", None, graphic_detail(fx), "endcard", src, "graphic"))
    return out


def graphic_detail(g):
    if g.get("type") == "chip":
        return " · ".join(x for x in (g.get("time"), g.get("place")) if x)
    for k in ("text", "title", "lines"):
        if g.get(k):
            return str(g[k]).replace("|", " ")
    return ""


# ---------------------------------------------------------------- checks and writing

def auto_blocks(video):
    """Blocks from the build record whose render has this video's picture."""
    try:
        import buildrecord as BR
    except Exception as e:
        raise Refuse(f"library/buildrecord.py couldn't be loaded ({e}), so build records can't be searched")
    recs = BR.find_records(BR.stream_md5(video, "v"))
    if not recs:
        raise Refuse("no build record has this video's picture (it was made before builds kept records, or by a "
                     "builder that doesn't keep one); give the build's printout or spec instead (see --help)")
    dur = duration(video)       # the same picture can sit in more than one record: take one of the right length
    r = next((x for x in recs if abs(float(x.get("duration") or 0) - dur) <= LEN_TOL), recs[0])
    doc = json.loads(Path(r["record"]).read_text())
    src = rel_studio(r["record"])
    out = []
    for b in doc.get("blocks") or []:
        entry = b.get("entry")
        if entry and entry not in glossary():
            entry = None        # a name the Glossary doesn't have (yet): keep the label, without a link
        out.append(block(b["t"], b["t"] + b["len"], b["label"], entry, b.get("detail", ""), b.get("key", ""), src,
                         b.get("group", "")))
    return out, doc, src


def check_picture(video, render):
    if not Path(render).is_file():
        return None
    if picture_md5(video) != picture_md5(render):
        raise Refuse(f"the video's picture isn't the picture of {Path(render).name}, the render these records come "
                     "from. They belong to another version.")
    return f"same picture as {rel_studio(render)}, bit for bit"


def check_cuts(video, dur, starts):
    cuts = detect_cuts(video, dur)
    if not cuts:
        return {"detected": 0, "on_scene_changes": 0, "share": None}
    on = sum(1 for c in cuts if any(abs(c - s) <= CUT_TOL for s in starts))
    return {"detected": len(cuts), "on_scene_changes": on, "share": round(on / len(cuts), 3)}


def lanes(blocks):
    """Overlapping blocks go on separate lanes (0 is the top one); scenes first."""
    blocks.sort(key=lambda b: (b["t"], 0 if b.get("group") == "scene" else 1))
    ends = []
    for b in blocks:
        for i, e in enumerate(ends):
            if b["t"] >= e - 0.001:
                b["lane"] = i
                ends[i] = b["t"] + b["len"]
                break
        else:
            b["lane"] = len(ends)
            ends.append(b["t"] + b["len"])
    return blocks


def map_path(video):
    return Path(str(video) + ".effects.json")


def show(video):
    f = map_path(video)
    if not f.exists():
        print(f"No effects map beside {Path(video).name}.")
        return
    d = json.loads(f.read_text())
    print(f"{f.name}  ({f.stat().st_size // 1024} KB, made {d.get('made')})\n  from: {', '.join(d.get('made_from', []))}"
          f"\n  checks: {d.get('checks')}")
    for b in d.get("blocks", []):
        print(f"  {b['t']:7.2f}-{b['t'] + b['len']:6.2f} s  lane {b.get('lane', 0)}  {b['label']}"
              + (f" · {b['detail']}" if b.get("detail") else "") + (f"  [Glossary: {b['entry']}]" if b.get("entry") else ""))


def _resolve_out(name, beside):
    """A file a printout names: absolute, or relative to the printout's folder, or to the kit."""
    p = Path(name)
    if p.is_absolute():
        return p
    for base in (Path(beside).resolve().parent, STUDIO):
        if (base / p).exists():
            return base / p
    return Path(beside).resolve().parent / p


def main():
    ap = argparse.ArgumentParser(description="Write a video's effects map (<video>.effects.json) for Video Review.")
    ap.add_argument("video")
    ap.add_argument("--log")
    ap.add_argument("--vocab", choices=[k for k in VOCAB if k != "graphics"])
    ap.add_argument("--spec")
    ap.add_argument("--build-log")
    ap.add_argument("--reel-spec")
    ap.add_argument("--render")
    ap.add_argument("--built-at")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--auto", action="store_true", help="from the build record (the default with no records given)")
    a = ap.parse_args()
    video = Path(a.video).expanduser().resolve()
    try:
        if not video.is_file() or video.suffix.lower() not in VIDEO_EXT:
            raise Refuse(f"not a video file: {video}")
        if a.show:
            return show(video)
        if any(p.lower() == "raw" for p in video.parent.parts):
            raise Refuse("this is a raw camera clip (it's in a Raw folder); effects maps are for finished videos")
        if map_path(video).exists() and not (a.replace or a.dry_run):
            raise Refuse(f"{map_path(video).name} is already there (add --replace to make it again)")
        dur = duration(video)
        blocks, starts, made_from, notes = [], [], [], []
        render = Path(a.render).resolve() if a.render else None
        picture_from_record = None

        def same_len(t, what):
            if abs(t - dur) > LEN_TOL:
                raise Refuse(f"{what} is {t:.2f} s long and the video is {dur:.2f} s, so it belongs to another version")

        def not_newer(p):
            if a.built_at and Path(p).stat().st_mtime > Path(a.built_at).stat().st_mtime + 1:
                raise Refuse(f"{Path(p).name} was changed after {Path(a.built_at).name} was made, so it may not "
                             "describe this video any more")

        if a.log:
            if not a.vocab:
                raise Refuse("--log needs --vocab (which builder printed it, e.g. fastcut)")
            scenes, out, total = read_log(a.log)
            same_len(total, Path(a.log).name)
            if render is None:
                render = _resolve_out(out, a.log)
                if not render.is_file():
                    if re.sub(r"_no(s)?fx$", "", out.stem) != video.stem:
                        raise Refuse(f"{Path(a.log).name} is the printout of {out.name}, which is gone, and its name "
                                     "isn't this video's, so nothing ties them together")
                    notes.append(f"the render {out.name} that {Path(a.log).name} names is no longer there, so the "
                                 "picture can't be compared; the log is matched by its name, its length and the shot changes")
            ends = [s[0] for s in scenes[1:]] + [total]
            rows = [(t0, t1, k, "") for (t0, k), t1 in zip(scenes, ends)]
            if a.spec:
                not_newer(a.spec)
                segs = json.loads(Path(a.spec).read_text()).get("segments") or []
                if len(segs) != len(rows) or any((s.get("layout") or "full") != r[2] for s, r in zip(segs, rows)):
                    raise Refuse(f"{Path(a.spec).name} doesn't list the same scenes as {Path(a.log).name} "
                                 f"({len(segs)} against {len(rows)}, or different layouts)")
                rows = [(r[0], r[1], r[2], (s["panel"] + " panel") if s.get("panel") else "") for s, r in zip(segs, rows)]
                for s, r in zip(segs, rows):
                    if s.get("tags"):
                        blocks.append(tags_block(r[0], r[1], [(float(tr), txt) for txt, tr in s["tags"]],
                                                 rel_studio(a.spec)))
                made_from.append(rel_studio(a.spec))
            blocks += scene_blocks(rows, total, a.vocab, rel_studio(a.log))
            starts += [r[0] for r in rows[1:]]
            made_from.append(rel_studio(a.log))
        if a.build_log:
            text = Path(a.build_log).read_text(errors="replace")
            m = re.search(r"wrote (\S+\.mp4) \(([\d.]+)s", text)
            if not m:
                raise Refuse(f"{Path(a.build_log).name} isn't a builder printout (no 'wrote … (… s' line)")
            same_len(float(m[2]), Path(a.build_log).name)
            if render is None:
                render = _resolve_out(m[1], a.build_log)
            for nm, t0, t1 in re.findall(r"^\s*effect\s+(\S+)\s+([\d.]+)-\s*([\d.]+)s", text, re.M):
                blocks.append(block(float(t0), float(t1), nm, nm, "", nm, rel_studio(a.build_log), "effect"))
            made_from.append(rel_studio(a.build_log))
        if a.reel_spec:
            not_newer(a.reel_spec)
            blocks += reel_spec_blocks(a.reel_spec, dur)
            made_from.append(rel_studio(a.reel_spec))
        if a.auto or not made_from:
            auto, rdoc, src = auto_blocks(video)
            same_len(float(rdoc.get("duration") or 0), Path(src).name)
            blocks += auto
            made_from.append(src)
            render = None
            picture_from_record = f"same picture as {rdoc.get('render')} (its build record), bit for bit"
        if not blocks:
            raise Refuse("the records name nothing special on screen (all plain footage), so there's no row to show")

        picture = check_picture(video, render) if render else picture_from_record
        cuts = check_cuts(video, dur, starts) if starts else None
        if cuts and cuts["share"] is not None and cuts["share"] < MIN_CUTS and not picture:
            raise Refuse(f"only {cuts['on_scene_changes']} of the {cuts['detected']} shot changes in the video fall on "
                         "the records' scene changes, so they don't describe this video")
        if not picture and not (cuts and cuts["share"] is not None and cuts["share"] >= MIN_CUTS):
            raise Refuse("nothing ties these records to this video: no render to compare the picture with, and no "
                         "scene list whose changes match the video's shot changes")
        for b in blocks:
            if b["t"] < -0.01 or b["t"] + b["len"] > dur + LEN_TOL:
                raise Refuse(f"'{b['label']}' at {b['t']:.2f} s runs outside the video")
            b["len"] = round(min(b["len"], dur - b["t"]), 3)
        st = video.stat()
        doc = {"about": ABOUT, "version": FORMAT_VERSION, "video": video.name, "video_size": st.st_size,
               "duration": round(dur, 3), "made": datetime.now().isoformat(timespec="seconds"), "made_from": made_from,
               "checks": {"lengths": "match", "picture": picture or "not compared", "cuts": cuts},
               "blocks": lanes(blocks)}
        if notes:
            doc["checks"]["notes"] = notes
        text = json.dumps(doc, indent=1, ensure_ascii=False) + "\n"
    except Refuse as e:
        sys.exit(f"Refused, nothing written: {e}")
    except RuntimeError as e:
        sys.exit(f"Stopped, nothing written: {e}")

    c = doc["checks"]
    print(f"{video.name}: {len(doc['blocks'])} blocks; picture: {c['picture']}; shot changes on scene changes: "
          + (f"{c['cuts']['on_scene_changes']} of {c['cuts']['detected']}" if c["cuts"] else "no scene list"))
    for n in notes:
        print("  note:", n)
    for b in doc["blocks"]:
        print(f"  {b['t']:7.2f}-{b['t'] + b['len']:6.2f} s  {b['label']}" + (f" · {b['detail']}" if b.get("detail") else "")
              + (f"  [Glossary: {b['entry']}]" if b.get("entry") else ""))
    if a.dry_run:
        print(f"Dry run: would write {map_path(video).name} ({len(text) // 1024 + 1} KB).")
        return
    f = map_path(video)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, f)
    print(f"Wrote {f}.")


if __name__ == "__main__":
    main()
