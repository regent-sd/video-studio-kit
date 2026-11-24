// Shared helpers for the walkthrough recorder: settings, the safety checks, the browser,
// optional sign-in and the work folders.
//
// Settings come from the kit's studio.json (laid over studio.example.json), key "walkthrough".
// STUDIO_CONFIG=/path/to/other.json uses another settings file, as the Python tools do.
// WALKTHROUGH_BASE overrides the base URL for one run.
import { chromium } from "playwright";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const RIG = path.dirname(fileURLToPath(import.meta.url));
export const KIT_ROOT = path.resolve(RIG, "../..");

const DEFAULTS = {
  work_dir: "~/Movies/Walkthroughs",
  base_url: "http://127.0.0.1:5199",
  test_hosts: [],
  app_env_file: "",
  app_env_require: {},
  login: null,
  browser_channel: "chrome",
  timezone: "",
  hyperframes_version: "0.9.40",
};

const expand = (p) => (p ? p.replace(/^~(?=$|\/)/, os.homedir()).replace(/\$\{?([A-Z_][A-Z0-9_]*)\}?/g, (_, k) => process.env[k] ?? "") : p);

function readJson(file) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return {}; }
}

/** The "walkthrough" settings, studio.json over studio.example.json over the defaults. */
export function settings() {
  const own = process.env.STUDIO_CONFIG ? expand(process.env.STUDIO_CONFIG) : path.join(KIT_ROOT, "studio.json");
  const ex = readJson(path.join(KIT_ROOT, "studio.example.json")).walkthrough || {};
  const mine = readJson(own).walkthrough || {};
  const s = { ...DEFAULTS, ...ex, ...mine };
  s.work_dir = expand(s.work_dir);
  s.app_env_file = expand(s.app_env_file);
  if (process.env.WALKTHROUGH_BASE) s.base_url = process.env.WALKTHROUGH_BASE;
  s.base_url = s.base_url.replace(/\/+$/, "");
  return s;
}

export const S = settings();
export const BASE = S.base_url;

// ---- safety checks ---------------------------------------------------------------

const TEST_LABEL = /^(staging|stage|dev|develop|test|testing|qa|sandbox|preview|demo)(\d+|-.*)?$/i;

/** Throws unless `url` is a local address, a *.localhost / *.test name, or a test host the
 *  settings list (test_hosts) whose name has a test label (staging., dev., qa., preview.…). */
export function assertSafeUrl(url, s = S) {
  let u;
  try { u = new URL(url); } catch { throw new Error(`Refusing to run: "${url}" is not a URL.`); }
  const h = u.hostname.replace(/^\[|\]$/g, "").toLowerCase();
  const local = ["localhost", "127.0.0.1", "::1"].includes(h) || h.endsWith(".localhost") || h.endsWith(".test");
  if (local) return;
  const listed = (s.test_hosts || []).map((x) => x.toLowerCase()).includes(h);
  const labelled = h.split(".").slice(0, -1).some((label) => TEST_LABEL.test(label));
  if (listed && labelled) return;
  throw new Error(
    `Refusing to run against ${h}: walkthroughs record only a local, dev or test copy of the app.\n` +
    `  Use localhost, or add a test host (its name must say staging/dev/test/qa/sandbox/preview) to\n` +
    `  "walkthrough.test_hosts" in studio.json.`,
  );
}

function readEnvFile(file) {
  const out = {};
  for (const line of fs.readFileSync(file, "utf8").split("\n")) {
    const m = line.match(/^\s*(?:export\s+)?([A-Za-z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^['"]|['"]$/g, "");
  }
  return out;
}

/** The app's own env file must point at its dev/test backend, as "app_env_require" says
 *  (key -> a pattern its value must match). Values are never printed. */
export function assertTestBackend(s = S) {
  const req = s.app_env_require || {};
  if (!Object.keys(req).length) return {};
  if (!s.app_env_file || !fs.existsSync(s.app_env_file)) {
    throw new Error(`Refusing to run: "walkthrough.app_env_require" is set but app_env_file (${s.app_env_file || "empty"}) isn't there.`);
  }
  const env = readEnvFile(s.app_env_file);
  for (const [key, pattern] of Object.entries(req)) {
    if (!new RegExp(pattern).test(env[key] || "")) {
      throw new Error(`Refusing to run: ${key} in the app's env file doesn't match the test backend pattern. Is it pointing at production?`);
    }
  }
  return env;
}

export function assertSafe(s = S) {
  assertSafeUrl(s.base_url, s);
  return assertTestBackend(s);
}

// ---- shapes ------------------------------------------------------------------------

// viewport is the page's CSS size; scale x viewport is captured, then fitted to `out`.
export const SHAPES = {
  desktop: { viewport: { width: 1600, height: 900 }, scale: 2, mobile: false, out: { width: 1920, height: 1080 } },
  phone: { viewport: { width: 390, height: 693 }, scale: 3, mobile: true, out: { width: 1080, height: 1920 } },
};

export async function launch({ shape = "desktop", headless = true } = {}) {
  const env = assertSafe();
  const sh = SHAPES[shape] || SHAPES.desktop;
  const opts = { headless };
  if (S.browser_channel) opts.channel = S.browser_channel;
  let browser;
  try {
    browser = await chromium.launch(opts);
  } catch (e) {
    if (!opts.channel) throw e;
    // No Google Chrome: fall back to Playwright's own Chromium if it's installed.
    browser = await chromium.launch({ headless });
  }
  const context = await browser.newContext({
    viewport: sh.viewport,
    deviceScaleFactor: sh.scale,
    isMobile: sh.mobile,
    hasTouch: sh.mobile,
    colorScheme: "light",
    ...(S.timezone ? { timezoneId: S.timezone } : {}),
  });
  const page = await context.newPage();
  return { browser, context, page, env, shape: sh };
}

/** Signs in with the settings' "login" block, if there is one. The password comes from an
 *  environment variable or the app's env file (password_env names it); it is never printed. */
export async function signIn(page, env = {}, s = S) {
  const L = s.login;
  if (!L) return;
  const pw = process.env[L.password_env] ?? env[L.password_env];
  if (!pw) throw new Error(`Sign-in needs ${L.password_env} (set it in your shell or the app's env file). It is never written to the kit.`);
  await page.goto(`${BASE}${L.path || "/login"}`, { waitUntil: "networkidle", timeout: 180000 });
  await page.locator(L.email_selector || 'input[type="email"]').fill(L.email);
  await page.locator(L.password_selector || 'input[type="password"]').fill(pw);
  await page.locator(L.submit_selector || 'button[type="submit"]').click();
  const loginPath = L.path || "/login";
  await page.waitForURL((u) => !u.pathname.startsWith(loginPath), { timeout: 120000 });
  await page.waitForLoadState("networkidle", { timeout: 120000 });
}

/** A folder inside the work folder (made if missing): outDir("recordings", "example"). */
export function outDir(...parts) {
  const d = path.join(S.work_dir, ...parts);
  fs.mkdirSync(d, { recursive: true });
  return d;
}

/** Where a take's frames go while recording: a local cache, never a synced folder. */
export function framesDir(name) {
  const base = process.env.WALKTHROUGH_CACHE || path.join(os.homedir(), "Library/Caches/video-studio-kit/walkthroughs");
  return path.join(base, name, "frames");
}
