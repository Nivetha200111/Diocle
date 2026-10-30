# Demo video plan (3 minutes)

The video is a primary judging artifact (Demo 25%; finalists are ranked live from it). Rules that shape it:
- **Say what was built during the hackathon** (on screen at the start and the end), and show only that.
- Show Meta models doing the work (Use of Meta AI tooling, 25%).
- Everything shown is real and runs on the live site; long waits are sped up and labelled as such.

## The story in one line
"AI writes the code. Diocle checks it against the original before anyone has to trust it", shown on one
program where ordinary testing passed and Diocle still caught the bug.

## Shot list (about 430 spoken words at a calm pace)

| Time | On screen | Narration (draft) |
|---|---|---|
| 0:00-0:15 | Title card: "Diocle. Built Oct 27 to Nov 4, 2026, for the Meta Global AI Developer Hackathon." Then the live Home page. | "Banks still run on COBOL, and AI can now translate it to Java in minutes. On a large migration I worked on, hundreds of people re-checked converted code by hand, because nobody could trust it. Diocle is the check." |
| 0:15-0:40 | Home page diagram, then Live runs list. | "Meta's Muse Spark translates each program. Then Diocle compiles the original COBOL with GnuCOBOL and runs it next to the Java on the same inputs: every output record must match byte for byte, plus the exit code and every line on screen. Nothing is accepted on the model's word." |
| 0:40-1:35 | Live runs → CHQCLR (`chqclr-20261028-214355`): the event timeline. Zoom on: "1004/1004 held-out inputs match", then "Breaker round 1: 2 of 10 designed inputs break the Java", the counterexample (CL-FEE original 20.00, converted 0.00), "Repair agent resumes", "1006/1006", "all 12 designed inputs match". | "This is a cheque-clearing program Diocle had never seen. Muse Spark's Java passed a thousand held-out tests. Most pipelines would ship it here. Diocle then sends a second Muse Spark agent, the breaker, to design inputs that should expose a difference. Two of ten do: the COBOL charges a 20 dollar fee, the Java charges nothing. The repair agent gets those as failing tests, patches the Java with real compiler and test tools, and it re-certifies on a fresh thousand inputs. The breaker attacks again and finds nothing." Caption: "Inputs with malformed numbers; agreement shown is with GnuCOBOL." |
| 1:35-2:05 | Delivery page: quillmark-mainframe → quillmark-java, six programs certified, PR #1 with CI "SUCCESS". Cut to the GitHub PR: certificate.json and the green reverify check. | "Certified programs go out as a pull request, each with an equivalence report. The target repository's own CI recompiles the COBOL and re-runs both on fresh inputs Diocle never used, so the reviewer doesn't have to trust Diocle either." |
| 2:05-2:20 | Live runs → a certified run → press "Re-verify on a fresh seed" → "PASS 1019/1019 … 1.9 s". | "Anyone can check it themselves: this button reruns both programs on a seed chosen right now." |
| 2:20-2:40 | Delivery → "Import a repository" with a real public COBOL repo, Start → the live stages (sped up, labelled "8x"). | "And you can bring your own: paste any public COBOL repository. Your code runs in a sandbox with no network and no credentials; Muse Spark converts it while you watch." |
| 2:40-2:52 | EVALUATION.md table, then the README correction. | "We measure ourselves too: on four unseen programs, and when an outside review found our comparator was too lenient, the stricter check caught a real sign-of-zero bug we had shipped. We published that." |
| 2:52-3:00 | Closing card: "Built during the hackathon: everything shown. Meta Muse Spark: translator, repair agent, breaker. github.com/Nivetha200111/Diocle · diocle.vercel.app" | "Diocle. AI writes the code; Diocle checks it." |

Keep the employer unnamed ("a large migration I worked on"), and the bank fictional (Quillmark Trust & Savings).

## Before recording (checklist)
- [x] CHQCLR and the other evaluation runs are on the live site; CHQCLR re-verifies there (1004/1004).
- [x] Live runs has a Breaker panel listing each counterexample (input, the agent's reason, what differed).
- [ ] INTACCR re-delivery PR on quillmark-modern merged and CI green (optional shot).
- [ ] Evaluation re-run (`eval-freeze-2`) added to EVALUATION.md, so the 2:40 shot shows both runs.
- [ ] One visitor import done beforehand on the repo you'll show (costs a few cents), so its finished result can
      be cut in after the live start.
- [ ] Browser: full screen, 1920x1080, zoom 110-125 %, bookmarks bar hidden, one tab, notifications off
      (Focus mode), cursor highlight on if available.

## The submission cut: `demo/promo/out/diocle-submission.mp4`, 2:05
Shaped for how judges watch (many videos back to back; a rubric; the final round watched live in a room):
- **First 5 seconds earn attention:** cold open on the climax ("It passed 1,004 tests." → 20.00 ≠ 0.00 → "It was
  still wrong."), a question the viewer wants answered, before any context.
- **One clear beat per rubric criterion:** Impact (firsthand migration story; today vs with Diocle), Use of Meta AI
  (three Muse Spark agents: one writes, one attacks, one repairs; private mode on Muse Spark Open), Technical depth
  (the judge is the original program, byte for byte), Demo (real clicks, a live PASS).
- **Novelty over "AI converts COBOL":** agents attacking their own code is what most entries won't have.
- **Credibility:** real numbers only, the honest evaluation and our own bug stay in (admitting a flaw raises trust).
- **Peak and end:** the breaker reveal is the peak; the end is impact plus "Try it now", not just a logo.
- **Rules:** "Built Oct 27 – Nov 4" at both ends.

Composition `Submission`: ColdOpen · Hook · Brand · Agents · HowItWorks · live click-through · PrivateMode · Honest
· Impact · TryNow.

Narration timed to it (about 280 words, calm; the picture carries the rest):

| Time | Narration |
|---|---|
| 0:00 | (no voice; let the cold open hit) |
| 0:05 | "Banks still run on COBOL. On a migration I worked on, hundreds of people re-checked converted code by hand. AI can write the Java in minutes. So who checks the AI?" |
| 0:13 | "This is Diocle." |
| 0:17 | "Three Meta Muse Spark agents. One writes the Java. One attacks it. One repairs it. And the judge isn't a model: it's the original program, run next to the Java, where every byte must match." |
| 0:27 | "Muse Spark translates; GnuCOBOL runs the original; if anything differs, the repair agent fixes the Java until it certifies on inputs it has never seen." |
| 0:39 | "We let AI rewrite a bank's programs, then tried to break them. This is the live product: a cheque-clearing program passed one thousand and four unseen tests." |
| 0:58 | "Then the breaker designed inputs to break it. Two did: the COBOL charges a twenty-dollar fee; the Java charges nothing. The repair agent fixed it, and it re-certified." |
| 1:10 | "Don't trust us: press Re-verify, and both programs run again on a seed chosen right now." |
| 1:17 | "Certified code ships as a pull request with an equivalence report, and the target repository's own CI checks it again. Or paste any public COBOL repository and watch it convert." |
| 1:31 | "Banks can't send code to a hosted API, so the same agents run on Muse Spark Open, Meta's open weights." |
| 1:39 | "We test ourselves too: a frozen evaluation with failures published, including a bug our own stricter check caught." |
| 1:48 | "Today, people re-check converted code by hand. With Diocle, every program arrives with proof anyone can re-run in seconds." |
| 1:57 | "Diocle. Try it now. Built during the hackathon, with Meta Muse Spark." |

Then: `demo/finish.sh voiceover.m4a` (captions from the voice, sound effects kept under it) → `final.mp4`.

## The promo (what we use now)
- `demo/capture.mjs` takes crisp 2x captures of the live site and GitHub, presses Re-verify for real, and writes
  every number the video shows to `demo/promo/src/data.json` (from the live API; nothing typed by hand).
- `demo/promo` is the video as code (Remotion 4.0.535, free for individuals): kinetic-type hook, brand reveal,
  animated "how it works" diagram, the CHQCLR story (held-out pass, breaker breaks it, 20.00 vs 0.00, repair agent
  tools, re-certified), delivery (PR table + CI), try it (live re-verify result, visitor import), honest
  evaluation, outro with "built during the hackathon". Render: `cd demo/promo && npm install && npm run render`
  (out/promo.mp4, 1080p). Preview and tweak: `npm run studio`. Scene lengths: `SCENES` in `src/Promo.tsx`.
- `demo/finish.sh voiceover.m4a`: captions from the voice with whisper.cpp (offline, `brew install whisper-cpp`,
  model `ggml-base.en.bin` in `~/.cache/whisper`), then video + voice (loudness-normalised) + captions =
  `demo/promo/out/final.mp4`.
- Order: record the voiceover from the narration above, retime `SCENES` to it, render, then finish.sh.

## The click-through video (vertical, for Instagram Reels / Shorts / X)
- `demo/capture-clicks.mjs` clicks through the live site for real (Live runs → CHQCLR → Re-verify → Delivery →
  the pull request → typing a repository into the import form) and saves each state as a full-page 2x screenshot
  with the page position of everything clicked (`demo/promo/src/clicks.json`).
- `ClickDemo` in `demo/promo` (1080x1920, 52 s): animated cursor with press and ripple, camera that follows the
  cursor and fits each highlighted element, typing revealed from the real typed screenshot, glowing highlights,
  result badges in one fixed slot, bold two-line captions, five-step progress bar, outro. Sounds in
  `public/sfx` are synthesised with ffmpeg (click, typing, whoosh, success, pop): no licensing. Peak -5 dB.
- Render: `cd demo/promo && npx remotion render ClickDemo out/click-demo.mp4 --codec=h264 --crf=16`.
- Music: add a trending track inside Instagram/TikTok when posting (licensed there); keep it under the clicks.

## The click-through video, 16:9 for YouTube
- `ClickDemoWide` (1920x1080, 58 s): same real clicks and beats as the vertical cut. Cinematic intro, then an
  editorial split: chapter tag, caption and result badge on the left; a browser window with the real address bar
  on the right, zooming into every click (with a small punch on each click) and a motion-blurred cursor; chapter
  progress along the bottom; outro with "built during the hackathon".
- Render: `npx remotion render ClickDemoWide out/click-demo-youtube.mp4 --codec=h264 --crf=15`.
- Music: put a licensed track at `demo/promo/public/music.mp3` (for example from the YouTube Audio Library) and
  re-render; it is mixed under the clicks automatically, with fades.

## Scripted recording (first attempt, kept for reference)
- `demo/record.mjs` (Playwright, drives the installed Google Chrome) plays each shot against the live site and
  records it: `cd demo && npm install && npm run record` (or `npm run record -- chqclr` for one shot). It adds a
  visible cursor, smooth scrolling and a yellow frame around what the narration talks about. The import shot
  fills the form but does not submit unless `DEMO_SUBMIT_IMPORT=1` (a real import spends model credits).
- `demo/build.sh` (ffmpeg) crops and scales each clip to 1920x1080 and joins them: `demo/out/rough-cut.mp4`.
  `demo/build.sh voiceover.m4a [captions.srt]` lays the narration (loudness-normalised) and burned-in captions
  over it: `demo/out/final.mp4`. Shot trims and speed changes are one line in `SHOTS` in build.sh.
- Chrome's screencast squeezes the page into the top 1280x640 of each 1280x720 frame; build.sh corrects it.

## Recording by hand (fallback), free tools only
- Screen: macOS **Cmd+Shift+5** (Record Entire Screen or Selected Portion). Record each shot separately.
- Voice: record the narration separately with a headset or the phone (quiet room); read the script, then cut.
- Edit: **iMovie** (free): line up the clips under the voice, add the title and closing cards, label speed-ups,
  export 1080p. Target 2:50 to leave margin under 3:00.
- Captions: add the narration as subtitles (judges may watch muted).
- Upload as unlisted on YouTube (or as the submission form asks), and post it on X after submitting (Community Vote,
  Most Viral).

## Timeline
- Oct 29-30: finish the checklist; record a rough cut and watch it once as a judge would.
- Oct 31-Nov 1: final narration and edit; ask one person to watch it cold and say what Diocle does.
- Nov 3: final export; Nov 4 morning IST: submit (deadline Nov 5, 6:30 AM IST).
