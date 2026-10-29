# Diocle

**AI writes the code. Diocle checks it against the original before anyone has to trust it.**

Diocle is a verification layer for AI-written code where a wrong cent costs money, starting with COBOL batch programs. Meta's Muse Spark converts COBOL to Java and repairs it. Nothing is accepted on the model's word: the original program runs next to the Java on the same inputs, and every output field, byte, exit code and display line must match, including on 1,000 held-out inputs the agent never saw. The result ships as a pull request with a certificate, and the target repository's CI repeats the test on fresh inputs.

## For judges: two minutes
- **Live product:** [diocle.vercel.app](https://diocle.vercel.app). Open **Live runs**, pick CHQCLR, and press
  **Re-verify on a fresh seed**: both programs run again on a seed chosen right then. Or open **Delivery** and paste
  any public COBOL repository (it runs in a sandbox with no network and no credentials; small daily budget).
- **Evidence, with links to every run:** [docs/EVIDENCE.md](docs/EVIDENCE.md) (end-to-end deliveries with the
  target repositories' own CI) and [docs/EVALUATION.md](docs/EVALUATION.md) (unseen programs, failures included).
- **Built during the hackathon:** everything in this repository, from Oct 27, 2026; the history is in
  [docs/BUILD_LOG.md](docs/BUILD_LOG.md) and the git log.
- **Meta models:** Muse Spark (Meta Model API) as translator, repair agent and breaker agent; Muse Spark Open (open
  weights, partner host) for private mode.

## What "certified" means, and does not

- **Means:** on every input tried (PIC boundaries, seeded random values, fixtures, corpus records, model-designed attacks and 1,000 held-out inputs), the Java's output records, display output and exit code equal those of the original COBOL compiled with GnuCOBOL 3.2 under IBM's TRUNC(STD) and DISPLAY defaults, or equal the mainframe's own captured output where golden files exist. CI repeats this with a seed Diocle never used.
- **Does not mean:** equivalence for every possible input (testing cannot show that), or equivalence to IBM Enterprise COBOL where GnuCOBOL differs from it and no mainframe output was captured. The demo golden files were produced by GnuCOBOL, so they exercise the replay path but are not mainframe evidence. CI reuses Diocle's verifier, so it shares its assumptions; it guards against tampering and lucky seeds, not against a flaw in the verifier itself.

## How this differs from commercial tools

Vendors already generate Java from COBOL (for example IBM watsonx Code Assistant for Z, which also offers validation). Diocle's focus is narrower and open: a repair agent driven by executable evidence, certificates that pin every input to the result, delivery as an ordinary pull request, an independent CI re-run anyone can inspect, and the ability to audit conversions produced by any tool ("bring your own conversion").

All code here was written during the Meta Global AI Developer Hackathon (building period Oct 27 to Nov 4 2026); nothing predates Oct 27. All COBOL and data are synthetic, for a fictional bank (Quillmark Trust & Savings).

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
| `services/analyzer` | Deterministic, no model calls. Derives record layouts from copybooks (DISPLAY, COMP-3, COMP, COMP-5, COMP-1/2, all sign modes, P scaling, OCCURS, REDEFINES, edited PICs, COPY REPLACING), wires files through SELECT/FD/OPEN and JCL, resolves CALLed programs, and flags legacy behaviour: ROUNDED, truncation, silent overflow, code cut at column 72, clock reads, EBCDIC-sensitive comparisons, hex floats. Imports GitHub repositories: any public one for visitors (everything runs in an isolated sandbox), allowed owners for pull-request delivery. |
| `services/verifier` | The oracle. Compiles the COBOL with GnuCOBOL 3.2 (-std=ibm, plus IBM's TRUNC(STD) and DISPLAY defaults), runs both sides on boundary, random, fixture, corpus and model-designed inputs, and compares field by field and byte by byte, for one or several input and output files (match-merge, SORT USING/GIVING): text and fixed-length records, packed and binary data, RETURN-CODE, stdout, a pinned clock, EBCDIC collation. Golden-file replay judges the Java against captured mainframe output, with a layout-aware EBCDIC and IBM hex-float codec. `reverify` re-proves a delivery in CI. |
| `services/converter` | Meta models only (Muse Spark hosted, or Muse Spark Open on Fireworks). Translator, tool-using repair agent, breaker agent that designs inputs to break certified Java, proof-gated fix memory, swarm mode (parallel agents share certified lessons mid-run), skill export. Hard caps on calls, rounds and attack cycles. |
| `services/api` | Serves runs and deliveries to the dashboard; `deliver` turns a legacy repo into a certified pull request on a target repo. |
| `services/mcp` | Diocle as an MCP server: `analyze_cobol`, `verify_conversion`, `certify_conversion`, `cobol_lessons`, so any agent's conversion can be checked. |
| `apps/web` | Dashboard: **Live runs** and **Delivery** show real data (agent trace, before/after, cost, CI status). Other views are a labelled mock. |
| `samples/` | Six synthetic programs with naive Java ports: INTACCR, TXNPOST, FEESCHD, DAYCTRL (display records), PKDPOST (packed, fixed-length, with a golden set) and ACCTMTCH (match-merge, two inputs, two outputs). |

Sample estate repositories: [quillmark-mainframe](https://github.com/Nivetha200111/quillmark-mainframe) (a z/OS library export) → [quillmark-java](https://github.com/Nivetha200111/quillmark-java) (certified Java, re-verifying CI); and [quillmark-legacy](https://github.com/Nivetha200111/quillmark-legacy) (COBOL in) and [quillmark-modern](https://github.com/Nivetha200111/quillmark-modern) (certified Java out, with re-verifying CI).

## Measured so far (pilot evidence: synthetic programs, small samples; costs are estimates from list prices)

- Six Quillmark programs (including a packed fixed-length extract and a two-input, two-output match-merge) translated from scratch by Muse Spark and certified for about $0.11 in total, then re-verified by GitHub CI on 6,714 fresh inputs: [quillmark-modern#3](https://github.com/Nivetha200111/quillmark-modern/pull/3). An earlier four-program delivery (#1) predates the IBM TRUNC/DISPLAY settings and is superseded.
- **Correction (Oct 28).** An independent review showed the comparator paired output records with inputs and compared numeric fields by value, so `+00` and `-00` counted as equal. It now compares the whole output sequence byte for byte. Re-checking every certified run found one that should not have passed: the INTACCR in quillmark-modern#3 writes `-000000000` where the COBOL writes `+000000000` on 30 of 1,019 inputs. The INTACCR delivered to [quillmark-java](https://github.com/Nivetha200111/quillmark-java) passes the stricter check, as do the other programs.
- **Unseen programs:** the frozen evaluation certified 2 of 4; both failures were the old comparator rejecting aggregation and fan-out. Re-run with the corrected verifier and fix memory off: **4 of 4 certified for about $0.11**, each passing five fresh seeds ([docs/EVALUATION.md](docs/EVALUATION.md)).
- **INTACCR re-delivered** to quillmark-modern under the byte-exact verifier (the repair agent fixed the negative-zero case itself), with the other five programs re-certified under the same verifier at zero model calls: [quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4).
- Fix memory over 18 runs: 30% lower cost and 37% less model time on average than without memory.
- Costs are estimates from list prices.

## Not supported yet
- Programs with EXEC SQL, CICS or DLI, INDEXED or RELATIVE files, files opened I-O, dynamic CALLs, several record types in one file, OCCURS DEPENDING ON, SYNCHRONIZED, PIC N or leading P scaling are reported as not convertible. Each new shape we found unhandled was added to this list with a test; there may be others.
- Without golden files, the oracle is GnuCOBOL, which can differ from IBM Enterprise COBOL in edge cases (intermediate precision, NUMPROC, hex float arithmetic). No real mainframe output has been tested yet.
- The breaker agent attacks single-file programs only. In the frozen evaluation it broke CHQCLR after the program had passed 1,000 held-out inputs: two designed records gave a fee of 20.00 vs 0.00 and a debit of -121.23 vs 0.00; the repair agent fixed both and the program re-certified. Both records carry malformed numeric content (a leading space, letters in a numeric field), so this shows agreement with GnuCOBOL's handling of bad data, not proven IBM behaviour.

## Run

Needs GnuCOBOL 3.2 (`cobc`), JDK 21 and Python 3.11+. Each service has its own README with setup and test commands. Model keys go in `.env` (see `.env.example`); nothing secret is committed.

See [CLAUDE.md](CLAUDE.md) for contributor rules and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## License

MIT. See [LICENSE](LICENSE).
