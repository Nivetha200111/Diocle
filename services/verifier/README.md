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
Contract: [`contracts/compile-check.schema.json`](../../contracts/compile-check.schema.json) v0.2 (diagnostics travel as a list of strings, never one joined string).
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
- `diagnostics` holds only cobc's own `FILE:LINE: error: TEXT` lines (file part `[\w.$-]+`, so gcc's `foo.c:12:5: error:` is not accepted). cobc echoes source context (`    2 |  <line>`) of any file the source COPYs, even by absolute path: such lines are dropped before matching, and the output is split on line ends only. Inside a kept line every word that is not a reserved word or a word of cobc's own messages (`diocle_verifier/diag_words.py`, generated by `scripts/gen_diag_words.py`) and all quoted text becomes `...`; file-not-found, permission denied and the like are one generic reason (`cannot read a COPY file`). Server and client both filter, string by string. `note` for `unknown` is always a fixed phrase.
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

## Programs with EXEC SQL, on a stand-in database (report v0.9, subset `db2-subset-1`)

**What is verified.** The COBOL with embedded SQL and the Java (JDBC) start from the SAME seeded database state plus the
same generated input files. Afterwards their files, stdout, exit code AND the final contents of every table they touched
are compared, value for value (`runs.database`, one `table:NAME` result per table with the first mismatching row and
column). Only the verifier certifies; a model's opinion never counts. **The claim is exactly this: equivalent on this
stand-in engine for these statements on the inputs tried. It is never "DB2-verified".**

**The engine is SQLite, not DB2.** Both sides use it (the COBOL side through a small C shim, `dbsupport/dioshim.c`, linked
into the GnuCOBOL executable; the Java side through the org.xerial JDBC driver), so what is compared is COBOL against Java
on identical engine semantics. Numbers never touch floating point: DECIMAL(p,s) and the integer types are INTEGER columns
holding value x 10^s (a CHECK keeps the value within p digits, SQLCODE -413), CHAR/VARCHAR are TEXT without trailing
blanks (CHECK on length, -404).

**Pipeline.** `sqlpre.py` rewrites each EXEC SQL statement into COBOL: host variables are MOVEd into work items (so
GnuCOBOL itself does PIC / COMP-3 / sign / scale conversion exactly as for any MOVE), one `CALL "DIOSQL"`, and MOVEs
of the results back. The statement table is generated C compiled in with the shim. `sqlseed.py`/`sqldb.py` seed one
database file per side (identical content): tables come from `sample.json` `sql.tables`, rows are deterministic from the
seed (boundary values, NULLs in nullable columns, unique primary keys), and key columns shared with an input file draw
from that file's values (80% present, so found and not-found paths both run). `seedRows` (per table; the analyzer sets 0
for tables the program only INSERTs into), `columnValues` and `keyLinks` in `sample.json` refine it. The Java is compiled
with the verifier's own `DioSql.java` over any file of that name in the conversion.

**The subset** (the analyzer's `sqlsubset.py` is the one definition; the precompiler refuses everything else):
INCLUDE SQLCA (required) and INCLUDE of copybooks (DCLGEN); DECLARE TABLE (program or copybook) or CREATE TABLE in a
`*.sql` file (no schema: refused, never guessed); host variables that are elementary items, with null indicators;
`SELECT cols | COUNT(*) | SUM/MIN/MAX(col) INTO ... FROM t [WHERE] [ORDER BY]` (one table); `INSERT INTO t [(cols)] VALUES`
(every column supplied); `UPDATE t SET col = value | col +/- value [WHERE]`; `DELETE FROM t [WHERE]`; cursors
(`DECLARE c CURSOR FOR SELECT ... ORDER BY`, OPEN, FETCH INTO, CLOSE; ORDER BY is required since the row order must be
defined); COMMIT; ROLLBACK; `WHENEVER ... CONTINUE`. Conditions: `col (= <> < > <= >=) host|literal`, `IS [NOT] NULL`, AND/OR,
parentheses. Types: CHAR, VARCHAR, SMALLINT, INTEGER, BIGINT (18 digits), DECIMAL(p<=18,s). SQLCODE set: 0, +100,
-803 duplicate key, -811 more than one row, -407, -404, -413, -305 (NULL without indicator), -501/-502 (cursor state), -901
(other engine error), -904 (statement cap, `DIOCLE_SQL_MAX_STMTS`, default 500000, COBOL side). Only SQLCODE and SQLERRD(3) are set;
a program that reads SQLSTATE, SQLERRM or SQLWARN is refused. COMMIT and ROLLBACK close every cursor; work still open at
normal end is committed (what DB2 does in batch).

**Refused, with the exact reason and line** (`notConvertibleReason`; convert-anyway still translates them as
`compiled-unverified`): dynamic SQL (PREPARE, EXECUTE, DESCRIBE), stored procedures (CALL), JOINs, subselects, GROUP BY, DISTINCT,
functions and special registers (CURRENT DATE, UPPER, ...), FETCH FIRST, WITH UR / isolation, FOR UPDATE, WHERE CURRENT OF,
cursor WITH HOLD, multi-row FETCH/INSERT, SQLDA, LOB/DATE/TIMESTAMP/float columns, DEFAULT columns, schema-qualified names, group host
variables, numeric-edited host variables. CICS and IMS are out of scope.

**Known gaps between SQLite and DB2** (nothing here is claimed): DB2 type and precision rules, isolation and locking
(no concurrent users here), -811/-305 corner cases beyond those listed, VARCHAR keeps trailing blanks in DB2 (here every
character value is blank-trimmed), character collation (SQLite sorts bytes; z/OS sorts EBCDIC unless told otherwise),
optimizer-dependent behaviour, DB2 error codes outside the small set above, SQL syntax DB2 accepts and SQLite does not (and
the reverse). A program that is equivalent here can still behave differently on DB2.

**Security model.** The engine runs inside the existing sandbox job: no network, no secrets, read-only image, the database
is a file in the job's private tmpfs (`/tmp`, created per job, removed with the job's directory; the sandbox also deletes
`/tmp` and kills every process after each job), rows are capped (2000 per table seeded), the database file is capped at 32 MB
(`max_page_count`), the job has the existing time limit, and a statement cap exists on the COBOL side. Statement text in the
generated C comes only from the parsed subset (escaped, identifiers validated), never from the program's raw text. Model-written
Java can run any SQL SQLite allows (ATTACH, extensions are off in the driver) but is confined to the container and to /tmp. The
JDBC driver and `libsqlite3-dev` are added to the image at BUILD time (`deploy/Dockerfile.api`); nothing is fetched at run time.
Residual risks: the driver jar is downloaded at build (checked against Maven Central's published checksum unless
`SQLITE_JDBC_SHA256` is pinned); the guard's Java policy is a speed bump, not a boundary (the sandbox is); the C shim is
our code linked into the same process as untrusted COBOL (a hostile COBOL program can overwrite its memory, as it can in any
program it compiles); the Java side has no statement counter (only the job timeout bounds it); SQLite and the JDBC driver
bundle different SQLite versions (the report states the verifier's); never run in the real container (see HANDOFF).

**Keeping the converted Java honest (report v0.9).** (1) Every converted `.java` file except the verifier's own `DioSql.java` is
checked before it runs (`sqlrun.check_java_source`): DriverManager, `jdbc:`, sqlite, Class.forName, ATTACH, PRAGMA, VACUUM,
load_extension, `.db` names, DIOCLE_DB, ProcessBuilder, Runtime, reflection, non-ASCII text and unicode escapes are refused (also across
string concatenation), and the refusal reaches the repair agent as the Java's build output. It is a speed bump: a determined author can
build names at run time. (2) The Java runs FIRST, in its own directory, on its own copy of the seeded database; the original's database does
not exist yet, so the Java cannot read or overwrite the answer it is compared with. The verifier hashes `seed.db` before and after the Java
run and refuses to run the original (verification fails closed, reason in `runs.original.stderr`) if it changed or if the Java created the
original's file. (3) The verifier itself opens both final databases for the dump; after the run each database file must be within the size
cap (32 MB, `PRAGMA max_page_count` on both sides plus a check by the verifier), else a failing `database-check` result. (4) A program
with INSERT/UPDATE/DELETE whose tables did not change from the seed on either side is NOT certified ("no write statement took effect on
the inputs tried"); `runs.database.tables[].changedFromSeed` says per table and side. This is per table, not per statement. Seeding draws key
columns from the input file only for the `keyLinks` the analyzer finds by name; a WHERE on a host variable the analyzer could not link may
still never match, and then the no-effect rule fails the run rather than certifying it. Same uid in the job: the checks above and the sandbox
(not file permissions) are the defence; a hostile Java that finds the original's directory after the COBOL run is not possible (nothing runs
after it), but a Java that damages other files in /tmp is only contained by the container. **Order of a SQL run (round 2):** seed, build the Java, hash everything the original is built from or reads (the input files and I-O seeds in the job's temp dir, `seed.db`, the COBOL source, modules and copybooks in the sample dir), run the Java, re-hash (any change, or a stray `original`, `original.db` or `sqlpre` the Java created, fails closed and the original is never built or run), and only then build the COBOL executable from the pristine source and run it. The static check also refuses System.load/loadLibrary, MethodHandles, ServiceLoader, Runtime.getRuntime/exec and any System.getenv other than a `DD_` file variable, DIOCLE_COLLATION or DIOCLE_CLOCK. The size cap is also enforced during the run (`PRAGMA max_page_count` in the verifier's `DioSql.connect`, test: a Java that inserts until the engine stops it). **Residual risk, stated plainly:** the Java runs as the same user as the verifier, so by absolute path it can still write anything under the job's temp directory (`/tmp/diocle-verify-*/`, including `classes/` and `java-src/`) and the sample directory (`/tmp/job-*/sample/` in the sandbox); we detect changes to what the original uses, we do not prevent them, and an unlisted file or a name built at run time is not caught. The sandbox container (no network, no secrets, tmpfs wiped after the job) is the boundary, not these checks. **SQLCODE is compared only through its visible effects**
(files, stdout, exit code, table contents): a SQLCODE the program never shows or acts on is not compared.

**Run locally.** GnuCOBOL 3.2, a JDK, a C compiler with the SQLite headers (`libsqlite3-dev`; macOS has them in the SDK), and
the JDBC driver: `export DIOCLE_SQLITE_JDBC=/path/to/sqlite-jdbc.jar` (or put it in `services/verifier/lib/sqlite-jdbc.jar`,
gitignored). Then `python -m diocle_verifier ../../samples/db2-account-report`. Tests: `tests/test_sql.py` (skipped when
cobc, javac or the driver are missing).

## Keyed (INDEXED) files, on GnuCOBOL's indexed handler (report v0.10, subset `ksds-subset-1`)

**What is verified.** Programs whose keyed files are in the subset (the analyzer's `keyed.py` is the one definition) run both
sides from identical seed records; afterwards the final contents of every keyed file are compared record by record in key
order (`runs.keyed`, one `keyed:DD` result, first mismatching key and kind: value / missing-in-converted / extra-in-converted),
together with the output files, stdout and exit code. **The claim is exactly: equivalent on GnuCOBOL's INDEXED handler (Berkeley DB),
for this subset of operations, on the inputs tried. It is not IBM VSAM** (no CI/CA splits, no alternate indexes, no locking, no IDCAMS).

**The two sides.** The original runs on the real handler in its own directory. The Java runs on `dbsupport/DioKsds.java`, the
verifier's own class (compiled over any file of that name in the conversion), which reproduces the handler's observable
behaviour: FILE STATUS codes (00 10 21 22 23 35 41 42 43 46 47 48 49), unsigned byte-wise key order, START and READ NEXT
positioning (including the quirks found by experiment: the first READ NEXT returns the record that was first when the file was opened, a
failed START makes the next READ NEXT report 46, a WRITE does not move the position, a sequential REWRITE or DELETE needs the
immediately preceding successful READ). `tests/test_ksds.py` runs randomised operation sequences (all three access modes, misuse
included, also under `-fdefault-colseq=EBCDIC`) on the real handler and on DioKsds and requires identical statuses and records. A sequential
REWRITE that changes the key is outside the subset (the real handler deletes and re-inserts); DioKsds throws, so such a Java fails.
**Key order:** the handler orders keys by raw bytes whatever the collating sequence, so the Java must too (the translator prompt says so).

**Seeding and comparison.** `ksds.py` makes unique keys (boundary keys such as all spaces, zeros, nines, `A`, `Z`, `a`, `z`; keys with leading
characters that sort differently in ASCII and EBCDIC), derives records from the layout (PIC boundaries and seeded random values), and
links transaction fields (`sample.json` `ksds.keyLinks`, set by the analyzer from names and widths) to the keys: about half present in the
seed, 40% absent. The original's keyed file is built and read back by small COBOL programs the verifier generates (`ksds-tools`), so the Python
side never parses the Berkeley DB format; the Java keeps plain fixed-length records in key order.

**Anti-tamper, as for SQL.** The Java runs first in its own directory on its own copy; inputs, seeds, the COBOL source, modules and copybooks are
hashed around the run and any change fails closed; strays (`original`, `*.kf`, `ksds-tools`) fail closed; the Java is statically refused if it
names a keyed file's DD, a `.kf` or `kseed` path, or uses reflection, processes, native code or `java.net` (a speed bump: a determined
author can build names at run time; the sandbox is the boundary); sizes are capped (20,000 records, 16 MB). A program that writes keyed
records where neither side's file differs from its seed is not certified.

**Not covered:** alternate keys, duplicates, RELATIVE files, locking, OPEN EXTEND, READ PREVIOUS, START `<`/`<=`, group/signed/packed keys, multiple OPEN modes of one file,
DECLARATIVES, keyed files together with EXEC SQL, IDCAMS and real VSAM behaviour (record length changes, CI/CA splits, free space).
