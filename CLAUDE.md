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
