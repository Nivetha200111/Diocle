# services/analyzer

Deterministic analysis of a COBOL estate. No model calls.

- **Layouts from copybooks:** display fields (`PIC X(n)`, `9(n)V9(m)`, `S9... SIGN LEADING SEPARATE`), with 88-level values for alphanumeric fields. Packed or binary usage in a record, REDEFINES, OCCURS and trailing (overpunch) signs are reported as unsupported, never guessed.
- **File wiring:** `SELECT ... ASSIGN TO <DD>`, the copybook under each `FD`, and `OPEN INPUT/OUTPUT` give each program's input and output files.
- **JCL:** which job runs each program and the dataset behind each DD name.
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
