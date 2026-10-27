# Diocle

**Status: scaffold, in progress.**

Diocle is an AI "system integrator" that modernizes legacy COBOL for finance organizations. Upload COBOL programs and their copybooks, and Diocle analyzes them (dependency graph, risky fraud/payment logic flagged), converts them (copybook trees to SQL schema, COBOL to Java services, generated tests) using Meta's Muse Spark through the Meta Model API, and then verifies the result by compiling the original with GnuCOBOL, running both versions on the same generated inputs, and diffing the outputs. Everything lands in a report dashboard.

## Pipeline

```
upload  >  analyze  >  convert  >  verify  >  report
```

1. **Upload**: COBOL sources and copybooks.
2. **Analyze**: dependency graph; flag risky logic (e.g. fraud, payment handling).
3. **Convert**: copybook trees to SQL schema, COBOL to Java services, generated tests. Uses Muse Spark via the Meta Model API only.
4. **Verify**: compile the original with GnuCOBOL, run original and converted code on the same generated inputs, diff outputs. Optional: SonarQube Community scan.
5. **Report**: results shown in a dashboard.

## Hackathon note

All code in this repo was written during the Meta Global AI Developer Hackathon, Oct 27 to Nov 4 2026. All sample COBOL is synthetic.

## Planned structure

```
apps/web            Next.js dashboard
services/api        API (Python or Node)
services/analyzer   COBOL parsing, dependency graph, risk flags
services/converter  Muse Spark conversion (SQL, Java, tests)
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
