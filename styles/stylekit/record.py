"""Build records (library/buildrecord.py): what a render shows over each stretch and its separate sound tracks,
kept by the builder after the render. The sound and effects maps beside a finished video are made from it, so
Video Review's rows fill in by themselves.

Nothing here may stop a render: every call is wrapped and a problem prints one line starting [build record].
"""
from __future__ import annotations

import importlib.util
import os
import sys

from . import paths

# Labels to use when buildrecord's own vocabulary doesn't know a layout name: (label, Glossary entry or None).
# None means plain footage: no block.
FALLBACK = {
    "fastcut": {"split": ("Split screen", "Split screen"), "card": ("Card", "Card"), "card_split": ("Card", "Card"),
                "end": ("End card", "End card"), "mosaic": ("Mosaic", "Mosaic"), "punch": ("Punch-in", "Punch-in"),
                "tag": ("Tag", None), "graphic": ("Full-screen graphic", None), "big": ("Big number", "Big number"),
                "explainer": ("Explainer", "Explainer"), "broll": ("B-roll", None), "other": ("Graphic", None),
                "full": None},
    "talking-head": {"talk": None, "footage": None, "punch": ("Punch-in", "Punch-in"), "broll": ("B-roll", None),
                     "split": ("Two camera views", None), "speed": ("Time-lapse", None)},
}
VOCAB_ALIASES = {"talking-head": ["talking-head"], "fastcut": ["fastcut"], "hands-on": ["hands-on"]}


def module():
    """library/buildrecord.py (VS_LIBRARY may point at another library folder, for tests)."""
    if "buildrecord" in sys.modules:
        return sys.modules["buildrecord"]
    lib = os.environ.get("VS_LIBRARY") or str(paths.KIT / "library")
    f = os.path.join(lib, "buildrecord.py")
    spec = importlib.util.spec_from_file_location("buildrecord", f)
    m = importlib.util.module_from_spec(spec)
    sys.modules["buildrecord"] = m
    try:
        spec.loader.exec_module(m)
    except Exception:
        sys.modules.pop("buildrecord", None)
        raise
    return m


def new(builder, inputs=()):
    """A Record for this render, or None (after one printed line) when buildrecord can't load."""
    try:
        return module().Record(builder, [str(p) for p in inputs if p])
    except Exception as e:
        print(f"  [build record] can't keep one ({e}); the render itself is fine", flush=True)
        return None


def layout(rec, vocab, key, t0, t1, detail=""):
    """One layout block, by the builder's own name for it (see FALLBACK)."""
    if rec is None:
        return
    try:
        BR = module()
        for v in VOCAB_ALIASES.get(vocab, [vocab]):
            table = getattr(BR, "VOCAB", {}).get(v)
            if table and key in table:
                rec.layout(t0, t1, v, key, detail)
                return
        fb = FALLBACK.get(vocab, {}).get(key, ("Graphic", None))
        if fb is None:
            return
        rec.block(t0, t1, fb[0], fb[1], detail, key, "scene")
    except Exception as e:
        try:
            rec.notes.append(f"layout {key}: {e}")
        except Exception:
            pass


def used(rec, clip, t0, t1, approx=False):
    """The raw seconds of a clip this render used (the Footage Log reads them to say what each video used)."""
    if rec is None or clip in (None, "gap"):
        return
    try:
        if hasattr(rec, "used"):
            rec.used(str(clip), t0, t1, approx=approx)
    except Exception as e:
        try:
            rec.notes.append(f"used {clip}: {e}")
        except Exception:
            pass


def save(rec, render, **kw):
    if rec is None:
        return None
    try:
        return rec.save(render, **kw)
    except Exception as e:
        print(f"  [build record] not saved ({e}); the render itself is fine", flush=True)
        return None
