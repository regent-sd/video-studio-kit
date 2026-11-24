#!/usr/bin/env python3
"""Start a product reel (the Remotion template in walkthrough/product-reel) in your work folder,
dressed in a brand.

    .venv/bin/python walkthrough/rig/new_reel.py launch-reel [--brand my-brand] [--wordmark "Mossy"]
    .venv/bin/python walkthrough/rig/new_reel.py launch-reel --theme-only     # redo the brand after changing brand.json

Copies the template to <work>/reels/<name>/ (the kit's copy stays clean: your voiceover, music,
clips and fonts never go into the kit), writes src/theme.json from brands/<brand>/brand.json, and
copies the brand's logo and fonts into public/. Then:

    cd <work>/reels/<name> && npm install && npx remotion studio
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
sys.path.insert(0, str(HERE))
import studio_config as sc  # noqa: E402
import brandcss  # noqa: E402

TEMPLATE = HERE.parent / "product-reel"
ROLES = ("title", "heading", "body")


def write_theme(project: Path, b: dict, wordmark: str | None):
    pub = project / "public"
    (pub / "clips").mkdir(parents=True, exist_ok=True)
    logo = ""
    src = sc.logo(b)
    if src:
        shutil.copy(src, pub / f"logo{src.suffix.lower()}")
        logo = f"logo{src.suffix.lower()}"
    files = brandcss.font_files(b, pub / "fonts")
    colors = {r: sc.hex_color(b, r) for r in ("background", "surface", "text", "muted", "accent", "highlight",
                                              "dark", "dark_surface", "on_dark")}
    colors["on_accent"] = brandcss.on(b, "accent")
    fonts = {}
    for role in ROLES:
        fam, weight, _ = brandcss.font_family(b, role)
        fonts[role] = {"family": fam.split(",", 1)[1].strip(), "file": f"fonts/{files[role]}", "weight": weight}
    theme = {"_about": "Written by walkthrough/rig/new_reel.py from brands/<brand>/brand.json. Run it again with "
                       "--theme-only after changing the brand.",
             "brand": b.get("slug"), "wordmark": wordmark or b.get("name", ""), "logo": logo,
             "colors": colors, "fonts": fonts}
    (project / "src" / "theme.json").write_text(json.dumps(theme, indent=2) + "\n")
    return theme


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--brand")
    ap.add_argument("--wordmark", help="the product name shown when the brand has no logo")
    ap.add_argument("--theme-only", action="store_true")
    a = ap.parse_args()
    work = Path((sc.get("walkthrough") or {}).get("work_dir") or "~/Movies/Walkthroughs").expanduser()
    project = work / "reels" / a.name
    if a.theme_only:
        if not (project / "src").exists():
            sys.exit(f"No reel at {project}. Start one without --theme-only first.")
    else:
        if project.exists():
            sys.exit(f"{project} already exists. Use --theme-only to redo its brand, or pick another name.")
        shutil.copytree(TEMPLATE, project, ignore=shutil.ignore_patterns("node_modules", "out", ".DS_Store"))
    b = sc.brand(a.brand)
    t = write_theme(project, b, a.wordmark)
    print(f"reel: {project}\n  brand {t['brand']}, logo: {t['logo'] or 'none (wordmark ' + repr(t['wordmark']) + ')'}, "
          f"fonts: {', '.join(t['fonts'][r]['file'] for r in ROLES)}")
    if not a.theme_only:
        print(f"next: cd \"{project}\" && npm install && npx remotion studio")


if __name__ == "__main__":
    main()
