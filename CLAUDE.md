# CLAUDE.md: shared agent rules for Diocle

## Project goal
Diocle modernizes legacy COBOL for finance orgs: upload COBOL + copybooks, analyze, convert (copybooks to SQL schema, COBOL to Java services, generated tests), verify by differential testing against the original compiled with GnuCOBOL, and report in a dashboard. Built for the Meta Global AI Developer Hackathon (Oct 27 to Nov 4 2026; submit by Nov 4 9PM ET).

## Stack
- `apps/web`: Next.js dashboard
- `services/api`: Python or Node API
- `services/analyzer`: parsing, dependency graph, risk flags
- `services/converter`: conversion via **Meta models only** (see rule 9). Never use any non-Meta LLM inside the product.
- `services/verifier`: GnuCOBOL differential testing; SonarQube Community quality gate (optional, feeds the repair agent)
- `samples/`: **synthetic COBOL only**
- `contracts/`: shared JSON schemas between modules

## Rules
1. **Own folder only.** Each agent edits only its own folder. Need a change elsewhere? Open an issue or PR note for the owner.
2. **Contracts first.** Change or agree on the JSON schema in `contracts/` before implementing either side of a hand-off.
3. **Small commits** with clear messages (imperative mood, one logical change).
4. **Never commit secrets.** Keys live in `.env` (gitignored); only `.env.example` with empty placeholders is committed.
5. **No real client code or data.** No code, names, or data from any employer or client. All samples are synthetic and written here.
6. **Record what was built during the hackathon.** Keep commits dated within the hackathon window; note notable milestones in `docs/`.
7. **No fake implementations.** Stubs must be labelled as stubs; do not present mocked results as real.
8. **Run tests before opening a PR**, and state what was run in the PR description.
9. **Meta models only** for LLM calls in the product: Muse Spark via the Meta Model API (hosted mode), and Muse Spark Open via a partner host: Fireworks, Baseten (`meta-models/muse-spark-open-1026`) or Modal (private mode). Model IDs, endpoints and keys come from `.env`, never hardcoded. Dev tooling (e.g. coding agents) is separate from the product.
10. **Cost caps.** Every model loop has hard limits (tool calls per round, rounds per run) and logs token usage. Never add a paid service or raise a limit without the owner's OK.

## Definition of done per module
- **analyzer**: parses sample COBOL + copybooks; emits output valid against `contracts/analysis-report.schema.json`; risky logic flagged; tests pass.
- **converter**: emits SQL schema, Java, and tests valid against `contracts/conversion-output.schema.json`, via Meta models only (rule 9); tests pass; no secrets in code or logs.
- **verifier**: compiles the original with GnuCOBOL, runs both versions on the same generated inputs, diffs outputs; emits `contracts/verification-report.schema.json`; reproducible on synthetic samples.
- **api**: exposes upload/analyze/convert/verify/report endpoints per the contracts; tests pass; documented run steps.
- **web**: dashboard renders real report data from the API; builds without errors; runs end to end for the demo.
- **docs/samples**: synthetic only; docs match what is actually implemented.

## Current priority (Oct 29 to Nov 1): dependencies, more versatile conversion
The owner's goal for the last days before submission. Work on the Mac (GnuCOBOL 3.2 + JDK 21 are there; the Windows
work laptop cannot compile or deploy). First: `deploy/update-engine.sh` (the engine needs it for `GET /runs/{id}/schema`).

Where dependencies stand (from the code): copybooks (incl. COPY REPLACING) drive layouts and verification; static
CALLs are followed transitively, translated together and linked into one GnuCOBOL executable; SELECT/FD/OPEN plus JCL
(procs, symbolics, DD overrides) map files to datasets; match-merge and SORT USING/GIVING work; output formats stay
byte-identical so downstream consumers are unaffected. Refused with a reason (`_not_convertible` in
`services/analyzer/diocle_analyzer/analyze.py`): EXEC SQL/CICS/DLI, INDEXED/RELATIVE files, I-O files, dynamic CALL,
CALLs to programs not in the repo, programs with no output file. Not done: converting the JCL job itself (step order,
DFSORT/IDCAMS steps), copybook to SQL schema.

Build in this order, each one proven by the same differential test (GnuCOBOL vs Java, byte for byte) before it counts,
contract first (rule 2), with tests, README "Not supported yet" updated, and a reviewer-agent pass before pushing:
1. **More programs convert (~0.5 day).** (a) Programs with no output file but DISPLAY output: compare stdout and exit
   code (the verifier already records `stdoutMatch`). (b) Sequential files opened I-O (REWRITE): seed from generated
   inputs, compare the final file contents. (c) `CALL identifier` where the identifier only ever holds literals
   (VALUE clause, literal MOVEs): resolve statically in `cobol.py`, otherwise keep refusing. Measure on
   github.com/openmainframeproject/cobol-programming-course (17 of 34 converted before).
2. **Whole JCL job end to end (~1 day).** From `jcl.py` steps: convert every COBOL step, emulate SORT steps
   (SORT FIELDS=), generate one Java pipeline that runs the steps in order through the same DD-to-file wiring, run the
   whole job both ways and compare every final dataset. Show it as one certificate per job.
3. **Copybook to SQL schema: DONE Oct 29 on the Windows laptop** (`diocle_verifier.sqlschema`, `GET /runs/{id}/schema`,
   schema.sql tab next to the Java; needs an engine deploy to show live). Original brief: DDL from the analyzer's layouts (packed and zoned
   decimals to DECIMAL(p,s), REDEFINES and OCCURS stated explicitly), proven by a round trip: load generated records
   into SQLite and write them back byte-identical. Fulfils the project goal above.
4. **DB2 / EXEC SQL (~1.5-2 days, only if time remains).** COBOL through an SQL precompiler against PostgreSQL, Java
   through JDBC, compare outputs and final table contents; needs a database inside the sandbox (security review).

Do not break what works: re-run the six Quillmark programs and the eval programs after each step, keep the live
demo (CHQCLR, Try the sample) green, and freeze deploys after submission (Nov 4, 9 PM ET = Nov 5, 7:30 AM IST).

## Session hand-off
Work moves between machines, and local Claude memory does not travel. At the start of every session read
`docs/HANDOFF.md`. As you build, keep it current: update "Current state", "Open work" and "Done recently"
after each meaningful step (a deploy, a merged change, a finding, a decision), and commit it with the work.
It is public: no secrets, passcodes, personal details or employer names.
