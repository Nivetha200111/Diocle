# services/converter

Status: **working slice** for the `interest-accrual` sample (Layer 2 of [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md)). Implemented: Meta model client with call caps and cost logging, whole-program translator (structured output), and the tool-using repair agent. Not yet implemented: Class Designer (2A), per-paragraph translation, SQL schema mapping, rule extractor, edge-case designer, judge, SonarQube issues, `conversion-output` contract emission.

Meta models only (CLAUDE.md rule 9), through the OpenAI-compatible Chat Completions API at `https://api.meta.ai/v1`.

## Repair agent
Tools: `run_differential_test`, `read_cobol_source`, `list_java_files`, `read_java_file`, `patch_java` (exact unique replacement, with a required rationale), `compile_java`, `finish`.
- Edits are confined to the run's Java workspace (`.java` files only).
- The agent sees test results for seed 1026 (200 random cases plus boundary and trap cases). **Certification re-runs the verifier on a held-out seed with 1,000 random cases**, so special-casing the inputs it saw doesn't pass.
- Caps: calls per run, calls per round, rounds (from `.env`). Every call's tokens (including cached input), latency and estimated cost are logged.
- Token efficiency: the COBOL, the Java and the first test result go in the opening message (no exploratory reads); `patch_java` returns the edited lines so the agent doesn't re-read files; a passing test tells the agent to finish immediately; history is append-only with stable content first so the provider's prompt cache applies (cached input is ~50x cheaper on `muse-spark-1.3-contributor`).

## Run
```sh
cd services/converter
python3 -m venv .venv && .venv/bin/pip install -e ../verifier -e . pytest jsonschema
.venv/bin/python -m diocle_converter smoke                                     # one tiny call: checks key + endpoint
.venv/bin/python -m diocle_converter repair ../../samples/interest-accrual     # bring your own conversion: repair the naive Java
.venv/bin/python -m diocle_converter run ../../samples/interest-accrual        # Meta model translates, then verify + repair
.venv/bin/python -m pytest -q                                                  # unit tests (scripted API double, no credits used)
```
Each run is saved under `runs/` at the repo root (gitignored): `java/`, `events.jsonl` (the agent trace), `run.json` (rounds, model calls, cost), `verification-report.json`.
