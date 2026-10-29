# services/verifier

Status: **working for the `interest-accrual` sample** (Layer 3 of [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)). Not yet implemented: SonarQube quality gate, agent tool endpoints, Spring Boot runner (Java runs as a plain `main` class for now), layouts from the analyzer (layouts are read from the sample's `sample.json` for now).

Differential testing: compile the original COBOL with GnuCOBOL, compile the converted Java, run both on the same generated inputs, and compare every output record field by field. Emits `contracts/verification-report.schema.json` (v0.2).

## How it works
1. **Inputs:** named trap cases from `sample.json` (`fixtureCases`), then PIC boundary values (zero, smallest unit, max, negatives) per field, then seeded random records (log-uniform magnitudes). Deterministic for a given `--seed`.
2. **Original:** `cobc -x -std=ibm -I <copybooks>`, run with `DD_<name>` environment variables pointing at the input and output files (JCL-style DD names).
3. **Converted:** `javac`, then `java <mainClass>` with the same `DD_<name>` variables.
4. **Diff:** parse both outputs with the output record layout and compare values per field; flag records whose length is wrong (a field overflowed and shifted the rest); compare stdout.

## Copybooks as SQL tables
`python -m diocle_verifier.sqlschema SAMPLE_DIR [--out DIR] [--data DD=PATH ...] [--ebcdic]` writes `schema.sql` and
`sql-schema.json` (`contracts/sql-schema.schema.json`). Deterministic, no model calls, no GnuCOBOL. One table per
file layout, one column per elementary field in record order: alphanumeric and edited fields `CHAR(n)` (`VARCHAR(n)`
above DB2's 254-byte limit); zoned, packed and binary numerics `DECIMAL(p,s)` with the PIC's precision (P scaling
widens the integer part), unsigned ones with `CHECK (col >= 0)`; COMP-5 sized by its bytes, since IBM COBOL does not
truncate it to its PIC; COMP-1/COMP-2 `REAL`/`DOUBLE PRECISION`; FILLER kept; `rec_no` keeps record order. REDEFINES
views are listed on the column whose bytes they share (stored once); OCCURS entries become numbered columns; both
are stated in the DDL comments.

The proof, per record: every field is checked against its column's type as published (length for CHAR, precision
and scale for DECIMAL; SQLite itself ignores declared sizes), the row goes into an SQLite copy of the tables, is read
back, re-encoded field by field (by position, so several FILLERs keep their own bytes) and compared byte for byte.
Sources: PIC boundaries and seeded random values, written by the same codec, so they test the column mapping; and any
data files given with `--data` (`--ebcdic` converts mainframe files to GnuCOBOL form first; PKDPOST's golden files
pass). A record the tables cannot hold is reported with its field: letters in a numeric field, a value beyond its
PIC, a non-canonical sign nibble or negative zero that a DECIMAL cannot keep, a NaN, a short record.

Limits: SQLite keeps only 15 significant digits in NUMERIC columns, so in the SQLite copy wider DECIMALs are TEXT
(PostgreSQL and DB2 hold `DECIMAL(p,s)` exactly); SQLite turns a COMP-2 `-0.0` into `0.0`, which is reported as a
difference although PostgreSQL keeps it. PostgreSQL text cannot hold NUL bytes, so alphanumeric fields carrying binary
data need BYTEA there. Variant records (several record types behind one REDEFINES) are kept as the redefined bytes,
not split into typed columns per variant.

## Compile check of the original (before any model call)
Contract: [`contracts/compile-check.schema.json`](../../contracts/compile-check.schema.json) v0.1.
`diocle_verifier.precheck.compile_original(sample_dir, wait=None)` answers `ok`, `fail` (with the compiler's first
errors) or `unknown`. It compiles the ORIGINAL only, with the same invocation as verification
(`runners.build_cobol`: `cobc -x -std=ibm` + `IBM_FLAGS`, the sample's copybook dir, its CALLed modules, its collation)
and runs nothing. It exists so a program that GnuCOBOL cannot build (for example `PROGRAM-ID. X` with no period,
which IBM accepts) is found before the translator is paid for. CLI: `python -m diocle_verifier.precheck SAMPLE_DIR [--wait S]`.
- Where it runs: with `DIOCLE_SANDBOX_URL` set (and not `DIOCLE_IN_SANDBOX`) the sample is packed (regular files only,
  8 MB cap) and posted to the sandbox's `POST /compile`; the compile happens there, as the unprivileged user in the
  private tmpfs, and is never done in the calling process, not even as a fallback. Without a sandbox URL (developer
  machines) it compiles locally, like `verify_sample`.
- Limits: `cobc` 30 s, whole compile job 60 s (a real verification job may take 300 s), reply at most 16 KB; the
  message is at most 600 characters, the first four error lines, absolute paths reduced to file names (the client
  strips them again, whatever the sandbox sent). The sandbox still runs one job at a time and answers 503 when busy; the
  client retries for `wait` seconds (default `DIOCLE_SANDBOX_WAIT`) and then answers `unknown`.
- `fail` only when cobc's own diagnostics, lines of the form `file:line: error: ...`, say why. Everything else is `unknown`: a killed gcc or negative return code, `Killed`, `No space left`, `Cannot allocate`, the 30 s timeout, empty or unparseable output, a busy or unreachable sandbox, a bad answer, an unreadable sample. Callers proceed as before on `unknown`.
- The message holds only those diagnostic lines (server and client both filter): cobc echoes context lines of any file the source COPYs, even by absolute path, so every other line is dropped, quoted text becomes `'...'`, and an `unexpected X` keeps X only when it looks like a COBOL word.
- Not exercised in a real container: every sandbox test (compile and verify) uses the sandbox's HTTP handler in-process on a developer machine. The compile path's setuid/kill/cleanup as root, the tmpfs, memory and pids limits and the hung-gcc path (a stuck cobc killed at 30 s / the 60 s job limit) have NOT been run in the container. After a deploy someone must rebuild and recreate the sandbox (`docker compose ps` and image ids show it is the new image), run `docker compose exec api python -I -m diocle_verifier.precheck <sample dir>` once, and confirm it answers `ok` or `fail` (not `unknown`).

## Run
Requires GnuCOBOL 3.x (`brew install gnucobol`), a JDK, and Python 3.11+.

```sh
cd services/verifier
python3 -m venv .venv && .venv/bin/pip install jsonschema pytest
.venv/bin/python -m diocle_verifier ../../samples/interest-accrual                  # naive Java conversion: FAIL
.venv/bin/python -m diocle_verifier ../../samples/interest-accrual \
    --java-dir tests/fixtures/reference --random 2000                                 # faithful conversion: PASS
.venv/bin/python -m diocle_verifier ../../samples/interest-accrual --out report.json  # write the report
.venv/bin/python -m pytest -q
```

Exit codes: `0` all cases match, `1` mismatches, `2` a build failed.

Both Java conversions used today are **hand-written test fixtures, not model output**: `samples/interest-accrual/java-conversion/` is a deliberately naive port, and `tests/fixtures/reference/` is a faithful one used to prove the pass path.

## Whole-JCL-job verification (v1: one SORT step feeding one COBOL step)

`diocle_verifier.jobs.verify_job(sample_dir, job, pipeline, seed, random_count) -> dict` differentially tests
a whole JCL job end to end, not just one program: it consumes the analyzer's `jobs[]` entry
(`services/analyzer/diocle_analyzer/jcl.py`) and the converter's matching `jobPipelines[]` entry
(`services/converter/diocle_converter/pipeline.py`) exactly as those two modules already produce them.

- **Original side:** the job's one `kind:"cobol"` step compiles with the existing GnuCOBOL path
  (`runners.build_cobol`, unchanged). The `kind:"sort"` step has no mainframe utility to compile, so its
  reference behaviour reuses `multi.py`'s own `_sort_key()` byte-collation convention directly (imported,
  not reimplemented), so the reference sort and the converter's generated SORT class are provably using
  identical byte collation. Steps run in job order in a temp working directory; one step's output file
  becomes the next step's input file on disk, per the job's `wiring[]`.
- **Converted side:** the generated job pipeline directory (every `.java` file) compiles once with `javac`,
  then the driver class's `main()` runs once end to end via `ProcessBuilder`/subprocess, the same pattern
  `services/converter/tests/test_pipeline.py`'s own end-to-end test uses.
- **Seeding:** only the job's true external inputs are seeded (a DD some step reads that no step in the
  same job produces — for this v1 shape that is `SORTIN` alone), using the same `generate_cases`/boundary
  generator every sample uses. Any other DD fed from the sample's own `fixtureFiles` (e.g. `MSTIN`, the
  account master) seeds from there. `SORTOUT`/`TXNIN` are never seeded directly: they come from actually
  running the SORT step, which is what proves the inter-step hand-off, not just each step in isolation.
- **Comparison:** `diff.py`'s `compare()` runs once per `(step, output DD)` pair — unchanged, still
  position-based and byte-for-byte — and every result is tagged with which step and DD produced it, so a
  failure names a specific step (`contracts/verification-report.schema.json`'s `jobs[].steps[].passed`), not
  just an aggregate pass/fail. `certified` requires every step's outputs to match, the job's final exit
  code (`RETURN-CODE`) to agree between both sides, and both sides to have compiled.

Run `services/verifier/tests/test_jobs.py` (needs GnuCOBOL, a JDK, and `services/converter`'s own venv set
up, since the test generates a real job pipeline with `diocle_converter.pipeline.generate_pipeline` as a
subprocess into that venv — read-only, the same cross-service hand-off convention used elsewhere in this
project, never importing `diocle_converter` from this package).

**Not supported yet** (v1 scope, matching the analyzer's and converter's own job-level limits): COND-gated
or PROC-conditional steps, jobs with 3 or more steps, more than one SORT step in a job, GDG relative-
generation arithmetic beyond an exact base-DSN match, and SORT `INCLUDE`/`OMIT COND=`, `OUTREC`/`INREC`,
`SUM FIELDS=` or `MERGE` (the analyzer refuses all of these with a specific reason before a job reaches this
verifier at all, so `verify_job` only ever sees the one-SORT-then-one-COBOL shape). `verify_job` is not yet
wired into the `diocle_verifier` CLI or `verify_sample()`'s auto-dispatch; call it directly for now.

## Programs with no output file, and files opened I-O (report v0.8)

- **DISPLAY only** (`sample.json` `"displayOnly": true`, set by the analyzer): the one result is `stdout`
  (`inputSource` and `outputDd` `stdout`). It matches only if stdout is byte-identical **and** the exit codes (COBOL
  RETURN-CODE) are equal, and the original printed something: a run that printed nothing and wrote nothing cannot pass,
  whatever the flag says. Without the flag a program with no output file has zero results and fails. Inputs
  (if the program reads files) are generated as usual; stdin is closed, so a stray `ACCEPT` sees end of file on both sides.
  A program with no input at all is deterministic, so this is one run, not many cases; the certificate says so
  (`runs.stdoutCompared`, `runs.files.inputs`).
- **Opened I-O** (`direction: "io"`): the file is seeded from generated records (plus fixtures and corpus, like an
  input), each side gets its own copy at its DD path, and the file's final contents are compared record by record,
  byte for byte, like an output (`runs.files.updated` lists records seeded and left by each side). Fixed-record
  SEQUENTIAL files only; the analyzer refuses the rest.
- Proof without model calls: `tests/test_stdout_and_update.py` runs the hand-written Java of `samples/ledger-rewrite`
  (OPEN I-O, REWRITE), `samples/display-report` (DISPLAY only) and `samples/call-identifier` (CALL identifier) against
  GnuCOBOL, plus mutated Java that must fail (wrong update, forgotten REWRITE, one different DISPLAY line, one
  different exit code), a no-output no-DISPLAY program that must not pass, and `reverify` rebuilding both shapes from a
  legacy checkout.
- **Not done:** `verify_job` still compares output files only, so the analyzer keeps such programs out of JCL jobs.
