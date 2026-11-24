# Walkthrough videos

Narrated how-to videos of your own software: a web app, or an iPhone app in the Simulator. You write a short script; the voiceover is made in your voice clone; a scripted browser take clicks through the app in time with each line; then the film gets a title card, step labels, captions, click sounds and an end card, and is checked before anyone sees it.

It works on any product. The kit ships a tiny made-up app, **Mossy** (a plant-watering list), so the whole thing runs before you point it at your own.

Say **"make a walkthrough of <topic>"** or type **`/walkthrough-video <topic>`**, and Claude runs the steps below.

## What's in this folder

| Path | What it is |
|---|---|
| `rig/recorder.mjs` | The recorder: drives the app with a visible cursor, captures sharp frames, and keeps a timeline of when each narration line starts. |
| `rig/lib.mjs` | Settings, the safety checks (local or test host only), sign-in, work folders. |
| `rig/takes/` | One take script per video. `example.mjs` records the demo app. |
| `rig/explore.mjs` | Screenshot plus accessibility snapshot of any screen, for writing a take's selectors. |
| `rig/serve.mjs` | Serves `demo-app/` on 127.0.0.1:5199. |
| `rig/gen_voice.py` | The voiceover, one clip per line: your clone in VoiceStudio, or a Mac voice (`--say`) until you have one. |
| `rig/build_film.py` | Builds the film (a HyperFrames project) from the take and the voice, and renders it with `--render`. |
| `rig/check_film.py` | Contact sheets of every few seconds, loudness, dead air and black frames. |
| `rig/import_recording.py` | Brings in a recording made elsewhere (iOS Simulator, QuickTime) so it can be finished the same way. |
| `rig/new_reel.py` | Starts a product reel from `product-reel/` in your brand. |
| `rig/brandcss.py` | Brand colours and fonts for the films and reels. |
| `scripts/` | Narration scripts, one per video. `example.md` shows the format. |
| `films/` | Film specs, one per video: title, step labels, punch-ins, end line. |
| `demo-app/` | Mossy, the made-up demo app. Nothing is saved; a reload resets it. |
| `product-reel/` | A Remotion template for a short vertical product reel ([its README](product-reel/README.md)). |
| `PHONE.md` | iPhone apps from the iOS Simulator, and phone-shaped web recordings. |

Scripts, takes and film specs are text and live here. Everything heavy goes to your **work folder** (`walkthrough.work_dir` in `studio.json`, default `~/Movies/Walkthroughs`), never into the kit:

```
<work folder>/
  voice/<name>/        one WAV per narration line + manifest.json
  recordings/<name>/   the take (<name>.mp4) + timeline.json
  films/<name>/        the HyperFrames project build_film.py writes
  out/<name>.mp4       the finished film, with <name>.srt captions next to it
  checks/<name>/       contact sheets from check_film.py
  explore/             screenshots and snapshots from explore.mjs
  reels/<name>/        product reels started with new_reel.py
```

Keep the work folder out of iCloud-synced folders (`~/Documents`, `~/Desktop`). A two-minute take writes about 6,000 frames (around 1 GB) while it records; those go to `~/Library/Caches/video-studio-kit/walkthroughs/` and are deleted once the MP4 is made.

## Set it up (once)

The kit's setup (`setup/INSTALL.md`) installs Node, Google Chrome, ffmpeg and the HyperFrames plugin. Then:

1. **The recorder's one package.** In `walkthrough/rig/`, run `npm install`. It installs Playwright 1.65 (about 20 MB). The recorder drives your installed Google Chrome, so no browser download is needed. Without Chrome, run `npx playwright install chromium` (about 350 MB) and set `"browser_channel": ""`.
2. **HyperFrames** renders the films. The first `npx --yes hyperframes@0.9.40 ...` downloads that version (about 110 MB) into npm's cache and its own headless Chrome (about 200 MB) into `~/.cache/hyperframes`; later runs reuse it. The version is pinned in `walkthrough.hyperframes_version`.
3. **Your voice clone** (optional at first): `setup/VOICE-STUDIO.md`. Until then, `gen_voice.py --say` uses a Mac voice so you can time and test everything.
4. **Settings.** Add a `walkthrough` block to `studio.json` (all optional; these are the defaults):

```json
"walkthrough": {
  "work_dir": "~/Movies/Walkthroughs",
  "base_url": "http://127.0.0.1:5199",
  "test_hosts": [],
  "app_env_file": "",
  "app_env_require": {},
  "login": null,
  "browser_channel": "chrome",
  "timezone": "",
  "hyperframes_version": "0.9.40"
}
```

| Setting | What it does |
|---|---|
| `base_url` | Where the app runs. Must be localhost, a `*.localhost` or `*.test` name, or a host in `test_hosts`. `WALKTHROUGH_BASE=...` overrides it for one run. |
| `test_hosts` | Hosted test copies you allow, by name. The name must have a test label (`staging.`, `dev.`, `test.`, `qa.`, `sandbox.`, `preview.`, `demo.`). |
| `app_env_file`, `app_env_require` | Optional extra lock: the app's own env file must point at its test backend. `{"DATABASE_URL": "my-dev-project"}` means that value must contain `my-dev-project`, or the recorder refuses to start. Values are never printed. |
| `login` | Optional sign-in for the demo account: `{"path": "/login", "email": "demo@example.com", "password_env": "DEMO_PASSWORD"}`, plus `email_selector`, `password_selector`, `submit_selector` if the defaults don't match. The password comes from that environment variable or the app's env file, never from a kit file. |
| `browser_channel` | `"chrome"` (installed Google Chrome) or `""` (Playwright's Chromium). |
| `timezone` | e.g. `"America/Chicago"`, so dates on screen match the demo data. |

Try it on the demo app:

```bash
cd walkthrough/rig && npm install
node serve.mjs &                                                   # Mossy on 127.0.0.1:5199
../../.venv/bin/python gen_voice.py ../scripts/example.md --say    # stand-in voice
node takes/example.mjs                                             # the take
../../.venv/bin/python build_film.py ../films/example.film.json --render
../../.venv/bin/python check_film.py ~/Movies/Walkthroughs/out/example.mp4
```

## What to say to Claude

| Say | What happens |
|---|---|
| "make a walkthrough of <topic>" or `/walkthrough-video <topic>` | The whole playbook below. Claude shows you the script before recording and the finished MP4 before anything is published. |
| "re-record walkthrough <name>" | New take on the current app, same script and voice; renders under the same file name. |
| "redo lines 3 and 5 of <name>" | `gen_voice.py ... --only 3,5`, then a new take (the timing shifts a little). |
| "make the <name> walkthrough phone-shaped" | A `--phone` take and a 1080x1920 film (`PHONE.md`). |
| "make a product reel for <product>" | `new_reel.py`, then the reel README. |

## Make one, step by step

Use `example` as the template: `scripts/example.md`, `rig/takes/example.mjs`, `films/example.film.json`.

### 1. Plan it

- One task per video, start to finish: "add a plant", not "everything about plants". Aim for 1:00 to 2:30.
- Know who it's for and what they can do at the end.
- List the screens in order, and what has to be on screen first (demo data, a starting page).

### 2. Start the app and look at the screens

- Run a **local or test copy** of your app with fake data (see Guardrails). Never your live account.
- `node rig/explore.mjs <path> <name>` saves a screenshot and an accessibility snapshot of a screen to `<work>/explore/`. Write the take's selectors from the snapshot: roles and names (`button "Add plant"`) survive redesigns better than CSS classes.

### 3. Write the script

`scripts/<name>.md`, in this format:

```markdown
say: Mossy = Mossy          (optional: how to say a word; captions keep the written one)

## 1. Intro
[screen] The plant list.
- Here's how to add a plant to Mossy, and keep track of when it needs water.

## 2. Add a plant
[screen] Add plant → Name → Room → Save.
- Click Add plant.
- Type its name, pick the room, and set how often it needs water.
```

- Each `## N. Title` is a scene. Each `- line` is one voice clip, and the take does that line's actions while it plays.
- Short, plain sentences. Use the **exact labels** on screen, so viewers can find them.
- Open with what the video shows. Close by saying where to get help.
- Spell things the way they should sound ("7 a.m.", "press 1"). If the voice says your product's name wrong, add a `say:` line.
- **Show the script to the owner before recording.** The voice only ever reads approved scripts.

### 4. Get the demo data ready

- Fake people, fake companies, fake numbers. Nothing from a real customer.
- Reset it before and after every take, so takes start the same and nothing leaks into the next video. If your app has a seed or reset script, use it; if you write one, scope it to the demo account only and make it refuse anything else (the `app_env_require` check is the same idea).
- Anything that sends email, texts or pushes: the local copy should have no keys for those. In the take, **hover** buttons like "Send invite" instead of clicking them.

### 5. Make the voice

```bash
.venv/bin/python walkthrough/rig/gen_voice.py walkthrough/scripts/<name>.md
```

- It makes one clip per line in `<work>/voice/<name>/` and a `manifest.json` with each line's length.
- With your clone it asks VoiceStudio for each scene in one go (one line per sentence, so the delivery flows) and cuts the take at the pauses (`--mode scene`). If a cut lands in the wrong pause it redoes that scene line by line. `--mode line` asks for each line on its own.
- Every line is transcribed back and compared with the script. Lines marked `CHECK` came out wrong: reword them, or redo those scenes with `--only 2,5 --seed <another>`.
- More energy: pass a lively clip of you with its exact words, `--ref-audio clip.wav --ref-text "..."`, and `--clean` to take its room sound out. `setup/VOICE-STUDIO.md` has the details.
- `--say` uses a Mac voice. It's for timing and drafts only; re-make the voice with the clone before publishing.
- **A person listens to the voice before anything is published.** Claude can't hear it.

### 6. Write and record the take

`rig/takes/<name>.mjs`. Copy `example.mjs`:

```js
const rec = await Recorder.start({ name: "<name>" });   // reads voice/<name>/manifest.json
await page.goto(`${BASE}/start`);                        // setup is not recorded
await rec.rolling();                                     // capture starts here
await rec.line(1, 1, async (r) => { await r.hover(page.getByRole("heading", { name: "Your plants" })); });
await rec.line(2, 1, async (r) => { await r.click(page.getByRole("button", { name: "Add plant" })); });
await rec.finish();
```

- `rec.line(scene, line, actions)` runs the actions while that line plays, then holds until the clip ends. Options: `{ lead: 250 }` ms before acting, `{ after: 0.45 }` s of quiet after the line.
- Actions: `r.click(locator)`, `r.hover(locator)`, `r.type(locator, text, { delay })`, `r.setValue(locator, value)`, `r.select(locator, label)` (a native select), `r.choose(trigger, option)` (a custom dropdown), `r.glide(x, y)`, `r.drag(from, to)`, `r.scroll(dy)`, `r.wait(ms)`.
- Wrap waits for page loads and "Saved" messages in `r.cutStart()` / `r.cutEnd()`: that stretch is cut out of the video and the later lines move up.
- Do all setup before `rec.rolling()`. End with `rec.finish()`; in the `catch`, `rec.fail(err)` saves a screenshot of where it broke.
- Run `node rig/takes/<name>.mjs --dry` first (3 s per line if there's no voice yet), then for real. The real run writes `<work>/recordings/<name>/` (the MP4 and `timeline.json`).
- `--phone` (if the take passes the shape through, as the example does) records 1080x1920. See `PHONE.md`.

### 7. Build and render the film

`films/<name>.film.json`:

```json
{
  "name": "<name>",
  "brand": "my-brand",
  "title": "Add a plant and keep it watered",
  "kicker": "Mossy walkthrough · 1",
  "steps": { "2": "Add a plant", "3": "Mark it watered" },
  "end_line": "Questions? Reply to any email from us.",
  "punch": [{ "scene": 3, "line": 1, "delay": 0.4, "hold": 2.2, "scale": 1.5 }]
}
```

| Field | What it does |
|---|---|
| `brand` | Colours, fonts and logo from `brands/<brand>/brand.json` (default: your default brand). |
| `wordmark` | The product name on the cards when the brand has no logo. |
| `steps` | A numbered label that slides in when that scene starts. |
| `punch` | Zooms in after that line's last click, toward where it clicked (or `"origin": [x, y]`). |
| `captions` | `true` (default) burns captions in; an `.srt` is always written. `"caption_position": "top"` if the app shows something important at the bottom. |
| `click_sound` | A file, or a path inside your sound library. Default: the first recorded "click" in the sound library, else a soft tick. |
| `music`, `music_db` | Optional licensed track (each video gets its own) and its level under the voice. |

```bash
.venv/bin/python walkthrough/rig/build_film.py walkthrough/films/<name>.film.json --render
```

It writes `<work>/films/<name>/`, runs `hyperframes check`, and renders `<work>/out/<name>.mp4` (1920x1080 or 1080x1920, voice at about -16 LUFS, about -14 LUFS overall). Without `--render` it prints the two commands to run yourself.

### 8. Check it

```bash
.venv/bin/python walkthrough/rig/check_film.py <work>/out/<name>.mp4
```

- Look at **every** contact sheet: the cursor goes where the voice says, nothing private or real is on screen, captions don't hide what's being clicked, the step labels match.
- It flags dead air (over 1.5 s of silence), black frames and loudness out of range.
- Listen to the whole film, or have the owner do it. The voice, the clicks and any music must be right before it goes anywhere.
- Then show the MP4 to the owner. To take notes in Video Review, put it in a shoot folder's `Style Tests/` or `Finished/YouTube/`.

### 9. Publish

- Publishing is the owner's call. Ask first, every time, and say exactly what goes where.
- Upload it wherever your help pages live (your site, your help desk, YouTube). If you script the upload: refuse to overwrite an existing file, check you're pointed at the right project, read keys from the environment (never print them, never write them into the kit), and print how to undo it.
- Give the owner the backout: how to unpublish the page and remove the one file.
- Check it as a signed-out visitor: the page reads right and the video plays.

### 10. Clean up

Reset the demo data, stop the local app, and keep the script, take and film spec (they're how you re-record it later).

## Changing a published one

- **Text around it:** edit the page; the video doesn't change.
- **The screens changed:** re-record the take and render under the **same file name**, so the page needs no edit. Many hosts and CDNs keep the old file for a while; replace it rather than adding a second one.
- When a screen shown in a video changes, that video is out of date. Keep a list of which videos show which screens.

## Guardrails

- **Record only a local, dev or test copy of the app, with fake data.** `rig/lib.mjs` refuses any base URL that isn't localhost, `*.localhost`, `*.test`, or a test host you listed whose name says it's a test copy.
- **Never a production account.** Use a demo account that exists only in the test copy. If the app's env file names its backend, set `app_env_require` so the recorder refuses to run against anything else.
- **Secrets never go in files in the kit.** Passwords come from environment variables or the app's own env file, which stays in the app's folder. The recorder never prints them.
- **Nothing real on screen:** no real customer names, emails, addresses, payment details, or anyone's private data. Check every sheet.
- **No real messages:** don't click buttons that send invites, emails, texts or payments. Hover them.
- **The voice reads only approved scripts**, and a person listens before publishing.
- **Ask before publishing**, and keep a backout.

## Gotchas

- **Dead air.** When a line ends long before its actions do, the film has silence (the recorder warns when it's more than 1.5 s). Type faster (`{ delay: 30 }`), cut waits with `cutStart`/`cutEnd`, split the step across two lines, or add a line to the script.
- **Selectors.** Prefer roles with `exact: true`. When a page has two of something ("Close"), take `.first()` or scope to the dialog. After a dialog closes, wait for it to hide before clicking what's behind it. A menu that sometimes needs a second click: check it opened, and click again if not.
- **Native dropdowns** (`<select>`) open outside the page, so the open list never shows in the video. Use `r.select()` (it shows the cursor going there and the new value) or a custom dropdown in the app.
- **Toasts and captions** both like the bottom of the screen. Use `"caption_position": "top"` for apps with bottom toasts.
- **Synced folders.** Keep the work folder out of iCloud; thousands of frames in a synced folder can hang the Mac.
- **A contrast warning** from `hyperframes check` on a frame that's mid-fade is usually not real. Look at that frame before changing colours.
- **The voice varies** a little between runs even with the same seed, so a redone scene's timing shifts slightly. Re-record the take after redoing voice lines.

## Tools and licences

| Tool | Used for | Licence |
|---|---|---|
| Playwright 1.65 (npm) | drives Chrome for the take | Apache-2.0 |
| Google Chrome | the browser the take records | Google's terms |
| ffmpeg | encoding, mixing, checks | LGPL/GPL |
| HyperFrames 0.9.40 (npx) | renders the films | see its repository |
| VoiceStudio + VoxCPM2 | your voice clone | AGPL-3.0 app, Apache-2.0 model |
| Remotion 4.0.545 (product reel only) | renders the reel | **free for individuals and small companies; larger companies need a paid licence** (remotion.dev/license) |
