// Look at a screen before writing a take.
//   node explore.mjs <path> [name] [--phone]
// Signs in (if the settings say how), opens <path> on the base URL, and saves a screenshot
// and an accessibility snapshot to <work>/explore/. Write the take's selectors from the
// snapshot: roles and names ("button", "Add plant") are what Playwright finds best.
import fs from "node:fs";
import path from "node:path";
import { launch, signIn, BASE, outDir } from "./lib.mjs";

const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const target = args[0] || "/";
const name = args[1] || target.replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "") || "home";
const dir = outDir("explore");

const { browser, page, env } = await launch({ shape: process.argv.includes("--phone") ? "phone" : "desktop" });
try {
  await signIn(page, env);
  await page.goto(`${BASE}${target}`, { waitUntil: "networkidle", timeout: 180000 });
  await page.waitForTimeout(1500);
  await page.screenshot({ path: path.join(dir, `${name}.png`) });
  const snap = await page.locator("body").ariaSnapshot();
  fs.writeFileSync(path.join(dir, `${name}.aria.yml`), snap);
  console.log(`saved ${path.join(dir, name)}.png and .aria.yml (${snap.length} chars) at ${page.url()}`);
} finally {
  await browser.close();
}
