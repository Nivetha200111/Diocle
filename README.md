# Diocle

**Status: scaffold, in progress.**

Diocle is an AI "system integrator" that modernizes legacy COBOL for finance organizations. Upload COBOL programs and their copybooks, and Diocle analyzes them (dependency graph, risky fraud/payment logic flagged), converts them (copybook trees to SQL schema, COBOL to Java services, generated tests) using Meta's models, and then verifies the result by compiling the original with GnuCOBOL, running both versions on the same generated inputs, and diffing the outputs. A tool-using repair agent fixes mismatches and SonarQube issues, and a fix is only accepted if the outputs still match the original. Everything lands in a report dashboard.

Models: Muse Spark through the Meta Model API (hosted mode), or Muse Spark Open open weights via Baseten/Modal (private mode, so source code stays in an environment you control).

## Pipeline

```
upload  >  analyze  >  convert  >  verify  >  report
```

1. **Upload**: COBOL sources and copybooks.
2. **Analyze**: dependency graph; flag risky logic (e.g. fraud, payment handling).
3. **Convert**: copybook trees to SQL schema, COBOL to Java services, generated tests. Uses Meta models only (Muse Spark or Muse Spark Open).
4. **Verify and repair**: compile the original with GnuCOBOL, run original and converted code on the same generated inputs, diff outputs, and optionally run a SonarQube Community scan. The repair agent fixes failures until the outputs match and the quality gate passes (capped rounds).
5. **Report**: results shown in a dashboard.

## Hackathon note

All code in this repo was written during the Meta Global AI Developer Hackathon, Oct 27 to Nov 4 2026. All sample COBOL is synthetic.

## Planned structure

```
apps/web            Next.js dashboard
services/api        API (Python or Node)
services/analyzer   COBOL parsing, dependency graph, risk flags
services/converter  Meta-model conversion (SQL, Java, tests) + repair agent
services/verifier   GnuCOBOL differential testing
samples/            Synthetic COBOL only
contracts/          Shared JSON schemas between modules
docs/               Architecture and hackathon rules
.claude/agents/     Claude Code subagent definitions
```

See [CLAUDE.md](CLAUDE.md) for contributor/agent rules and [docs/](docs/) for the draft architecture.

## License

MIT. See [LICENSE](LICENSE).

## How to run

TBD. Nothing is implemented yet.
