// Walkthrough recorder: drives a local or test copy of your app with a visible cursor,
// captures sharp frames over the Chrome DevTools protocol (a 2x or 3x page fitted to
// 1920x1080, or 1080x1920 for the phone shape), and keeps a timeline of when each
// narration line starts, so the voice can be laid on top exactly.
//
//   const rec = await Recorder.start({ name: "example" });   // reads voice/example/manifest.json
//   ... set up the first screen ...
//   await rec.rolling();                                      // capture starts here
//   await rec.line(1, 1, async (r) => { await r.click(page.getByRole("button", { name: "Add" })); });
//   await rec.finish();                                       // writes recordings/example/
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { launch, signIn, BASE, outDir, framesDir } from "./lib.mjs";

const cursorJs = (kind) => `
(() => {
  const install = () => {
    if (document.getElementById('__wt_cursor')) return;
    const c = document.createElement('div');
    c.id = '__wt_cursor';
    ${kind === "touch"
      ? `c.innerHTML = '<div style="width:34px;height:34px;border-radius:50%;background:rgba(17,24,39,.28);border:2px solid rgba(255,255,255,.9)"></div>';
    Object.assign(c.style, {position:'fixed', left:'-60px', top:'-60px', width:'34px', height:'34px', zIndex:2147483647, pointerEvents:'none', transform:'translate(-17px,-17px)'});`
      : `c.innerHTML = '<svg width="28" height="28" viewBox="0 0 28 28"><path d="M5 3 L5 22 L10 17.5 L13.5 25 L17 23.5 L13.6 16.2 L20 16 Z" fill="#111827" stroke="white" stroke-width="1.8" stroke-linejoin="round"/></svg>';
    Object.assign(c.style, {position:'fixed', left:'-40px', top:'-40px', width:'28px', height:'28px', zIndex:2147483647, pointerEvents:'none', transform:'translate(-4px,-2px)', filter:'drop-shadow(0 2px 3px rgba(0,0,0,.35))'});`}
    document.documentElement.appendChild(c);
    const style = document.createElement('style');
    style.textContent = '@keyframes __wt_ripple{from{transform:translate(-50%,-50%) scale(.3);opacity:.55}to{transform:translate(-50%,-50%) scale(1.6);opacity:0}} .__wt_r{position:fixed;width:46px;height:46px;border-radius:50%;background:rgba(37,99,235,.45);pointer-events:none;z-index:2147483646;animation:__wt_ripple .5s ease-out forwards} *{scrollbar-width:none} ::-webkit-scrollbar{display:none}';
    document.documentElement.appendChild(style);
    document.addEventListener('mousemove', (e) => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    document.addEventListener('mousedown', (e) => { const r = document.createElement('div'); r.className='__wt_r'; r.style.left=e.clientX+'px'; r.style.top=e.clientY+'px'; document.documentElement.appendChild(r); setTimeout(()=>r.remove(), 600); }, true);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install); else install();
})();`;

const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export class Recorder {
  /**
   * name: the take's name (recordings/<name>/, voice/<name>/).
   * dry: record to <name>-dry with 3 s per line when there's no voice yet.
   * shape: "desktop" (1920x1080) or "phone" (1080x1920).
   * voice: the voice folder's name, when it isn't the take's (a phone take of the same script).
   * voiceManifest: defaults to <work>/voice/<voice or name>/manifest.json when it exists.
   */
  static async start({ name, voice, dry = process.argv.includes("--dry"), shape = "desktop", voiceManifest, signIn: doSignIn = true } = {}) {
    if (!name) throw new Error("Recorder.start needs a name");
    const r = new Recorder();
    r.name = dry ? `${name}-dry` : name;
    r.shapeName = shape;
    r.dir = outDir("recordings", r.name);
    // Frames go to a local cache, never a synced folder: a two-minute take writes about
    // 6,000 JPEGs (around 1 GB). They are deleted once the MP4 is encoded.
    r.framesDir = framesDir(r.name);
    fs.rmSync(r.framesDir, { recursive: true, force: true });
    fs.mkdirSync(r.framesDir, { recursive: true });
    const manifest = voiceManifest ?? path.join(outDir("voice", voice || name), "manifest.json");
    r.voice = manifest && fs.existsSync(manifest) ? JSON.parse(fs.readFileSync(manifest, "utf8")) : null;
    if (!r.voice) console.log(`no voice manifest at ${manifest}: each line holds 3 s (fine for a dry run)`);
    const { browser, context, page, env, shape: sh } = await launch({ shape });
    r.shape = sh;
    r.cursorJs = cursorJs(sh.mobile ? "touch" : "arrow");
    await context.addInitScript(r.cursorJs);
    r.browser = browser; r.context = context; r.page = page; r.env = env;
    r.mouse = { x: sh.viewport.width / 2, y: sh.viewport.height / 2 };
    r.timeline = [];
    r.frames = [];
    if (doSignIn) await signIn(page, env);
    return r;
  }

  /** Start capturing. Do all the setup (sign-in, first page, scroll position) before this. */
  async rolling() {
    await this.page.evaluate(this.cursorJs);
    await this.page.mouse.move(this.mouse.x, this.mouse.y);
    this.cdp = await this.context.newCDPSession(this.page);
    let n = 0;
    this.cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
      const file = path.join(this.framesDir, `f${String(++n).padStart(6, "0")}.jpg`);
      fs.writeFileSync(file, Buffer.from(data, "base64"));
      this.frames.push({ t: metadata.timestamp, file });
      try { await this.cdp.send("Page.screencastFrameAck", { sessionId }); } catch {}
    });
    const { width, height } = this.shape.out;
    await this.cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: width, maxHeight: height, everyNthFrame: 1 });
    this.t0 = Date.now() / 1000;
    // The screencast only sends a frame when the page changes; a tiny repaint ticker keeps
    // a steady cadence so still moments aren't one long frame.
    await this.page.evaluate(() => {
      if (window.__wt_tick) return;
      const d = document.createElement("div");
      Object.assign(d.style, { position: "fixed", right: "0", bottom: "0", width: "1px", height: "1px", opacity: "0.01", zIndex: 2147483645, pointerEvents: "none" });
      document.documentElement.appendChild(d);
      let i = 0; window.__wt_tick = setInterval(() => { d.style.background = (i++ % 2) ? "#fff" : "#fefefe"; }, 33);
    });
  }

  now() { return Date.now() / 1000 - this.t0; }
  wait(ms) { return this.page.waitForTimeout(ms); }

  /** Run `actions` while narration line (scene, line) plays, then hold until it ends.
   *  lead: ms to wait before acting. after: seconds of quiet kept after the line. */
  async line(scene, line, actions = async () => {}, { lead = 250, after = null } = {}) {
    const meta = this.voice?.scenes?.[String(scene)]?.lines?.[line - 1];
    if (this.voice && !meta) console.warn(`warning: no voice line ${scene}.${line} in the manifest (is the script newer than the voice?)`);
    const dur = meta ? meta.seconds : 3;
    const start = this.now();
    const cut0 = this.cutTotal || 0;
    this.timeline.push({ scene, line, start: +start.toFixed(3), seconds: dur, file: meta?.file || null, text: meta?.text || "" });
    await this.wait(lead);
    await actions(this);
    const gap = after ?? 0.45;
    const remaining = start + dur + gap - (this.now() - ((this.cutTotal || 0) - cut0));
    if (remaining > 0) await this.wait(remaining * 1000);
    else if (remaining < -1.5) console.warn(`  line ${scene}.${line}: actions ran ${(-remaining).toFixed(1)} s past the voice (dead air in the film; see README, "Dead air")`);
  }

  async pause(ms) { await this.wait(ms); }

  /** Everything between cutStart() and cutEnd() is removed from the video (a slow save,
   *  a page load), and later narration lines move earlier by the same amount. */
  cutStart() { this._cut = this.now(); }
  cutEnd() {
    if (this._cut == null) return;
    const b = this.now();
    (this.cuts ||= []).push([this._cut, b]);
    this.cutTotal = (this.cutTotal || 0) + (b - this._cut);
    this._cut = null;
  }

  // ---- cursor ---------------------------------------------------------------------
  async glide(x, y, ms = 520) {
    const { x: x0, y: y0 } = this.mouse;
    const steps = Math.max(8, Math.round(ms / 16));
    for (let i = 1; i <= steps; i++) {
      const k = ease(i / steps);
      await this.page.mouse.move(x0 + (x - x0) * k, y0 + (y - y0) * k);
      await this.wait(ms / steps);
    }
    this.mouse = { x, y };
  }

  async center(locator) {
    await locator.waitFor({ state: "visible", timeout: 15000 });
    await locator.scrollIntoViewIfNeeded();
    const b = await locator.boundingBox();
    if (!b) throw new Error("no bounding box for locator");
    return { x: b.x + b.width / 2, y: b.y + b.height / 2, b };
  }

  async hover(locator, ms = 700) {
    const { x, y } = await this.center(locator);
    await this.glide(x, y, ms);
  }

  async click(locator, { ms = 520, settle = 300, offset = null } = {}) {
    const { x, y, b } = await this.center(locator);
    const tx = offset ? b.x + offset.x : x, ty = offset ? b.y + offset.y : y;
    await this.glide(tx, ty, ms);
    await this.wait(120);
    const { width, height } = this.shape.viewport;
    (this.clicks ||= []).push({ t: this.now(), x: tx / width, y: ty / height });
    await this.page.mouse.down(); await this.wait(70); await this.page.mouse.up();
    await this.wait(settle);
  }

  async type(locator, text, { delay = 55 } = {}) {
    await this.click(locator, { settle: 150 });
    await locator.pressSequentially(text, { delay });
  }

  async setValue(locator, value) {
    await this.click(locator, { settle: 150 });
    await locator.fill(value);
    await this.wait(200);
  }

  /** Open a custom dropdown (role=combobox/button) and pick an option by its name. */
  async choose(trigger, optionName) {
    await this.click(trigger, { settle: 380 });
    await this.click(this.page.getByRole("option", { name: optionName, exact: true }), { ms: 500, settle: 300 });
  }

  /** A native <select>: glide to it, then pick the option (the open list isn't drawn in a screencast). */
  async select(locator, label) {
    await this.click(locator, { settle: 200 });
    await locator.selectOption({ label });
    await this.wait(250);
  }

  async drag(from, to, { ms = 1100 } = {}) {
    const a = await this.center(from);
    await this.glide(a.x, a.y, 600);
    await this.wait(150);
    await this.page.mouse.down();
    await this.wait(150);
    await this.page.mouse.move(a.x + 6, a.y + 6, { steps: 4 });
    this.mouse = { x: a.x + 6, y: a.y + 6 };
    await this.wait(150);
    const bTo = await to.boundingBox();
    await this.glide(bTo.x + bTo.width / 2, bTo.y + bTo.height / 2, ms);
    await this.wait(250);
    await this.page.mouse.up();
    await this.wait(500);
  }

  async scroll(dy, { ms = 900 } = {}) {
    const steps = Math.max(6, Math.round(ms / 40));
    for (let i = 0; i < steps; i++) { await this.page.mouse.wheel(0, dy / steps); await this.wait(ms / steps); }
  }

  // ---- finish ---------------------------------------------------------------------
  async finish({ tail = 1.2 } = {}) {
    await this.wait(tail * 1000);
    const end = Date.now() / 1000;
    await this.cdp.send("Page.stopScreencast");
    await this.wait(300);
    await this.browser.close();
    const cuts = (this.cuts || []).map(([a, b]) => [this.t0 + a, this.t0 + b]);
    const inCut = (t) => cuts.some(([a, b]) => t >= a && t < b);
    const cutBefore = (t) => cuts.reduce((acc, [a, b]) => acc + Math.max(0, Math.min(t, b) - a) * (t > a ? 1 : 0), 0);
    let frames = this.frames.filter((f) => f.t >= this.t0 - 0.5).sort((a, b) => a.t - b.t);
    frames = frames.filter((f) => !inCut(f.t)).map((f) => ({ ...f, t: f.t - cutBefore(f.t) }));
    if (!frames.length) throw new Error("no frames captured");
    const removed = cuts.reduce((acc, [a, b]) => acc + (b - a), 0);
    const list = [];
    for (let i = 0; i < frames.length; i++) {
      const next = i + 1 < frames.length ? frames[i + 1].t : end - removed;
      const d = Math.max(0.001, next - Math.max(frames[i].t, this.t0));
      if (frames[i].t < this.t0 && i + 1 < frames.length && frames[i + 1].t <= this.t0) continue;
      list.push(`file '${frames[i].file}'`, `duration ${d.toFixed(4)}`);
    }
    list.push(`file '${frames[frames.length - 1].file}'`);
    const listFile = path.join(path.dirname(this.framesDir), "frames.ffconcat");
    fs.writeFileSync(listFile, "ffconcat version 1.0\n" + list.join("\n") + "\n");
    const mp4 = path.join(this.dir, `${this.name}.mp4`);
    const { width: W, height: H } = this.shape.out;
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", listFile,
      "-vf", `fps=30,scale=${W}:${H}:flags=lanczos:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=white,format=yuv420p`,
      "-c:v", "libx264", "-crf", "16", "-preset", "slow", "-movflags", "+faststart", mp4]);
    for (const l of this.timeline) l.start = +(l.start - cutBefore(this.t0 + l.start)).toFixed(3);
    const clicks = (this.clicks || []).filter((c) => !inCut(this.t0 + c.t))
      .map((c) => ({ t: +(c.t - cutBefore(this.t0 + c.t)).toFixed(3), x: +c.x.toFixed(4), y: +c.y.toFixed(4) }));
    const duration = +(end - this.t0 - removed).toFixed(3);
    fs.rmSync(path.dirname(this.framesDir), { recursive: true, force: true });
    const timeline = {
      name: this.name, shape: this.shapeName, size: { width: W, height: H }, duration,
      cuts: this.cuts || [], clicks,
      voice: this.voice ? { engine: this.voice.engine || null, profile: this.voice.profile || null } : null,
      lines: this.timeline,
    };
    fs.writeFileSync(path.join(this.dir, "timeline.json"), JSON.stringify(timeline, null, 2));
    console.log(`recorded ${mp4}: ${duration}s, ${frames.length} frames, ${this.timeline.length} narration lines, ${clicks.length} clicks`);
    return { mp4, duration };
  }

  /** Call from a take's catch block: saves a screenshot of where it failed, then closes. */
  async fail(err) {
    await this.page.screenshot({ path: path.join(this.dir, "error.png") }).catch(() => {});
    console.error("TAKE FAILED:", err?.message || err);
    console.error(`  screenshot: ${path.join(this.dir, "error.png")}`);
    try { if (this.cdp) await this.finish({ tail: 0.2 }); else await this.browser.close(); } catch {}
    process.exitCode = 1;
  }
}

export { BASE };
