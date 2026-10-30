# Hand-off: where Diocle stands and what is next

Read this first in every session; update it as you build (see CLAUDE.md, "Session hand-off").
Newest state at the top of each section. Dates are 2026, times IST unless marked UTC.
This repository is public: never write secrets, passcodes, personal details or employer names here.

## Convert anyway (Oct 30, branch `convert-anyway` on origin/main 59c9ff9, local, NOT pushed or deployed)
- **What:** opt-in mode (`--convert-anyway` or `DIOCLE_CONVERT_ANYWAY=1`; admin or local CLI only) so no program is refused. Contracts first:
  run v0.14 (`assurance`, `assuranceReason`, `cobolRepair`), delivery v0.4 (`convertAnyway`, `repoMaxUsd`, `spentUsd`, per-program `assurance`/`costUsd`).
  Labels: `certified` | `certified-against-repaired-cobol` | `compiled-unverified` | `failed`; only the first sets `certified: true`, so every
  existing "N certified" count is unchanged and the web shows the others as their own badges/counts.
- **How:** analyzer `--convert-anyway` writes a non-certifiable sample (`convertAnyway.reason`, missing copybooks). Converter: refused programs are
  translated with `TRANSLATOR_ANYWAY` (labelled `// ADAPTER REQUIRED` interfaces, no invented DB behaviour), `javac`-compiled with <= 3 model fix
  rounds, never run (`anyway.py`, `_finish_unverified`). An original that does not compile under `-std=ibm` is repaired first
  (`cobolrepair.py`): deterministic missing-period fix, else a bounded Muse loop (`compile_cobol`/`patch_cobol`), rule enforced in code (<= 20 lines and <= 10% of the
  file; PROCEDURE DIVISION edits only within 2 lines of a diagnostic); patched copy `<name>.repaired.cbl`, the user's file untouched; Java is then verified
  against the patched COBOL and labelled `certified-against-repaired-cobol`. If the patch fails: translate the broken COBOL, compile-check only.
  Spend: per-run `--max-usd` (client refuses the next call over it; unknown price fails closed) and `REPO_MAX_USD` (default 1.00) across the delivery
  (sequential in this mode), skipped programs say "repo spend cap reached". Local command: `python -m diocle_converter repo PATH_OR_URL --convert-anyway` (README).
- **Visitors cannot enable it:** `--public --convert-anyway` is an error, the visitor job and `start_delivery` strip `DIOCLE_CONVERT_ANYWAY`, `POST /deliveries`
  with `convertAnyway` and no passcode is 403 (tests in `services/api/tests/test_convert_anyway.py`).
- **Tests:** analyzer 84, converter 177, verifier 96, api 62 (+1 skipped), web `tsc --noEmit` and `next build` clean. Screenshots of the badges rendered via Playwright against a labelled stub engine.
- **Not done / not claimed:** not deployed (engine needs `deploy/update-engine.sh`); programs that compile but never terminate are not COBOL-patched and are not
  labelled with a special reason beyond what the verifier reports; EXEC SQL programs are not COBOL-patched; only one deterministic COBOL fix exists; the ADAPTER Java is
  never executed, so whether the model's adapters are sensible is a reviewer's call; the PR delivery path (`deliver()` writing `not-certified/<PROGRAM>/`) is unit-tested for
  wording only, not run against a real target repository.
- **Reviewer round 1 (Oct 30), all fixed as new commits, then merged with origin/main (run contract is now v0.14):**
  B1 the COBOL patch rule is now enforced in code in every division: fixed-format files only (free-format, tabs, no locatable PROCEDURE DIVISION fail closed), a patch never adds, removes or blanks a line, may only change a line the compiler reported in a fresh compile (compile_cobol required after every applied patch), and each changed line (judged against the ORIGINAL line, so edits cannot drift across patches) must be one identifier correction (edit distance <= 3, no verb/clause word/number/literal), a missing period, or one added word from TO THEN IS DIVISION SECTION; plus the size caps. NOT enforceable: that the corrected identifier is the one the author meant, and that a one-identifier swap to another defined variable is not a logic change (a person must confirm the patch). An added period can end an IF or EVALUATE early and change its scope, and the position of an inserted TO/THEN/IS/DIVISION/SECTION is not checked (only the compiler rejects a misplaced one); the compile-after-patch step, the size caps and the label are the mitigations. 
  B2 dollar cap is projected (refuses a call when spent + worst case would pass the cap; guard and cross-check count against the same cap; unpriced model refused). S1 a converter that dies without a run record is charged what it was granted. S2/S3 commit message no longer says checked for unverified programs; directory is `not-certified/<PROGRAM>/`. S4 `--document` is skipped for repaired, unverified and failed convert-anyway runs. S5 mission control shows the label. S6 API takes `convertAnyway` only with the admin passcode, and on an engine with neither DIOCLE_HOSTED nor DIOCLE_ADMIN_TOKEN only from loopback; deploy env example and README warn that a hosted engine MUST set both. S7 `run --convert-anyway` defaults to REPO_MAX_USD or $0.25. Real re-run of BADNAME, NOPERIOD and SQLRPT under the new rule: same labels, $0.0072.
- **One real run (Oct 30, Meta key, `muse-spark-1.3-contributor`), `python -m diocle_converter repo samples/convert-anyway-repo --convert-anyway --repo-max-usd 0.12`: total $0.0110 (cap 0.12; budget 0.15), first try, prompt not changed.**
  ADDFEE: `certified` (1005/1005 held-out, 1 call, $0.0028). NOPERIOD (missing period): COBOL fixed deterministically for $0 (1 line), Java then
  passed 1005/1005 against the patched COBOL: `certified-against-repaired-cobol` ($0.0032). BADNAME (undefined name `WS-FEES`): the Muse COBOL repair loop (5 calls, $0.0008) changed
  1 line (`WS-FEES` -> `WS-FEE`), compiled, Java 1005/1005 against the patched COBOL: `certified-against-repaired-cobol` ($0.0039). SQLRPT (EXEC SQL): `compiled-unverified`
  ($0.0011): the Java has an `AccountsAdapter` interface labelled `// ADAPTER REQUIRED`, a default implementation that throws, the SELECT kept as a comment, and compiled with javac on the first try; never run.
  Not exercised for real: the compile-fix rounds (the Java compiled first time), the `failed` label, the REPO_MAX_USD skip (unit tests only), the PR path, a model repair rejected by the size rule (unit tests only).


## Verified documentation (Oct 30, branch `verified-docs`, local, NOT pushed or deployed; contracts `behavior-claims` v0.1, run v0.13)
- **What:** a Muse Spark model writes a plain-English behaviour spec of a COBOL program as claims (one sentence + 1-3 examples: input
  field values and expected output field values). The verifier runs the ORIGINAL COBOL (GnuCOBOL -std=ibm, sandbox `POST /claims` when
  `DIOCLE_SANDBOX_URL` is set) on every example: claim `confirmed` (all examples matched), `refuted` (actual value kept) or `unchecked`
  (invalid for the layout via the breaker's `explain`, or the program did not run). The model never decides. Wording: "confirmed on
  the examples tried", never "proven": it means the examples' stated expectations held on GnuCOBOL; the claim's sentence is not
  machine-checked, numbers compare by value, and an example is unchecked after a non-zero exit or when it compares only a count or
  return code. Single-file record programs only.
- **Code:** `services/verifier/diocle_verifier/claims.py` (+ sandbox kind `claims`), `services/converter/diocle_converter/documenter.py`,
  CLI `run|repair ... --document` and `document SAMPLE`, run.json `behavior`, `behavior.json`/`behavior.md`; API passes `behavior`
  through; web `components/behavior-panel.tsx` (badges, expected vs actual, Markdown download). Caps: `DOC_MAX_CALLS` 2,
  `DOC_MAX_USD` 0.10 (worst case of a call checked up front; unpriced model refused), `DOC_MAX_OUTPUT_TOKENS` 9000 (NEVER exercised: the real run used 6000 and hit it once; 9000 was not re-run), `DOC_MODEL_*` optional.
  Never fails a run (any problem becomes `skipped`/`unchecked`).
- **Run it:** `cd services/converter && .venv/bin/python -m diocle_converter run ../../samples/interest-accrual --document --no-memory`
  (or `document ../../samples/interest-accrual` for the spec alone, about a third of a cent).
- **Real run (INTACCR, runs/interest-accrual-20261030-075737, local only):** certified 1027/1027; spec: 9 claims, 9 confirmed, 0 refuted,
  0 unchecked, 17 examples run; 2 documenter calls (the first hit the then 6000-token output cap mid-JSON and was unusable, the retry
  worked; cap raised to 9000), 7,425 in / 10,192 out tokens, about $0.0028 (whole run $0.0086). No refuted claim this time; that
  shows the model's claims held on the examples it chose, not that the spec is complete.
- The stored real run above was judged by the first version of the rules (before the non-zero-exit and weak-expectation rules, the null-for-unstated schema and the Markdown escaping); it was not re-run (no new model calls). Its 9/9 stands as judged then.
- **Deploy notes (second review):** the model's JSON schema uses nullable types (`["integer","null"]` in `response_format`, not strict); that form has NEVER reached the real Meta API (the stored real run used the earlier -1 sentinel schema), so make one `document` run after deploy and read the result. A claims job holds the sandbox's single job lock for up to 180 s (CLAIMS_JOB_TIMEOUT; typically a 60 s compile cap plus runs bounded at 90 s) and `/verify` and `/compile` wait behind it; a caller that finds it busy waits only `DIOCLE_CLAIMS_WAIT` (60 s) and then leaves the examples unchecked. Judging is on the raw expected values (flattening is display only); numbers must be plain decimals; a crash or truncated stdout gives unchecked, never refuted.
- **Owner steps:** engine redeploy AND sandbox image rebuild (new `/claims` endpoint; not exercised in a real container, only the in-process
  handler), seed the run folder to the server volume, then check the Behaviour spec panel on that run.
- **Not done:** multi-file / DISPLAY-only / I-O programs; the checked-in samples have no stored spec yet.

## Compile pre-check for visitor imports (Oct 30, branch `worktree-agent-aeaa1ad23cf3a94b1`, local, NOT pushed or deployed)
- `diocle_verifier.precheck.compile_original` + sandbox `POST /compile` (contract `contracts/compile-check.schema.json` v0.1):
  compiles the ORIGINAL with the verification flags inside the sandbox (60 s job limit, 8 MB in, 16 KB out, paths stripped),
  never in the engine process when `DIOCLE_SANDBOX_URL` is set. `deliver.py --public` uses it before the translator: an
  uncompilable original is `skipped` with the compiler's reason and does not use a slot of the 3 (max 12 checked,
  240 s total, stops after two "unknown" answers). Needs an engine deploy AND a sandbox image rebuild (new endpoint).
- Measured with the analyzer + this check on cobol-programming-course (24 analyzer-convertible, 8 compile under `-std=ibm`:
  CBL0013, CBL0014, CBL0015, CBLC2, DEPTPAY, EMPPAY, HELLO, PAYROL00; 15 fail on `PROGRAM-ID.` without a period
  ("unexpected ENVIRONMENT"), PAYROL0X on a numeric-edited name). Repo LICENSE is CC-BY-4.0; 24 of 32 program files carry an
  SPDX CC-BY-4.0 header (6 of the 8 compilable ones do not, the repo LICENSE covers them).
- **Reviewer fixes (Oct 30):** the message keeps only `file:line: error:` cobc lines (a COPY of any readable file made cobc echo its contents); `fail` only on such a diagnostic, everything else (killed gcc, ENOSPC, timeout, silence) is `unknown`; `delivery.json` has `precheck` (checked, why it stopped); unreadable pre-check output is logged.
- **Second review (Oct 30):** compile-check contract v0.2 (diagnostics list; context lines dropped before matching; words masked against cobc's own vocabulary; gcc-style lines refused); delivery notes are fixed phrases; sandbox test no longer depends on the process-wide job lock.
- **Deploy checklist, NOT exercised in a real container: every sandbox test (compile and verify) uses the sandbox's HTTP handler in-process on a developer machine. The compile path's setuid/kill/cleanup as root, the tmpfs, memory and pids limits and the hung-gcc path (a stuck cobc killed at 30 s / the 60 s job limit) have NOT been run in the container. After a deploy someone must rebuild and recreate the sandbox (`docker compose ps` and image ids show it is the new image), run `docker compose exec api python -I -m diocle_verifier.precheck <sample dir>` once, and confirm it answers `ok` or `fail` (not `unknown`).
- Not done: making near-miss originals compile (e.g. inserting the missing period) would change the original, so it is not claimed.

## Oct 30 early morning: what is pushed but NOT deployed (owner action needed)
- **origin/main (3c8a6db) is ahead of the live engine (71ac3b3).** The auto-mode permission check denied the production deploy
  (the earlier seed of three runs went through after the owner authorized it in chat; the deploy did not), so it was not retried.
  **To deploy, from the Mac with the SSH key:** `git pull && deploy/update-engine.sh` (it refuses while a delivery runs; the script's
  `$HOST` echo bug is fixed on main). Then run the reviewer's checklist for the sandbox compile pre-check:
  1. `docker compose -f docker-compose.api.yml ps` and `docker inspect` both `deploy-api-1` and `deploy-sandbox-1`: the **sandbox image
     must have been rebuilt** (an old sandbox answers 404 on `/compile`, which degrades to the old behaviour with no skipping).
  2. `docker compose -f docker-compose.api.yml exec -T api python -I -m diocle_verifier.precheck /opt/diocle/samples/interest-accrual`
     must print `ok` (not `unknown`); if it prints `unknown`, the `python -I` editable install is not working in the container.
  3. `curl -X POST https://diocle.vercel.app/api/runs/chqclr-20261028-214355/reverify` still 1004/1004; health ok.
  4. A visitor import of github.com/openmainframeproject/cobol-programming-course should now skip the 16 originals that do not
     compile under -std=ibm (15 lack a period after PROGRAM-ID) and take CBL0013/CBL0014/CBL0015 (a few cents). If it does not,
     read `precheck` in the delivery record (fixed-phrase notes) and `deliver.log`.
- **Pushed this night (all reviewed, tests green: analyzer 81, converter 163, verifier 93, api 48):** sandboxed compile-only pre-check
  of visitor originals (contract compile-check v0.2, delivery.precheck; the message filter keeps only masked cobc diagnostics, was
  hardened over three review rounds against COPY-echo leaks; NOT exercised in a real sandbox container, see checklist above); printout
  to COBOL intake with Muse Wonder (CLI only; running the model's COBOL is opt-in `--run-model-code`; one real run: 1,013/1,013 for
  $0.067, third-party Wonder price); tier-2 breaker defaults; uptime workflow (.github/workflows/uptime.yml); live seed of the Wonder
  and Spark-1.3 tiers runs and the cross-check run (done, re-verifiable).
- **Wonder vs Spark 1.3 as breaker (one run each, INTACCR):** both found the real sign-of-zero defect; Wonder in round 1 ($0.62 run),
  Spark 1.3 in round 3 ($0.41 run). Not a measurement of which is better.

## Where things stand at the end of Oct 29 (night, Mac)
- **origin/main** has everything below; the engine on Vultr was redeployed at 71ac3b3 (guard policy, cross-check code, tiers, item 1,
  pre-check fix). After that: only the tier-2 breaker default (5af5672/4409559) and docs are on main but not deployed (CLI only).
- **Built and pushed this session:** whole JCL job v1 (rebased), guard agent merged (policy live, Baseten model review OFF: needs
  `GUARD_MODEL_*` in `.env` and on the server + a live smoke test), independent Spark Open cross-check (`--crosscheck`, CLI only,
  run on Baseten OK), item 1 (DISPLAY-only, OPEN I-O, CALL identifier; analyzer + verifier; no real model conversion of these shapes yet),
  stop-before-repair when the original COBOL does not compile (CBL0001 of the OpenMainframe course burned 27 calls before this),
  model tiers `--tiers` (tier 1 contributor, 2 muse-spark-1.3, 3 muse-wonder-1.0; hard caps; breaker and after-break repair at tier 2;
  Wonder opt-in), README model-roles diagram + Meta-key note.
- **Evidence from the first real tiers run** (interest-accrual-20261029-230750, local `runs/` only): Muse Wonder as breaker found a real
  sign-of-zero overflow defect (-000000000 vs +000000000, the INTACCR issue), cheap-tier repair fixed it for ~$0.02, re-certified;
  but two Wonder breaker calls cost $0.595 of the run's $0.619. A second run with the tier-2 breaker was in progress (result not recorded
  here: check `runs/` in the worktree or re-run `python -m diocle_converter run ../../samples/interest-accrual --tiers --breaker`).
- **Video:** draft-2 (2:42) rendered with ElevenLabs narration; owner rejected the first voice pacing, approved the new voice id
  (in `.env`, never committed); a full re-render with story-driven pauses (`diocle-draft-3.mp4`) was started. Voice is a synthetic
  non-Meta voice: the end card says so. Meta's `muse-voice-transcribe-1.0` only transcribes; no Muse text-to-speech exists on the API.
- **Owner to do next:** listen to draft-3; decide whether the next cut should feature the Wonder catch (needs a clean run on screen,
  ~$0.6 with Wonder) ; add `GUARD_MODEL_*` if the guard review should run; decide the INTACCR re-delivery to quillmark-modern;
  fix site wording ("6/6" for quillmark-modern#4 is the repo CI, #4 itself re-delivers INTACCR; stale "19/23 runs" counter);
  upload the video and submit by Nov 4, 9 PM ET (your own cutoff Nov 4 7:30 PM IST).
- **Not done / not claimed:** Glimmer and Voice (no such models on the key), DB2/EXEC SQL, whether higher tiers repair better
  (measured once: the cheap tier was enough), a real model conversion of DISPLAY-only/I-O programs.

## Current state (updated 2026-10-29)

- **Printout intake built and run once (Oct 30, Mac, branch `worktree-agent-a13889e328de92c45`, local, NOT pushed or deployed; contract
  `contracts/transcription.schema.json` v0.1):** `python -m diocle_converter transcribe IMAGE --out DIR [--against SAMPLE]`
  (`services/converter/diocle_converter/vision.py`, off unless `VISION_MODEL_ID` is set, e.g. `muse-wonder-1.0`). **Muse Wonder accepts
  OpenAI-style `image_url` base64 parts through our Meta key** (probe $0.005). The model transcribes; the gates decide: `cobc -fsyntax-only
  -std=ibm` (one re-prompt with the errors) and a differential of the transcription vs the original on 1,013 generated inputs. Proven once:
  `samples/loyalty-waiver-printout` (greenbar PNG rendered by `demo/render-listing.py`): 1 call, $0.067, compiled, 1013/1013 matched.
  Not proven: photos (the image is a clean render), other programs/fonts, long listings. The model collapsed runs of spaces on 4 lines
  (harmless here), and random inputs rarely hit exact boundaries, so a boundary mis-read (`5000.00`) could pass: the status is "no
  difference on 1,013 inputs", not equality. CLI only: no engine/API path. **Running the transcription is opt-in (`--run-model-code`): it builds and executes model-written COBOL on this machine; only for our own synthetic printouts on a dev machine.** Without the flag `--against` stops at `compiled-unchecked`. The refusal scan (fixed-format only, no directives/tabs, no SYSTEM/CBL_/C$/dynamic CALL, ASSIGN only to the original's DD names, COPY only its copybooks) is best-effort and NOT a security boundary (continuation lines are refused because they split keywords past the scans; COPY is refused without an original; compiler errors are filtered to the transcription's own `file:N: error:` lines with quotes masked before storage or re-prompting; a third reviewer found these); on macOS the executable also runs under sandbox-exec (no network, writes only in its temp dir, no exec of others; reads, CPU and memory not limited). Two reviewer passes found a false pass (`--out` == `--against`), a free-format scan bypass and other gaps; all fixed with regression tests (the real run above predates these layers and was not repeated, to save money). Total spend
  for the build and the one real run: about $0.07. Caps: `VISION_MAX_CALLS` 3, `VISION_MAX_USD` 0.20, `VISION_MAX_OUTPUT_TOKENS` 5000.
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
- **Plan step 1 done, verifier first (Oct 29, branch `worktree-agent-a6a8db8578f8d9014`, local, NOT pushed or deployed;
  analysis contract v0.5, verification contract v0.8):** (a) programs with no output file but DISPLAY output are
  certified on stdout + exit code (one `stdout` result; refused if the original printed nothing; `displayOnly` in
  sample.json set by the analyzer, re-derived by `reverify`); (b) sequential fixed-record files opened I-O (REWRITE) are
  seeded from generated records and their final contents compared byte for byte (`runs.files.updated`; both sides get
  their own copy of the seed); (c) `CALL identifier` resolves only when nothing but literals can assign it (token-based,
  so multi-line MOVEs are seen; STRING/UNSTRING/ACCEPT/READ INTO/LINKAGE/CALL USING/second literal all keep it refused).
  The analyzer says convertible only for shapes the verifier handles, and a JCL job with such a COBOL step is refused
  as a job. Proven end to end with hand-written Java (no model calls): `samples/display-report`, `samples/ledger-rewrite`,
  `samples/call-identifier`, plus mutated-Java negative tests. Re-verified every certified run's existing Java before and
  after: identical results (six Quillmark programs and CHQCLR pass). Measured with the analyzer only on the course repo:
  16 of 32 programs analyzer-convertible before, 25 of 32 after (9 DISPLAY-only; none use OPEN I-O or a CALL identifier; this says nothing about certification). Reviewer pass done: CALL-identifier resolver tightened (88-levels, level-66 RENAMES, PIC width, COPY members refused), verifier stdout decoded byte-for-byte as latin-1, README states that a DISPLAY that never fires fails only at verification. NOT
  proven: the translator model on these shapes (no paid calls were made), and the real course programs through the
  verifier (compiling cloned code was not run in this session).
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
- **Model tiers built (Oct 29 night, branch `tiers`, run contract v0.12, not deployed):** `--tiers` escalates the repair agent
  tier 1 (`muse-spark-1.3-contributor`) -> `MODEL_TIER_2_ID` -> `MODEL_TIER_3_ID` after each failed certification round, breaker
  a break after certification resumes repair at tier 2, the breaker attacks at tier 2 by default (`MODEL_TIER_BREAKER`; Wonder is opt-in: one Wonder breaker call cost $0.22-0.37 in the first real run, 96% of that run's $0.62, and it found a real INTACCR sign-of-zero defect that the cheap repair tier then fixed for $0.02), own hard caps (projected: a second call as dear as the dearest so far is refused) (`MODEL_ESCALATION_MAX_CALLS` 12, `MODEL_ESCALATION_MAX_USD` 0.50), falls back to tier 1 when
  spent. Muse Wonder (`muse-wonder-1.0`) answered a tool-call and a structured-output test through the Meta key ($0.007), but
  whether higher tiers repair better is NOT measured: run the comparison (e.g. CHQCLR vs INTACCR on tier 1 vs 2 vs 3, est. $0.30-0.60,
  needs owner OK) before claiming it. Wonder's $4/$20 price is third-party, unconfirmed.
- **Visitor import of the course repo found a waste (Oct 29 night):** CBL0001 (`PROGRAM-ID.    CBL0001` with no period, valid for
  IBM, rejected by GnuCOBOL `-std=ibm`) could not compile, yet the translator and 3 repair rounds ran (27 calls, $0.037). Fixed on
  branch `precheck` (converter `original_failure`): after the first verification, an original that does not compile stops the run
  with that reason, before any repair round, breaker or review. Still costs the one translator call; a pre-translation compile
  check for visitor imports now exists (see the Oct 30 section).
- **Engine deployed Oct 29 night at ebe2beb** (guard policy + cross-check code + item 1). After deploy: CHQCLR re-verify 1004/1004,
  TXNPOST 1024/1024 (two runs), PKDPOST 1037/1037; a visitor import of quillmark-legacy certified 3/3 programs (about $0.012, guard
  blocked nothing). The guard's Baseten review is OFF on the server (no `GUARD_MODEL_*`); the cross-check key lines are in
  `deploy/diocle.env` but nothing starts it. Not yet run on the engine: any DISPLAY-only / I-O / CALL-identifier program.
- **Spark Open cross-checker built and run live twice (Oct 29 night, Mac; run contract v0.10; deployed with the engine at 7c28841 and later, but CLI-only: nothing on the server starts it):**
  `services/converter/diocle_converter/crosscheck.py` + `--crosscheck` flag. After certification Muse Spark Open
  proposes inputs and names suspected fields; every input runs through GnuCOBOL vs Java, its opinion certifies nothing,
  a real mismatch goes to the repair agent. Own hard cap (`CROSSCHECK_MAX_CALLS`, default 2), skipped with a reason if
  unconfigured / already on the open model / multi-file / host down. Calls merge into the run's usage (cost now priced per
  call by its own model). Run JSON `crosscheck`, API pass-through, web panel + "Independent check" row in the model card.
  Opt-in (costs ~$0.05 per run on Fireworks/Baseten). To try: put `OPEN_MODEL_*` in `.env`, then
  `python -m diocle_converter run ../../samples/interest-accrual --crosscheck`. The guard fields became run contract v0.11 when the branches merged. Live results on interest-accrual (Fireworks, ~$0.03-0.04
  per cross-check, both runs certified, 0 real mismatches): the first prompt got only 2 of 15 and 1 of 13 proposed cases
  accepted (10 "too many digits or a sign on an unsigned field", 2 "not a number": the prompt itself invited overflow and
  malformed content, which the layout cannot express). The prompt was rewritten to state the layout rules; NOT yet re-run
  (~$0.04), so check `crosscheck.rejectedBecause` in run.json on the next run. Reviewer pass: push OK; noted
  `deliver.py` formatted a None cost if a call was on an unpriced model: fixed on `guard-merge` (prints n/a).
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
- **Guard agent (Oct 29, merged with the cross-checker on branch `guard-merge`, merge-ready, NOT pushed or deployed):** a "manager" agent over the translator, repair, breaker and cross-check agents
  (`services/converter/diocle_converter/guard.py`, run contract v0.11; the cross-checker is v0.10). Policy before any Java runs
  (refuses Java that openly uses the network, processes, reflection/native code, other env vars or literal outside
  paths; the repair agent is told why; a speed bump, the sandbox is the boundary),
  COBOL scanned for text aimed at an AI, and one review of the final Java by Muse Spark Open on **Baseten**
  (`GUARD_MODEL_*`, own key, `GUARD_MAX_CALLS=2`) that can revoke certification. The guard reviews after the cross-check,
  so it sees the final Java. Guard and cross-check calls are all logged in the run's usage, each priced by its own model,
  each with its own hard cap (`GUARD_MAX_CALLS`, `CROSSCHECK_MAX_CALLS`); a failure of either never fails a certified run
  and neither can certify anything. **Live Baseten test still owed (no key was available when merging):**
  add the Baseten key as `GUARD_MODEL_API_KEY` in `.env`, `cd services/converter && .venv/bin/python -m pytest -q &&
  .venv/bin/python -m diocle_converter smoke` (both models answer), then
  `.venv/bin/python -m diocle_converter run ../../samples/interest-accrual --breaker --crosscheck` (about $0.05 Meta + a few cents
  per open-model host) and check run.json `guard.review.verdict` and `crosscheck`. Then push, put the key in `deploy/diocle.env` on the server
  (owner types it), `deploy/seed-runs.sh` and `deploy/update-engine.sh`. Fireworks stays the private-mode host.
  **Review findings fixed (Oct 29, Windows):** comments set aside and literals decoded before the rules (the comment,
  text-block, octal and method-reference bypasses are refused; words in comments and strings no longer block);
  reflection, management, jshell, javax.xml and socket-channel rules added; only the program's own DD names, never
  KEY/TOKEN/SECRET-like ones; computed or missing getenv names refused; review answers read finding by finding;
  random fence per call with quoted findings inside it; cut sources never a clean pass; refusals go back to the repair
  agent at the start and at certification; smoke sends the real guard request and warns on an unpriced model;
  provider errors stored as type and HTTP status only; verifier javac gets -proc:none. Merge notes: the flaky
  `test_start_delivery_validates_and_allows_one_at_a_time` passed only because its 409 came from the same-second delivery-id
  check (the test wrote an old `startedAt`); it now writes a current time and asserts "still running". Still to do: the
  live Baseten test above, then push `guard-merge` (or merge it to main) and deploy.
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

Former gap, now closed (merged and deployed to the engine at ebe2beb, Oct 29 night; no model conversion of these shapes has run yet): programs that only DISPLAY are
compared on stdout and exit code (see the first Current-state bullet). Good test repo for visitor imports:
github.com/openmainframeproject/cobol-programming-course (EXEC SQL ones correctly refused).

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

### Oct 30: course-repo visitor import (live engine, after the deploy)
- `delivery-20261030-022234` on https://github.com/openmainframeproject/cobol-programming-course (CC-BY-4.0, credited on /evidence):
  the compile pre-check skipped 11 programs whose originals do not compile under `-std=ibm` (no model spend), the visitor cap skipped 10,
  **CBL0013 and CBL0014 certified** (DISPLAY-only, one run each, 10 and 5 model calls), **CBL0015 not certified because it loops forever**
  (the engine reports a verifier traceback; open work: report "the original never terminates" in plain words). Spend $0.0074.

## Open work (priority order)
- **Plan for Oct 29 to Nov 1: CLAUDE.md, "Current priority"** (item 1 is built on the branch above, awaiting a reviewer pass,
  a merge and one real model run per new sample; dependencies: display-only and I-O programs,
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

- **Mission control (Oct 30, branch `mission-control`, local, not pushed or deployed).** New route `/mission`
  (`apps/web/components/mission-control.tsx`, `apps/web/lib/mission.ts`): a replay of a recorded run built only from
  run.json (events in recorded order, usage.modelCalls priced with the existing PRICES table, tiers, breaker
  counterexamples, repair patches, final certification). Run events have no timestamps, so pauses are not real
  durations and the page says so. Cast row, cost meter, tier prices, breaker input beside the repair patch, held-out
  certification, play/pause/scrub/speed; reduced-motion shows the final state. Default run
  interest-accrual-20261029-230750; picker lists runs with breaker/cross-check/tiers data. Linked from the top bar and
  the front page. Also reworded the "20.00 vs 0.00" CHQCLR labels (returned-cheque fee, no currency invented).
  Checked with tsc, next build and a replay driven with Playwright against a local dev server, with the live engine's
  GET responses proxied through the test (the engine sends no CORS header for localhost); not tested from a deployed origin.
- 2026-10-30: printout intake (see Current state): contract, `vision.py`, CLI, 12 tests (scripted fake client; two use real cobc), renderer, one real end-to-end run.
- 2026-10-29: **CLAUDE.md plan item 1 (more programs convert), verifier support first.** See the Current-state bullet
  "Plan step 1 done" for what, the tests and the measurement. Commit order on the branch: contracts, verifier,
  analyzer, converter prompt text, samples, tests, docs. Still refused: EXEC SQL/CICS/DLI, INDEXED/RELATIVE, LINE
  SEQUENTIAL opened I-O, mixed I-O modes, dynamic CALL (anything but literals), unknown CALL targets, no output and no
  DISPLAY, DISPLAY-only with console ACCEPT.
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
