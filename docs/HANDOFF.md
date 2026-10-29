# Hand-off: where Diocle stands and what is next

Read this first in every session; update it as you build (see CLAUDE.md, "Session hand-off").
Newest state at the top of each section. Dates are 2026, times IST unless marked UTC.
This repository is public: never write secrets, passcodes, personal details or employer names here.

## Current state (updated 2026-10-29)

**Judge-facing pass (Oct 29, from an outside scoring review).** Web: front page shows CHQCLR's COBOL next to its
certified Java with a verdict strip replaying the breaker story and **Try the sample** (public re-verify on a fresh
seed; tested against the live engine: 1,004/1,004 in 1.8 s); "Powered by Meta Muse Spark" in the top bar; per-run
model card (role, model ID, tokens, cost); private-mode badge; Evidence page (`/evidence`) citing
**quillmark-modern#4 as the one canonical delivery** (6 programs, 6,719 fresh CI inputs, 0 differences, about $0.13);
one URL per view (`/`, `/runs`, `/delivery`, `/evidence`); skeleton loaders, 5-column runs table, glossary
tooltips, honest failure reasons (none of the three failed deliveries was a verifier refusal: two certified every
program and then hit engine errors, the third was the visitor import stopped for the security fix), interrupted and
superseded runs labelled. A reviewer pass found and we fixed: `/runs` was git-ignored (the `runs/` rule; now
`/runs/`), visitor runs saved before the marker (now detected by their sample), timezone-sensitive "interrupted"
(now decided by the engine), and wording that overstated the recorded CHQCLR result. README: canonical #4, the `openai` package note,
coding-agent disclosure. HACKATHON_RULES deadline corrected (Nov 5, 7:30 AM IST).
- **Copybooks as SQL (Oct 29, plan step 3, built on the Windows laptop):** `diocle_verifier.sqlschema` (contract
  `contracts/sql-schema.schema.json` v0.1) writes one table per file layout (`DECIMAL(p,s)` from the PIC, CHECK on
  unsigned, COMP-5 by its bytes, REDEFINES and OCCURS stated) and proves it per record: values checked against the
  published column types, then a byte-exact SQLite round trip. All 24 tables of the 11 sample and evaluation
  programs pass on generated records, and PKDPOST's golden files pass after EBCDIC conversion. A reviewer pass found
  the first version did not check scale or length, mixed up repeated FILLERs and cached failures; all fixed, with
  tests. `GET /runs/{id}/schema` serves it (cached per sample, visitor runs withheld); the front page and Live runs
  show `schema.sql` next to the Java. Tested end to end
  locally against a local API. **Needs an engine deploy** to show live: on the Mac, `git pull && deploy/update-engine.sh`
  (until then the tab is simply absent).
- **Engine deployed Oct 29 evening at c3420eb** (`/source` and `/schema` answer 200). `deploy/update-engine.sh` fails under
  macOS `sh` (`$HOST…` is read as part of the name; use `${HOST}...`); run a patched copy until fixed.
- **Spark Open cross-checker built (Oct 29 night, Mac; run contract v0.10; NOT yet run live, NOT deployed):**
  `services/converter/diocle_converter/crosscheck.py` + `--crosscheck` flag. After certification Muse Spark Open
  proposes inputs and names suspected fields; every input runs through GnuCOBOL vs Java, its opinion certifies nothing,
  a real mismatch goes to the repair agent. Own hard cap (`CROSSCHECK_MAX_CALLS`, default 2), skipped with a reason if
  unconfigured / already on the open model / multi-file / host down. Calls merge into the run's usage (cost now priced per
  call by its own model). Run JSON `crosscheck`, API pass-through, web panel + "Independent check" row in the model card.
  Opt-in (costs ~$0.05 per run on Fireworks/Baseten). To try: put `OPEN_MODEL_*` in `.env`, then
  `python -m diocle_converter run ../../samples/interest-accrual --crosscheck`. The `guard-agent` branch also claims run
  contract v0.10; renumber one of them to v0.11 when merging.
- **Loyalty-waiver breaker run (Oct 29 evening, Mac, `loyalty-waiver-20261029-190213`, local only, not seeded to the engine):**
  certified at round 0 (1013/1013, stdout matches), no repair needed. The breaker found nothing: 8 designed inputs matched
  (4 rejected as invalid for the layout), then 0 valid in rounds 2 and 3. 4 model calls, est. $0.012. So the breaker stays
  unproven on this sample: no red to repair, and the 5000.00 boundary was not shown to be missed. Use CHQCLR's
  20.00 vs 0.00 as the red, repair, certified story.
- **Reviewed and rebased Oct 29 evening:** reviewer pass on the JCL-job commits found two blockers, both resolved. The
  analyzer had marked DISPLAY-only and OPEN I-O programs convertible with no verifier support, so those commits
  (9e8d697, b70bc64, c1b5c3b, kept on local branch `backup-pre-rebase`) were NOT pushed; item 1 of CLAUDE.md "Current
  priority" is still open. The duplicate copybook-DDL commit (f031fe0) was dropped in favour of the upstream
  `sqlschema`. SORT keys are CH only (ZD/PD/BI refused). The JCL job check (`verify_job`) is not deployed to the engine.
- Engine deployed after the judge-facing pass (checked Oct 29: `GET /runs/{id}/source` answers 200, Try the sample
  re-verified 1,004/1,004 in 1.8 s on the live site).
- Windows note: building the web app in Git Bash rewrites `NEXT_PUBLIC_DIOCLE_API_URL=/api` into a Windows path;
  set `MSYS2_ENV_CONV_EXCL=NEXT_PUBLIC_DIOCLE_API_URL` (`MSYS_NO_PATHCONV=1` breaks next's cwd; Vercel is unaffected).

**Pitch.** Diocle is a verification layer for AI-written COBOL→Java: "AI writes the code. Diocle checks it
against the original before anyone has to trust it." Never claim proof for all inputs (README, "What certified
means and does not"). Meta Global AI Developer Hackathon, Indie track, submit by **Nov 4, 9 PM ET**.

**Live product.**
- Site: https://diocle.vercel.app (Vercel Hobby, project root `apps/web`, env `NEXT_PUBLIC_DIOCLE_HOSTED=1`,
  `NEXT_PUBLIC_DIOCLE_API_URL=/api`, `DIOCLE_API_ORIGIN=https://65-20-92-159.sslip.io`). Vercel redeploys on
  every push to `main`.
- Engine: Vultr, Mumbai, Ubuntu 24.04, 1 vCPU / 2 GB, IP `65.20.92.159`, HTTPS at `65-20-92-159.sslip.io`
  (sslip.io + Caddy; no domain bought). Code in `/opt/diocle`; config in `/opt/diocle/deploy/diocle.env`
  (secrets, root-only, never print it) and `/opt/diocle/deploy/.env` (`DIOCLE_API_DOMAIN`).
- Containers (`deploy/docker-compose.api.yml`): `api` (holds secrets), `sandbox` (no secrets, internal network
  only, read-only rootfs), `caddy`. Update: `ssh root@65.20.92.159`, `cd /opt/diocle && git pull && cd deploy &&
  docker compose -f docker-compose.api.yml up -d --build`. Rebuilding restarts the api and kills a running
  delivery.
- SSH key `~/.ssh/diocle` exists only on the original Mac. On a new machine: create a key
  (`ssh-keygen -t ed25519 -f ~/.ssh/diocle`), add the `.pub` in the Vultr console (server → Settings → SSH keys,
  or use the Vultr web console to append it to `/root/.ssh/authorized_keys`).
- Seeded data: 19 runs on the engine as of Oct 29 (16 certified, 1 interrupted) and 4 deliveries via `deploy/seed-runs.sh root@65.20.92.159`. Public
  re-verify checked on 11 runs, all pass in about 2 s each.
- Admin passcode (`DIOCLE_ADMIN_TOKEN`) was generated on the server; the owner has it. It unlocks
  "Deliver as a pull request" on the Delivery page.

**Visitor imports: ON since 2026-10-28 ~23:50 IST** (`DIOCLE_PUBLIC_IMPORTS=1` on the server; owner's
decision). To switch off: set it to 0 in `deploy/diocle.env` and `docker compose -f docker-compose.api.yml up -d`. Goal from the owner: judges must be able to *use* it, i.e. import any public
GitHub repo and have Muse Spark convert it, open access without a passcode, but secure.

How it works now:
- `POST /deliveries` without a passcode starts a visitor import (any public repo, no target, no PR) when
  `DIOCLE_PUBLIC_IMPORTS=1` and the sandbox is configured. Limits in `services/api/diocle_api/public.py`:
  budget over a rolling 24 h (fails closed on unpriced runs), 3 per visitor per day (best effort), 3 programs
  x 1500 lines, one job at a time (start lock, record written before the response, dead jobs marked failed).
- Visitor runs: `--memory-read-only`, no `GH_TOKEN`, a `visitor` marker file in the run dir (run contract
  v0.8 `visitor`), labelled in Live runs, refused by public re-verify.
- Sandbox (`services/verifier/diocle_verifier/sandbox.py`): `verify_sample` posts the sample + Java (regular
  files only) to `http://sandbox:8100/verify`; the job runs as `nobody` in a private tmpfs, returns the report
  on stdout; afterwards the root server (caps SETUID/SETGID/KILL only) kills every other process until none is
  left and deletes the job's files. No secrets, no volumes, internal network only, read-only rootfs, busy
  answers 503 (callers retry within `DIOCLE_SANDBOX_WAIT`), job timeout 300 s. The api refuses requests from
  the sandbox's address.
- Analyzer clones with `core.symlinks=false`, 300 MB cap, `DIOCLE_IMPORT_ANY=1` only for visitor runs; a
  second file with the same PROGRAM-ID is skipped.

Security reviews (reviewer agent): first review found 7 issues (symlink exfiltration of secrets via a shared
work volume, surviving processes, sandbox reading all runs, start race, stuck jobs, visitor runs writing fix
memory, budget gaps); a re-review confirmed all 7 fixed and found N1-N5 (job and server shared a uid, FIFO
report wedge, sandbox queue DoS, self-forged reports, sandbox reaching the api); all fixed in a893171..e1fca29.
Live attack test 2026-10-28 with a hostile Java program (symlink outputs to /proc/1/environ, print env,
SIGSTOP the server, forking background loop): server was not stopped (only the job froze itself), see
"Done recently" for the outcome. Known accepted risk: a program can forge its *own* report; contained by the
visitor label, read-only memory and no public re-verify.

Before turning visitor imports on: confirm the attack test outcome, re-verify works, then on the server
`sed -i "s/^DIOCLE_PUBLIC_IMPORTS=0/DIOCLE_PUBLIC_IMPORTS=1/" deploy/diocle.env` and
`docker compose -f docker-compose.api.yml up -d`. Owner decides.

Known gap: programs that only DISPLAY (no output file) are skipped as "writes no output file to compare";
stdout could be compared. Seen on github.com/openmainframeproject/cobol-programming-course (17 of 34 programs
convertible; EXEC SQL ones correctly refused). Good test repo for visitor imports.

### Verifier correctness (independent review, 2026-10-28 late evening)
- **Fixed:** the comparator paired output records with inputs (aggregation / fan-out programs failed even when
  both sides agreed) and compared numeric fields by parsed value (+00 == -00). Now: whole output sequence by
  position, byte for byte (line records may differ only in trailing spaces), field parsing only explains a
  difference (report contract v0.6, `inputSource: "output"`, fieldDiffs `note`). Commits 08d282e, d08064e.
- **Consequence:** re-verifying every certified run found `intaccr-20261028-191523` differs (-000000000 vs
  +000000000 on 30/1019 inputs). It is the INTACCR delivered in **quillmark-modern#3 (merged)**. quillmark-java's
  INTACCR (`intaccr-20261028-194951`) and all other runs pass. README carries a correction. Pending owner
  decision: re-deliver INTACCR to quillmark-modern from the clean run
  (`python -m diocle_api.deliver https://github.com/Nivetha200111/quillmark-legacy
  https://github.com/Nivetha200111/quillmark-modern --programs INTACCR --runs intaccr-20261028-194951`; needs
  GH_TOKEN; opens a PR whose CI uses the new verifier commit).
- Breaker evidence: CHQCLR (eval) was certified on held-out inputs, then the breaker broke it twice (fee 20.00
  vs 0.00, debit -121.23 vs 0.00) on malformed numeric input; repaired and re-certified. README updated.
- Delivery page CI status now comes from GitHub's REST API (03fa503); it used a gh CLI the server lacks.
- Frozen evaluation (`eval-freeze-1`) ran with the OLD comparator throughout (the LOANAMRT converter process
  started 22:12, before the change). Publish it as-is in `docs/EVALUATION.md`, then run a corrected follow-up
  with the new comparator and report both; LOANAMRT's round-3 failures are "extra output record" (fan-out).

### Videos (Oct 29)
- **Submission video:** `demo/promo/out/diocle-final.mp4` (2:05, 1080p): Remotion composition `Submission`, shaped
  for judges (cold open on 20.00 ≠ 0.00, three Muse Spark agents, judge diagram, live click-through, private mode,
  honest evaluation, impact, "Try it now"); synthetic narration (Kokoro, `demo/voiceover.py`) with captions; end
  card discloses the synthetic voice. Other cuts: `click-demo-youtube.mp4` (16:9), `click-demo.mp4` (9:16 for
  X/Reels), `promo.mp4`. Videos are gitignored; copies are in the owner's private `diocle-handoff` bundle.
- Pipeline: `demo/capture.mjs` and `demo/capture-clicks.mjs` (real captures + numbers from the live API) →
  `demo/promo` (Remotion) → `demo/voiceover.py` → loudnorm. See docs/DEMO_PLAN.md.
- Done: fresh private-mode run on Muse Spark Open (interest-accrual-20261029-084702) is in the video and evidence;
  quillmark-modern PR #4 merged with CI green.
- To do (review's suggested re-cut, 2:50): human opening in the owner's own voice (or keep the synthetic-voice
  disclosure), Meta credit by 0:30, real capture of the new front page: COBOL next to Java, Try the sample, breaker
  red → repair → certified, then #4's CI, private mode, evaluation 2/4 → 4/4, visitor import, end card with build
  dates. Record after the engine deploy above so the Java pane is filled.
- Evaluation re-run done: 4/4 certified, memory off (docs/EVALUATION.md).
- Prizes: post the vertical cut on **X** right after submitting (Most Viral counts engagement until Nov 8).

## Open work (priority order)
- **Plan for Oct 29 to Nov 1: CLAUDE.md, "Current priority"** (dependencies: display-only and I-O programs,
  whole JCL jobs, then DB2 if time; copybook to SQL schema is done). Do it on the Mac; deploy the engine first.
0. Deploy the engine again for the SQL tab (above), then re-shoot the video against the new front page. After submitting: freeze deploys
   until judging ends (Nov 5-9), add an uptime monitor, and watch that visitor imports don't drain the credits.
1. Watch visitor imports (spend in `/api/config`, deliveries list); finish the two in-flight jobs above.
2. **Done (v1 scope only, see below).** Roadmap item 2, "whole JCL job end to end," is built and tested for
   exactly one shape: one SORT step feeding one COBOL step. Not yet done: wiring `verify_job` into the
   `diocle_verifier` CLI or `verify_sample()`'s auto-dispatch (it is a standalone function today, called
   directly — see services/verifier/README.md), `services/converter/README.md` documenting `run-job`/
   `sortgen.py`/`pipeline.py` (that update was not part of the converter-agent's committed work and is still
   owed), and every "not supported yet" item listed under "Done recently" below (3+ step jobs, multiple SORT
   steps, COND-gated steps, GDG arithmetic beyond exact-DSN match, SORT INCLUDE/OMIT/OUTREC/INREC/SUM
   FIELDS=/MERGE). Next roadmap item: copybook to SQL schema (CLAUDE.md item 3).
3. Evaluation: frozen run finished and published in `docs/EVALUATION.md` + `eval/results-eval-freeze-1.json` (2/4 certified;
   BRNCHSUM and LOANAMRT failed because the old comparator rejected aggregation/fan-out; their final Java passes
   the corrected comparator on fresh seeds). Next: full re-run with the corrected verifier under a new tag
   (`eval-freeze-2`), reported next to the original. Costs about $0.3.
4. Breaker test on `samples/loyalty-waiver`: run once Oct 29, found nothing (see Current state). The breaker is
   still unproven until it finds a defect other inputs missed.
5. Demo video (under 3 min): one visible failure and repair on the live site, then re-verify.
6. A review from a COBOL maintainer (owner arranges). Module README consistency.

## Done recently
- 2026-10-29: **Roadmap item 2, whole JCL job end to end (v1 scope: one SORT step feeding one COBOL step),
  all three passes done and cross-checked together** (d28a04a analyzer, cc3f3ae converter, 20a0bc0
  verifier — see each commit for its own module's detail). The analyzer groups JCL steps into jobs and
  reports convertibility (`jobs[]`, refuses anything beyond the v1 shape with a specific reason); the
  converter generates a deterministic Java SORT-emulation class plus one driver per job that runs steps via
  `ProcessBuilder` with the same DD-env-var convention the verifier already used; the verifier's new
  `diocle_verifier.jobs.verify_job()` runs both sides end to end on the same seeded external input
  (`SORTIN` only — internal hand-offs like `SORTOUT`/`TXNIN` are produced by actually running the SORT step,
  never seeded directly) and compares every step's output dataset, tagging each result with the step that
  produced it so a failure names a specific step, not just an aggregate. Proven on the real
  `samples/account-match/jcl/QMKD010.jcl` fixture: positive end-to-end test certifies `SORTOUT`, `NEWMST`
  and `EXCOUT` all match; a negative test deliberately corrupts the generated SORT class's comparator and
  confirms the job reports `certified: false` with `SORT005` specifically named, not a vague failure.
  `contracts/verification-report.schema.json` v0.7 adds additive `jobs[]` (one entry per job: per-step
  pass/fail, results tagged with `step`, run metadata, one `certified` bool). Full three-service suite after
  the change: analyzer 33, converter 40, verifier 38 passed (111 total), all green.
- 2026-10-28: hosted on Vercel + Vultr; fixed `GET /runs` crash on a latin-1 byte (d5e0ecb) and macOS `._*`
  files breaking re-verify (9d8d149); visitor imports built then paused (above).
- quillmark-modern PR #3 (refreshed 6-program delivery, CI green on 6,714 fresh inputs) merged.
- quillmark-java PR #1 merged (from quillmark-mainframe, a z/OS-style PDS export), CI green on 6,709 inputs.
- Earlier history: `docs/BUILD_LOG.md`.

## Repositories (all public, owner Nivetha200111)
Diocle (product); quillmark-legacy → quillmark-modern; quillmark-mainframe → quillmark-java. The bank
"Quillmark Trust & Savings" is fictional and all data is synthetic.

## Working agreements with the owner
- Budget is very tight: flag any cost before incurring it; prefer free tiers. Vultr is about $12/month.
- Secrets: never ask for keys in chat, never read or print `.env` / `diocle.env`; the owner types secrets on
  the server.
- Before every push: `git log origin/main..HEAD`; push only your own commits; ask if others' are present.
  The owner's local edits to `apps/web/next-env.d.ts` and `apps/web/tsconfig.json` are theirs: leave them.
- Small commits, one module each, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run every touched module's tests (and `npx tsc --noEmit` + `next build` for web) before committing.
- Use the reviewer agent on security-sensitive or large batches of work; it has found real bugs every time.
- The product should look like a real product (no "demo" wording), keeping the 90s retro operator-console look.
- Account creation, payments and repo visibility changes are done by the owner, not by Claude.
