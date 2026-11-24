#!/usr/bin/env python3
"""Download the demo clips (free stock footage) onto this Mac and set them up as a demo shoot.

    .venv/bin/python demo/fetch_stock.py              # show the list and the total size, ask, then download
    .venv/bin/python demo/fetch_stock.py --yes        # don't ask
    .venv/bin/python demo/fetch_stock.py --dry-run    # check every link (HEAD requests only), download nothing
    .venv/bin/python demo/fetch_stock.py --manual     # print the pages and file names to download by hand
    .venv/bin/python demo/fetch_stock.py --list       # the clips, what each shows, and their licenses

Options:
  --out DIR     the shoot folder to fill (default: the newest '<date> Demo Shoot' in your content folder,
                or a new one named for today)
  --only a,b    only these clips (ids from clips.json)
  --pause S     seconds to wait between downloads (default 1)

The clips come from Pexels and Mixkit (demo/clips.json lists each one, its page, its creator and its
license). You download them yourself, under each site's license, onto your own Mac; the kit never ships them.
Files already there at the right size are skipped. CREDITS.txt in the shoot lists every clip's source and
license. Next: demo/make_narration.py, then demo/run_samples.py.
"""

from __future__ import annotations

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import demo_common as dc  # noqa: E402

DEAD = {401, 403, 404, 410, 451}
CAMERAS = ["Raw/Camera", "Raw/POV", "Raw/Phone", "Raw/Screen"]


class Dead(Exception):
    """The link answers, but there's no file there any more."""


class Failed(Exception):
    """The download didn't finish (network trouble, wrong kind of file, cut short)."""


def say(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------ links
def head(url: str, ua: str, timeout: float = 30) -> tuple[int, int, str, str]:
    """(status, size, content type, final url) from a HEAD request, following redirects."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": ua})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, int(r.headers.get("Content-Length") or 0), r.headers.get("Content-Type", ""), r.url
    except urllib.error.HTTPError as e:
        return e.code, 0, "", url
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, 0, str(getattr(e, "reason", e)), url


def download(url: str, dest: Path, ua: str, retries: int = 3) -> int:
    """Stream url to dest (via dest.part). Returns the bytes written. Raises Dead or Failed."""
    part = dest.with_name(dest.name + ".part")
    last = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=60) as r:
                ctype = r.headers.get("Content-Type", "")
                if not (ctype.startswith("video/") or "octet-stream" in ctype):
                    raise Dead(f"the link gives a {ctype or 'non-video'} page, not a video")
                total = int(r.headers.get("Content-Length") or 0)
                got, shown = 0, -1
                with open(part, "wb") as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        got += len(chunk)
                        pct = int(got * 100 / total) if total else -1
                        if pct != shown and (pct % 10 == 0 or pct < 0):
                            print(f"\r    {dc.mb(got)}" + (f" of {dc.mb(total)} ({pct}%)" if total else ""), end="", flush=True)
                            shown = pct
                print()
            if total and got != total:
                raise Failed(f"cut short: {got} of {total} bytes")
            if got == 0:
                raise Failed("the file was empty")
            part.replace(dest)
            return got
        except urllib.error.HTTPError as e:
            part.unlink(missing_ok=True)
            if e.code in DEAD:
                raise Dead(f"HTTP {e.code}")
            last = f"HTTP {e.code}"
        except Dead:
            part.unlink(missing_ok=True)
            raise
        except (Failed, urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            part.unlink(missing_ok=True)
            last = str(getattr(e, "reason", e))
        if attempt < retries:
            wait = 3 * attempt
            say(f"    trouble ({last}); trying again in {wait} s")
            time.sleep(wait)
    raise Failed(last or "unknown error")


def check_video(path: Path, clip: dict) -> str | None:
    """None if the file plays (ffprobe), else what's wrong. Skipped when ffprobe isn't installed."""
    info = dc.probe(path)
    if not dc.tool("ffprobe"):
        return None
    if not info.get("has_video"):
        return "ffprobe can't read a video stream in it"
    want = float(clip.get("duration_s") or 0)
    if want and abs(info["duration"] - want) > max(2.0, want * 0.15):
        return f"it's {info['duration']:.1f} s long, expected about {want:.0f} s"
    return None


# ------------------------------------------------------------------ the plan
def pick(clips: list[dict], only: str | None) -> list[dict]:
    if not only:
        return clips
    want = [s.strip() for s in only.split(",") if s.strip()]
    ids = {c["id"] for c in clips}
    bad = [w for w in want if w not in ids]
    if bad:
        raise SystemExit(f"No clip called {', '.join(bad)}. Clips: {', '.join(sorted(ids))}")
    return [c for c in clips if c["id"] in want]


def show_plan(shoot: Path, clips: list[dict]) -> list[dict]:
    todo = []
    say(f"Demo shoot: {shoot}")
    say(f"{'clip':<20} {'goes in':<12} {'size':>9}  {'from':<7} status")
    for c in clips:
        have = dc.have_clip(shoot, c)
        if have:
            note = dc.size_note(have, c)
            status = "already there" + (f" ({note}; kept)" if note else "")
        else:
            status = "to download"
            todo.append(c)
        say(f"{c['id']:<20} {c['camera']:<12} {dc.mb(c.get('bytes') or 0):>9}  {c['source']:<7} {status}")
    total = sum(int(c.get("bytes") or 0) for c in todo)
    say(f"{len(todo)} of {len(clips)} to download, {dc.mb(total)} in all.")
    return todo


def list_clips(data: dict):
    for c in data["clips"]:
        say(f"{c['id']}  ({c['camera']}, {c['width']}x{c['height']}, {c['duration_s']} s, {dc.mb(c['bytes'])})")
        say(f"    {c['shows']}")
        say(f"    '{c['title']}' by {c['creator']} - {c['page_url']}")
        say(f"    {c['license']} - {c['license_url']}")
    say("")
    for lic in data["licenses"].values():
        say(f"{lic['name']} ({lic['url']}): {lic['allows']}")
        for lim in lic["limits"]:
            say(f"  - {lim}")
        say(f"  {lic['fetching']}")


def manual(shoot: Path, todo: list[dict]):
    say("\nTo download them by hand, open each page, download the size given, and save it under the name shown:")
    for c in todo:
        say(f"\n  {c['id']}: {c['page_url']}")
        say(f"    pick the {c['width']}x{c['height']} file ({dc.mb(c['bytes'])}), or the closest size offered")
        say(f"    save as: {dc.clip_path(shoot, c)}")
    say("\nThen run this script again: it skips what's there and writes CREDITS.txt.")
    say("A different size of the same clip is fine; the script notes it and keeps it.")


def dry_run(clips: list[dict], ua: str) -> int:
    say("\nChecking every link (HEAD requests only, nothing is downloaded):")
    bad, total = 0, 0
    for c in clips:
        st, size, ctype, final = head(c["file_url"], ua)
        ok = st == 200 and (ctype.startswith("video/") or "octet-stream" in ctype)
        note = ""
        if ok and c.get("bytes") and size and size != c["bytes"]:
            note = f" (expected {dc.mb(c['bytes'])}: the site changed the file)"
        if ok:
            total += size
            say(f"  ok    {c['id']:<20} {dc.mb(size):>9}{note}")
            continue
        alt_ok = ""
        for alt in c.get("alt_urls") or []:
            ast, asize, actype, _ = head(alt, ua)
            if ast == 200 and (actype.startswith("video/") or "octet-stream" in actype):
                alt_ok = f"backup link works ({dc.mb(asize)})"
                total += asize
                break
        say(f"  {'BACKUP' if alt_ok else 'DEAD'}  {c['id']:<20} main link: {('HTTP ' + str(st)) if st else ctype or 'no answer'}"
            + (f"; {alt_ok}" if alt_ok else f"; get it by hand from {c['page_url']}"))
        if not alt_ok:
            bad += 1
    say(f"\n{len(clips) - bad} of {len(clips)} clips can be downloaded, {dc.mb(total)} in all.")
    return 1 if bad else 0


# ------------------------------------------------------------------ credits
def write_credits(shoot: Path, data: dict) -> Path:
    lines = [
        "DEMO SHOOT: where these clips came from",
        "",
        "These are free stock clips, downloaded onto this Mac by demo/fetch_stock.py from the video studio kit.",
        "You downloaded them yourself, under each site's license (below). Use them to try the styles and effects.",
        "Keep them on your Mac: don't share or sell the clips themselves, as they are. Finished videos made from",
        "them are yours to use under the same licenses. Credit isn't required; it's kind to credit the creators.",
        "",
        "CLIPS",
        "",
    ]
    for c in data["clips"]:
        have = dc.have_clip(shoot, c)
        where = f"{c['camera']}/{c['file']}"
        lines.append(f"{where}{'' if have else '   (not downloaded yet)'}")
        lines.append(f"  '{c['title']}' by {c['creator']} ({c['creator_url']})")
        lines.append(f"  {c['page_url']}")
        lines.append(f"  {c['license']}: {c['license_url']}")
        if c.get("voice"):
            lines.append(f"  make_narration.py adds the demo narration (computer speech) to this clip; the clip as downloaded is kept in {dc.STOCK_DIR}/{c['file']}.")
        lines.append("")
    lines += ["NARRATION", "",
              "Raw/Camera/voiceover.wav is computer speech of demo/narration.md, made on this Mac by demo/make_narration.py.", "",
              "LICENSES", ""]
    for lic in data["licenses"].values():
        lines.append(f"{lic['name']}  {lic['url']}  (terms: {lic['terms_url']})")
        lines.append(f"  {lic['allows']}")
        lines += [f"  - {x}" for x in lic["limits"]]
        lines.append("")
    lines.append("Read the license pages themselves before you publish anything; they are the rules, this is a summary.")
    p = shoot / "CREDITS.txt"
    p.write_text("\n".join(lines) + "\n")
    return p


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description="Download the demo clips into a demo shoot.")
    ap.add_argument("--yes", action="store_true", help="don't ask before downloading")
    ap.add_argument("--dry-run", action="store_true", help="check the links with HEAD requests; download nothing")
    ap.add_argument("--manual", action="store_true", help="print what to download by hand, and where to save it")
    ap.add_argument("--list", action="store_true", help="list the clips and their licenses")
    ap.add_argument("--out", help="the shoot folder (default: the newest '<date> Demo Shoot' in your content folder)")
    ap.add_argument("--only", help="only these clip ids, comma-separated")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between downloads (default 1)")
    a = ap.parse_args()

    data = dc.load_clips()
    ua = data.get("user_agent") or "video-studio-kit-demo/1.0"
    if a.list:
        list_clips(data)
        return 0
    clips = pick(data["clips"], a.only)
    shoot = dc.shoot_dir(a.out, create=False)
    todo = show_plan(shoot, clips)

    if a.dry_run:
        return dry_run(clips, ua)
    if a.manual:
        if todo:
            manual(shoot, todo)
        else:
            say("Nothing to download.")
        return 0

    if todo and not a.yes:
        hosts = sorted({c["source"] for c in todo})
        say(f"\nThese are free stock clips from {' and '.join(h.capitalize() for h in hosts)}. You download them yourself,")
        say("under each site's license, and they stay on this Mac (licenses: demo/README.md, or --list).")
        if not sys.stdin.isatty():
            say("Not asking without a terminal: run again with --yes to download.")
            return 1
        ans = input(f"Download {len(todo)} clip(s), {dc.mb(sum(c.get('bytes') or 0 for c in todo))}? [y/N] ").strip().lower()
        if ans not in {"y", "yes"}:
            say("Nothing downloaded.")
            return 1

    shoot.mkdir(parents=True, exist_ok=True)
    for cam in sorted({c["camera"] for c in data["clips"]} | set(CAMERAS)):
        (shoot / cam).mkdir(parents=True, exist_ok=True)
    (shoot / "Style Tests").mkdir(exist_ok=True)

    failed = []
    for i, c in enumerate(todo):
        dest = dc.clip_path(shoot, c)
        say(f"\n[{i + 1}/{len(todo)}] {c['id']}: '{c['title']}' by {c['creator']} -> {c['camera']}/{c['file']}")
        got, used, why = 0, None, []
        for url in [c["file_url"]] + list(c.get("alt_urls") or []):
            try:
                got = download(url, dest, ua)
                used = url
                break
            except (Dead, Failed) as e:
                why.append(f"{'main' if url == c['file_url'] else 'backup'} link: {e}")
                say(f"    {why[-1]}")
        if not used:
            failed.append((c, "; ".join(why)))
            continue
        bad = check_video(dest, c)
        if bad:
            dest.unlink(missing_ok=True)
            failed.append((c, f"downloaded, but {bad}"))
            say(f"    removed it: {bad}")
            continue
        if used != c["file_url"]:
            say(f"    got it from the backup link ({dc.mb(got)}; it may be a bigger size than listed).")
        elif c.get("bytes") and got != c["bytes"]:
            say(f"    note: {dc.mb(got)}, expected {dc.mb(c['bytes'])}. The site changed the file; it's fine to use.")
        else:
            say("    ok")
        if i < len(todo) - 1 and a.pause > 0:
            time.sleep(a.pause)

    credits = write_credits(shoot, data)
    say(f"\nWrote {credits}")
    if failed:
        say(f"\n{len(failed)} clip(s) didn't download:")
        for c, why in failed:
            say(f"  {c['id']}: {why}")
            say(f"    get it by hand: open {c['page_url']}, download it, and save it as {dc.clip_path(shoot, c)}")
            say("    (any similar clip saved under that name works too)")
        say("\nThe rest of the demo works without them.")
    say("\nNext: .venv/bin/python demo/make_narration.py   (adds the narration and its word times)")
    return 1 if failed and len(failed) == len(todo) else 0


if __name__ == "__main__":
    sys.exit(main())
