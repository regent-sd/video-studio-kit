# Demo shoot

The kit ships no footage. This folder gets you some anyway, so you can try every style and effect on day one, before you've filmed anything: it downloads a small set of free stock clips onto your Mac, sets them up as a normal shoot, adds a narration track so there's speech, and renders the style samples and effect previews from them.

The clips stay on your Mac. You download them yourself, from the stock sites, under each site's license. They never go in git.

## What's in this folder

| File | What it is |
|---|---|
| `clips.json` | The 14 clips: what each shows, which camera folder it goes in, its page, its direct file link, its creator and license, its size, length and resolution, and which styles and effects it suits. |
| `fetch_stock.py` | Downloads the clips into a demo shoot. Shows the list and the total size first and asks. Skips what's already there. |
| `narration.md` | The demo script (about 35 s, written to match the clips) and a shot list of which clip goes with each line. |
| `make_narration.py` | Turns the script into speech, gets the word times with whisper.cpp, and gives the talking take its sound. |
| `run_samples.py` | Renders the style samples and the effect previews from the demo shoot. |
| `demo_common.py` | Shared helpers for the three scripts. |

## Run it

```
.venv/bin/python demo/fetch_stock.py          # about 163 MB; it asks first (--yes to skip the question)
.venv/bin/python demo/make_narration.py       # a few seconds
.venv/bin/python demo/run_samples.py          # the styles' contact sheets, then a preview per effect (a while)
```

Or tell Claude: **"set up the demo shoot"** or **"make the demo samples"**.

Useful options:

- `fetch_stock.py --dry-run` checks every link with a HEAD request and prints the sizes. Nothing is downloaded.
- `fetch_stock.py --list` lists the clips, their creators and the license terms.
- `fetch_stock.py --manual` prints each clip's page and the exact file name and folder to save it under, if you'd rather download by hand. Run the script again afterwards: it skips what's there and writes the credits.
- `fetch_stock.py --only talking-head,hands-wheel` gets just those.
- `make_narration.py --voice "Daniel" --rate 170` picks another macOS voice (`say -v '?'` lists them).
- `run_samples.py --brand my-brand` renders in your brand's colours and fonts. `--effects-only --only spotlight,orbit --sheet-only` is a quick first look.

## What you get

```
<content folder>/<today> Demo Shoot/
  Raw/Camera/   talking-head.mp4 (with the narration as its sound), talking-head-green.mp4, hands-wheel.mp4,
                hands-kneading.mp4, hands-carving.mp4, glaze-pour.mp4, cups-detail.mp4, shelves.mp4,
                tea-pour.mp4, town-aerial.mp4, voiceover.wav, and a .words.txt beside each file with speech
  Raw/POV/      pov-walk.mp4
  Raw/Phone/    workout.mp4, phone-scroll.mp4
  Raw/Screen/   laptop-typing.mp4 (camera footage of a laptop; your real screen recordings go here)
  Style Tests/Samples/   one contact sheet per style and skin
  Style Tests/Effects/   FX_<effect>.mp4 for each effect, and contact.jpg
  .stock/       the talking take as downloaded (silent); make_narration.py starts from it each time
  CREDITS.txt   every clip's title, creator, page and license
```

The scripts find the newest `<date> Demo Shoot` folder by themselves, so you can run them on different days. `--out` (fetch) and `--shoot` (the other two) point them at another folder.

The story is a small pottery studio: the walk in, a talking take, clay on the wheel, carving, glazing, the finished cups, orders on the laptop and a cup of tea. The workout and phone clips are there for the styles that use them.

**Stock clips have no speech.** `make_narration.py` makes `voiceover.wav` with macOS `say` (or your VoiceStudio voice, if `studio.json` has `voice.profile_id`; if VoiceStudio isn't open it falls back to `say`), transcribes it, and lays it onto the talking take, so captions, voice cuts and word-timed effects have words. The man's lips won't match the computer voice. That's expected in a demo. The narration is Claude's wording, not yours, so don't post it as yours.

To log the demo clips like real footage, say **"log new footage"** after fetching. Delete the demo shoot folder whenever you like; nothing else depends on it.

## The clips

| Clip | Shows | Folder | Size | Source |
|---|---|---|---|---|
| `talking-head` | A man talking to the camera, vertical, 41 s | Camera | 14.4 MB | Pexels, MART PRODUCTION |
| `talking-head-green` | A man talking head-on on a green background, 16 s | Camera | 49.8 MB | Mixkit |
| `hands-wheel` | Hands shaping a bowl on a pottery wheel, vertical | Camera | 8.6 MB | Pexels, Mikhail Nilov |
| `hands-kneading` | Hands kneading clay on a studio table | Camera | 14.5 MB | Pexels, Yaroslav Shuraev |
| `hands-carving` | Hands carving detail into a clay pot, vertical | Camera | 12.2 MB | Pexels, KoolShooters |
| `glaze-pour` | White glaze poured over a plate | Camera | 12.3 MB | Pexels, KoolShooters |
| `cups-detail` | Finished handmade cups, close up, vertical | Camera | 2.1 MB | Pexels, KoolShooters |
| `shelves` | Bowls and plates on studio shelves, no people | Camera | 5.0 MB | Pexels, Yaroslav Shuraev |
| `tea-pour` | Tea poured into a ceramic cup, vertical | Camera | 5.3 MB | Pexels, Ivan S |
| `town-aerial` | Aerial view of a small town in winter | Camera | 13.5 MB | Pexels, EJ Merl |
| `workout` | Push-ups with dumbbells, vertical | Phone | 5.5 MB | Pexels, Julia Larson |
| `pov-walk` | First-person walk along a sidewalk | POV | 11.6 MB | Pexels, Kelly |
| `phone-scroll` | A hand scrolling on a phone, vertical | Phone | 4.7 MB | Pexels, RDNE Stock project |
| `laptop-typing` | Hands typing on a laptop, vertical | Screen | 3.2 MB | Pexels, Cup of Couple |

All are 1080p (1080×1920, 1920×1080 or 2048×1080), 6–41 s long, 162.7 MB in all. They were picked from their descriptions to have no logos or readable brands. Glance at them before you use one in anything public.

**If a link dies.** The fetcher tries each clip's backup link (the site's own download link, which may be a bigger size), then tells you which clips it couldn't get, with the page to get them from by hand. The demo works without any one clip. To swap a clip for another, edit its entry in `clips.json`: keep `file` and `camera`, change the links, and set `bytes` to the new file's size (or `0`).

## Licenses

Read the license pages themselves before you publish anything. In short:

**Pexels License** (13 clips), https://www.pexels.com/license/ — free to use, commercial use included, no credit required, and you may edit the clips. Not allowed: showing identifiable people in a bad light or an offensive way; selling unaltered copies (prints, products); suggesting that the people or brands in a clip endorse your product; redistributing or selling the clips on other stock or wallpaper sites; using a clip as part of a trademark or business name.

**Mixkit Stock Video Free License** (1 clip), https://mixkit.co/license/#videoFree and the terms at https://mixkit.co/terms/ — free for commercial and non-commercial projects, no credit required. Use the clip inside your own work; don't hand out or sell the clip itself, and don't use it to build a competing stock service. Only clips marked "Free License" may be used commercially (this one is). You must be 18 or over to use Mixkit.

**Downloading by script.** Both sites' terms forbid bulk or mass downloading by robots or scripts. The fetcher downloads one short, fixed list, once, when you ask, one file at a time with a pause between. If you'd rather not use a script at all, `--manual` gives you the pages to download from by hand.

This is why the kit doesn't include the clips: each person downloads their own copy under the site's license. Don't commit them, share them as files, or upload them anywhere as they are. Videos you make from them are yours to post under those licenses. Credit isn't required, but `CREDITS.txt` has what you need if you want to give it.

## Needs

- Python (the kit's `.venv`), `ffmpeg` and `ffprobe`, and an internet connection for the download.
- `whisper-cli` with the model at `~/.cache/whisper.cpp/ggml-base.en.bin` (setup installs both). Another model: set `"whisper_model"` in `studio.json`.
- macOS `say` (built in), or VoiceStudio for your own voice (`setup/VOICE-STUDIO.md`).
- `styles/make_samples.py` and `effects/make_previews.py` for `run_samples.py`. If one isn't there, it says so and runs the other.
