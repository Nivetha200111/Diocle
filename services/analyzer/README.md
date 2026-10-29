# services/analyzer

Deterministic analysis of a COBOL estate. No model calls.

- **Layouts from copybooks:** display fields (`PIC X(n)`, `9(n)V9(m)`, `S9... SIGN LEADING SEPARATE`), with 88-level values for alphanumeric fields. Packed or binary usage in a record, REDEFINES, OCCURS and trailing (overpunch) signs are reported as unsupported, never guessed.
- **File wiring:** `SELECT ... ASSIGN TO <DD>`, the copybook under each `FD`, and `OPEN INPUT/OUTPUT` give each program's input and output files.
- **JCL:** which job runs each program and the dataset behind each DD name.
- **Jobs (`jobs[]`, v1):** groups JCL steps by job in source/EXEC order, classifies each step (`cobol`/`sort`/`other`), parses `SORT FIELDS=` control statements, wires step-to-step DD/DSN flow, and says whether the whole job converts. Scope for this v1 is deliberately narrow: a job converts only if it is exactly one SORT step followed by one COBOL step, where the SORT step's output DD's DSN exactly matches one of the COBOL step's input DD DSNs. **Not supported yet** (refused with a specific reason): COND-gated or PROC-conditional steps, jobs with 3+ steps, more than one SORT step, GDG relative-generation arithmetic beyond an exact-DSN match (`(0)`/`(+1)`/`(-1)` are normalized away for comparison, nothing more), and SORT `INCLUDE`/`OMIT COND=`, `OUTREC`/`INREC`, `SUM FIELDS=`, `MERGE` or a key format other than `CH`/`ZD`/`PD`/`BI`.
- **Findings:** `COMPUTE ROUNDED` (half away from zero), `COMPUTE` without `ROUNDED` (truncation), no `ON SIZE ERROR` (silent high-order overflow), and `DISPLAY` of binary counters.

Output: [`contracts/analysis-report.schema.json`](../../contracts/analysis-report.schema.json). With `--samples-dir`, each convertible program (one input file, one output file, supported layouts) is written as a Diocle sample directory for the converter.

## Run

```sh
cd services/analyzer
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/python -m diocle_analyzer https://github.com/Nivetha200111/quillmark-legacy --out /tmp/report.json --samples-dir /tmp/imported
.venv/bin/python -m pytest
```

GitHub imports are cloned shallow into `runs/imports/` and pinned to the commit analyzed. The verifier compiles and runs imported code, so imports are limited to the owners in `DIOCLE_IMPORT_OWNERS` (default `Nivetha200111`) until they run in a sandbox.
