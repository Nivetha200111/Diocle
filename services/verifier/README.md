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
