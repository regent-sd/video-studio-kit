"""The effects. One module per effect: catalog/<name>.py (hyphens in the name become underscores).

Each module sets
  NAME    "spotlight"
  KIND    "cards" (on top of you) | "behind" (between you and the room) | "restyle" (you, redrawn) | "camera" (moves, copies, cuts)
  ABOUT   one line for the list
  DUR     default length in seconds when only a start is given
  PARAMS  settings and their defaults (text, colours, numbers...). Numbers on screen must be real: default to none.
  NEEDS   optional, e.g. {"words"} or {"plate"}
  render(c) -> PIL RGB image (c is core.Ctx)
"""
import importlib, os

ALIASES = {
    "press-front": "news", "newspaper": "news", "orbit-ring": "orbit", "toggles": "apple-toggles",
    "glass": "glass-widgets", "widgets": "glass-widgets", "checklist": "todo", "impact": "impact-frame",
    "ascii": "code-body", "clones": "clone-row", "dust": "blow-away", "vertigo": "dolly-zoom",
    "pullback": "pull-back", "greenscreen": "green-screen", "cover": "cover-story", "magazine": "cover-story",
    "chart": "chart-grow", "headlines": "headline-wall", "doodle": "doodle-boil", "ransom": "paper-cut",
    "phone": "phone-mockup", "prompt": "ui-world", "camcorder": "digital-zoom", "zoom-cut": "zoom-through",
}
# an alias can also bring its own settings (a look the effect is often asked for by that name)
PRESETS = {"checklist": {"style": "compact"}}
# aliases that get their own slash command (common names for the same effect)
COMMAND_ALIASES = ["checklist", "vertigo"]

# The four kinds, in the order the README and `fx.py list` show them.
KIND_ORDER = ["cards", "behind", "restyle", "camera"]
KIND_HEADINGS = {"cards": "On top of you", "behind": "Behind you (uses the cutout)", "restyle": "You, restyled",
                 "camera": "Camera and body tricks"}

# Effects that work as a transition: put the window across a cut in an edit (effects go on the edited picture, before
# captions) and the cut is hidden at this share of the window. make_previews.py shows them over a cut between two clips.
TRANSITIONS = {"zoom-through": 0.5, "paper-tear": 0.3, "blade-slice": 0.8, "letter-dive": 0.5}

# Quiet effects for a brand set to restrained ("effects": {"restrained": true} in its brand.json).
QUIET = ["paper-tear", "news", "letter-dive", "rack-focus", "typewriter", "sketch-words"]
# Tech-looking effects: only when you ask for one.
ASK_FIRST = ["code-body", "timeline", "live-cursor", "predict-keys"]
HERE = os.path.dirname(os.path.abspath(__file__))

def names():
    return sorted(f[:-3].replace("_", "-") for f in os.listdir(HERE) if f.endswith(".py") and not f.startswith("_"))

def get(name):
    name = ALIASES.get(name, name)
    try:
        m = importlib.import_module("catalog." + name.replace("-", "_"))
    except ModuleNotFoundError:
        raise SystemExit(f"no effect called '{name}'. Effects: {', '.join(names())}")
    for k, v in dict(KIND="cards", ABOUT="", DUR=3.0, PARAMS={}, NEEDS=set()).items():
        if not hasattr(m, k): setattr(m, k, v)
    if not hasattr(m, "NAME"): m.NAME = name
    return m
