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
breaker attacks with tier 2 (`MODEL_TIER_BREAKER`, default 2; set 3 to opt in to Muse Wonder). When the breaker (or the
cross-check) breaks a Java that had already certified, the repair agent resumes at tier 2 (`MODEL_TIER_AFTER_BREAK`, default 2).
Why not the top tier by default: in a real run one Muse Wonder breaker call cost $0.22 to $0.37 (reasoning tokens bill at
$20/M) and made up 96% of the run's cost, while the cheap tier fixed the break it found for about $0.02. Hard caps (rule 10) on everything above tier 1: `MODEL_ESCALATION_MAX_CALLS`
(default 12) and `MODEL_ESCALATION_MAX_USD` (default 0.50) per run, counted as calls happen; when spent, the run falls back to
tier 1 and still finishes. A model with no entry in `PRICES` counts as the whole cap (fail closed), and the cap is checked
before each call and projects one more call as dear as the dearest escalated call so far, so a second large call is refused; there is no output-token limit, so the first large call can still overshoot (a Wonder call with a long repair conversation measured about $0.22). The breaker's attack calls spend the same cap first, so a repair resume after a break may find it spent and fall back to tier 1. The contributor tier lets Meta use requests to improve its products;
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

## Verified documentation (`--document`, or `document SAMPLE`)

`documenter.py` asks a Muse Spark model (the run's default contributor model unless `DOC_MODEL_ID` is set; same host and key
unless `DOC_MODEL_BASE_URL`/`DOC_MODEL_API_KEY`) to write a plain-English behaviour spec of the COBOL as claims: one sentence
about observable output each, plus 1 to 3 concrete examples (input records as field values, expected output field values). Every
example is validated against the input layout with the breaker's `explain` (same rules) and run on the **original COBOL** through
the verifier (`diocle_verifier.claims`, in the sandbox when `DIOCLE_SANDBOX_URL` is set; no Java, no network). **GnuCOBOL decides:**
a claim is *confirmed* (every example matched), *refuted* (the COBOL produced something else; the actual value is kept and shown)
or *unchecked* (an example was invalid for the layout, or the program did not run). Wording: "confirmed on the examples tried",
never "proven". Single-file record programs only. Hard caps: `DOC_MAX_CALLS` (2; the second call only retries an unusable
answer), `DOC_MAX_USD` (0.10; a call whose worst case could pass it is refused before it is made), `DOC_MAX_OUTPUT_TOKENS`
(6000, because reasoning tokens bill as output); an unpriced model is refused (fail closed). It never fails a run: any problem
becomes `skipped`/`unchecked` with a reason. Output: run.json `behavior` (run contract v0.13, `contracts/behavior-claims.schema.json`),
`behavior.json`, `behavior.md`; token use is logged in the run's usage.

## Printout intake (`transcribe`): photo of a listing to COBOL

`python -m diocle_converter transcribe IMAGE --out SAMPLE_DIR [--against ORIGINAL_SAMPLE [--run-model-code]]` (`vision.py`, record contract
`contracts/transcription.schema.json` v0.1). A vision model reads a PNG/JPEG (at most 2 MB, judged by its bytes) of a
fixed-format COBOL listing and writes the source to `SAMPLE_DIR/src/<PROGRAM-ID>.cbl`; `transcription.json` records the model,
tokens, cost, attempts and both gate results. **Off unless `VISION_MODEL_ID` is set** (we use Meta's `muse-wonder-1.0`, on the
same Meta Model API key: `VISION_MODEL_BASE_URL`/`VISION_MODEL_API_KEY` fall back to `META_MODEL_*`). The model is never the
judge:
1. **Compile gate:** `cobc -fsyntax-only -std=ibm` with the verifier's IBM flags, locally. A failure sends the compiler errors back once
   more (the same image, the previous answer and the errors); there is no other re-prompt.
2. **Differential gate** (needs `--against` and `--run-model-code`): the transcription and the original are both built with GnuCOBOL and run on the same
   1,013 generated inputs (the verifier's generator and comparator, seed 1026); output records, stdout and exit code must match.
   A mismatch is reported as status `differs`, never hidden or "repaired" by the model. The original's copybooks are copied
   into `SAMPLE_DIR` (they are not on the printout) and a `sample.json` without any Java is written.
Without `--against` the best status is `compiled-unchecked`: it compiles, and nothing proves it is what the paper said.
Hard caps (rule 10): `VISION_MAX_CALLS` (3), `VISION_MAX_USD` (0.20, checked before each call against a worst case of the
whole `VISION_MAX_OUTPUT_TOKENS` (5000) at the output price, so a second call can be refused after an expensive first), and every call is
logged with tokens and cost. Muse Wonder's reasoning tokens bill as output ($20/M, third-party price, unconfirmed), `reasoning_effort`
is `low` (`VISION_REASONING_EFFORT`). The compile check runs the local `cobc` on text a model wrote: this is the CLI path for our own
synthetic printouts, not a designed engine/API path (compiling untrusted text would belong in the sandbox).

**Safety and limits of the gates (reviewed twice).**
- **Running model-written COBOL is opt-in.** `--against` alone does the compile check and the refusal scan, then stops at
  `compiled-unchecked` ("running model-written COBOL on this machine needs --run-model-code"). Only `--run-model-code`
  (`run_model_code=True`) builds and **executes the transcription on this machine** (a one-line warning is printed). Use it only for
  our own synthetic printouts on a dev machine, never for text from strangers; each program run is limited to 120 s, the compile to 60 s.
- **The refusal scan is a best-effort filter and NOT a security boundary.** Before anything is compiled the text must be plain
  fixed format (no tabs, no compiler directives such as `>>SOURCE FORMAT IS FREE` or `$ SET`, columns 1-6 blank or digits, column 7
  one of blank `*` `/`, nothing after column 72; **continuation lines (column 7 `-`) are refused outright** because they can split a keyword (`COP` + `-  Y "/etc/hosts"`, `CA` + `-  LL`) so the scans never see it); it must not contain `CALL 'SYSTEM'`, any `CBL_*` or `C$*` routine, a `CALL` of an
  identifier or of a program not listed in the original's `modules`; with `--against`, `ASSIGN TO` may name only the original's DD names
  (no paths or literals) and `COPY` only the original's own copybooks (without an original no `COPY` at all, since cobc would read the named file). A refusal is status `refused`: never compiled, run or
  written, no further model calls. A determined model can still build names or behaviour at run time in ways no deny-list sees.
- **macOS defense in depth:** where `sandbox-exec` exists, the transcription's executable (only that, not cobc and not the original)
  runs under a profile that denies network, denies file writes outside its own work directory (plus `/dev/null` and the tty) and denies
  executing anything but itself (`differential.sandbox` says `sandbox-exec`; elsewhere `none`). It does NOT limit reads (the GnuCOBOL
  runtime and the input are read from all over the disk, so file contents can still be read), CPU or memory (only the 120 s timeout),
  and `sandbox-exec` is deprecated by Apple. The compile step runs `cobc` unsandboxed on the scanned text.
- **Compiler output is filtered** before it goes into `transcription.json` or back to the model as the retry prompt: only `<transcription file>:N: error: <message>` lines about the transcription's own file survive (max 20 lines, 1,500 characters), quoted text is masked, and everything else (other files, echoed source lines) is dropped, so a file the compiler read cannot leak through its errors.
- `--out` must be new or empty, not a symbolic link, and must not overlap `--against` (refused, 0 calls, nothing written); the
  original is also snapshotted into a temp directory before anything is written and the differential uses the snapshot. The original's
  copybooks are copied to `SAMPLE_DIR/copybooks` (never a name that could collide) and `sample.json` points there; the original's
  `modules`, if any, are not copied.
- `verified-identical` needs something actually compared: at least one output record, or a non-empty stdout (a DISPLAY-only original, with
  one input file and no output file, is compared on stdout and exit code). Otherwise `compiled-unchecked`. A timeout, a missing `cobc` or an
  unusable `sample.json` is reported (`compile-failed`, a differential with `ran: false` and `compiled-unchecked`, or `refused`) and
  `transcription.json` is still written.
- Exit codes of `transcribe`: 0 only for `verified-identical`; 2 `compiled-unchecked`, 3 `differs`, 4 `compile-failed`, 5 `refused`, 6 `no-transcription`.

Proven once, on one synthetic printout, before the opt-in and sandbox layers existed (`samples/loyalty-waiver-printout`, rendered from `samples/loyalty-waiver` by
`demo/render-listing.py`): Wonder accepted the image part, transcribed 44 lines in one call (1,586 in / 3,018 out tokens
including 2,596 reasoning, $0.067), it compiled first time and matched the original on 1,013 of 1,013 inputs. **Not proven:** that this
holds for other printouts, photos (this image is clean, rendered, not a camera shot), other fonts, long programs or handwriting. The
transcription was NOT textually identical: the model collapsed runs of spaces on 4 lines (comment indent, `FD  LY-FILE`, the
`PIC` alignment), which does not change behaviour; reading column positions off an image is its weakest point. And the
differential only samples: random inputs rarely hit exact boundaries (the same weakness the breaker agent exists for, e.g. `NOT <
5000.00` read as `>` would change only the inputs at exactly 5000.00), so `verified-identical` means "no difference on 1,013
generated inputs", not equality for all inputs.

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
