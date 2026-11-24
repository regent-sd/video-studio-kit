# Install the tools

Everything the studio uses, in the order to install it. You don't have to run any of this by hand: open Claude Code in the kit folder and say **"set up my studio"**. Claude works through this page step by step, checks what's already there (`setup/doctor.py`), and **asks before every download**, saying what it is, where it comes from and how big it is.

If you'd rather do a step yourself, each one has the commands, and a prompt you can paste to Claude instead.

**Needs:** a Mac with Apple Silicon (M1 or newer), macOS 14 or later, about **25 GB free** (most of it the voice model and sound tools), and Claude Code. Intel Macs can't run the voice engine.

## What gets installed

| Tool | What it's for | Size | License |
|---|---|---|---|
| Xcode Command Line Tools | git, and compiling the small Swift helpers some effects use | ~1 GB | Apple |
| Homebrew | installs the rest | small | BSD-2 |
| ffmpeg-full | every cut, mix and export | ~200 MB | LGPL/GPL |
| whisper.cpp + base.en model | transcripts with word times | ~150 MB | MIT |
| Python 3.14 + Pillow, numpy, scipy | the builders, effects and review pages | ~300 MB | PSF / open source |
| rubberband | time-stretching sound to fit picture | small | GPL |
| Node.js | the walkthrough recorder, HyperFrames, Remotion | ~100 MB | MIT |
| Google Chrome | the walkthrough recorder drives it | — | Google |
| Earshot | lets Claude "listen": judges, compares and checks sound | ~2 GB with models | MIT |
| Real SFX skill | places real recorded sound effects on the right frames | small | MIT (sounds CC0) |
| HyperFrames plugin + CLI | HTML-to-video: title cards, walkthrough films | ~300 MB with its headless Chrome | see its repo |
| Playwright | drives Chrome to record walkthrough takes | ~20 MB | Apache-2.0 |
| Remotion | React-to-video: product reels | ~250 MB per reel project | **Remotion license** (below) |
| Chrome DevTools plugin | records web pages as video | small | Apache-2.0 |
| VoiceStudio + VoxCPM2 | your voice clone, on your Mac | ~7 GB | AGPL-3.0 app, Apache-2.0 model |

**Remotion's license:** free for individuals, non-profits and companies of up to 3 people. Bigger companies need a company license. Check https://www.remotion.dev/license before you use it for a business. Everything else above is free to use commercially, but read each license if you plan to sell what you make with it.

---

## 1. Xcode Command Line Tools

```bash
xcode-select -p || xcode-select --install
```

A window opens; click Install. (Prompt: *"Check the Xcode command line tools and install them if they're missing."*)

## 2. Homebrew

Check first: `brew --version`. If it's missing, the install command is on https://brew.sh. It asks for your Mac password, so **you** run it in Terminal, not Claude. Then follow its "Next steps" to add brew to your PATH.

## 3. Command-line tools

```bash
brew install ffmpeg-full whisper.cpp python@3.14 rubberband node jq yt-dlp
```

`ffmpeg-full` is "keg-only": it doesn't replace any other ffmpeg until you put it first on your PATH. Add this line to `~/.zshrc`, then open a new Terminal:

```bash
export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
```

Check: `ffmpeg -hide_banner -filters | grep -E 'drawtext|rubberband|loudnorm'` should list all three.

`yt-dlp` is optional: it saves a reel you want to study for the Classroom shelf.

(Prompt: *"Install ffmpeg-full, whisper.cpp, python 3.14, rubberband, node, jq and yt-dlp with Homebrew, and put ffmpeg-full first on my PATH."*)

## 4. The transcription model

whisper.cpp needs one model file (~148 MB) from its official Hugging Face page:

```bash
mkdir -p ~/.cache/whisper.cpp
curl -L -o ~/.cache/whisper.cpp/ggml-base.en.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
```

Check: `whisper-cli -h` runs, and the file is about 148 MB.

## 5. The studio's Python

From the kit folder:

```bash
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Every studio command then runs as `.venv/bin/python <script>`. The venv keeps the studio working even when Homebrew upgrades its own Python later.

## 6. Swift helpers for the effects

A few effects find people and faces in the frame with Apple's Vision framework. Build their small helpers once:

```bash
bash effects/build_helpers.sh
```

## 7. Claude Code plugins

In Claude Code, type `/plugin` and install:

- **chrome-devtools-mcp** from the official marketplace (records web pages as video).
- **hyperframes**: add the marketplace `heygen-com/hyperframes` (`/plugin marketplace add heygen-com/hyperframes`), then install `hyperframes`.
- **Remotion skills**: search the plugin list for Remotion, or follow https://www.remotion.dev/docs/ai for the current install command.

Restart Claude Code afterwards so the new tools load.

## 8. Earshot (so Claude can judge sound)

Claude can't hear. Earshot describes, compares and measures sound so it can check a mix, pick a sound effect, or catch a clipped word.

```bash
mkdir -p ~/tools
git clone https://github.com/Leonxlnx/earshot ~/tools/earshot
cd ~/tools/earshot
python3.11 -m venv .venv 2>/dev/null || python3.14 -m venv .venv
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -e ".[mcp]"
.venv/bin/python -m earshot doctor --fetch      # downloads its two models (~1.1 GB)
mkdir -p ~/.claude/skills
ln -s ~/tools/earshot/skills/earshot ~/.claude/skills/earshot
ln -s ~/tools/earshot/skills/real-sound ~/.claude/skills/real-sound
```

Keep it in `~/tools`, not in iCloud-synced Documents. Then register it with Claude Code. This changes your Claude settings, so **you** run it:

```bash
claude mcp add earshot --scope user -e EARSHOT_THREADS=3 -- ~/tools/earshot/.venv/bin/python -m earshot mcp
```

## 9. Real SFX (places real sound effects)

```bash
git clone https://github.com/Clipwing/skills ~/tools/clipwing-skills
cp -R ~/tools/clipwing-skills/skills/real-sfx ~/.claude/skills/real-sfx
```

It needs a sound library to pick from. `setup/SOUND-LIBRARY.md` builds a free starter library and points Real SFX at it.

## 10. The walkthrough and product-reel tools

Only if you'll make product walkthrough videos (`walkthrough/README.md`):

```bash
cd walkthrough/rig && npm install          # Playwright (~20 MB)
npx --yes hyperframes@0.9.40 --help        # HyperFrames CLI (~110 MB, plus ~200 MB of headless Chrome on first render)
```

The recorder drives your installed Google Chrome. Without Chrome, `npx playwright install chromium` gets its own (~350 MB).

Product reels (Remotion) install per reel: `walkthrough/rig/new_reel.py` copies the template into your work folder, then `npm install` there (Remotion, React, TypeScript, ~250 MB). See `walkthrough/product-reel/README.md`.

## 11. VoiceStudio and your voice clone

Its own guide: `setup/VOICE-STUDIO.md`. You make the clone yourself in the VoiceStudio app (it records you), then Claude uses it.

## 12. Check everything

```bash
.venv/bin/python setup/doctor.py
```

It lists each tool as ready, missing or needs attention, with the fix. Run it any time something stops working.
