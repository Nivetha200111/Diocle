# services/verifier

Status: **working for the `interest-accrual` sample** (Layer 3 of [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)). Not yet implemented: SonarQube quality gate, agent tool endpoints, Spring Boot runner (Java runs as a plain `main` class for now), layouts from the analyzer (layouts are read from the sample's `sample.json` for now).

Differential testing: compile the original COBOL with GnuCOBOL, compile the converted Java, run both on the same generated inputs, and compare every output record field by field. Emits `contracts/verification-report.schema.json` (v0.2).

## How it works
1. **Inputs:** named trap cases from `sample.json` (`fixtureCases`), then PIC boundary values (zero, smallest unit, max, negatives) per field, then seeded random records (log-uniform magnitudes). Deterministic for a given `--seed`.
2. **Original:** `cobc -x -std=ibm -I <copybooks>`, run with `DD_<name>` environment variables pointing at the input and output files (JCL-style DD names).
3. **Converted:** `javac`, then `java <mainClass>` with the same `DD_<name>` variables.
4. **Diff:** parse both outputs with the output record layout and compare values per field; flag records whose length is wrong (a field overflowed and shifted the rest); compare stdout.

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
