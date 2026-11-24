# House rules

The standing rules Claude follows on every video, before any style or brand rule. This is the **starter set**: rules that came out of many rounds of real editing notes. At setup you choose to adopt them, edit them, or start clean (`house-rules.blank.md`). The ones you keep are copied to `rules/house-rules.md`, which is yours to change any time: say **"add a house rule: …"** or **"drop the house rule about …"**.

Each rule has a short reason, so you can judge whether it fits you.

## Asking and approving

- **Ask which style.** There's no default style. If a request doesn't name one, Claude asks which, with a one-line description of each. *Why: each style suits different footage; guessing wastes a render.*
- **A plan before a build.** For a new video Claude shows the story in order, the footage with times, each effect with its moment, and any text it would write. It builds only after you say go.
- **A new look isn't a style until you say so.** Something made for one video stays "in review" until you approve reusing it, and becomes a named style only when you approve it as one.
- **Never overwrite a reviewed file.** A fix is always a new version (v2, v3…). Notes stay with the version they were left on.

## Words and honesty

- **Only real numbers on screen.** Where there's no real number, show a flag (LOW, ↑ Better), never a made-up value.
- **Flag anything Claude wrote.** Hook titles, labels, jokes, explainer text and any words an effect shows that you didn't say are listed for you to approve before posting.
- **Your own words first.** Captions come from what was said. Claude doesn't put words in your mouth.

## Cutting

- **Tight and filler-free.** Cut the ums, false starts and long pauses.
- **Never cut a word short.** Check every voice cut against the sound, not only the transcript. Transcript word times can be off by half a second; a clipped ending ("tank" for "tanked") is the first thing viewers hear.
- **Keep the bridge.** When two parts of the story join, keep the line that connects them, even if it's not the snappiest.
- **Show steps in the order they really happen.**
- **Swap a fumbled take** for a clean one when there is one, and use the better camera angle of the same moment when there are two.

## On screen

- **A caption shows once.** It never carries across a cut (it gets drawn twice in the next layout).
- **A tag stays up long enough to read** (at least 1.5 s) and matches what's on screen.
- **Moving footage, not still frames.** A punch-in on moving footage beats a stack of stills.
- **Never over a face, and inside the safe zones** (nothing important above y 220 or below y 1470 on a 1080×1920 reel).
- **Clean frames.** Check every cut against the brand's keep-out list (other brands, screens with private details, clutter). A new crop can bring back something the old framing hid.
- **People.** Anyone clearly visible has said yes. Claude lists everyone recognisable in the hand-off. No children unless you say so for that video.

## Sound

- **Every video gets its own music.** Never reuse a track across videos. Real licensed tracks you pick beat generated music, which tends to sound generic.
- **A sound-effects pass on every video**, without being asked. Effects only where something on screen causes them, about 6–8 dB under the voice, never on a word, never over real sound the footage already has. The hand-off lists every effect so you can cut any of them.
- **Sound matches the picture.** The sound of what's on screen, not a different machine or a different moment.
- **No stray bangs, knocks or bits of words** at the cuts.
- **Music arrives with energy.** Skip quiet intros; bring the bed in at a level you can feel.

## Effects

- **Effects land on something said:** a hook word, a list, a real number, a quote, a turn in the story.
- **At most one every 10–15 seconds.** Propose each in the plan with its moment and why.
- **Restrained brands stay restrained** (`"effects": {"restrained": true}` in `brand.json`).

## After approval

- When you approve a video, Claude does the whole approved-video routine (`guides/after-approval.md`) without being asked.
- A note that says how you like things in general goes into `guides/storytelling.md`, in your words, with the date.
