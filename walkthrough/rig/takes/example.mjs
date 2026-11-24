// Take for the example walkthrough (scripts/example.md) on the demo app.
//   node serve.mjs                 # in another terminal: the demo app on 127.0.0.1:5199
//   node takes/example.mjs --dry   # timing check, 3 s per line if there's no voice yet
//   node takes/example.mjs         # the real take, timed to voice/example/manifest.json
// Add --phone for a 1080x1920 phone-shaped take (recordings/example-phone; build it with
// build_film.py films/example.film.json --take example-phone).
//
// A take is: set up the first screen, rec.rolling(), then one rec.line() per narration line
// with the actions that go with it, then rec.finish(). Each line holds until its voice clip
// ends, so the cursor never runs ahead of the words.
import { Recorder, BASE } from "../recorder.mjs";

const phone = process.argv.includes("--phone");
// A phone take is its own recording (example-phone) narrated by the same voice (voice/example).
const rec = await Recorder.start({ name: phone ? "example-phone" : "example", voice: "example", shape: phone ? "phone" : "desktop" });
const page = rec.page;

// Selectors by role and name, written from `node explore.mjs / plants`.
const addButton = () => page.getByRole("button", { name: "Add plant", exact: true });
const dialog = () => page.getByRole("dialog");
const card = (name) => page.getByRole("listitem", { name, exact: true });
const roomChip = (room) => page.getByRole("group", { name: "Room" }).getByRole("button", { name: room, exact: true });

try {
  // Pre-roll (not recorded): open the app and let it settle.
  await page.goto(`${BASE}/#/plants`, { waitUntil: "networkidle" });
  await rec.wait(800);
  await rec.rolling();

  // 1. Intro
  await rec.line(1, 1, async (r) => {
    await r.hover(page.getByRole("heading", { name: "Your plants" }), 800);
    await r.wait(400);
    await r.hover(card("Basil"), 700);
  });

  // 2. Add a plant
  await rec.line(2, 1, async (r) => {
    await r.click(addButton());
    await dialog().waitFor();
  });
  await rec.line(2, 2, async (r) => {
    const d = dialog();
    await r.type(d.getByPlaceholder("e.g. Peace lily"), "Peace lily", { delay: 45 });
    await r.select(d.getByLabel("Room"), "Bedroom");
    await r.setValue(d.getByLabel("Water every"), "7");
  });
  await rec.line(2, 3, async (r) => {
    await r.click(dialog().getByRole("button", { name: "Save", exact: true }));
    // The save takes a moment; cut the wait out of the video.
    r.cutStart();
    await dialog().waitFor({ state: "hidden" });
    await r.wait(150);
    r.cutEnd();
    await r.hover(card("Peace lily"), 600);
  });

  // 3. Mark it watered
  await rec.line(3, 1, async (r) => {
    await r.click(card("Basil").getByRole("button", { name: "Mark watered" }));
  });
  await rec.line(3, 2, async (r) => {
    await r.hover(card("Basil").getByText(/^In \d+ days?$/), 700);
  });

  // 4. Find a room
  await rec.line(4, 1, async (r) => {
    await r.click(roomChip("Kitchen"));
  }, { after: 0.8 });

  // 5. Outro
  await rec.line(5, 1, async (r) => {
    await r.click(roomChip("All rooms"));
    await r.wait(300);
    await r.glide(page.viewportSize().width / 2, page.viewportSize().height * 0.6, 900);
  }, { after: 1.0 });

  await rec.finish({ tail: 1.0 });
} catch (err) {
  await rec.fail(err);
}
