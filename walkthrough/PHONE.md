# Phone walkthroughs

Three ways to get a phone-shaped (1080x1920) walkthrough. They all end the same way: a recording plus a `timeline.json` in `<work>/recordings/<name>/`, then `build_film.py` (tall title card, step labels at the top, captions above the app's tab bar) and `check_film.py`.

| Your app | Best route |
|---|---|
| A web app (it works on a phone browser) | **1. A `--phone` take**: scripted, timed to the voice, repeatable |
| An iPhone app | **2. The iOS Simulator**: sharper than any phone capture |
| Only on a real device | **3. The phone's own screen recording**, imported |

## 1. Web app, phone-shaped take

The recorder has a phone shape: an iPhone-sized page (390 x 693 points at 3x, so 9:16), touch emulation, and a round touch dot instead of the arrow cursor.

```bash
node rig/takes/example.mjs --phone          # records <work>/recordings/example-phone/
.venv/bin/python walkthrough/rig/build_film.py walkthrough/films/example.film.json --take example-phone --render
```

In your own take, pass the shape through the way `example.mjs` does:

```js
const phone = process.argv.includes("--phone");
const rec = await Recorder.start({ name: phone ? "signup-phone" : "signup", voice: "signup", shape: phone ? "phone" : "desktop" });
```

`voice: "signup"` lets both takes share one voiceover. Selectors usually work in both shapes; menus that collapse into a "hamburger" on narrow screens need their own steps (`if (phone) { ... }`).

`node rig/explore.mjs <path> <name> --phone` shows what a screen looks like at phone width before you write the take.

### Without the recorder: the Chrome DevTools screencast

The Chrome DevTools plugin can also record a page as video. It's handy for a quick capture, with limits: it shows no cursor, it only sends a frame when the page changes, and it can only save inside the session's folders. Sizes that come out sharp:

1. Resize the page to 529 x 941, then emulate a 390 x 694 mobile viewport at 2x.
2. Record, then crop the top-left 780 x 1388 and scale it about 1.4x to 1080 x 1920:
   `ffmpeg -i screencast.mp4 -vf "fps=30,crop=780:1388:0:0,scale=1080:1920:flags=lanczos,format=yuv420p" -c:v libx264 -crf 16 phone.mp4`
3. Bring it in with `import_recording.py` (below).

## 2. iPhone app, from the iOS Simulator

The Simulator records the app's real pixels at full resolution, with no compression from a phone.

**Set up the screen**

```bash
open -a Simulator                                   # pick a device: File > Open Simulator
xcrun simctl ui booted appearance light             # or dark, to match the video
xcrun simctl status_bar booted override --time 9:41 --batteryState charged --batteryLevel 100 \
  --wifiBars 3 --cellularBars 4 --dataNetwork wifi  # a clean status bar
```

Install a **test build** of your app that points at a test backend, sign in to a demo account with fake data, and turn off anything that sends real notifications. Afterwards, `xcrun simctl status_bar booted clear` puts the status bar back.

**Record**

```bash
xcrun simctl io booted recordVideo --codec=h264 --force <work>/recordings/raw/signup.mov
```

It records until it's interrupted: press Ctrl-C (or, when Claude runs it in the background, `kill -INT <pid>`), and it finishes writing the file. Stopping it any other way can leave a broken file.

**Drive the app** while it records, either by hand or by asking Claude to tap through it with its iOS Simulator tools ("tap Sign up, type the demo email, tap Continue"). Go at a calm pace: a beat of stillness after each tap gives the voice room. The recording shows no cursor or touches, so the film's tap sounds and punch-ins carry that.

**Make the voice first** (`gen_voice.py`), so you know how long each line is. Then find when each line's action starts: a contact sheet with a frame every second shows it.

```bash
.venv/bin/python walkthrough/rig/check_film.py <work>/recordings/raw/signup.mov --every 1
.venv/bin/python walkthrough/rig/import_recording.py <work>/recordings/raw/signup.mov --name signup --voice signup \
    --starts 0.5,3.8,7.9,12.4 --taps 3.2:0.5:0.82,7.4:0.5:0.31 --trim 1.0:40
.venv/bin/python walkthrough/rig/build_film.py walkthrough/films/signup.film.json --take signup --render
```

- `--starts`: when each narration line starts, in script order, in seconds of the trimmed recording. Leave it out to lay the lines end to end first and adjust from there.
- `--taps`: when each tap happens, as `t` or `t:x:y` (x and y from 0 to 1 across the screen). They place the tap sounds and aim the punch-ins.
- `--trim start:end`: drop the fumbling at either end.
- A Simulator iPhone is taller than 9:16, so it's fitted inside 1080x1920 with bars at the sides. `--bg "#F6F1E9"` colours them (your brand's background works well).

For a walkthrough you'll re-record often, a UI test (XCUITest) can tap through the same steps every time while `recordVideo` runs.

## 3. A real phone's screen recording

Record with the phone's own screen recording (Control Center), with Do Not Disturb on and the demo account signed in. AirDrop it to the Mac and bring it in the same way as a Simulator recording:

```bash
.venv/bin/python walkthrough/rig/import_recording.py ScreenRecording.mov --name signup --voice signup --starts ...
```

A phone recording is softer than the Simulator's and its status bar shows the real time and battery, so prefer the Simulator when you can.

## Check the phone film

`check_film.py` as usual, and look for:

- the step label and captions covering something the voice talks about (move captions with `"caption_position": "top"`);
- notification banners, real names or anything personal on screen;
- the keyboard covering the field being typed in.

For a social reel rather than a how-to, the product reel (`product-reel/`) puts these clips in a phone frame under big headlines.
