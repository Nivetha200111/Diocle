# services/converter

Status: **working slice** for the `interest-accrual` sample (Layer 2 of [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)). Implemented: Meta model client with call caps and cost logging, whole-program translator (structured output), and the tool-using repair agent. Not yet implemented: Class Designer (2A), per-paragraph translation, SQL schema mapping, rule extractor, edge-case designer, judge, SonarQube issues, `conversion-output` contract emission.

Meta models only (CLAUDE.md rule 9), through the OpenAI-compatible Chat Completions API at `https://api.meta.ai/v1`.

## Repair agent
Tools: `run_differential_test`, `read_cobol_source`, `list_java_files`, `read_java_file`, `patch_java` (exact unique replacement, with a required rationale), `compile_java`, `finish`.
- Edits are confined to the run's Java workspace (`.java` files only).
- The agent sees test results for seed 1026 (200 random cases plus boundary and trap cases). **Certification re-runs the verifier on a held-out seed with 1,000 random cases**, so special-casing the inputs it saw doesn't pass.
- Caps: calls per run, calls per round, rounds (from `.env`). Every call's tokens (including cached input), latency and estimated cost are logged.
- Token efficiency: the COBOL, the Java and the first test result go in the opening message (no exploratory reads); `patch_java` returns the edited lines so the agent doesn't re-read files; a passing test tells the agent to finish immediately; history is append-only with stable content first so the provider's prompt cache applies (cached input is ~50x cheaper on `muse-spark-1.3-contributor`).

## Model tiers (`--tiers`)

Opt-in escalation by task difficulty, hosted mode only. `META_MODEL_ID` is tier 1 (default
`muse-spark-1.3-contributor`, $0.10/$0.20 per 1M tokens); `MODEL_TIER_2_ID` (e.g. `muse-spark-1.3`, $1.25/$4.25) and
`MODEL_TIER_3_ID` (e.g. `muse-wonder-1.0`, $4/$20, price per third-party coverage, unconfirmed on dev.meta.ai) are other
models on the same host and key. With `--tiers` the repair agent stays on tier 1 until a certification round fails, then
moves up one tier per failed round (each move is a trace event and a `tiers.escalations` entry in run.json), and the
breaker attacks with the highest configured tier. Hard caps (rule 10) on everything above tier 1: `MODEL_ESCALATION_MAX_CALLS`
(default 12) and `MODEL_ESCALATION_MAX_USD` (default 0.50) per run, counted as calls happen; when spent, the run falls back to
tier 1 and still finishes. A model with no entry in `PRICES` counts as the whole cap (fail closed), and the cap is checked
before each call, so one large call can overshoot it. The contributor tier lets Meta use requests to improve its products;
escalating to a paid tier also sends those rounds to a model that does not. Whether higher tiers repair better has not been
measured yet. Private mode (Muse Spark Open) has no tiers.

## Independent cross-check (`--crosscheck`)

After a run certifies, `crosscheck.py` asks **Muse Spark Open** (open weights; `CROSSCHECK_MODEL_*`, falling back to
`OPEN_MODEL_*`, on its own host and key) to read the COBOL and the certified Java and propose inputs where it thinks they
differ, plus the fields it suspects. It reuses the breaker's loop: each proposed input is validated against the record
layout, then run through GnuCOBOL and the Java. **The model's opinion certifies nothing**; only a case that really differs
counts, and it goes to the repair agent like a breaker case (certification is revoked if the repair does not fix it).
Hard cap: `CROSSCHECK_MAX_CALLS` (default 2) model calls. Skipped, and said so in the run, when no open model is
configured, when the run itself is already on the open model, for multi-file programs, or if the host is down (a certified
run is never failed by it). It is opt-in because it spends on a second host (about $0.05 per run at list price).
Result: run.json `crosscheck` (run contract v0.10), its calls appear in the run's model card as "Independent check".

## Guard agent (in progress, not yet run against a live model)
`guard.py` watches the other agents (translator, repair, breaker) for leaks and test gaming.
- **Policy** (deterministic, every run): checked on the workspace before Java is executed (every differential test,
  certification and breaker attack). Unicode escapes are decoded, comments set aside and string literals (text blocks,
  octal escapes) decoded first. It refuses Java that openly uses the network, starts processes, uses reflection,
  dynamically loaded or native code, reads environment variables other than the program's own DD names,
  `DIOCLE_CLOCK` and `DIOCLE_COLLATION`, or names literal paths outside its working files. A refusal goes back to the
  repair agent (as a test result, at the start or at certification), which can remove the code. Threads, deletes and
  system properties are flagged. COBOL lines that look addressed to an AI are flagged.
- **Review** (`GUARD_MODEL_*`, e.g. Muse Spark Open on Baseten, its own key, capped by `GUARD_MAX_CALLS`): one call
  after a run is certified (and after the breaker), reading the final Java (comments removed) next to the COBOL
  (comment lines removed), fenced with a random token per call. The answer is read finding by finding; a `block`
  revokes certification and fix-memory lessons. Sources cut for length are never a clean pass. A failed review is
  recorded as `error` (type and HTTP status only) and does not revoke: the tests and the policy stand, and anyone able
  to break the answer could as easily talk the model into "pass". `smoke` sends the guard's real request.
- Results go to `run.json` (`guard`, run contract v0.11) and the trace (`guard` events); its calls are logged and
  priced with the run's.
- **Limits:** the policy is a speed bump, not a boundary. Java that builds a path or a class name at run time gets past
  it; only the sandbox (no secrets, no network, nothing kept) stops that. A model can be talked round.

## File shapes the translator is told about

`Program.io_text()` tells the model how each DD is used: inputs from `DD_x`, outputs written to `DD_y`, files opened I-O
(`io`) read from and written back to the same path with untouched records byte-identical, and, when the program writes
no file, that its DISPLAY output and exit code are the whole result. No new model call or limit was added for these
shapes (rule 10); the repair agent sees the one `stdout` result like any failing case. The breaker and cross-check
skip them (they need exactly one input and one output file).

## Run
```sh
cd services/converter
python3 -m venv .venv && .venv/bin/pip install -e ../verifier -e . pytest jsonschema
.venv/bin/python -m diocle_converter smoke                                     # one tiny call per model: checks keys + endpoints
.venv/bin/python -m diocle_converter repair ../../samples/interest-accrual     # bring your own conversion: repair the naive Java
.venv/bin/python -m diocle_converter run ../../samples/interest-accrual        # Meta model translates, then verify + repair
.venv/bin/python -m pytest -q                                                  # unit tests (scripted API double, no credits used)
```
Each run is saved under `runs/` at the repo root (gitignored): `java/`, `events.jsonl` (the agent trace), `run.json` (rounds, model calls, cost), `verification-report.json`.
