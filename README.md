# Diocle

**AI writes the code. Diocle proves it.**

Diocle is a proof layer for AI-written code where a wrong cent costs money, starting with COBOL batch programs. Meta's Muse Spark converts COBOL to Java and repairs it. Nothing is accepted on the model's word: the original program is compiled with GnuCOBOL, both versions run on the same inputs, and every output field, byte and exit code must match, including on 1,000 held-out inputs the agent never saw. The result ships as a pull request with an equivalence certificate, and the target repository's CI re-proves it independently.

All code here was written during the Meta Global AI Developer Hackathon (Oct 27 to Nov 4 2026). All COBOL and data are synthetic, for a fictional bank (Quillmark Trust & Savings).

## What runs today

```
GitHub repo link ─► analyze ─► Muse Spark translates ─► repair agent ◄─► verifier (GnuCOBOL vs Java)
                                                              │
                         breaker agent attacks ◄── held-out certification (1,000 unseen inputs)
                                                              │
                     pull request + certificate ─► target repo CI re-verifies on fresh inputs
```

| Part | What it does |
|---|---|
| `services/analyzer` | Deterministic, no model calls. Derives record layouts from copybooks (DISPLAY, COMP-3, COMP, COMP-5, COMP-1/2, all sign modes, P scaling, OCCURS, REDEFINES, edited PICs, COPY REPLACING), wires files through SELECT/FD/OPEN and JCL, resolves CALLed programs, and flags legacy behaviour: ROUNDED, truncation, silent overflow, code cut at column 72, clock reads, EBCDIC-sensitive comparisons, hex floats. Imports GitHub repos (allowed owners only). |
| `services/verifier` | The oracle. Compiles the COBOL with GnuCOBOL 3.2 (-std=ibm, plus IBM's TRUNC(STD) and DISPLAY defaults), runs both sides on boundary, random, fixture, corpus and model-designed inputs, and compares field by field and byte by byte, for one or several input and output files (match-merge, SORT USING/GIVING): text and fixed-length records, packed and binary data, RETURN-CODE, stdout, a pinned clock, EBCDIC collation. Golden-file replay judges the Java against captured mainframe output, with a layout-aware EBCDIC and IBM hex-float codec. `reverify` re-proves a delivery in CI. |
| `services/converter` | Meta models only (Muse Spark hosted, or Muse Spark Open on Fireworks). Translator, tool-using repair agent, breaker agent that designs inputs to break certified Java, proof-gated fix memory, swarm mode (parallel agents share certified lessons mid-run), skill export. Hard caps on calls, rounds and attack cycles. |
| `services/api` | Serves runs and deliveries to the dashboard; `deliver` turns a legacy repo into a certified pull request on a target repo. |
| `services/mcp` | Diocle as an MCP server: `analyze_cobol`, `verify_conversion`, `certify_conversion`, `cobol_lessons`, so any agent's conversion can be checked. |
| `apps/web` | Dashboard: **Live runs** and **Delivery** show real data (agent trace, before/after, cost, CI status). Other views are a labelled mock. |
| `samples/` | Six synthetic programs with naive Java ports: INTACCR, TXNPOST, FEESCHD, DAYCTRL (display records), PKDPOST (packed, fixed-length, with a golden set) and ACCTMTCH (match-merge, two inputs, two outputs). |

Demo repositories: [quillmark-legacy](https://github.com/Nivetha200111/quillmark-legacy) (COBOL in) and [quillmark-modern](https://github.com/Nivetha200111/quillmark-modern) (certified Java out, with re-verifying CI).

## Measured so far

- Four Quillmark programs translated from scratch and certified for about $0.025 in total, then re-proven by GitHub CI on 4,000+ fresh inputs. Those runs predate the IBM TRUNC/DISPLAY settings in the oracle (their counters print GnuCOBOL's 10-digit width) and need re-certifying.
- Fix memory over 18 runs: 30% lower cost and 37% less model time on average than without memory.
- Costs are estimates from list prices.

## What Diocle proves, and what it does not yet

Proves: on the inputs it runs (generated, boundary, fixture, corpus, model-designed and held-out), the Java's output records, stdout and exit code equal the original's under GnuCOBOL, or under the mainframe's own output where golden files exist.

Not yet:
- Programs with EXEC SQL, CICS or DLI, INDEXED or RELATIVE files, files opened I-O, dynamic CALLs, several record types in one file, OCCURS DEPENDING ON, SYNCHRONIZED, PIC N or leading P scaling are reported as not convertible. Each new shape we found unhandled was added to this list with a test; there may be others.
- Without golden files, the oracle is GnuCOBOL, which can differ from IBM Enterprise COBOL in edge cases (intermediate precision, TRUNC, NUMPROC, hex float arithmetic). Golden files from the real mainframe are the authority.
- Testing shows equivalence on the inputs tried, not for all inputs.

## Run

Needs GnuCOBOL 3.2 (`cobc`), JDK 21 and Python 3.11+. Each service has its own README with setup and test commands. Model keys go in `.env` (see `.env.example`); nothing secret is committed.

See [CLAUDE.md](CLAUDE.md) for contributor rules and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## License

MIT. See [LICENSE](LICENSE).
