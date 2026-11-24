"""Studio: the front door of the video studio. review.py serves it; nothing here runs on its own.

Pages (all of them are studio.html; the page picks its tab from the address):
    /studio  /studio/edits  /studio/new  /studio/card/<id>  /studio/glossary
    /studio/classroom  /studio/ideas  /studio/guides[/<key>]  /studio/say
API:
    GET  /api/studio/home        what needs you: cards in progress, open notes, tracker
    GET  /api/studio/options     choices for the project card form
    GET  /api/studio/cards       every project card (short)
    GET  /api/studio/card?id=    one project card
    POST /api/studio/card        create (no id) or save (with id) a card
    GET  /api/studio/glossary    every named thing, built from the files that define it
    GET  /api/studio/classroom   the editing references in classroom/*.md (reels saved for how they're cut)
    GET  /api/studio/ideas       the content references in ideas/*.md (reels saved for what they say)
    GET  /api/studio/guides      the guides and READMEs the Guides tab can show
    GET  /api/studio/guide?key=  one of them, as HTML
    GET  /api/studio/sample.jpg?name=   an effect's contact sheet (effects/samples/<name>.jpg)

The only thing this module writes is cards/<id>.card.json inside the kit. Everything else is
read at request time from the files that already hold it (effects/catalog, the effects skill and
README, STYLES.md, brands/, the video tracker, the notes files, classroom/*.md, ideas/*.md, guides/*.md),
so there is nothing to keep in sync by hand. Standard library only.
"""
import ast
import html
import json
import os
import re
import threading
import unicodedata
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

HERE = Path(__file__).resolve().parent          # <kit>/review
STUDIO = HERE.parent                             # the kit
import sys  # noqa: E402
sys.path.insert(0, str(STUDIO / "lib"))
import studio_config as sc  # noqa: E402

CARDS = STUDIO / "cards"
CLASSROOM = STUDIO / "classroom"   # editing references: read when planning an edit
IDEAS = STUDIO / "ideas"           # content references: what to make and how to plan it; never an editing reference
GUIDES = STUDIO / "guides"
EFFECTS = STUDIO / "effects"
SKILLS = STUDIO / ".claude" / "skills"

# Brands come from brands/<slug>/brand.json and styles from STYLES.md, read each time (brand_choices, style_choices).
# These are used only when STYLES.md can't be read yet.
FALLBACK_STYLES = ["Fast Cut – Dark skin", "Fast Cut – Brand skin", "Talking Head Classic", "Hands-On Classic"]
ASK_ME = "Ask me"
OTHER = "Other"
CARD_STATUSES = ["new", "in progress", "in review", "approved"]
PLATFORMS = ["Instagram Reel", "TikTok", "YouTube Short", "YouTube", "Instagram Reel + YouTube", "Other"]

TEXT_LIMITS = {"title": 120, "brand_other": 80, "clips": 6000, "vision": 6000, "script": 12000, "length": 60,
               "must_keep": 4000, "must_avoid": 4000, "references": 4000}
LIST_LIMITS = {"shoots": (20, 120), "classroom": (40, 80), "effects": (60, 40)}
CARD_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,80}$")
NAME_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")
CARDS_LOCK = threading.Lock()
BODY_LIMIT = 256_000

CARD_ABOUT = ('Project card from the Studio page (/studio). Claude: when you are told "start the card <title>", read this card, '
              'guides/storytelling.md, rules/house-rules.md, the brand in brands/, the style in STYLES.md and the Glossary '
              '(/studio/glossary), then propose a plan before building. See CLAUDE.md and cards/README.md.')

# The pages the Guides tab can show: a guide is picked by key, never by a path from the page. "Start here" guides are
# the ones written for you; the rest explain how the tools work (written for Claude). Brand guides and style READMEs
# are added from brands/ and styles/ (guide_files).
GUIDE_FILES = [
    ("storytelling", "guides/storytelling.md", "Read this first: your rules for telling a story, with where each came from", True),
    ("house-rules", "rules/house-rules.md", "The standing rules Claude follows on every video", True),
    ("after-approval", "guides/after-approval.md", "What happens when you approve a video", True),
    ("what-to-say", "guides/what-to-say.md", "Every phrase Claude knows", True),
    ("glossary-words", "guides/glossary-words.md", "The studio's own words, and names given to new looks", True),
    ("start-here", "START-HERE.md", "One page for someone new to the kit", True),
    ("readme", "README.md", "What the kit is and what's in it", True),
    ("styles", "STYLES.md", "The named styles and how each is built", True),
    ("classroom-how", "classroom/README.md", "How a classroom card is written (reels saved for their editing)", True),
    ("ideas-how", "ideas/README.md", "How an idea card is written (reels saved for what they say)", True),
    ("cards-how", "cards/README.md", "How project cards are saved", True),
    ("claude", "CLAUDE.md", "Claude's instructions for this kit", False),
    ("effects-when", ".claude/skills/effects/SKILL.md", "When an effect fits a moment, and how many", False),
    ("effects", "effects/README.md", "The effects library: every effect and its settings", False),
    ("sound", "sound/README.md", "The sound-effects pass every video gets", False),
    ("review", "review/README.md", "Video Review: notes at exact moments", False),
    ("library", "library/README.md", "The Footage Log and the video tracker", False),
    ("assets", "assets/README.md", "The Asset Library: photos, logos and design files", False),
    ("walkthrough", "walkthrough/README.md", "Screen walkthrough videos", False),
    ("demo", "demo/README.md", "The demo: every style and effect on stock footage", False),
    ("install", "setup/INSTALL.md", "Installing the tools", False),
    ("sound-library", "setup/SOUND-LIBRARY.md", "Building a starter sound-effects library", False),
    ("rules-how", "rules/README.md", "How the house rules work", False),
    ("brands-how", "brands/README.md", "How a brand folder is set up", False),
]


def guide_files():
    """The fixed list, plus each brand's BRAND.md and VOICE.md and each style's README.md, as (key, path, about, mine)."""
    out = list(GUIDE_FILES)
    try:
        for slug in sc.list_brands():
            try:
                name = sc.brand(slug).get("name") or slug
            except (OSError, ValueError):
                name = slug
            out.append((f"brand-{slug}", f"brands/{slug}/BRAND.md", f"{name}: the brand guide", True))
            out.append((f"voice-{slug}", f"brands/{slug}/VOICE.md", f"{name}: how the brand sounds", True))
    except OSError:
        pass
    sd = STUDIO / "styles"
    if sd.is_dir():
        for f in sorted(sd.glob("*/README.md")):
            if NAME_ID.match(f.parent.name):
                out.append((f"style-{f.parent.name}", f"styles/{f.parent.name}/README.md",
                            f"The {f.parent.name} builder", False))
    return out


def guide_keys():
    return {k: (p, about) for k, p, about, _ in guide_files()}


def guide_by_path():
    return {p: k for k, p, _, _ in guide_files()}

KIND_FALLBACK = {"cards": "On top of you", "behind": "Behind you", "restyle": "You, restyled", "camera": "Camera and body tricks"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def read(p, default=""):
    try:
        return Path(p).read_text(errors="replace")
    except OSError:
        return default


# ---------------------------------------------------------------- markdown (a small, safe subset)

LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[a-z]?[.)])\s+(.*)$")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
RULE_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def slug(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def inline(s, link_for=None):
    """Escape a line of markdown and render code spans, links, bold and italics."""
    keep = []

    def stash(h):
        keep.append(h)
        return f"\x00{len(keep) - 1}\x00"

    s = str(s).replace("\x00", "")
    s = re.sub(r"`([^`]+)`", lambda m: stash("<code>" + html.escape(m.group(1)) + "</code>"), s)

    def link(m):
        text, url = m.group(1), m.group(2).strip()
        if re.match(r"^https?://", url):
            return stash(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">') + text + stash("</a>")
        key = link_for(url) if link_for else None
        if key:
            return stash(f'<a href="/studio/guides/{key}">') + text + stash("</a>")
        return text

    s = re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)", link, s)

    def bare(m):
        url = m.group(0)
        tail = ""
        while url and url[-1] in ".,;:!?'\"":
            tail, url = url[-1] + tail, url[:-1]
        return stash(f'<a href="{html.escape(url)}" target="_blank" rel="noopener">{html.escape(url)}</a>') + tail

    s = re.sub(r"https?://[^\s<>()\x00\"]+", bare, s)
    s = html.escape(s, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
    return re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], s)


def split_cells(line):
    """Cells of a markdown table row; a | inside `code` doesn't split."""
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, cur, code = [], "", False
    for ch in line:
        if ch == "`":
            code = not code
        if ch == "|" and not code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
    cells.append(cur.strip())
    return cells


def md_to_html(text, link_for=None):
    """Markdown to HTML for the Guides tab: headings, paragraphs, lists, tables, code, quotes, links.
    Every bit of text is escaped; only http(s) links and links to other guides become links."""
    lines = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").split("\n")
    out = []
    il = lambda s: inline(s, link_for)
    if lines and lines[0].strip() == "---":
        for j in range(1, min(len(lines), 80)):
            if lines[j].strip() == "---":
                fm, lines = lines[1:j], lines[j + 1:]
                desc = next((l.split(":", 1)[1].strip().strip('"') for l in fm if l.lower().startswith("description:")), "")
                if desc:
                    out.append('<p class="fm">' + il(desc) + "</p>")
                break
    para, lists = [], []

    def flush():
        if para:
            out.append("<p>" + il(" ".join(x.strip() for x in para)) + "</p>")
            para.clear()

    def close_lists(level=0):
        while len(lists) > level:
            out.append("</li></%s>" % lists.pop()[1])

    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            flush()
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if lists and not (j < n and (LIST_RE.match(lines[j]) or lines[j][:1] in (" ", "\t"))):
                close_lists()
            i = j
            continue
        if line.lstrip().startswith("```"):
            flush(); close_lists()
            body, i = [], i + 1
            while i < n and not lines[i].lstrip().startswith("```"):
                body.append(lines[i]); i += 1
            out.append("<pre><code>" + html.escape("\n".join(body)) + "</code></pre>")
            i += 1
            continue
        m = HEAD_RE.match(line)
        if m:
            flush(); close_lists()
            lv = len(m.group(1))
            out.append(f'<h{lv} id="{slug(m.group(2))}">{il(m.group(2))}</h{lv}>')
            i += 1
            continue
        if RULE_RE.match(line) and not para:
            close_lists()
            out.append("<hr>")
            i += 1
            continue
        if line.lstrip().startswith("|") and i + 1 < n and TABLE_SEP.match(lines[i + 1]):
            flush(); close_lists()
            head = split_cells(line)
            i += 2
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append(split_cells(lines[i])); i += 1
            t = ['<div class="tablewrap"><table><thead><tr>' + "".join(f"<th>{il(c)}</th>" for c in head) + "</tr></thead><tbody>"]
            for r in rows:
                t.append("<tr>" + "".join(f"<td>{il(c)}</td>" for c in r) + "</tr>")
            out.append("".join(t) + "</tbody></table></div>")
            continue
        if line.lstrip().startswith(">"):
            flush(); close_lists()
            q = []
            while i < n and lines[i].lstrip().startswith(">"):
                q.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            out.append("<blockquote><p>" + il(" ".join(q)) + "</p></blockquote>")
            continue
        m = LIST_RE.match(line)
        if m:
            flush()
            ind = len(m.group(1).expandtabs(4))
            mark = m.group(2)
            tag = "ol" if mark[0].isdigit() else "ul"
            while lists and ind < lists[-1][0]:
                out.append("</li></%s>" % lists.pop()[1])
            if lists and ind == lists[-1][0]:
                if lists[-1][1] != tag:
                    out.append("</li></%s>" % lists.pop()[1])
                    out.append(f"<{tag}><li>"); lists.append([ind, tag])
                else:
                    out.append("</li><li>")
            else:
                out.append(f"<{tag}><li>"); lists.append([ind, tag])
            if tag == "ol":
                out.append(f'<span class="mk">{html.escape(mark)}</span> ')
            out.append(il(m.group(3)))
            i += 1
            continue
        if lists and line[:1] in (" ", "\t"):
            out.append(" " + il(line.strip()))
            i += 1
            continue
        close_lists()
        para.append(line)
        i += 1
    flush(); close_lists()
    return "\n".join(out)


def guide_link_for(doc_rel):
    """For links inside a guide: a relative .md path that is another guide opens in the Guides tab."""
    base = Path(doc_rel).parent

    def f(url):
        url = url.split("#", 1)[0]
        if not url or "://" in url:
            return None
        try:
            rel = os.path.normpath((base / url).as_posix()).replace(os.sep, "/")
        except ValueError:
            return None
        by = guide_by_path()
        return by.get(rel) or by.get(url)
    return f


def first_heading(text, default):
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return re.sub(r"[`*]", "", m.group(1))
    return default


def guides_list():
    out = []
    for key, rel, about, mine in guide_files():
        p = STUDIO / rel
        title = first_heading(read(p), rel) if p.is_file() else rel
        if rel.endswith("SKILL.md"):
            title = "When to use an effect (/effects)"
        out.append({"key": key, "path": rel, "title": title, "about": about, "exists": p.is_file(), "new": mine})
    return {"guides": out}


def guide(key):
    keys = guide_keys()
    if key not in keys:
        raise ValueError("unknown guide")
    rel, about = keys[key]
    p = STUDIO / rel
    if not p.is_file():
        raise FileNotFoundError(rel)
    text = read(p)
    return {"key": key, "path": rel, "about": about, "title": first_heading(text, rel),
            "html": md_to_html(text, guide_link_for(rel)), "updated": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="minutes")}


# ---------------------------------------------------------------- project cards

def clean_text(v, limit, label):
    if v is None:
        return ""
    if not isinstance(v, (str, int, float)):
        raise ValueError(f"{label}: expected text")
    s = str(v).replace("\r\n", "\n").replace("\r", "\n")
    s = "".join(ch for ch in s if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cs")).strip()
    if len(s) > limit:
        raise ValueError(f"{label} is too long (at most {limit} characters)")
    return s


def clean_list(v, limits, label, pattern=None):
    count, each = limits
    if v in (None, ""):
        return []
    if not isinstance(v, list):
        raise ValueError(f"{label}: expected a list")
    if len(v) > count:
        raise ValueError(f"{label}: at most {count}")
    out = []
    for x in v:
        s = clean_text(x, each, label).replace("\n", " ")
        if pattern and not pattern.match(s):
            raise ValueError(f"{label}: '{s[:40]}' isn't a name the studio uses")
        if s and s not in out:
            out.append(s)
    return out


def card_path(card_id):
    if not isinstance(card_id, str) or not CARD_ID.match(card_id):
        raise ValueError("bad card name")
    p = (CARDS / f"{card_id}.card.json").resolve()
    if p.parent != CARDS.resolve():
        raise PermissionError("outside the cards folder")
    return p


def load_card(card_id):
    p = card_path(card_id)
    if not p.is_file():
        raise FileNotFoundError(f"no card called {card_id}")
    try:
        d = json.loads(p.read_text())
    except ValueError:
        raise ValueError(f"cards/{p.name} isn't valid JSON (fix it by hand or ask Claude)")
    if not isinstance(d, dict):
        raise ValueError(f"cards/{p.name} isn't a card")
    d["id"] = card_id
    return d


def brand_label(slug, other=""):
    if slug == OTHER:
        return other or OTHER
    try:
        return str(sc.brand(slug).get("name") or slug) if slug else ""
    except (OSError, ValueError):
        return slug


def card_summary(d):
    out = {k: d.get(k, "") for k in ("id", "title", "brand", "brand_other", "style", "status", "platform", "length",
                                     "shoots", "created", "updated")}
    out["brand_label"] = brand_label(out["brand"], out["brand_other"])
    return out


def list_cards():
    out = []
    if CARDS.is_dir():
        for f in CARDS.glob("*.card.json"):
            cid = f.name[: -len(".card.json")]
            if not CARD_ID.match(cid):
                continue
            try:
                out.append(card_summary(load_card(cid)))
            except (ValueError, OSError) as e:
                out.append({"id": cid, "title": cid, "status": "", "error": str(e)})
    out.sort(key=lambda c: c.get("updated") or c.get("created") or "", reverse=True)
    return out


def clean_card(body, old=None):
    """The card's fields, checked. old: the saved card, whose brand or style may still be kept after the brand
    folder or STYLES.md changed."""
    old = old or {}
    c = {}
    for k, lim in TEXT_LIMITS.items():
        c[k] = clean_text(body.get(k), lim, k.replace("_", " ").capitalize())
    if not c["title"]:
        raise ValueError("Give the edit a title")
    brands = [b["name"] for b in brand_choices()]
    styles = [x["name"] for x in style_choices()]
    for k, choices, label, default in (("brand", brands, "Brand", ""), ("style", styles, "Style", ASK_ME),
                                       ("platform", PLATFORMS, "Platform", ""), ("status", CARD_STATUSES, "Status", "new")):
        v = clean_text(body.get(k), 80, label)
        if v and v not in choices and v != old.get(k):
            raise ValueError(f"{label}: '{v[:40]}' isn't one of the choices")
        c[k] = v or default
    if c["brand"] != OTHER:
        c["brand_other"] = ""
    c["shoots"] = clean_list(body.get("shoots"), LIST_LIMITS["shoots"], "Shoots")
    if any("/" in s or "\\" in s for s in c["shoots"]):
        raise ValueError("Shoots: a shoot is a folder name, not a path")
    c["classroom"] = clean_list(body.get("classroom"), LIST_LIMITS["classroom"], "Classroom", NAME_ID)
    c["effects"] = clean_list(body.get("effects"), LIST_LIMITS["effects"], "Effects", NAME_ID)
    return c


def new_card_id(title):
    base = f"{datetime.now():%Y-%m-%d}-{(slug(title)[:48].strip('-') or 'edit')}"
    for k in range(1, 100):
        cid = base if k == 1 else f"{base}-{k}"
        if not card_path(cid).exists():
            return cid
    raise ValueError("too many cards with this title today")


def write_card(p, d):
    CARDS.mkdir(exist_ok=True)
    tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, p)


def save_card(body):
    """Create a card (no id) or save one (id). Returns (http code, card or error)."""
    with CARDS_LOCK:
        cid = body.get("id")
        c = clean_card(body, load_card(cid) if cid else None)
        if cid:
            old = load_card(cid)
            seen = body.get("seen_updated")
            if seen and old.get("updated") and seen != old.get("updated"):
                return 409, {"error": "This card changed since you opened it (Claude may have updated it). "
                                      "Reload to see the new version, then make your change again.", "card": old}
            created = old.get("created") or now()
            extra = {k: v for k, v in old.items() if k not in c and k not in ("about", "id", "created", "updated")}
        else:
            cid, created, extra = new_card_id(c["title"]), now(), {}
        order = ["title", "brand", "brand_other", "style", "status", "shoots", "clips", "vision", "script", "length",
                 "platform", "must_keep", "must_avoid", "classroom", "effects", "references"]
        d = {"about": CARD_ABOUT, "id": cid, **{k: c[k] for k in order}, **extra, "created": created, "updated": now()}
        write_card(card_path(cid), d)
        return 200, d


# ---------------------------------------------------------------- footage choices

def shoots(root):
    """The shoot folders in the content folder: every folder named "YYYY-MM-DD Title", newest first."""
    names = set()
    try:
        for d in Path(root).iterdir():
            if d.is_dir() and re.match(r"^\d{4}-\d{2}-\d{2} ", d.name):
                names.add(d.name)
    except OSError:
        pass
    return sorted(names, reverse=True)


def brand_choices():
    """[{name: slug, label, about}] for every brand folder (the default first), then Other."""
    out = []
    try:
        default = sc.load().get("default_brand") or ""
        for slug in sorted(sc.list_brands(), key=lambda x: (x != default, x)):
            try:
                b = sc.brand(slug)
            except (OSError, ValueError):
                continue
            about = str(b.get("about") or "")
            if slug == "example-brand":
                about = "The made-up brand the kit ships with. Say \"set up my brand\" to add yours."
            out.append({"name": slug, "label": str(b.get("name") or slug), "about": about[:160]})
    except OSError:
        pass
    out.append({"name": OTHER, "label": OTHER, "about": ""})
    return out


def style_choices():
    """[{name, about}]: each style in STYLES.md (Fast Cut once per skin), then Ask me."""
    entries = style_entries()
    styles = [e for e in entries if e["group"] == "style"]
    skins = [e for e in entries if e["group"] == "skin"]
    out = []
    for e in styles:
        mine = [k for k in skins if not k.get("style") or k.get("style") == e["name"]] if skins and "fast cut" in e["name"].lower() else []
        if mine:
            for k in mine:
                skin = k["name"]
                out.append({"name": f"{e['name']} – {skin}", "about": f"{e['about']} {skin}: {k['about']}".strip()})
        else:
            out.append({"name": e["name"], "about": e["about"]})
    if not out:
        out = [{"name": n, "about": ""} for n in FALLBACK_STYLES]
    out.append({"name": ASK_ME, "about": "Claude asks which style before editing. There's no default style."})
    return out


# ---------------------------------------------------------------- glossary

_AST_CACHE = {}


def module_consts(p, names=("NAME", "KIND", "ABOUT", "DUR", "PARAMS", "SAMPLE", "ALIASES", "PRESETS", "COMMAND_ALIASES")):
    """Top-level constants of a Python file, read with ast (the file is never run)."""
    try:
        st = p.stat()
    except OSError:
        return {}
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _AST_CACHE:
        return _AST_CACHE[key]
    out = {}
    try:
        tree = ast.parse(p.read_text(errors="replace"))
    except SyntaxError:
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            k = node.targets[0].id
            if k not in names:
                continue
            if k == "PARAMS":
                v = node.value
                if isinstance(v, ast.Call):
                    out[k] = [kw.arg for kw in v.keywords if kw.arg]
                elif isinstance(v, ast.Dict):
                    out[k] = [ast.literal_eval(x) for x in v.keys if isinstance(x, ast.Constant)]
                continue
            try:
                out[k] = ast.literal_eval(node.value)
            except (ValueError, SyntaxError, TypeError):
                pass
    _AST_CACHE[key] = out
    return out


def name_in(name, text):
    return re.search(r"(?<![a-z0-9-])" + re.escape(name) + r"(?![a-z0-9-])", text) is not None


def frontmatter_description(text):
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        if line.lower().startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def reel_cards(folder):
    """The reel cards in one folder (classroom/ or ideas/): same file format, two shelves."""
    out = []
    if not folder.is_dir():
        return out
    for f in sorted(folder.glob("*.md")):
        if f.name.lower() == "readme.md" or f.name.startswith("_"):
            continue
        text = read(f)
        title = first_heading(text, f.stem)
        fields, sections, cur, body = {}, [], None, []
        for line in text.splitlines():
            m = re.match(r"^##\s+(.+?)\s*$", line)
            if m:
                if cur:
                    sections.append((cur, "\n".join(body)))
                cur, body = m.group(1), []
                continue
            if cur is None:
                m = re.match(r"^\s*[-*]\s+\*\*(.+?):\*\*\s*(.*)$", line)
                if m:
                    fields[m.group(1).strip().lower()] = m.group(2).strip()
                continue
            body.append(line)
        if cur:
            sections.append((cur, "\n".join(body)))
        link = fields.get("link", "")
        url = link if re.match(r"^https?://\S+$", link) else ""
        led = next((b for h, b in sections if h.lower().startswith("what it led to")), "")
        out.append({
            "id": f.stem, "title": title, "file": f"{folder.name}/{f.name}",
            "creator": fields.get("creator", ""), "link": url, "link_note": "" if url else (link or "Link not recorded"),
            "added": fields.get("added", ""),
            "tags": [t.strip().lower() for t in fields.get("tags", "").split(",") if t.strip()],
            "sections": [{"title": h, "html": md_to_html(b, guide_link_for(f"{folder.name}/x.md"))} for h, b in sections if b.strip()],
            "led_to": re.findall(r"`/?([a-z0-9-]+)`", led),
            "text": re.sub(r"\s+", " ", text)[:4000],
        })
    out.sort(key=lambda e: (e["added"][:10] if re.match(r"^\d{4}-\d{2}-\d{2}", e["added"]) else "0000", e["title"]), reverse=True)
    return out


def classroom_entries():
    return reel_cards(CLASSROOM)


def shelf(entries):
    tags = Counter(t for e in entries for t in e["tags"])
    return {"entries": [{k: v for k, v in e.items() if k != "text"} | {"search": e["text"]} for e in entries],
            "tags": [t for t, _ in sorted(tags.items(), key=lambda x: (-x[1], x[0]))]}


def classroom():
    return shelf(classroom_entries())


def ideas():
    return shelf(reel_cards(IDEAS))


def effect_entries(root, tracker, classroom_list):
    cat = EFFECTS / "catalog"
    if not cat.is_dir():
        return []
    names = sorted(f.stem.replace("_", "-") for f in cat.glob("*.py") if not f.name.startswith("_"))
    init = module_consts(cat / "__init__.py")
    aliases = init.get("ALIASES") or {}
    presets = init.get("PRESETS") or {}
    cmd_aliases = init.get("COMMAND_ALIASES") or []
    readme = read(EFFECTS / "README.md")
    skill = read(SKILLS / "effects" / "SKILL.md")

    # kind headings as the README lists them
    kinds, cur, on = {}, None, False
    for line in readme.splitlines():
        if re.match(r"^##\s+The effects", line):
            on = True
            continue
        if on:
            m = re.match(r"^###\s+(.+?)\s*$", line)
            if m:
                cur = m.group(1)
                continue
            m = re.match(r"^\|\s*`([a-z0-9-]+)`\s*\|", line)
            if m and cur:
                kinds[m.group(1)] = cur

    # when each one fits, from the effects skill
    fits = {}
    part = skill.split("**When an effect earns its place.**", 1)
    if len(part) == 2:
        for line in part[1].split("**How many.**", 1)[0].splitlines():
            m = re.match(r"^\s*-\s+(.+?):\s+(.*)$", line)
            if not m:
                continue
            for tok in re.findall(r"`/?([a-z0-9-]+)[^`]*`", m.group(2)):
                n = aliases.get(tok, tok)
                if n in names and m.group(1) not in fits.setdefault(n, []):
                    fits[n].append(m.group(1))
    # the quiet effects for brands set to "restrained" in brand.json, as the effects skill lists them
    m = re.search(r"[Rr]estrained[^:\n]{0,80}:\s*([^\n]*?)\.(\s|$)", skill)
    restrained = {n for n in names if m and name_in(n, m.group(1))}
    m = re.search(r"tech-looking ones \(([^)]*)\)", skill)
    ask_first = {n for n in names if m and name_in(n, m.group(1))}

    # in review: named on an "in review" list in the skill or README, or its preview is in review in the tracker
    listed = set()
    for text in (skill, readme):
        for mm in re.finditer(r"in review", text, re.I):
            seg = re.split(r"[;()]|\.\s|\n\n", text[mm.end(): mm.end() + 900], maxsplit=1)[0]
            listed.update(n for n in names if name_in(n, seg))
    fx_status, fx_file = {}, {}     # effect previews (effects/make_previews.py: FX_<name>.mp4) the tracker lists
    for v in tracker.get("videos", []):
        m = re.search(r"(^|/)FX_([a-z0-9-]+)\.mp4$", v.get("file", ""))
        if m:
            fx_status[m.group(2)] = v.get("status", "")
            fx_file[m.group(2)] = v.get("file", "")

    samples = {}
    try:
        samples = json.loads(read(EFFECTS / "samples.json", "{}"))
    except ValueError:
        pass
    prev_dir = samples.get("out") or ""
    reels = {}
    for e in classroom_list:
        for tok in e["led_to"]:
            n = aliases.get(tok, tok)
            if n in names:
                reels.setdefault(n, [])
                if e["id"] not in [r["id"] for r in reels[n]]:
                    reels[n].append({"id": e["id"], "title": e["title"]})

    out = []
    for n in names:
        meta = module_consts(cat / (n.replace("-", "_") + ".py"))
        if n in listed:
            status, why = "in review", "On the in-review list in the effects skill and README"
        elif fx_status.get(n) == "in review":
            status, why = "in review", "Its preview is still 'in review' in the video tracker"
        else:
            status, why = "approved", "Not on any in-review list (effects README and skill)"
        prev_rel = fx_file.get(n) or (f"{prev_dir}/FX_{n}.mp4" if prev_dir else "")
        prev_ok = bool(prev_rel) and (Path(root) / prev_rel).is_file()
        also = []
        for a in cmd_aliases:
            if aliases.get(a) == n and (SKILLS / a / "SKILL.md").is_file():
                pre = presets.get(a) or {}
                also.append({"command": "/" + a,
                             "about": "the same effect" + (" with " + ", ".join(f"{k}={v}" for k, v in pre.items()) if pre else "")})
        sample = meta.get("SAMPLE") if isinstance(meta.get("SAMPLE"), dict) else {}
        out.append({
            "group": "effect", "name": n, "kind": kinds.get(n) or KIND_FALLBACK.get(meta.get("KIND", ""), "Effect"),
            "about": meta.get("ABOUT", ""), "length": meta.get("DUR"), "settings": meta.get("PARAMS") or [],
            "command": ("/" + n) if (SKILLS / n / "SKILL.md").is_file() else "",
            "also": also, "aliases": sorted(a for a, t in aliases.items() if t == n),
            "fits": fits.get(n, []), "restrained": n in restrained, "ask_first": n in ask_first,
            "status": status, "status_why": why,
            "preview": {"path": prev_rel, "exists": prev_ok},
            "sample": f"/api/studio/sample.jpg?name={n}" if (EFFECTS / "samples" / f"{n}.jpg").is_file() else "",
            "sample_note": sample.get("note", ""),
            "from": reels.get(n, []),
            "source": f"effects/catalog/{n.replace('-', '_')}.py",
        })
    return out


def style_entries():
    text = read(STUDIO / "STYLES.md")
    out = []
    for line in text.splitlines():
        # a row of the styles table: | **Name** | what it is | good for | built with |
        m = re.match(r"^\|\s*\*\*(.+?)\*\*\s*\|(.+)\|\s*$", line)
        if m:
            cells = split_cells("|" + m.group(2) + "|")
            if len(cells) < 2:
                continue
            out.append({"group": "style", "name": m.group(1).strip(), "kind": "Style", "about": cells[0],
                        "fits": [cells[1]] if cells[1] else [], "built_with": cells[2] if len(cells) > 2 else "",
                        "status": "approved", "status_why": "In STYLES.md, where only approved looks go", "source": "STYLES.md"})
    m = re.search(r"\*\*Skins\.\*\*(.*?)(?:\n\n|$)", text, re.S)
    if m:
        para = m.group(1)
        fit = {s.strip(): who.strip() for who, s in re.findall(r"([^;.]+?) gets the ([\w ]+?) skin", para)}
        for nm, desc in re.findall(r"\*\*([^*]+?)\*\*\s*\(([^)]+)\)", para):
            out.append({"group": "skin", "name": f"{nm} skin", "kind": "Fast Cut skin", "about": desc.strip(),
                        "fits": [fit[nm]] if nm in fit else [], "status": "approved",
                        "status_why": "Part of Fast Cut in STYLES.md", "source": "STYLES.md (Skins)"})
    m = re.search(r"^### Layouts\s*$(.*?)(?=^#{2,3} |\Z)", text, re.S | re.M)
    if m:
        for nm, desc in re.findall(r"^\d+\.\s+\*\*(.+?)\.?\*\*\s*(.*)$", m.group(1), re.M):
            out.append({"group": "layout", "name": nm.rstrip("."), "kind": "Fast Cut layout",
                        "about": desc.strip() or "(STYLES.md gives no description)", "status": "approved",
                        "status_why": "Part of Fast Cut in STYLES.md", "source": "STYLES.md (Fast Cut, Layouts)"})
    return out


def word_entries(statuses):
    """guides/glossary-words.md: the studio's own words and names given to looks made for one edit."""
    text = read(GUIDES / "glossary-words.md")
    out, section = [], ""
    for line in text.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            section = m.group(1)
            continue
        m = re.match(r"^\s*-\s+\*\*(.+?)\*\*\s*(\(([^)]*)\))?\s*:\s*(.*)$", line)
        if not m or not section:
            continue
        name, where, desc = m.group(1).strip(), (m.group(3) or "").strip(), m.group(4).strip()
        src = ""
        sm = re.search(r"\s*\(([^()]*\.(?:md|py|json)[^()]*)\)\s*$", desc)
        if sm:
            src, desc = sm.group(1), desc[: sm.start()].strip()
        st = re.search(r"Status:\s*(in review|approved)\.?", desc, re.I)
        low = section.lower()
        if st:
            status = st.group(1).lower()
            desc = (desc[: st.start()] + desc[st.end():]).strip()
        else:
            status = "in review" if "in review" in low else ""
        group = "status" if "status" in low else ("look" if "look" in low or "name" in low else "word")
        if group != "status":
            desc = desc[:1].upper() + desc[1:]
        out.append({"group": group, "name": name, "kind": section, "about": desc, "where": where,
                    "status": status, "status_why": "guides/glossary-words.md" if status else "",
                    "source": src or "guides/glossary-words.md"})
    have = {e["name"] for e in out if e["group"] == "status"}
    for s in statuses:
        if s not in have:
            out.append({"group": "status", "name": s, "kind": "Tracker statuses", "about": "(no description yet in guides/glossary-words.md)",
                        "status": "", "source": "review/review.py"})
    return out


def glossary(root, tracker, statuses):
    cl = classroom_entries()
    entries = []
    sk = read(SKILLS / "effects" / "SKILL.md")
    if sk:
        d = frontmatter_description(sk)
        entries.append({"group": "command", "name": "/effects", "kind": "Command", "command": "/effects",
                        "about": (d.split(". ", 1)[0] + ".") if d else "Lists every effect and the sampler.",
                        "status": "", "source": ".claude/skills/effects/SKILL.md"})
    entries += style_entries()
    entries += effect_entries(root, tracker, cl)
    entries += word_entries(statuses)
    for e in entries:
        e["about_html"] = inline(e.get("about") or "")
    counts = Counter(e["group"] for e in entries)
    return {"entries": entries, "counts": counts,
            "in_review": sum(1 for e in entries if e.get("status") == "in review"),
            "classroom": [{"id": e["id"], "title": e["title"]} for e in cl]}


# ---------------------------------------------------------------- home

def home(root, library, tracker):
    vids = library().get("videos", [])
    open_notes = sorted((v for v in vids if v.get("open")), key=lambda v: -v.get("mtime", 0))
    tr = tracker()
    tv = tr.get("videos", [])

    def item(v):
        f = v.get("file", "")
        return {"file": f, "title": v.get("title") or f.rsplit("/", 1)[-1], "shoot": v.get("shoot", ""),
                "kind": v.get("kind", ""), "status": v.get("status", ""), "brand": v.get("brand", ""),
                "platform": v.get("platform", ""), "posted_on": v.get("posted_on", ""),
                "effect_preview": bool(re.search(r"(^|/)FX_[a-z0-9-]+\.mp4$", f)) or "/Effects/" in f}
    groups = {s: [item(v) for v in tv if v.get("status") == s] for s in ("in review", "ready to post", "scheduled")}
    for g in groups.values():
        g.sort(key=lambda x: (x["shoot"], x["title"]), reverse=True)
    cards = list_cards()
    loop = ""
    try:
        loop = guide("after-approval")["html"]
    except (ValueError, OSError):
        pass
    owner = sc.owner("")
    return {
        "owner": owner,
        "assets": (STUDIO / "assets" / "browser" / "serve.py").is_file(),
        "rules_missing": not sc.rules_path().is_file(),
        "cards": cards,
        "cards_open": [c for c in cards if c.get("status") != "approved"],
        "open_notes": [{"path": v["path"], "name": v["name"], "folder": v["folder"], "open": v["open"],
                        "done": v.get("done", 0), "mtime": v.get("mtime", 0)} for v in open_notes],
        "tracker": groups,
        "counts": dict(Counter(v.get("status", "") for v in tv)),
        "tracker_missing": bool(tr.get("missing")),
        "loop_html": loop,
    }


def options(root):
    st = style_choices()
    cl = classroom_entries()
    fx = []
    cat = EFFECTS / "catalog"
    if cat.is_dir():
        fx = sorted(f.stem.replace("_", "-") for f in cat.glob("*.py") if not f.name.startswith("_"))
    return {"brands": brand_choices(), "styles": st, "statuses": CARD_STATUSES, "platforms": PLATFORMS,
            "shoots": shoots(root), "classroom": [{"id": e["id"], "title": e["title"]} for e in cl],
            "effects": fx, "limits": TEXT_LIMITS}


# ---------------------------------------------------------------- requests

def read_body(h):
    try:
        n = int(h.headers.get("Content-Length") or 0)
    except ValueError:
        raise ValueError("bad Content-Length")
    if n < 0 or n > BODY_LIMIT:
        raise ValueError("too much data")
    raw = h.rfile.read(n) if n else b"{}"
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        raise ValueError("not JSON")
    if not isinstance(d, dict):
        raise ValueError("expected a JSON object")
    return d


def handle(h, method, u, root, library, tracker, statuses):
    """One request under /studio or /api/studio/. Errors are raised for review.py's handler to report
    (ValueError 400, PermissionError 403, FileNotFoundError 404)."""
    path = u.path
    q = parse_qs(u.query)
    one = lambda k: (q.get(k) or [""])[0]
    if path == "/studio" or path.startswith("/studio/"):
        if method != "GET":
            raise ValueError("pages only answer GET")
        return h.send_bytes((HERE / "studio.html").read_bytes(), "text/html; charset=utf-8")
    api = path[len("/api/studio/"):]
    if method == "POST" and api != "card":
        raise ValueError("use GET")
    if api == "home":
        return h.send_json(home(root, library, tracker))
    if api == "options":
        return h.send_json(options(root))
    if api == "cards":
        return h.send_json({"cards": list_cards()})
    if api == "card":
        if method == "POST":
            code, d = save_card(read_body(h))
            return h.send_json(d, code)
        return h.send_json(load_card(one("id")))
    if api == "glossary":
        return h.send_json(glossary(root, tracker(), statuses))
    if api == "classroom":
        return h.send_json(classroom())
    if api == "ideas":
        return h.send_json(ideas())
    if api == "guides":
        return h.send_json(guides_list())
    if api == "guide":
        return h.send_json(guide(one("key")))
    if api == "sample.jpg":
        name = one("name")
        if not NAME_ID.match(name):
            raise ValueError("bad effect name")
        p = (EFFECTS / "samples" / f"{name}.jpg").resolve()
        if p.parent != (EFFECTS / "samples").resolve() or not p.is_file():
            raise FileNotFoundError(f"no sample for {name}")
        return h.send_bytes(p.read_bytes(), "image/jpeg", cache=False)
    h.send_json({"error": "not found"}, 404)
