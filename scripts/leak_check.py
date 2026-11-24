#!/usr/bin/env python3
"""Leak check: stop personal details, private paths and media from going into the repo.

    python3 scripts/leak_check.py            # check every file in the kit
    python3 scripts/leak_check.py --staged   # only what's staged for commit (the git hook runs this)

What it looks for:
  - words on your private list: ~/.config/video-studio-kit/leak-terms.txt (one per line,
    case-insensitive; # starts a comment). The list lives outside the repo, so the repo
    never names what it's hiding. Put your own name, brands, people, places and products in it.
  - home-folder paths (/Users/<name>/...), cloud-drive mount paths, email addresses,
    links to individual social posts
  - video, audio, photo and voice files, and any file over 1 MB

Exit code 1 if it finds anything. Install the git hook with: python3 scripts/leak_check.py --install-hook
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERMS_FILE = Path(os.environ.get("LEAK_TERMS", Path.home() / ".config/video-studio-kit/leak-terms.txt"))
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "work", "cache", "out", "recordings"}
MEDIA = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".wav", ".mp3", ".m4a", ".aac", ".aif", ".aiff",
         ".flac", ".ovsvoice", ".jpg", ".jpeg", ".heic", ".psd", ".gif"}
# Small images the kit itself draws (icons, the example logo) may be committed if listed here.
ALLOWED_MEDIA = {"brands/example-brand/logo.png"}
MAX_BYTES = 1_000_000

PATTERNS = [
    ("home path", re.compile(r"/Users/(?!<|\{|\$|you\b|name\b|USER\b|me\b)[A-Za-z0-9._-]+")),
    ("cloud drive path", re.compile(r"CloudStorage|GoogleDrive-|Mobile Documents/com~apple")),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+-]+@(?!example\.(com|org)\b|anthropic\.com\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("social post link", re.compile(r"(instagram\.com/(reel|reels|p)/|tiktok\.com/@[^/\s]+/video/|youtube\.com/shorts/)")),
]
# Lines that are allowed to match a pattern (placeholders in docs).
ALLOW_LINE = re.compile(r"noreply@anthropic\.com|you@example\.com")


def load_terms() -> list[str]:
    if not TERMS_FILE.exists():
        return []
    out = []
    for line in TERMS_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def term_regex(terms: list[str]):
    if not terms:
        return None
    parts = []
    for t in terms:
        e = re.escape(t)
        # whole-word for plain words so "Chrisp" or "metric" don't trip a short term
        if re.fullmatch(r"[A-Za-z0-9 ]+", t):
            e = r"(?<![A-Za-z0-9])" + e + r"(?![A-Za-z0-9])"
        parts.append(e)
    return re.compile("|".join(parts), re.IGNORECASE)


def files_to_check(staged: bool) -> list[Path]:
    if staged:
        r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                           cwd=ROOT, capture_output=True, text=True, check=True)
        return [ROOT / p for p in r.stdout.splitlines() if p]
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".nosync")]
        for f in filenames:
            out.append(Path(dirpath) / f)
    return out


def check(staged: bool = False) -> list[str]:
    rx = term_regex(load_terms())
    problems = []
    for p in files_to_check(staged):
        if not p.exists():
            continue
        rel = p.relative_to(ROOT).as_posix()
        if rel in {"scripts/leak_check.py"}:
            continue
        if rx and rx.search(rel):
            problems.append(f"{rel}: file name has a private word ({rx.search(rel).group(0)!r})")
        if p.suffix.lower() in MEDIA and rel not in ALLOWED_MEDIA:
            problems.append(f"{rel}: media file ({p.suffix}) — media never goes in the repo")
            continue
        size = p.stat().st_size
        if size > MAX_BYTES and rel not in ALLOWED_MEDIA:
            problems.append(f"{rel}: {size // 1024} KB, over the 1 MB limit")
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            if p.suffix.lower() not in {".png", ".ico", ".woff", ".woff2", ".pyc"}:
                problems.append(f"{rel}: binary file — check it's meant to be here")
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if ALLOW_LINE.search(line):
                continue
            if rx:
                m = rx.search(line)
                if m:
                    problems.append(f"{rel}:{n}: private word {m.group(0)!r}")
            for name, pat in PATTERNS:
                m = pat.search(line)
                if m:
                    problems.append(f"{rel}:{n}: {name} {m.group(0)!r}")
    return problems


def install_hook() -> None:
    hook = ROOT / ".git" / "hooks" / "pre-commit"
    if not hook.parent.exists():
        sys.exit("No .git folder here. Run 'git init' first.")
    hook.write_text('#!/bin/sh\nexec python3 "$(git rev-parse --show-toplevel)/scripts/leak_check.py" --staged\n')
    hook.chmod(0o755)
    print(f"Installed {hook.relative_to(ROOT)}. Every commit is checked now.")


def main() -> int:
    if "--install-hook" in sys.argv:
        install_hook()
        return 0
    staged = "--staged" in sys.argv
    if not TERMS_FILE.exists():
        print(f"note: no private word list at {TERMS_FILE}; checking paths, emails and media only.")
    problems = check(staged)
    if problems:
        print(f"Leak check: {len(problems)} problem(s)")
        for p in problems:
            print("  " + p)
        return 1
    print("Leak check: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
