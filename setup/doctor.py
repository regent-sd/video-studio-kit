#!/usr/bin/env python3
"""Check that everything the studio needs is installed and set up.

    .venv/bin/python setup/doctor.py          # a list: ready / missing / needs attention, with the fix
    .venv/bin/python setup/doctor.py --json   # the same as JSON (Claude reads this during setup)

It only looks. It never installs, downloads or changes anything.
Runs with any Python 3.9+, so it works before the studio's own Python exists.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
HOME = Path.home()
sys.path.insert(0, str(KIT / "lib"))

OK, MISSING, WARN, SKIP = "ready", "missing", "attention", "optional"
results: list[dict] = []


def add(group: str, name: str, status: str, detail: str = "", fix: str = "") -> None:
    results.append({"group": group, "name": name, "status": status, "detail": detail, "fix": fix})


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)


def which(name: str) -> str | None:
    return shutil.which(name)


def check_mac() -> None:
    g = "Mac"
    arm = platform.machine() == "arm64"
    add(g, "Apple Silicon", OK if arm else MISSING, platform.machine(),
        "" if arm else "The voice engine needs an M1 or newer Mac. Everything except the voice clone still works.")
    ver = platform.mac_ver()[0] or "?"
    try:
        major = int(ver.split(".")[0])
    except ValueError:
        major = 0
    add(g, "macOS 14 or later", OK if major >= 14 else WARN, ver, "" if major >= 14 else "Update macOS (System Settings → General → Software Update).")
    free = shutil.disk_usage(HOME).free / 1e9
    add(g, "Free disk", OK if free > 25 else WARN, f"{free:.0f} GB free", "" if free > 25 else "The tools and models need about 25 GB.")
    code, _ = run(["xcode-select", "-p"])
    add(g, "Xcode Command Line Tools", OK if code == 0 else MISSING, "", "" if code == 0 else "xcode-select --install")


def check_cli() -> None:
    g = "Command-line tools"
    add(g, "Homebrew", OK if which("brew") else MISSING, which("brew") or "", "" if which("brew") else "Install from https://brew.sh (you run it: it asks for your password).")
    ff = which("ffmpeg")
    if not ff:
        add(g, "ffmpeg-full", MISSING, "", "brew install ffmpeg-full, then put it first on PATH (setup/INSTALL.md, step 3)")
    else:
        _, out = run([ff, "-hide_banner", "-filters"])
        need = [f for f in ("drawtext", "rubberband", "loudnorm", "afftdn") if f" {f} " not in out]
        add(g, "ffmpeg-full first on PATH", OK if not need else WARN, ff,
            "" if not need else f"This ffmpeg lacks {', '.join(need)}. brew install ffmpeg-full and add export PATH=\"$(brew --prefix ffmpeg-full)/bin:$PATH\" to ~/.zshrc")
    add(g, "ffprobe", OK if which("ffprobe") else MISSING, "", "" if which("ffprobe") else "Comes with ffmpeg-full.")
    add(g, "whisper.cpp (whisper-cli)", OK if which("whisper-cli") else MISSING, "", "" if which("whisper-cli") else "brew install whisper.cpp")
    model = HOME / ".cache/whisper.cpp/ggml-base.en.bin"
    ok = model.exists() and model.stat().st_size > 100_000_000
    add(g, "whisper base.en model", OK if ok else MISSING, str(model).replace(str(HOME), "~"), "" if ok else "setup/INSTALL.md, step 4 (~148 MB download)")
    for tool, fix in (("rubberband", "brew install rubberband"), ("node", "brew install node"), ("jq", "brew install jq")):
        add(g, tool, OK if which(tool) else MISSING, "", "" if which(tool) else fix)
    add(g, "yt-dlp", OK if which("yt-dlp") else SKIP, "for saving reels to study", "" if which("yt-dlp") else "brew install yt-dlp (optional)")
    add(g, "swiftc", OK if which("swiftc") else MISSING, "", "" if which("swiftc") else "Comes with the Xcode Command Line Tools.")


def check_python() -> None:
    g = "Studio Python"
    py = KIT / ".venv/bin/python"
    if not py.exists():
        add(g, ".venv", MISSING, "", "python3.14 -m venv .venv && .venv/bin/pip install -r requirements.txt")
        return
    code, out = run([str(py), "-c", "import sys, PIL, numpy, scipy; print(sys.version.split()[0], PIL.__version__, numpy.__version__, scipy.__version__)"])
    add(g, ".venv with Pillow, numpy, scipy", OK if code == 0 else MISSING, out.splitlines()[-1] if out else "",
        "" if code == 0 else ".venv/bin/pip install -r requirements.txt")
    helpers = KIT / "effects/build_helpers.sh"
    if helpers.exists():
        bindir = Path(os.environ.get("EFFECTS_CACHE", KIT / "effects/cache")) / "bin"
        built = list(bindir.glob("*")) if bindir.exists() else []
        add(g, "Swift helpers for effects", OK if built else MISSING, f"{len(built)} built", "" if built else "bash effects/build_helpers.sh")


def check_claude() -> None:
    g = "Claude Code"
    add(g, "claude command", OK if which("claude") else WARN, which("claude") or "", "" if which("claude") else "Install Claude Code: https://claude.com/claude-code")
    skills = HOME / ".claude/skills"
    for s, fix in (("earshot", "setup/INSTALL.md, step 8"), ("real-sound", "setup/INSTALL.md, step 8"), ("real-sfx", "setup/INSTALL.md, step 9")):
        p = skills / s
        add(g, f"skill: {s}", OK if (p / "SKILL.md").exists() else MISSING, "", "" if (p / "SKILL.md").exists() else fix)
    try:
        cfg = json.loads((HOME / ".claude.json").read_text())
    except (OSError, ValueError):
        cfg = {}
    mcp = cfg.get("mcpServers") or {}
    add(g, "Earshot MCP server", OK if "earshot" in mcp else MISSING, "", "" if "earshot" in mcp else "You run: claude mcp add earshot ... (setup/INSTALL.md, step 8)")
    plugins = set()
    for f in (HOME / ".claude/settings.json", HOME / ".claude/plugins/installed_plugins.json"):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        plugins |= set((d.get("enabledPlugins") or {}).keys()) | set((d.get("plugins") or {}).keys())
    for name, fix in (("hyperframes", "/plugin marketplace add heygen-com/hyperframes, then install hyperframes"),
                      ("chrome-devtools-mcp", "/plugin → install chrome-devtools-mcp from the official marketplace")):
        have = any(p.split("@")[0] == name for p in plugins)
        add(g, f"plugin: {name}", OK if have else MISSING, "", "" if have else fix)
    have_remotion = any("remotion" in p for p in plugins) or any((skills).glob("remotion*"))
    add(g, "Remotion skills", OK if have_remotion else SKIP, "for product reels", "" if have_remotion else "https://www.remotion.dev/docs/ai (optional)")
    earshot_py = HOME / "tools/earshot/.venv/bin/python"
    add(g, "Earshot install", OK if earshot_py.exists() else MISSING, "~/tools/earshot", "" if earshot_py.exists() else "setup/INSTALL.md, step 8")
    rs = skills / "real-sfx/config.json"
    libs = []
    try:
        libs = (json.loads(rs.read_text()).get("libraries") or [])
    except (OSError, ValueError):
        pass
    add(g, "Real SFX sound library", OK if libs else MISSING, f"{len(libs)} libraries", "" if libs else "setup/SOUND-LIBRARY.md")


def check_voice() -> None:
    g = "Voice"
    app = Path("/Applications/VoiceStudio.app")
    add(g, "VoiceStudio app", OK if app.exists() else SKIP, "", "" if app.exists() else "setup/VOICE-STUDIO.md (optional until you want voiceovers)")
    try:
        import studio_config as sc
        v = sc.voice()
    except Exception:
        v = {}
    api = v.get("api") or "http://127.0.0.1:3900"
    health = None
    try:
        with urllib.request.urlopen(api.rstrip("/") + "/health", timeout=3) as r:
            health = json.loads(r.read().decode())
    except Exception:
        pass
    if app.exists():
        add(g, "VoiceStudio running", OK if health else WARN, json.dumps(health) if health else api, "" if health else "Open the VoiceStudio app.")
    pid = v.get("profile_id")
    add(g, "Voice clone in studio.json", OK if pid else SKIP, v.get("name") or "", "" if pid else "Make your clone in VoiceStudio, then add its profile id (setup/VOICE-STUDIO.md, step 5)")


def check_studio() -> None:
    g = "Your studio"
    try:
        import studio_config as sc
    except Exception as e:
        add(g, "lib/studio_config.py", MISSING, str(e))
        return
    add(g, "studio.json", OK if sc.has_settings() else MISSING, "", "" if sc.has_settings() else "Say \"set up my studio\" (or copy studio.example.json to studio.json)")
    cfg = sc.load()
    cr = Path(cfg["content_root"])
    add(g, "Content folder", OK if cr.exists() else MISSING, str(cr).replace(str(HOME), "~"), "" if cr.exists() else f"mkdir -p \"{cr}\"")
    if "Mobile Documents" in str(cr) or str(cr).startswith(str(HOME / "Documents")) or str(cr).startswith(str(HOME / "Desktop")):
        add(g, "Content folder outside iCloud", WARN, "", "Documents and Desktop may sync to iCloud, which evicts big files mid-build. ~/Movies is a safe place.")
    if str(KIT).startswith(str(HOME / "Documents")) or str(KIT).startswith(str(HOME / "Desktop")):
        add(g, "Kit folder outside iCloud", WARN, str(KIT), "Move the kit to ~/Developer or another folder iCloud doesn't sync; node_modules and git hang in synced folders.")
    try:
        b = sc.brand()
        add(g, "Default brand", OK if b["slug"] != "example-brand" else WARN, b["name"], "" if b["slug"] != "example-brand" else "Still the example brand. Say \"set up my brand\".")
    except Exception as e:
        add(g, "Default brand", MISSING, str(e), "Say \"set up my brand\"")
    add(g, "House rules", OK if sc.rules_path().exists() else MISSING, "", "" if sc.rules_path().exists() else "Say \"set up my studio\": it asks whether to adopt the starter rules or start clean.")
    sl = Path(cfg["sound_library"])
    n = sum(1 for _ in sl.rglob("*") if _.suffix.lower() in {".wav", ".mp3", ".aif", ".aiff", ".flac"}) if sl.exists() else 0
    add(g, "Sound library", OK if n else MISSING, f"{n} sounds in {str(sl).replace(str(HOME), '~')}", "" if n else "setup/SOUND-LIBRARY.md")
    roots = cfg.get("asset_roots") or []
    if roots:
        missing = [r for r in roots if not Path(r).exists()]
        cat = Path(cfg["asset_library_dir"]) / "asset-catalog.json"
        add(g, "Asset Library", OK if (not missing and cat.exists()) else WARN,
            f"{len(roots)} folder(s)" + (f", {len(missing)} not found" if missing else ""),
            "" if (not missing and cat.exists()) else ".venv/bin/python assets/catalog.py scan (assets/README.md)")
    else:
        add(g, "Asset Library", SKIP, "no asset_roots in studio.json", "Optional: list your photo/logo folders in asset_roots (assets/README.md)")
    rig = KIT / "walkthrough/rig/node_modules"
    if (KIT / "walkthrough/rig/package.json").exists():
        add(g, "Walkthrough recorder", OK if rig.exists() else SKIP, "", "" if rig.exists() else "cd walkthrough/rig && npm install (only for product walkthroughs)")
    chrome = Path("/Applications/Google Chrome.app").exists()
    add(g, "Google Chrome", OK if chrome else SKIP, "", "" if chrome else "Needed only for product walkthroughs.")


def main() -> int:
    for f in (check_mac, check_cli, check_python, check_claude, check_voice, check_studio):
        try:
            f()
        except Exception as e:  # a broken check shouldn't hide the others
            add(f.__name__, "check failed", WARN, str(e))
    if "--json" in sys.argv:
        print(json.dumps(results, indent=1))
        return 0
    mark = {OK: "✓", MISSING: "✗", WARN: "!", SKIP: "·"}
    group = None
    for r in results:
        if r["group"] != group:
            group = r["group"]
            print(f"\n{group}")
        line = f"  {mark[r['status']]} {r['name']}"
        if r["detail"]:
            line += f"  ({r['detail']})"
        print(line)
        if r["fix"] and r["status"] != OK:
            print(f"      → {r['fix']}")
    counts = {s: sum(1 for r in results if r["status"] == s) for s in (OK, MISSING, WARN, SKIP)}
    print(f"\n{counts[OK]} ready, {counts[MISSING]} missing, {counts[WARN]} need attention, {counts[SKIP]} optional not set up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
