// Crisp 2x captures of the live site for the promo (demo/promo), plus the real numbers behind them.
//   cd demo && node capture.mjs
// Writes demo/promo/public/captures/*.png and demo/promo/src/data.json. Every number the video shows comes
// from data.json, which comes from the live API: nothing is typed in by hand.
import { chromium } from "playwright";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SITE = process.env.DEMO_SITE ?? "https://diocle.vercel.app";
const HERE = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.join(HERE, "promo", "public", "captures");
const CHQCLR = "chqclr-20261028-214355";
const REVERIFY_RUN = "chqclr-20261028-214355";
const JAVA_DELIVERY = "delivery-20261028-201807";
const CI_JOB = "https://github.com/Nivetha200111/quillmark-java/actions/runs/40709567888/job/122890827709";
const IMPORT_REPO = "https://github.com/openmainframeproject/cobol-programming-course";

const api = async (p) => (await fetch(`${SITE}/api${p}`)).json();
const panel = (page, title) => page.locator("section.panel", { has: page.locator("h2", { hasText: title }) }).first();

async function shot(locator, name) {
  await locator.scrollIntoViewIfNeeded();
  await locator.page().waitForTimeout(400);
  await locator.screenshot({ path: path.join(OUT, `${name}.png`), animations: "disabled" });
  console.log(`captured ${name}`);
}

await mkdir(OUT, { recursive: true });
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER ?? "chrome" });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
const page = await context.newPage();

// The live site
await page.goto(SITE, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);
await page.screenshot({ path: path.join(OUT, "home.png") });
console.log("captured home");

await page.goto(`${SITE}/#run=${CHQCLR}`, { waitUntil: "networkidle" });
await page.locator(".trace-cert").first().waitFor();
await page.waitForTimeout(1200);
await shot(page.locator(".breaker-panel"), "breaker");
await shot(panel(page, "Agent trace"), "trace");
await shot(page.locator(".stats-grid").first(), "stats");
await shot(panel(page, "Agent efficiency"), "efficiency");

await page.goto(`${SITE}/#run=${REVERIFY_RUN}`, { waitUntil: "networkidle" });
const button = page.getByRole("button", { name: "Re-verify on a fresh seed" });
await button.waitFor();
await button.click();
const verdict = panel(page, "Check it yourself").getByText(/PASS ·/);
await verdict.waitFor({ timeout: 120000 });
const reverifyText = (await verdict.innerText()).trim();
await shot(panel(page, "Check it yourself"), "reverify");

await page.goto(SITE, { waitUntil: "networkidle" });
await page.locator(".nav-item", { hasText: "Delivery" }).first().click();
await page.waitForTimeout(1500);
const select = page.locator(".dlv-select");
if (await select.count()) await select.selectOption(JAVA_DELIVERY);
await page.waitForTimeout(2000);
await shot(page.locator(".dlv-stages"), "stages");
await shot(panel(page, "Pull request"), "pr-panel");
await page.locator(".dlv-start input").first().fill(IMPORT_REPO);
await shot(page.locator(".dlv-start"), "import");

// GitHub: the pull request Diocle opened and the target repository's own CI
await page.goto("https://github.com/Nivetha200111/quillmark-java/pull/1", { waitUntil: "load" });
await shot(page.locator(".comment-body table").first(), "pr-table");
await page.goto(CI_JOB, { waitUntil: "load" });
await page.waitForTimeout(1500);
// The job's step list (GitHub's markup changes, so clip the region around the step names instead).
const stepName = page.getByText("Re-verify every program on fresh inputs").first();
await stepName.scrollIntoViewIfNeeded();
const box = await stepName.boundingBox();
const title = await page.getByText("succeeded", { exact: false }).first().boundingBox();
const top = Math.max(0, (title?.y ?? box.y - 380) - 50);
await page.screenshot({ path: path.join(OUT, "ci.png"), clip: { x: box.x - 70, y: top, width: 760, height: box.y + 260 - top } });
console.log("captured ci");
await page.goto("https://github.com/Nivetha200111/Diocle/blob/main/docs/EVALUATION.md", { waitUntil: "load" });
await shot(page.locator("article table").first(), "eval-table");
await shot(page.locator("article table").nth(2), "eval-rerun");  // tables: first run, comparator check, re-run

await browser.close();

// The numbers
const run = await api(`/runs/${CHQCLR}`);
const delivery = await api(`/deliveries/${JAVA_DELIVERY}`);
const events = run.events;
const certs = events.filter((e) => e.type === "certification");
const breakers = events.filter((e) => e.type === "breaker");
const data = {
  capturedAt: new Date().toISOString(),
  site: SITE,
  chqclr: {
    id: run.id, model: run.model, program: run.program,
    firstCert: certs[0]?.result?.split("\n")[0] ?? null,
    breakerFirst: breakers[0]?.message ?? null,
    recert: certs[1]?.result?.split("\n")[0] ?? null,
    breakerAgain: breakers[1]?.message ?? null,
    breaker: run.breaker,
    tools: events.filter((e) => e.type === "agent-step").map((e) => ({ tool: e.tool, why: e.rationale ?? "" })),
    calls: run.usage.calls, costUsd: run.usage.estimatedCostUsd,
  },
  reverify: reverifyText,  // the real result of pressing the button during capture
  delivery: {
    id: delivery.id, target: delivery.target, programs: delivery.programs.map((p) => ({ name: p.name, status: p.status })),
    pr: delivery.pullRequest?.url ?? null, checks: delivery.pullRequest?.checks ?? [],
  },
};
await writeFile(path.join(HERE, "promo", "src", "data.json"), JSON.stringify(data, null, 2) + "\n");
console.log("wrote data.json");
