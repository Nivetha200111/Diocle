# Headline measurement: Muse Spark alone vs. with Diocle

> **Status: PLAN (pre-registration), written and committed before any model call. Results are appended below after the run.**
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

**(c) Not planned.** Applying the breaker to the (a) first translations is out of budget scope and is not run.

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
