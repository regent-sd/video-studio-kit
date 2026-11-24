# VoiceStudio: your voice clone

A voice clone lets Claude make voiceovers in **your** voice for walkthroughs, explainers and narration, from scripts you approve. Everything runs on your Mac; nothing is uploaded.

The order matters: **you** make the clone yourself in the VoiceStudio app (it records you there), and only then does Claude use it. Claude never records you, never builds the clone for you, and never makes audio from a script you haven't approved.

## Ground rules

- **Only your own voice**, or a voice whose owner gave you written permission for the specific use.
- **Only scripts you approved.** Never use the clone to answer people, sign off on anything, or say something you didn't write or OK.
- **The clone file is like a password.** The exported `.ovsvoice` file lets anyone make audio in your voice. Keep it off shared drives and out of git (the kit's `.gitignore` blocks it). Back it up somewhere private.
- **A person listens before anything is used.** Claude can't hear; it checks the words by transcribing, but you listen.

## Needs

- Apple Silicon Mac (M1 or newer), macOS 13.3+. Intel Macs can't run the voice engine.
- About 15 GB free: the app (~255 MB), its Python environment and the voice model (~5 GB).
- A quiet room and 20–30 seconds of you reading naturally.

## 1. Install VoiceStudio

VoiceStudio is a free, open-source app (AGPL-3.0): https://github.com/debpalash/VoiceStudio

1. From its latest release, download `VoiceStudio-Electron-<version>-mac-arm64.dmg` and `SHA256SUMS.txt`. (Prompt to Claude: *"Download the latest VoiceStudio Mac release and check its checksum."* Claude tells you the size and asks first.)
2. Check the download: `shasum -a 256 VoiceStudio-Electron-*.dmg` must match the line in `SHA256SUMS.txt`.
3. Open the DMG and drag **VoiceStudio.app** to Applications.
4. The app isn't notarized, so macOS may block it the first time. **You** open it: right-click VoiceStudio.app → **Open** → **Open** (on macOS 15+: System Settings → Privacy & Security → **Open Anyway**). Don't turn off Gatekeeper.
5. Answer the first-run analytics question yourself.

Check the app's local server is up:

```bash
curl -s http://127.0.0.1:3900/health
# {"status":"ok","device":"mps",...}   (mps = your Mac's GPU)
```

On first launch it may start downloading its default voice model (~3 GB) and speech-to-text models (~3 GB) by itself. They're harmless and the speech-to-text models are useful in step 6.

## 2. Use the VoxCPM2 engine (needed for business use)

The app's default engine, OmniVoice, is licensed **non-commercial only**. **VoxCPM2** (`openbmb/VoxCPM2`) is **Apache-2.0**, free for commercial use, so use it for anything you'll post.

In the app: **Model Catalogue → VoxCPM2 → Install**, then pick it as the speech engine. Or let Claude do it (Prompt: *"Install the VoxCPM2 engine in VoiceStudio and make it the active voice engine."*):

```bash
B=http://127.0.0.1:3900
curl -s -X POST $B/engines/sidecar/voxcpm2/install                                  # engine (~1.3 GB)
curl -s -X POST $B/models/install -H 'content-type: application/json' -d '{"repo_id":"openbmb/VoxCPM2"}'   # weights (~5 GB)
curl -s $B/engines/sidecar/voxcpm2/install/status                                    # wait for "installed": true
curl -s -X POST $B/engines/select -H 'content-type: application/json' \
     -d '{"family":"tts","backend_id":"voxcpm2","model_id":"openbmb/VoxCPM2"}'
curl -s $B/engines/tts | jq '{active}'                                               # must say "voxcpm2"
```

## 3. Make your clone in the app (you do this)

1. In VoiceStudio: **Voices → new clone → record**. Record inside the app; it gives far better results than a recording made elsewhere and imported.
2. Read 20–30 seconds of natural, unhurried speech in a quiet room, once start to finish. Use something you'd really say, in your normal speaking voice. Not a script you're nervous about; a paragraph about what you do works well.
3. Give it a name you'll recognise ("My voice").
4. Optional: add VoiceStudio's consent recording. It's only needed for the app's online features, not for making audio on your Mac.

**Tip for more energy.** The engine copies the energy of the sample. If your clone sounds too calm for reels, record a second, livelier sample (or use a clean clip of you talking to camera) and have Claude pass it as a reference for that one script. Claude cleans up the room sound afterwards.

## 4. Back it up

In the app's Voices list, export your clone as a persona file (`.ovsvoice`) and keep it somewhere private. That file is your clone; with it you can set up a new Mac in two minutes (`POST /personas/import`). Never share it.

## 5. Tell the studio which voice is yours

```bash
curl -s http://127.0.0.1:3900/profiles | jq '.[] | {id, name}'
```

Copy your clone's `id` into `studio.json`:

```json
"voice": { "api": "http://127.0.0.1:3900", "profile_id": "<your id>", "name": "My voice" }
```

(Prompt: *"Find my voice clone in VoiceStudio and put its id in studio.json."*)

## 6. How Claude makes and checks voiceovers

**Generate.** Send only the profile id and the text, **one sentence per line**, in **one call** for the whole script, with every other setting at the app's default:

```bash
curl -s --max-time 900 -X POST $B/generate -F profile_id=$PID -F "text=$TEXT" -o voice.wav -D headers.txt
```

The model leaves natural 0.3–0.6 s pauses between lines. The first call takes 20–90 s while the model loads; after that it runs about twice real time. The walkthrough tools wrap this in `walkthrough/rig/gen_voice.py`.

Do:
- Spell things the way they should sound ("7 a.m. to 4 p.m.", "press 1", dates as words: "March twenty-first").
- Use periods between list items, not commas, so items don't run together.
- Keep a take you like by noting its `seed` (in the response headers) and passing `-F seed=<n>` again.

Don't (each was tried and sounded worse):
- Don't generate sentence by sentence and splice: the joins pop, and the silence between sounds artificial.
- Don't change speed, denoise or effect presets, or add your own EQ or room tone. The defaults sound most like you.

**Check.** Claude transcribes every take and compares it with the script word for word:

```bash
curl -s --max-time 300 $B/v1/audio/transcriptions -F file=@voice.wav -F response_format=verbose_json -F language=en | jq -r '.text'
```

- A dropped or extra word happens now and then. Regenerate with a different seed until it matches.
- The transcriber can invent words in trailing silence. Segments that start after the audio ends aren't really there.
- If a phrase keeps coming out oddly, reword it rather than hoping the next seed fixes it.
- Then **you listen** and approve it.

## If something's wrong

| Problem | Fix |
|---|---|
| `curl: (7) Failed to connect` | Open the VoiceStudio app; the server runs while it's open. |
| Sounds robotic or not like you | Check the active engine is VoxCPM2; re-record the sample inside the app in a quieter room. |
| Too flat for a reel | Use a livelier reference sample for that script (step 3, tip). |
| Takes minutes per line | The first call loads the model; later calls are faster. Close other heavy apps. |
