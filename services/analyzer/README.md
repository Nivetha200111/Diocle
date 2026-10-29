# services/analyzer

Deterministic analysis of a COBOL estate. No model calls.

- **Layouts from copybooks:** display fields (`PIC X(n)`, `9(n)V9(m)`, `S9... SIGN LEADING SEPARATE`), with 88-level values for alphanumeric fields. Packed or binary usage in a record, REDEFINES, OCCURS and trailing (overpunch) signs are reported as unsupported, never guessed.
- **File wiring:** `SELECT ... ASSIGN TO <DD>`, the copybook under each `FD`, and `OPEN INPUT/OUTPUT` give each program's input and output files.
- **JCL:** which job runs each program and the dataset behind each DD name.
- **Jobs (`jobs[]`, v1):** groups JCL steps by job in source/EXEC order, classifies each step (`cobol`/`sort`/`other`), parses `SORT FIELDS=` control statements, wires step-to-step DD/DSN flow, and says whether the whole job converts. Scope for this v1 is deliberately narrow: a job converts only if it is exactly one SORT step followed by one COBOL step, where the SORT step's output DD's DSN exactly matches one of the COBOL step's input DD DSNs. **Not supported yet** (refused with a specific reason): COND-gated or PROC-conditional steps, jobs with 3+ steps, more than one SORT step, GDG relative-generation arithmetic beyond an exact-DSN match (`(0)`/`(+1)`/`(-1)` are normalized away for comparison, nothing more), and SORT `INCLUDE`/`OMIT COND=`, `OUTREC`/`INREC`, `SUM FIELDS=`, `MERGE` or a key format other than `CH`/`ZD`/`PD`/`BI`.
- **Programs with no output file (`displayOnly`, contract v0.5):** convertible when the PROCEDURE DIVISION DISPLAYs to stdout (a `USAGE DISPLAY` clause and `DISPLAY ... UPON SYSERR` do not count) and no `ACCEPT` reads the console. The verifier then compares stdout and the exit code. A program with no output file and no DISPLAY is still refused ("writes no output file to compare").
- **Files opened I-O (direction `io`):** convertible only for fixed-record `ORGANIZATION SEQUENTIAL` files opened I-O everywhere in the program; the verifier seeds the file from generated records and compares its final contents. LINE SEQUENTIAL, INDEXED and RELATIVE files, and a file opened I-O in one place and another way in another, are refused.
- **`CALL identifier` (`resolvedCalls`):** resolved to a program name only when the identifier is a plain elementary WORKING-STORAGE item (level 01/77, no REDEFINES/OCCURS, not in LINKAGE or a copybook) and every use of it in the PROCEDURE DIVISION is a read (DISPLAY, a condition, the source of a MOVE), the call itself, or `MOVE 'literal' TO` it, with the VALUE clause and all literals naming one program. STRING/UNSTRING/ACCEPT/READ INTO/INITIALIZE/SET/INSPECT/arithmetic, passing it in CALL ... USING, a subscript or reference modification, or a second literal keeps the call refused as dynamic. Statements are read as tokens, so a MOVE split over several lines is seen. The resolved program is linked like any static CALL.
- **A JCL job does not inherit these shapes:** a job whose COBOL step is DISPLAY-only or updates a file in place is not convertible as a job (the job check compares output files only); the program still converts on its own.
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
