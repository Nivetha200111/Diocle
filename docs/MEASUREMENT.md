# Headline measurement: Muse Spark alone vs. with Diocle

> **Status: COMPLETE. The plan below was written and committed before any model call; results and deviations are appended at the end ("Results", "Deviations").**
> All programs are **synthetic**. Nothing here is a benchmark of general COBOL.

## Question
How many programs does the model get right on its **first translation**, compared with how many Diocle **certifies**
(repair loop + held-out verification + breaker), on the same fixed program set, with fix memory off?

## Programs (15, fixed now)
Every program in `samples/*` and `eval/samples/*` that the verifier can run end to end (original compiles under GnuCOBOL;
inputs are generated). Excluded before any run, with reasons:
`samples/loyalty-waiver-printout` (same COBOL as `loyalty-waiver`, a transcription demo, would double count),
`samples/convert-anyway-repo` and `samples/db2-dynamic-sql` (no `sample.json`: refused on purpose, nothing to verify),
`samples/quillmark` (a data folder, not a program).

| Program | Directory | Status | Why |
|---|---|---|---|
| BRNCHSUM | eval/samples/brnchsum | **UNSEEN** | written after tag `eval-freeze-1`, committed before any model run |
| CHQCLR | eval/samples/chqclr | **UNSEEN** | same |
| FXCONV | eval/samples/fxconv | **UNSEEN** | same |
| LOANAMRT | eval/samples/loanamrt | **UNSEEN** | same |
| INTACCR | samples/interest-accrual | SEEN | used throughout development, prompts, fix memory, tests |
| TXNPOST | samples/txn-posting | SEEN | Quillmark delivery, tests |
| FEESCHD | samples/fee-schedule | SEEN | Quillmark delivery, tests |
| TXNLIST | samples/display-report | SEEN | display-only certification work, tests |
| LDGRWRT | samples/ledger-rewrite | SEEN | I-O / REWRITE work, tests |
| FEEPOST | samples/call-identifier | SEEN | CALL-identifier work, tests |
| DAYCTRL | samples/daily-control | SEEN | Quillmark delivery, tests |
| ACCTRPT | samples/db2-account-report | SEEN | EXEC SQL work (SQLite stand-in, not DB2), tests |
| ACCTMTCH | samples/account-match | SEEN | match-merge / JCL work, tests |
| PKDPOST | samples/packed-posting | SEEN | packed-decimal work, golden files, tests |
| LOYWAIVE | samples/loyalty-waiver | SEEN | demo and tests |

"Seen" means the program (or its traps) was used in earlier runs, prompts, fix-memory lessons or tests while Diocle
was being built. "Unseen" is the four programs frozen at `eval-freeze-1`; the unseen set is the cleaner test, but the
translator prompt and verifier were later fixed in response to other findings, and the unseen programs were run
(and their results published) in `docs/EVALUATION.md` before this measurement, so "unseen" means "not tuned to".

## Model and environment
- Model: `muse-spark-1.3-contributor` (Meta Model API, hosted), `MODEL_REASONING_EFFORT` default (medium). No tiers
  (`MODEL_TIER_*` empty), no escalation. Default caps (60 calls/run, 20/round, 3 rounds, 3 attack rounds, 1 breaker cycle).
- Guard: **policy only** (`GUARD_MODEL_API_KEY` empty, so the guard model review does not run).
- Fix memory: **off** (`--no-memory`); it is neither read nor written.
- Verifier: this repository at the base commit `1b17381`; GnuCOBOL 3.2 `-std=ibm`-style settings as the verifier sets them, JDK 21.

## Metrics
**(a) First try, "Muse Spark alone".** For each program, K = 3 independent first translations. A first translation is
the output of the translator step alone (`diocle_converter.translate.translate`, the same prompt and structured output
the product uses): **no repair, no breaker, no fix memory, no retry**. Each is verified by the verifier on **1,000
random held-out inputs with seed 8801** (a seed not used by any earlier run, test or agent: repair certifies on
4242+round, tests use 1026, the earlier evaluation used 9001-9005). It **passes** only if the original and converted
compile, the exit codes match, stdout matches and every output record (or final file/table) matches byte for byte
(`diocle_verifier.verify.passes`). Reported: passes/attempts per program and in total, plus "at least one of 3" and "all 3".
A translation that does not compile, or whose run errors, counts as a failure.

**(b) With Diocle.** For each program, ONE full run: `python -m diocle_converter run SAMPLE --no-memory --breaker`,
default caps, policy-only guard. **Certified** = the run record says certified, which means held-out certification
(1,000 inputs, seed 4242+round) passed AND the breaker agent found nothing that survived (a break that was repaired
and re-certified counts as certified). Reported: certified or not, repair rounds, breaker attempts and catches, model
calls, estimated cost, wall-clock time. "Looks right, is wrong": a run whose Java passed the held-out check with zero
repair rounds and was then broken by the breaker is reported explicitly.

**(c) Added after the main arm, by the owner's decision (see Deviations).** The breaker is applied to one fresh first translation per program that passed the 1,000 held-out inputs, to count translations that pass the test and are still wrong. Script: `eval/headline_attack.py`.

## Cost cap and stopping rule
Hard cap **$1.00** real spend for everything, owner-approved. Cost is the sum of the per-call token usage
(estimated at the list prices in `services/converter/diocle_converter/config.py`: $0.10 in / $0.20 out per 1M tokens for the
contributor model; cached input at its listed price) read from the first-try client and from each run's `run.json`.
**No new run is launched once the running total reaches $0.85**; the report then says exactly what was completed
(programs not reached are listed as "not run", not dropped). Order: the four UNSEEN programs first, then the seen ones in
the order of the table. Per program: the K=3 first translations, then the full run.

## Rules during the run
- No re-run of a program to get a better result. A re-run is allowed only after an infrastructure failure (network or
  provider error, not a wrong answer) and is logged in the results file.
- A program that cannot be verified for infrastructure reasons is reported as excluded with the reason.
- A program Diocle does not certify is reported as not certified.
- The plan is not changed after results are seen; any deviation is appended below, labelled.

## Script
`eval/headline.py` (sequential, resumable): writes `eval/results-headline.json` after every unit of work and prints the
running spend.


## Results

Raw data: `eval/results-headline.json` (main arm, merged from three shards) and `eval/results-headline-attack.json`
(attack arm). Total real spend about **$0.69** (main arm $0.47, attack arm $0.15, plus $0.07 for the excluded ACCTRPT units, see Deviations), under the $1.00 cap. Estimated from
list prices. n is small (15 programs, one model, one day, synthetic programs): read these as a measurement of this set,
not as a general rate.

### Main arm: first translation vs. full Diocle run

| Program | Status | First try, passes of 3 | Diocle run | Repair rounds | Breaker: broke / tried |
|---|---|---|---|---|---|
| ACCTMTCH | seen | 3/3 | certified | 0 | 0 / 0 |
| ACCTRPT | seen | 1/3 | certified | 1 | 0 / 0 |
| BRNCHSUM | unseen | 3/3 | certified | 0 | 0 / 8 |
| CHQCLR | unseen | 3/3 | **not certified** | 2 | 12 / 24 |
| DAYCTRL | seen | 3/3 | certified | 1 | 2 / 18 (fixed) |
| FEEPOST | seen | 3/3 | certified | 0 | 0 / 12 |
| FEESCHD | seen | 3/3 | certified | 0 | 0 / 36 |
| FXCONV | unseen | 3/3 | certified | 0 | 0 / 36 |
| INTACCR | seen | 1/3 | certified | 1 | 1 / 32 (fixed) |
| LDGRWRT | seen | 1/3 | certified | 1 | 0 / 0 |
| LOANAMRT | unseen | 3/3 | certified | 0 | 0 / 36 |
| LOYWAIVE | seen | 3/3 | certified | 0 | 0 / 24 |
| PKDPOST | seen | 1/3 | certified | 2 | 1 / 11 (fixed) |
| TXNLIST | seen | 3/3 | certified | 0 | 0 / 0 |
| TXNPOST | seen | 3/3 | certified | 0 | 0 / 21 |

- **First translations passing 1,000 held-out inputs: 37 of 45 (82%).** All 15 programs passed at least once in three
  tries; 11 passed all three; four (ACCTRPT, INTACCR, LDGRWRT, PKDPOST) passed one of three.
- **Unseen programs (4): 12 of 12 first translations passed. Seen programs (11): 25 of 33.** The unseen set is small and
  was not harder for the model on this test; do not read the seen/unseen difference as evidence of overfitting either way.
- **Full Diocle run: 14 of 15 certified.** It certified all four programs the model got wrong on some first tries.
  **CHQCLR was not certified**: the breaker broke it on 12 of 24 inputs, one repair cycle did not fix it within the caps.
- **"1,000 held-out inputs" is the number requested.** The cases actually compared per translation ranged from 766 to 2,031 for most programs
  (several records per input file), and TXNLIST, a display-only program, compared 1.
  We report it as it came out.
- Model spend: first translations about $0.18 in total, full runs about $0.29 in total.

### Attack arm: do translations that pass the held-out test survive an attacker?

15 programs; 12 can be attacked, and 10 of those 12 passed the held-out test (the breaker designs single-file records, so ACCTMTCH, ACCTRPT and TXNLIST are not
applicable). One fresh first translation per program, 1,000 held-out inputs (seed 8801), then the breaker.

| Outcome | Programs | Count |
|---|---|---|
| Failed the 1,000 held-out inputs already | LDGRWRT, PKDPOST | 2 |
| Passed, and the breaker found no breaking input | BRNCHSUM, FEEPOST, FEESCHD, FXCONV, LOANAMRT, LOYWAIVE | 6 |
| **Passed, then broken by the breaker** | CHQCLR, DAYCTRL, INTACCR, TXNPOST | **4** |

**Headline: of 10 attackable translations that passed 1,000 held-out inputs, 4 were still wrong when attacked
(40%).** Among the 4 unseen programs the breaker broke 1 (CHQCLR); among the 6 seen programs it broke 3.

What this does and does not show:
- It shows that passing a large random held-out test is not the same as being correct for these programs. The breaker's
  inputs were designed by Muse Spark to attack risky operations and are checked against GnuCOBOL.
- It does not say Diocle "catches them all": the breaker is itself limited (single-file programs only, a cap on rounds
  and inputs), and CHQCLR stayed uncertified. A program the breaker cannot break is not proven correct.
- The 4 programs the breaker broke are on the 82% side of the first-try number: three of them passed all 3 first-try
  trials. The two numbers (82% of first translations passing the test; 6 of 10 attackable test-passers surviving the attack)
  are different measures on overlapping program sets; do not multiply or merge them.

## Deviations from the plan (appended after the run, labelled)

1. **Step (c) was added.** The plan said it was out of scope. After the main arm the owner approved it within the same
   $1.00 cap; it was run and is reported above as its own arm.
2. **ACCTRPT (db2-account-report) was excluded and re-run once for an infrastructure defect.** The sqlite-jdbc driver
   was missing in the measurement checkout, so every ACCTRPT test ran 0 of 0 cases. The first-try units and the full run
   (about $0.07 of spend, one run that spent 3 repair rounds on a 0-case result) were excluded and logged in
   `infrastructureLog` in `eval/results-headline.json`, with the excluded record kept. The driver was installed (sha256
   in the log) and ACCTRPT was re-run once; the table uses the re-run. Spend for the excluded units counts toward the total.
   ACCTRPT first try after the re-run: 1 of 3 passed. Trial 1 passed (1,358 cases); trial 2 did not compile (counted as a
   failure, per the plan); trial 3 failed 670 of 1,358 cases. The ACCTRPT full run's initial check ran 0 cases (as did PKDPOST's) and it
   certified after one repair round and 21 model calls.
3. **Sharding.** To save time the work ran in three parallel shards and was merged (`--shard I/N`, `--merge`); this does
   not change what each unit did.
4. **Base commit.** The plan named base commit `1b17381`; the units ran in a worktree at that commit plus the eval scripts in this branch. Later changes to `main` (keyed files, mutation testing, minimization, voice question) are not in the measured code.
5. **No re-runs for a better result.** Apart from item 2, no unit was repeated.
