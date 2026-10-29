// Scripted recordings of the live site for the demo video (docs/DEMO_PLAN.md): one 1920x1080 clip per shot.
//   cd demo && npm run record                 # all shots
//   cd demo && npm run record -- chqclr home  # some shots
// Clips land in demo/out/<shot>.webm (gitignored). Nothing here changes the site; the import shot fills the form
// but does not submit unless DEMO_SUBMIT_IMPORT=1 (a real import spends model credits).
import { chromium } from "playwright";
import { mkdir, rename, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const SITE = process.env.DEMO_SITE ?? "https://diocle.vercel.app";
const OUT = path.join(path.dirname(fileURLToPath(import.meta.url)), "out");
// The browser window is 1280x720 so text reads on video. Chrome's screencast squeezes the page into the top
// 1280x640 of each frame (measured with a calibration page); build.sh crops that and scales it to 1920x1080.
const VIEW = { width: 1280, height: 720 };
const CHQCLR = "chqclr-20261028-214355";
const REVERIFY_RUN = "intaccr-20261028-194951";
const JAVA_DELIVERY = "delivery-20261028-201807";
const CI_JOB = "https://github.com/Nivetha200111/quillmark-java/actions/runs/40709567888/job/122890827709";
const IMPORT_REPO = "https://github.com/openmainframeproject/cobol-programming-course";

const pause = (page, ms) => page.waitForTimeout(ms);

// A visible cursor and a highlight box: headless recordings show neither by default.
const OVERLAY = `
  (() => {
    if (window.__diocleOverlay) return;
    window.__diocleOverlay = true;
    const style = document.createElement("style");
    style.textContent = \`
      #demo-cursor { position: fixed; z-index: 2147483647; width: 22px; height: 22px; margin: -3px 0 0 -3px;
        pointer-events: none; transition: transform 60ms linear;
        background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='22' height='22'><path d='M2 2 L2 18 L7 13 L11 21 L14 20 L10 12 L17 12 Z' fill='white' stroke='black' stroke-width='1.5'/></svg>") no-repeat; }
      .demo-highlight { outline: 4px solid #ffcc00 !important; outline-offset: 4px !important;
        box-shadow: 0 0 0 9999px rgba(0,0,0,0.28) !important; position: relative; z-index: 50; transition: outline-color .3s; }
      html { scroll-behavior: smooth; }\`;
    document.head.appendChild(style);
    const cursor = document.createElement("div");
    cursor.id = "demo-cursor";
    document.body.appendChild(cursor);
    window.addEventListener("mousemove", (e) => { cursor.style.left = e.clientX + "px"; cursor.style.top = e.clientY + "px"; });
  })();
`;

async function overlay(page) {
  await page.evaluate(OVERLAY);
}

async function moveTo(page, locator) {
  const box = await locator.boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 25 });
}

async function click(page, locator) {
  await locator.scrollIntoViewIfNeeded();
  await moveTo(page, locator);
  await pause(page, 350);
  await locator.click();
}

async function show(page, locator, ms = 2500) {
  // Centre an element, frame it, hold, unframe.
  await locator.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "center" }));
  await pause(page, 900);
  await locator.evaluate((el) => el.classList.add("demo-highlight"));
  await pause(page, ms);
  await locator.evaluate((el) => el.classList.remove("demo-highlight"));
}

async function scrollPage(page, pixels, steps = 12) {
  for (let i = 0; i < steps; i++) {
    await page.mouse.wheel(0, pixels / steps);
    await pause(page, 60);
  }
}

async function nav(page, name) {
  await click(page, page.locator(".nav-item", { hasText: name }).first());
  await pause(page, 1500);
}

async function card(page, title, lines) {
  await page.setContent(`
    <style>
      body { margin: 0; height: 100vh; display: grid; place-items: center; background: #008080;
             font-family: Tahoma, Verdana, sans-serif; }
      .win { width: 1000px; background: #c0c0c0; box-shadow: inset -2px -2px #0a0a0a, inset 2px 2px #fff,
             inset -4px -4px #808080, inset 4px 4px #dfdfdf; }
      .bar { background: linear-gradient(90deg, #000080, #0f62fe); color: #fff; font-weight: bold;
             padding: 10px 16px; font-size: 22px; letter-spacing: .5px; }
      .body { padding: 40px 48px 48px; }
      h1 { margin: 0 0 24px; font-size: 56px; font-family: "Courier New", monospace; }
      p { margin: 10px 0; font-size: 24px; line-height: 1.35; }
    </style>
    <div class="win"><div class="bar">DIOCLE · OPERATIONS CONSOLE</div>
      <div class="body"><h1>${title}</h1>${lines.map((l) => `<p>${l}</p>`).join("")}</div></div>`);
  await pause(page, 5000);
}

const SHOTS = {
  async title(page) {
    await card(page, "Diocle", [
      "AI writes the code. Diocle checks it against the original.",
      "Built during the Meta Global AI Developer Hackathon, starting Oct 27, 2026.",
    ]);
  },

  async home(page) {
    await page.goto(SITE, { waitUntil: "networkidle" });
    await overlay(page);
    await pause(page, 2500);
    await scrollPage(page, 900, 20);
    await pause(page, 2500);
    await scrollPage(page, 900, 20);
    await pause(page, 2500);
    await scrollPage(page, -1800, 20);
    await pause(page, 1000);
  },

  async chqclr(page) {
    await page.goto(`${SITE}/#run=${CHQCLR}`, { waitUntil: "networkidle" });
    await overlay(page);
    await page.locator(".trace-cert").first().waitFor();
    await pause(page, 2000);
    const cert = page.locator(".trace-cert", { hasText: "1004/1004" }).first();
    await show(page, cert, 3000);
    const broke = page.locator(".trace-cert", { hasText: "break the Java" }).first();
    await show(page, broke, 3500);
    await show(page, page.locator(".breaker-panel"), 6000);
    const recert = page.locator(".trace-cert", { hasText: "1006/1006" }).first();
    await show(page, recert, 3000);
    const again = page.locator(".trace-cert", { hasText: "match the COBOL" }).first();
    await show(page, again, 3000);
  },

  async delivery(page) {
    await page.goto(SITE, { waitUntil: "networkidle" });
    await overlay(page);
    await nav(page, "Delivery");
    const select = page.locator(".dlv-select");
    if (await select.count()) await select.selectOption(JAVA_DELIVERY);
    await pause(page, 2500);
    await show(page, page.locator(".dlv-stages"), 3000);
    await scrollPage(page, 700, 20);
    await pause(page, 2500);
    await show(page, page.locator(".dlv-pr"), 3500);
    // The pull request Diocle opened: its results table, then the target repository's own CI job (green steps).
    await page.goto("https://github.com/Nivetha200111/quillmark-java/pull/1", { waitUntil: "load" });
    await overlay(page);
    await pause(page, 2000);
    const table = page.locator(".comment-body table").first();
    if (await table.count()) await show(page, table, 5000);
    await page.goto(CI_JOB, { waitUntil: "load" });
    await overlay(page);
    await pause(page, 2000);
    const step = page.getByText("Re-verify every program on fresh inputs").first();
    if (await step.count()) await show(page, step, 3500);
    await page.goto("https://github.com/Nivetha200111/quillmark-java/blob/main/programs/INTACCR/certificate.json",
                    { waitUntil: "load" });
    await overlay(page);
    await pause(page, 2000);
    await scrollPage(page, 500, 15);
    await pause(page, 3000);
  },

  async reverify(page) {
    await page.goto(`${SITE}/#run=${REVERIFY_RUN}`, { waitUntil: "networkidle" });
    await overlay(page);
    const button = page.getByRole("button", { name: "Re-verify on a fresh seed" });
    await button.waitFor();
    await button.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "center" }));
    await pause(page, 1500);
    await click(page, button);
    await page.getByText(/PASS ·/).first().waitFor({ timeout: 120000 });
    await show(page, page.locator(".reverify"), 4000);
  },

  async import(page) {
    await page.goto(SITE, { waitUntil: "networkidle" });
    await overlay(page);
    await nav(page, "Delivery");
    const input = page.locator(".dlv-start input").first();
    await click(page, input);
    await input.pressSequentially(IMPORT_REPO, { delay: 35 });
    await pause(page, 1200);
    await show(page, page.locator(".dlv-start .dlv-note").last(), 3500);
    const start = page.getByRole("button", { name: "Import and convert" });
    await moveTo(page, start);
    await pause(page, 1000);
    if (process.env.DEMO_SUBMIT_IMPORT === "1") {
      await start.click();
      await pause(page, 20000);
    }
  },

  async evaluation(page) {
    await page.goto("https://github.com/Nivetha200111/Diocle/blob/main/docs/EVALUATION.md", { waitUntil: "load" });
    await overlay(page);
    await pause(page, 2000);
    await scrollPage(page, 700, 20);
    await pause(page, 3500);
    await scrollPage(page, 900, 20);
    await pause(page, 3500);
  },

  async closing(page) {
    await card(page, "Diocle", [
      "Everything shown was built during the hackathon, starting Oct 27, 2026.",
      "Meta Muse Spark: translator, repair agent, breaker agent.",
      "diocle.vercel.app · github.com/Nivetha200111/Diocle",
    ]);
  },
};

const wanted = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SHOTS);
await mkdir(OUT, { recursive: true });
// The installed Google Chrome: no separate browser download.
const browser = await chromium.launch({ channel: process.env.DEMO_BROWSER ?? "chrome" });
for (const name of wanted) {
  if (!SHOTS[name]) throw new Error(`unknown shot ${name}; shots: ${Object.keys(SHOTS).join(", ")}`);
  const context = await browser.newContext({ viewport: VIEW, recordVideo: { dir: OUT, size: VIEW }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  try {
    await SHOTS[name](page);
  } catch (e) {
    console.error(`${name}: ${e.message.split("\n")[0]}`);
  } finally {
    const video = page.video();
    await context.close();
    const target = path.join(OUT, `${name}.webm`);
    await rm(target, { force: true });
    await rename(await video.path(), target);
    console.log(`recorded ${target}`);
  }
}
await browser.close();
