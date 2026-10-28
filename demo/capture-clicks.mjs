// Click through the live site for real and save every state the click-through video shows.
//   cd demo && node capture-clicks.mjs
// Writes demo/promo/public/clicks/<state>.png (full page, 2x) and demo/promo/src/clicks.json: each state's page
// size and the page coordinates of everything the video points at or clicks. The video animates a cursor and a
// camera over these states; every state is a real screenshot taken after a real click.
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SITE = process.env.DEMO_SITE ?? "https://diocle.vercel.app";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "promo", "public", "clicks");
const IMPORT_REPO = "https://github.com/openmainframeproject/cobol-programming-course";
const W = 1280, H = 800;

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER ?? "chrome" });
const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
const page = await context.newPage();
const states = {};

const panel = (title) => page.locator("section.panel", { has: page.locator("h2", { hasText: title }) }).first();
async function box(locator) {
  await locator.waitFor();
  return locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left + window.scrollX, y: r.top + window.scrollY, w: r.width, h: r.height };
  });
}
// Panels that scroll inside themselves (the agent trace, delivery logs) are expanded for the full-page capture,
// so every line the video points at is really on the screenshot.
const EXPAND = ".trace-list, .dlv-log, .table-scroll { max-height: none !important; overflow: visible !important; }";
async function save(name, targets) {
  await page.addStyleTag({ content: EXPAND }).catch(() => {});
  await page.waitForTimeout(700);
  const boxes = {};
  for (const [key, locator] of Object.entries(targets)) boxes[key] = await box(locator);
  const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
  await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true, animations: "disabled" });
  states[name] = { ...size, boxes };
  console.log(`state ${name} ${size.w}x${size.h}`);
}

// 1. Home, then Live runs
await page.goto(SITE, { waitUntil: "networkidle" });
await save("home", { liveRuns: page.locator(".nav-item", { hasText: "Live runs" }).first(), hero: page.locator("main h1, main h2").first() });
await page.locator(".nav-item", { hasText: "Live runs" }).first().click();
await page.waitForLoadState("networkidle");
const row = page.locator("tr", { hasText: "CHQCLR" }).first();
await save("runs", { chqclrRow: row });

// 2. Open the CHQCLR run
await row.click();
await page.locator(".trace-cert", { hasText: "1006/1006" }).first().waitFor();
await save("run", {
  firstCert: page.locator(".trace-cert", { hasText: "1004/1004" }).first(),
  broke: page.locator(".trace-cert", { hasText: "break the Java" }).first(),
  breaker: page.locator(".breaker-panel"),
  breakerRow: page.locator(".breaker-panel tbody tr").first(),
  recert: page.locator(".trace-cert", { hasText: "1006/1006" }).first(),
  again: page.locator(".trace-cert", { hasText: "match the COBOL" }).first(),
  reverifyButton: page.getByRole("button", { name: "Re-verify on a fresh seed" }),
  stats: page.locator(".stats-grid").first(),
});

// 3. Press Re-verify (real): running, then the verdict
await page.getByRole("button", { name: "Re-verify on a fresh seed" }).click();
await save("running", { reverifyButton: panel("Check it yourself").locator("button") });
const verdict = panel("Check it yourself").getByText(/PASS ·/);
await verdict.waitFor({ timeout: 120000 });
await save("verified", { verdict, reverifyPanel: panel("Check it yourself") });
const verdictText = (await verdict.innerText()).trim();

// 4. Delivery: the pull request and its CI, then the import form
await page.locator(".nav-item", { hasText: "Delivery" }).first().click();
await page.waitForLoadState("networkidle");
const select = page.locator(".dlv-select");
if (await select.count()) await select.selectOption("delivery-20261028-201807");
await page.waitForTimeout(1500);
await save("delivery", {
  deliveryNav: page.locator(".nav-item", { hasText: "Delivery" }).first(),
  stages: page.locator(".dlv-stages"),
  prPanel: panel("Pull request"),
  prButton: panel("Pull request").locator("a.button").first(),
  input: page.locator(".dlv-start input").first(),
  importButton: page.getByRole("button", { name: "Import and convert" }),
});
await page.locator(".dlv-start input").first().fill(IMPORT_REPO);
await save("typed", { input: page.locator(".dlv-start input").first(), importButton: page.getByRole("button", { name: "Import and convert" }) });

// 5. The pull request on GitHub
await page.goto("https://github.com/Nivetha200111/quillmark-java/pull/1", { waitUntil: "load" });
await save("pr", { table: page.locator(".comment-body table").first(), merged: page.locator("span", { hasText: "Merged" }).first() });

await browser.close();
await writeFile(path.join(HERE, "promo", "src", "clicks.json"),
  JSON.stringify({ capturedAt: new Date().toISOString(), viewport: { w: W, h: H }, importRepo: IMPORT_REPO, verdict: verdictText, states }, null, 2) + "\n");
console.log("wrote clicks.json");
