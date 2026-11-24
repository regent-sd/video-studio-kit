"""The effects library (effects/fx.py) as the builders use it: effects go on the picture before captions.

    EFFECTS = ["spotlight@stronger", ("checklist", 12.0, 17.5), {"effect": "orbit", "at": "muscle+5"}]

Each item is an effect by name, at a word ("@word", "@word+4" for a length), at seconds ("@2.5-6"), or as
(name, start, end[, settings]). Times are reel time. effects/README.md lists the effects and what each needs.
"""
from __future__ import annotations

import sys

from . import paths

# The builders' skin names as the effects library knows them ("brand:<slug>" picks a brand).
SKIN_NAMES = {"dark": ["dark"], "brand": ["brand"]}


def _load():
    fx_dir = paths.KIT / "effects"
    if not (fx_dir / "fx.py").exists() and not (fx_dir / "core.py").exists():
        raise RuntimeError(f"the effects library isn't in this kit ({fx_dir}/fx.py)")
    if str(fx_dir) not in sys.path:
        sys.path.append(str(fx_dir))   # after the styles' own folders, so names can't clash
    mods = []
    for name in ("fx", "core"):
        try:
            mods.append(__import__(name))
        except Exception:
            pass
    for m in list(mods):
        sub = getattr(m, "core", None)
        if sub is not None:
            mods.append(sub)
    return mods


def _fn(name):
    for m in _load():
        f = getattr(m, name, None)
        if callable(f):
            return f, m
    raise RuntimeError(f"effects/fx.py has no {name}()")


def skin_name(skin, mod=None):
    if ":" in str(skin):          # "brand:<slug>": the effects library builds that brand's skin itself
        return skin
    want = SKIN_NAMES.get(skin, [skin])
    table = getattr(mod, "SKINS", None) if mod is not None else None
    if isinstance(table, dict):
        for n in want:
            if n in table:
                return n
    return want[0]


def render_with_effects(n, picture, captions, effects, out, words=None, audio=None, skin="dark"):
    """Frame builders (Fast Cut): picture(f) -> PIL frame without captions; captions(img, f) draws them.
    Writes `out` (silent): picture -> effects -> captions."""
    f, m = _fn("render_with_effects")
    return f(n, picture, captions, effects, str(out), words=words, audio=audio, skin=skin_name(skin, m))


def effects_pass(video, effects, words=None, audio=None, skin="brand", out=None):
    """Clip builders (Talking Head, Hands-On): effects on a joined picture before captions. Returns the new path."""
    f, m = _fn("effects_pass")
    return f(str(video), effects, words=words, audio=str(audio) if audio else None, skin=skin_name(skin, m),
             out=str(out) if out else None)


def applied():
    """Every effect window resolved in this run so far: [(name, start, end)] (for the build record)."""
    for name in ("core", "fx"):
        m = sys.modules.get(name)
        a = getattr(m, "APPLIED", None) if m else None
        if a is not None:
            return list(a)
    return []
