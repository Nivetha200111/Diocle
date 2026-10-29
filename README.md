# Diocle

**AI writes the code. Diocle checks it against the original before anyone has to trust it.**

Diocle is a verification layer for AI-written code where a wrong cent costs money, starting with COBOL batch programs. Meta's Muse Spark converts COBOL to Java and repairs it. Nothing is accepted on the model's word: the original program runs next to the Java on the same inputs, and every output field, byte, exit code and display line must match, including on 1,000 held-out inputs the agent never saw. The result ships as a pull request with a certificate, and the target repository's CI repeats the test on fresh inputs.

## For judges: two minutes
- **Live product:** [diocle.vercel.app](https://diocle.vercel.app). The front page shows CHQCLR's COBOL next to its
  certified Java; press **Try the sample**, and both programs run again on about 1,000 inputs from a seed chosen
  right then. Or open [Delivery](https://diocle.vercel.app/delivery) and paste any public COBOL repository (small
  daily budget; every compile and run of imported code happens in a sandbox with no network and no credentials,
  while cloning, analysis and the model calls run in the engine).
- **Evidence, with links to every run:** [diocle.vercel.app/evidence](https://diocle.vercel.app/evidence),
  [docs/EVIDENCE.md](docs/EVIDENCE.md) (the canonical delivery, [quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4),
  with its CI) and [docs/EVALUATION.md](docs/EVALUATION.md) (unseen programs, failures included).
- **Built during the hackathon:** everything in this repository, from Oct 27, 2026; the history is in
  [docs/BUILD_LOG.md](docs/BUILD_LOG.md) and the git log.
- **Meta models:** Muse Spark (Meta Model API) as translator, repair agent and breaker agent; Muse Spark Open (open
  weights, partner host) for private mode. No other model is used in the product. The converter depends on the
  `openai` Python package only as an OpenAI-compatible HTTP client: its base URL is the Meta Model API
  (`https://api.meta.ai/v1`) or the Muse Spark Open host, set in `.env`; no OpenAI model is called.
- **Development tools:** the code was written with help from coding agents (Claude Code; see `.claude/` and the
  `Co-Authored-By` lines in the git log). They are development tooling only and are not part of the product.

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
| `apps/web` | Dashboard: **Home** (COBOL next to certified Java, re-verify on a fresh seed), **Delivery**, **Live runs** (agent trace, Meta model per role, before/after, cost) and **Evidence** show real data. Other views, only in local builds, are a labelled mock. |
| `samples/` | Six synthetic programs with naive Java ports: INTACCR, TXNPOST, FEESCHD, DAYCTRL (display records), PKDPOST (packed, fixed-length, with a golden set) and ACCTMTCH (match-merge, two inputs, two outputs). |

Sample estate repositories: [quillmark-mainframe](https://github.com/Nivetha200111/quillmark-mainframe) (a z/OS library export) → [quillmark-java](https://github.com/Nivetha200111/quillmark-java) (certified Java, re-verifying CI); and [quillmark-legacy](https://github.com/Nivetha200111/quillmark-legacy) (COBOL in) and [quillmark-modern](https://github.com/Nivetha200111/quillmark-modern) (certified Java out, with re-verifying CI).

## Measured so far (pilot evidence: synthetic programs, small samples; costs are estimates from list prices)

- **Canonical delivery: [quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4).** Six Quillmark programs (including a packed fixed-length extract and a two-input, two-output match-merge), translated from scratch by Muse Spark, all certified under one pinned byte-exact verifier, then re-verified by the target repository's GitHub CI on **6,719 fresh inputs with 0 differences** ([CI run](https://github.com/Nivetha200111/quillmark-modern/actions/runs/40811476870)). About $0.13 of model spend for the six conversions.
- **Correction (Oct 28).** An independent review showed the comparator paired output records with inputs and compared numeric fields by value, so `+00` and `-00` counted as equal. It now compares the whole output sequence byte for byte. Re-checking every certified run found one that should not have passed: the INTACCR in the earlier quillmark-modern#3 writes `-000000000` where the COBOL writes `+000000000` on 30 of 1,019 inputs. INTACCR was converted again (the repair agent fixed the negative-zero case itself) and the other five programs were re-certified under the new verifier at zero model calls; that is #4.
- **Unseen programs:** the frozen evaluation certified 2 of 4; both failures were the old comparator rejecting aggregation and fan-out. Re-run with the corrected verifier and fix memory off: **4 of 4 certified for about $0.11**, each passing five fresh seeds ([docs/EVALUATION.md](docs/EVALUATION.md)).
- **Breaker agent:** on CHQCLR it broke Java that had passed 1,004 held-out inputs (fee 20.00 vs 0.00); the repair agent fixed it and it re-certified on 1,006 fresh ones.
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
