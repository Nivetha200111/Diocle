// Renders the v13 candidate's captions and corrected stamps to full-frame transparent PNGs. No footage is invented: these go
// over the unchanged v12 picture. Usage: CHROME=/path/to/chromium node overlays.mjs OUT_DIR PLAYWRIGHT_DIR
import { createRequire } from 'module';
const [out, pw] = process.argv.slice(2);
const { chromium } = createRequire(pw + '/')('playwright');
const FONT = `<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>*{box-sizing:border-box}html,body{margin:0;width:1920px;height:1080px;background:transparent;font-family:'IBM Plex Sans',sans-serif}
.bar{position:absolute;left:44px;right:44px;background:#f6f2e8;border:5px solid #8c1c13;border-radius:8px;padding:18px 28px;color:#17130c}
.bar b{display:block;font-size:44px;line-height:1.14;color:#8c1c13;font-weight:700}.bar span{display:block;font-size:31px;line-height:1.26;margin-top:6px}
.info{border-color:#1f5c3a}.info b{color:#1f5c3a}
.stamp{position:absolute;width:668px;height:182px;display:flex;flex-direction:column;justify-content:center;background:#f6f2e8;border:6px solid #8c1c13;border-radius:12px;text-align:center;color:#8c1c13;transform:rotate(-5.7deg);box-shadow:0 5px 0 #6e140e}
.stamp b{display:block;font:700 62px/1.05 'IBM Plex Mono',monospace;letter-spacing:3px}.stamp span{font:600 26px/1.2 'IBM Plex Mono',monospace;color:#3a2b20}
.patch{position:absolute;background:#f4f1e8;font:700 37px/56px 'IBM Plex Sans';color:#17130c;padding-left:4px}
.card{position:absolute;inset:0;background:#f4f1e8;padding:56px 82px;color:#17130c}.card small{font:400 22px 'IBM Plex Mono',monospace;letter-spacing:1px;color:#444;display:block;border-bottom:2px solid #555;padding-bottom:14px;margin-bottom:34px}
.card h1{font-size:66px;margin:0 0 30px;line-height:1.08}.card p{font-size:46px;line-height:1.24;margin:0 0 26px}.card p b{color:#1f5c3a}.card p.no b{color:#8c1c13}.card .open{font-size:32px;color:#333;margin-top:30px;font-family:'IBM Plex Mono',monospace}
</style>`;
const O = {
  'patch-passed': `<div class="patch" style="left:58px;top:452px;width:590px;height:56px">about 1,000 generated records</div>`,
  'patch-broken': `<div class="patch" style="left:58px;top:452px;width:590px;height:56px">differed under attack</div>`,
  'hook-stamp': `<div class="stamp" style="left:1185px;top:153px"><b>DIFFERS</b><span>CL-FEE · COBOL 20.00 · Java 0.00</span></div>`,
  'hook-stamp-slam': `<div class="stamp" style="left:1185px;top:153px;transform:rotate(-5.7deg) scale(1.18)"><b>DIFFERS</b><span>CL-FEE · COBOL 20.00 · Java 0.00</span></div>`,
  'hook-bar': `<div class="bar" style="left:26px;right:26px;top:876px;height:198px"><b>Matched on 1,004 generated records. Differed on a malformed one.</b><span>CHQCLR, stored run. The fee field held a space where PIC 9 expects a digit. Under GnuCOBOL; IBM not tested. Repaired, then matched on 1,006.</span></div>`,
  'hood-malformed': `<div class="bar" style="bottom:92px"><b>The three inputs: letters where numbers belong.</b><span>Malformed data designed by Muse Spark, compared under GnuCOBOL. Not ordinary transactions; IBM not tested.</span></div>`,
  'hood-stamp': `<div class="stamp" style="left:1203px;top:159px"><b>DIFFERS</b><span>COBOL ABCDEFGH · Java 12345678</span></div>`,
  'hood-stamp-slam': `<div class="stamp" style="left:1203px;top:159px;transform:rotate(-5.7deg) scale(1.18)"><b>DIFFERS</b><span>COBOL ABCDEFGH · Java 12345678</span></div>`,
  'hood-weak': `<div class="bar info" style="bottom:92px"><b>A weak check for this program, and we fixed it.</b><span>Its generated records then had zero amounts. Generator fixed Nov 1; this Java then matched on 1,000 well-formed records with real amounts.</span></div>`,
  'ci': `<div class="bar info" style="bottom:92px"><b>The same comparison, re-run by this repository's CI.</b><span>Fresh inputs, pinned verifier, under GnuCOBOL. It re-checks the result; it shares the verifier's assumptions and is not a formal proof.</span></div>`,
  'measured': `<div class="bar" style="bottom:92px"><b>4 of 10, by the breaker's stated reasons: 1 on malformed data, 3 on a negative-zero sign byte.</b><span>37/45 counts attempts and 14/15 programs, so this is not model vs Diocle. CHQCLR was not certified in this run, and was in others with different settings. One model, small sample.</span></div>`,
  'limits': `<div class="card"><small>WHAT IT SHOWS, AND WHAT IT DOES NOT</small><h1>Evidence on the inputs tried, not a formal proof.</h1>
    <p class="no"><b>Not shown:</b> every possible input, or IBM Enterprise COBOL.</p>
    <p class="no"><b>Stand-ins:</b> SQLite for DB2, Berkeley DB for VSAM.</p>
    <p class="no"><b>Still yours:</b> code review, real data, acceptance on your runtime.</p>
    <p class="open">Synthetic programs. Model spend only; compute, hosting and review not measured.</p></div>`,
  'end': `<div class="patch" style="left:0;right:0;top:860px;height:60px;font:600 30px/60px 'IBM Plex Mono',monospace;text-align:center;background:transparent;color:#1f5c3a">No key? sh scripts/quickstart.sh --no-key re-checks stored Java with no model call.</div>`,
};
const b = await chromium.launch({ executablePath: process.env.CHROME });
const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
for (const [name, html] of Object.entries(O)) {
  await p.setContent(`<!doctype html><html><head>${FONT}</head><body>${html}</body></html>`, { waitUntil: 'networkidle' });
  await p.screenshot({ path: `${out}/${name}.png`, omitBackground: true });
}
await b.close();
