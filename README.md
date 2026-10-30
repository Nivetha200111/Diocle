# Diocle

**AI writes the code. Diocle checks it against the original before anyone has to trust it.**

Diocle is a verification layer for AI-written code where a wrong cent costs money, starting with COBOL batch programs. Meta's Muse Spark converts COBOL to Java and repairs it. Nothing is accepted on the model's word: the original program runs next to the Java on the same inputs, and every output field, byte, exit code and display line must match, including on 1,000 held-out inputs the agent never saw. The result ships as a pull request with a certificate, and the target repository's CI repeats the test on fresh inputs.

## Why it matters

COBOL still runs about 43% of US banking systems and 95% of ATM swipes, with some 220 billion lines in use
(Reuters, 2017), and the people who wrote it are retiring. Rewriting it is where banks get hurt: TSB's 2018
core-banking migration locked close to two million customers out of their accounts, and its chief executive stepped
down. AI makes the rewrite fast; it does not make it safe. The risk is silent: Java that compiles, runs and is wrong
by a cent, or by the sign of zero on 30 inputs in a thousand. Diocle's job is to catch that before anyone ships it.

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
  weights, on a partner host: Fireworks for private mode, Baseten for the optional independent cross-check and guard
  review). Diagram and per-role detail: [Which model does what](#which-model-does-what). No other model is used in the
  product. The converter depends on the `openai` Python package only as an OpenAI-compatible HTTP client: its base URL
  is the Meta Model API (`https://api.meta.ai/v1`) or the Muse Spark Open host, set in `.env`; no OpenAI model is called.
- **Development tools:** the code was written with help from coding agents (Claude Code; see `.claude/` and the
  `Co-Authored-By` lines in the git log). They are development tooling only and are not part of the product.

## Which model does what

```mermaid
flowchart LR
    SRC["COBOL + copybooks"] --> AN["Analyzer<br/>(deterministic, no model)"]
    AN --> TR["Muse Spark<br/>translates to Java"]
    TR --> V{{"GnuCOBOL verifier<br/>runs the original and the Java on the same inputs.<br/>The only thing that can certify."}}
    V -- "mismatch" --> RP["Muse Spark<br/>repair agent"]
    RP --> V
    V -- "certified on 1,000 held-out inputs" --> BR["Muse Spark<br/>breaker agent attacks the Java"]
    BR -- "break found" --> RP
    BR --> XC["Muse Spark Open (open weights)<br/>independent cross-check, opt-in"]
    XC -- "a real mismatch only" --> RP
    GP["Guard policy<br/>(deterministic: refuses Java that opens<br/>the network, runs processes, reads secrets)"] -. "gates every Java run" .-> V
    XC --> OUT["Certificate + pull request"]
```

| Role | Model | Served by | What it may do |
|---|---|---|---|
| Translator, repair agent, breaker | Muse Spark (`muse-spark-1.3-contributor` by default) | Meta Model API | Write and patch Java, design attack inputs. Cannot certify. |
| Independent cross-check (`--crosscheck`, opt-in) | Muse Spark Open | Partner host (Baseten or Fireworks) | Propose inputs where it thinks the Java differs. Every input runs through GnuCOBOL and the Java; its opinion certifies nothing. |
| Guard review (optional, off on the live site) | Muse Spark Open | Baseten | One review of the final Java; can only revoke certification, never grant it. |
| Escalation tiers (`--tiers`, opt-in) | Muse Spark contributor, then `muse-spark-1.3`, then `muse-wonder-1.0` | Meta Model API | The repair agent moves up one tier after each failed certification round and the breaker attacks at tier 2 by default (Muse Wonder is opt-in with `MODEL_TIER_BREAKER=3`); hard caps on calls and dollars above tier 1. Not yet shown to repair better than tier 1 alone. |
| Private mode | Muse Spark Open replaces Muse Spark in all three agent roles | Partner host | Same loop on open weights, for code that must not leave your control. |
| **Verifier** | none, it is GnuCOBOL and a byte-for-byte comparison | Sandbox (no network, no credentials) | **The only thing that certifies.** |

The guard's deterministic policy runs on every run. Its model review is off on the live site (no key is configured
there), so the live site runs the policy only. The narration of the demo video is a synthetic voice from a non-Meta
service; Meta's speech model on the API (`muse-voice-transcribe-1.0`) transcribes speech and does not speak.

## What "certified" means, and does not

- **Means:** on every input tried (PIC boundaries, seeded random values, fixtures, corpus records, model-designed attacks and 1,000 held-out inputs), the Java's output records, display output and exit code equal those of the original COBOL compiled with GnuCOBOL 3.2 under IBM's TRUNC(STD) and DISPLAY defaults, or equal the mainframe's own captured output where golden files exist. CI repeats this with a seed Diocle never used.
- **Does not mean:** equivalence for every possible input (testing cannot show that), or equivalence to IBM Enterprise COBOL where GnuCOBOL differs from it and no mainframe output was captured. The demo golden files were produced by GnuCOBOL, so they exercise the replay path but are not mainframe evidence. CI reuses Diocle's verifier, so it shares its assumptions; it guards against tampering and lucky seeds, not against a flaw in the verifier itself.

## How this relates to other work

Vendors already generate Java from COBOL (for example IBM watsonx Code Assistant for Z, which also offers validation). Diocle's focus is narrower and open: a repair agent driven by executable evidence, certificates that pin every input to the result, delivery as an ordinary pull request, an independent CI re-run anyone can inspect, and the ability to audit conversions produced by any tool ("bring your own conversion").

- **Judging translations without running them.** IBM Research's evaluation of watsonx Code Assistant for Z's COBOL-to-Java output ([Froimovich et al., arXiv:2507.23356](https://arxiv.org/abs/2507.23356)) uses static checkers (variable-access, procedure-call and middleware-call matching, hallucination flags) and an LLM-as-a-judge on a 1-7 scale, and notes that proving two programs equivalent is undecidable. It does not report running the Java against the original COBOL. Diocle takes the other route: it runs both on the same inputs and compares every output byte, and a model only writes and repairs code, never judges it. Per-program proof matters because errors compound: if each of ten paragraphs is right 90% of the time, the whole program is right only about a third of the time (0.9¹⁰ ≈ 0.35), the paper's own illustration.
- **GnuCOBOL off the mainframe.** Bankdata and the University of Southern Denmark ([Askholm, Johnsen and Mauro, arXiv:2604.00936](https://arxiv.org/abs/2604.00936)) report a bank running GnuCOBOL in GitHub Actions for COBOL testing. The paper does not address where GnuCOBOL differs from IBM Enterprise COBOL; Diocle pins those differences (IBM TRUNC(STD) and DISPLAY defaults, EBCDIC collation) and replays captured mainframe output where it exists.
- **Parallel run.** The method is the "parallel run" migration pattern (Sam Newman, *Monolith to Microservices*): run old and new side by side and compare results. Diocle makes it automatic, per program, before the code ships, and again in the target repository's CI.

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
| `services/verifier` | The oracle. Compiles the COBOL with GnuCOBOL 3.2 (-std=ibm, plus IBM's TRUNC(STD) and DISPLAY defaults), runs both sides on boundary, random, fixture, corpus and model-designed inputs, and compares field by field and byte by byte, for one or several input and output files (match-merge, SORT USING/GIVING): text and fixed-length records, packed and binary data, RETURN-CODE, stdout, a pinned clock, EBCDIC collation. Golden-file replay judges the Java against captured mainframe output, with a layout-aware EBCDIC and IBM hex-float codec. `reverify` re-proves a delivery in CI. `sqlschema` turns the copybooks into SQL tables (`DECIMAL(p,s)` from the PIC, REDEFINES and OCCURS stated) and proves them by a round trip through SQLite that must return every record byte for byte; no model. |
| `services/converter` | Meta models only (Muse Spark hosted, or Muse Spark Open on Fireworks or Baseten). Translator, tool-using repair agent, breaker agent that designs inputs to break certified Java, guard agent, in progress (a policy that refuses to run Java that openly uses the network, processes, reflection, other environment variables or literal outside paths, a speed bump in front of the sandbox; and a Muse Spark Open review of certified Java that can revoke certification for leaks or test gaming), proof-gated fix memory, swarm mode (parallel agents share certified lessons mid-run), skill export. Hard caps on calls, rounds and attack cycles. |
| `services/api` | Serves runs and deliveries to the dashboard; `deliver` turns a legacy repo into a certified pull request on a target repo. |
| `services/mcp` | Diocle as an MCP server: `analyze_cobol`, `verify_conversion`, `certify_conversion`, `cobol_lessons`, so any agent's conversion can be checked. |
| `apps/web` | Dashboard: **Home** (COBOL next to certified Java, re-verify on a fresh seed), **Delivery**, **Live runs** (agent trace, Meta model per role, before/after, cost) and **Evidence** show real data. Other views, only in local builds, are a labelled mock. |
| `samples/` | Nine synthetic programs (the last three were added for DISPLAY-only, OPEN I-O and CALL identifier shapes: TXNLIST, LDGRWRT, FEEPOST) with naive Java ports: INTACCR, TXNPOST, FEESCHD, DAYCTRL (display records), PKDPOST (packed, fixed-length, with a golden set) and ACCTMTCH (match-merge, two inputs, two outputs). |

Sample estate repositories: [quillmark-mainframe](https://github.com/Nivetha200111/quillmark-mainframe) (a z/OS library export) → [quillmark-java](https://github.com/Nivetha200111/quillmark-java) (certified Java, re-verifying CI); and [quillmark-legacy](https://github.com/Nivetha200111/quillmark-legacy) (COBOL in) and [quillmark-modern](https://github.com/Nivetha200111/quillmark-modern) (certified Java out, with re-verifying CI).

### Verified documentation

`python -m diocle_converter run SAMPLE --document` (or `document SAMPLE` on its own) has a Muse Spark model write a plain-English behaviour spec of a COBOL program as claims, each with concrete examples (input records and expected output fields). The original COBOL, compiled with GnuCOBOL and run in the sandbox, then decides every claim: **confirmed on the examples tried** (the examples' stated expectations held on GnuCOBOL; the claim's sentence itself is not machine-checked, and numbers are compared by value, not byte for byte), **refuted** (the actual value is kept and shown) or **unchecked** (invalid example, the program did not run or ended with a return code the example does not expect, or the expectation compares nothing but a record count or return code). The model never decides, and "confirmed" is not "proven". Wrong claims are caught and shown, not hidden. The dashboard shows it as the Behaviour spec panel with a Markdown download. Contract: `contracts/behavior-claims.schema.json`. Single-file record programs only; opt-in, capped (2 calls, $0.10) and never fails a run. Not deployed to the live engine yet.

## Measured so far (pilot evidence: synthetic programs, small samples; costs are estimates from list prices)

- **Canonical delivery: [quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4).** Six Quillmark programs (including a packed fixed-length extract and a two-input, two-output match-merge), translated from scratch by Muse Spark, all certified under one pinned byte-exact verifier, then re-verified by the target repository's GitHub CI on **6,719 fresh inputs with 0 differences** ([CI run](https://github.com/Nivetha200111/quillmark-modern/actions/runs/40811476870)). About $0.13 of model spend for the six conversions.
- **Correction (Oct 28).** An independent review showed the comparator paired output records with inputs and compared numeric fields by value, so `+00` and `-00` counted as equal. It now compares the whole output sequence byte for byte. Re-checking every certified run found one that should not have passed: the INTACCR in the earlier quillmark-modern#3 writes `-000000000` where the COBOL writes `+000000000` on 30 of 1,019 inputs. INTACCR was converted again (the repair agent fixed the negative-zero case itself) and the other five programs were re-certified under the new verifier at zero model calls; that is #4.
- **Unseen programs:** the frozen evaluation certified 2 of 4; both failures were the old comparator rejecting aggregation and fan-out. Re-run with the corrected verifier and fix memory off: **4 of 4 certified for about $0.11**, each passing five fresh seeds ([docs/EVALUATION.md](docs/EVALUATION.md)).
- **Copybooks as SQL:** for all 11 sample and evaluation programs (24 tables), generated records (PIC boundaries and seeded random values) fit the published column types and come back from SQLite byte for byte; so do PKDPOST's golden files after EBCDIC conversion. The front page and Live runs show each run's `schema.sql` next to its Java.
- **Breaker agent:** on CHQCLR it broke Java that had passed 1,004 held-out inputs (fee 20.00 vs 0.00); the repair agent fixed it and it re-certified on 1,006 fresh ones.
- Fix memory over 18 runs: 30% lower cost and 37% less model time on average than without memory.
- Costs are estimates from list prices.

## Not supported yet
- **Convert anyway (local or admin only, see "Running on your own repo") never certifies what the verifier could not run.** Programs the analyzer refuses (EXEC SQL/CICS/DLI, keyed files, dynamic or external CALLs, missing copybooks, no output) are translated with labelled `// ADAPTER REQUIRED` interfaces (no invented database behaviour), compile-checked with `javac`, never executed, and labelled `COMPILED, NOT VERIFIED`; nothing here is a working DB2, CICS or keyed-file conversion. An original that does not compile under GnuCOBOL gets a bounded patch first (see the rule below) and its Java is labelled `VERIFIED AGAINST REPAIRED COBOL`, which is not `CERTIFIED`. Visitor imports on the public site cannot enable the mode and keep refusing as before.
- Programs with EXEC SQL, CICS or DLI, INDEXED or RELATIVE files, LINE SEQUENTIAL files opened I-O (only fixed-record SEQUENTIAL files are updated in place), a file opened I-O in one place and another way elsewhere, CALL identifiers that anything other than literals can assign (STRING, UNSTRING, ACCEPT, READ INTO, a LINKAGE parameter, a MOVE from a field, a second literal), DISPLAY-only programs that ACCEPT from the console or that DISPLAY only UPON SYSERR, programs with no output file and no DISPLAY, a JCL job whose COBOL step is DISPLAY-only or updates a file in place (the job check compares output files only), several record types in one file, OCCURS DEPENDING ON, SYNCHRONIZED, PIC N or leading P scaling are reported as not convertible. Each new shape we found unhandled was added to this list with a test; there may be others.
- A program whose original COBOL does not compile under GnuCOBOL `-std=ibm` (for example a missing period after `PROGRAM-ID`, which IBM's compiler accepts) cannot be verified. Visitor imports find this before any model call with a compile-only check in the sandbox, skip the program with the compiler's reason and give its slot to the next compilable program (at most 12 programs checked per import; if the sandbox is unavailable the check is skipped). Other paths (CLI runs, owner deliveries) still find it only after the first translator call, where the run stops with that reason. Diocle does not repair or rewrite the original so that it compiles.
- DISPLAY-only and OPEN I-O programs are accepted from what the source says, not from a run: a program whose DISPLAY (or REWRITE) never fires on the generated inputs, or that prints something nondeterministic such as `FUNCTION RANDOM`, cannot certify, and this is found only at verification time, after the translator call has been paid for. Neither shape has been through a real model conversion yet; the three synthetic samples (`display-report`, `ledger-rewrite`, `call-identifier`) are proven with hand-written Java only.
- JCL jobs convert end to end only in one shape: one SORT step (SORT FIELDS= with character keys, optional OPTION EQUALS) feeding one COBOL step. Jobs with three or more steps, several SORT steps, COND-gated steps, numeric (ZD/PD/BI) sort keys, INCLUDE/OMIT, INREC/OUTREC, SUM or MERGE are reported as not convertible with a reason. The job-level check is a library function (`diocle_verifier.jobs.verify_job`), not yet wired into the CLI or the delivery flow.
- SQL schemas are proven on SQLite only. Alphanumeric fields that carry binary bytes (LOW-VALUES, a REDEFINES over packed data) would need BYTEA/BINARY in PostgreSQL or DB2, and a record type split behind a REDEFINES is kept as the shared bytes, not as typed columns per variant.
- Without golden files, the oracle is GnuCOBOL, which can differ from IBM Enterprise COBOL in edge cases (intermediate precision, NUMPROC, hex float arithmetic). No real mainframe output has been tested yet.
- The breaker agent attacks single-file programs only. In the frozen evaluation it broke CHQCLR after the program had passed 1,000 held-out inputs: two designed records gave a fee of 20.00 vs 0.00 and a debit of -121.23 vs 0.00; the repair agent fixed both and the program re-certified. Both records carry malformed numeric content (a leading space, letters in a numeric field), so this shows agreement with GnuCOBOL's handling of bad data, not proven IBM behaviour.
- Verified documentation covers single-file record programs only (multi-file, DISPLAY-only and I-O programs are skipped), checks only the examples a model wrote, and is not on the live engine yet.


## Run

Needs GnuCOBOL 3.2 (`cobc`), JDK 21 and Python 3.11+. Each service has its own README with setup and test commands. Model keys go in `.env` (see `.env.example`); nothing secret is committed.

### Using your own Meta key

Judges do not need a key: the live site, **Try the sample** and the public re-verify run on our engine. To run the
converter yourself:

1. Create an API key for the Meta Model API in your Meta developer account at [dev.meta.ai](https://dev.meta.ai).
2. `cp .env.example .env`, then set `META_MODEL_API_KEY=` (the base URL `https://api.meta.ai/v1` and the model
   `muse-spark-1.3-contributor` are already filled in; use `muse-spark-1.3` for anything private).
3. Optional, for private mode or the independent cross-check: set `OPEN_MODEL_API_KEY`, `OPEN_MODEL_BASE_URL` and
   `OPEN_MODEL_ID` (Fireworks and Baseten examples are in `.env.example`).
4. Check the key and endpoint: `cd services/converter && .venv/bin/python -m diocle_converter smoke` (one tiny call,
   about a hundredth of a cent). A first full run on a sample costs a few cents; every model loop has hard call caps
   (`MODEL_MAX_CALLS_PER_RUN` and the others in `.env.example`).

### Running on your own repo (local, your own key)

Any COBOL repository, local directory or GitHub URL, with your own Meta key and no visitor caps:

```sh
# prerequisites: GnuCOBOL 3.2 (cobc), JDK 21, Python 3.11+, the services' venvs (see each README), META_MODEL_* in .env
cd services/converter
.venv/bin/python -m diocle_converter repo /path/to/legacy-repo --convert-anyway        # or https://github.com/<owner>/<repo>
#   --repo-max-usd 2.50   raise REPO_MAX_USD for this run (default 1.00, enforced across every program of the run)
#   --programs PAYROLL,LEDGER   only these PROGRAM-IDs
# equivalent: cd services/api && .venv/bin/python -m diocle_api.deliver /path/to/legacy-repo --convert-anyway
# one program: python -m diocle_converter run SAMPLE_DIR --convert-anyway --max-usd 0.20
```

Without `--convert-anyway` (and without `DIOCLE_CONVERT_ANYWAY=1`) nothing changes: refused programs stay refused. The
results stay under `runs/` and show on the dashboard; pass a target repository to `diocle_api.deliver` to open a pull request
(it lists every program under its label). Every program ends with exactly one label:

| Label | Meaning | Counted as certified? |
|---|---|---|
| `CERTIFIED` | The differential test passed against the original COBOL, as always. | yes |
| `VERIFIED AGAINST REPAIRED COBOL` | The original did not compile under GnuCOBOL `-std=ibm`; the COBOL was patched (diff in the run record, the patched file is written beside your file as `<name>.repaired.cbl`, your file is never touched) and the Java passed against the patched COBOL. A person must confirm the patch preserves what the IBM compiler accepted. | no |
| `COMPILED, NOT VERIFIED` | The Java compiles with `javac`; no differential test could run (the reason is stated); the Java was never executed. A developer must review it. | no |
| `FAILED` | No compiling Java within the caps, or the differential test ran and the Java still differs. | no |

A program that compiles and verifies normally is certified normally even in this mode. Programs skipped when `REPO_MAX_USD`
is reached are recorded as `skipped: repo spend cap reached`, never dropped. Model use stays within the per-run call caps and a
dollar cap (`--max-usd`, the rest of `REPO_MAX_USD`) and logs tokens and cost per program.

**The COBOL patch rule** (enforced in `diocle_converter/cobolrepair.py`, not just asked of the model): first mechanical fixes that
cannot change behaviour (today: the missing period after `PROGRAM-ID`); only if the original still does not compile, a bounded
Muse loop with `compile_cobol` and `patch_cobol` tools (at most `COBOL_REPAIR_MAX_CALLS`, default 8, inside the run caps; tier
escalation with `--tiers`). The patched file may differ from the original by at most `COBOL_REPAIR_MAX_LINES` (20) and
`COBOL_REPAIR_MAX_SHARE` (10%) of its lines, whichever is smaller, and a patch may only change a line the compiler reported in a fresh compile (fixed-format files only, no lines added, removed or
blanked; per line one identifier correction of at most 3 characters, a missing period, or one added TO/THEN/IS/DIVISION/SECTION).
Not enforceable: that a corrected identifier is the one the author meant, that an added period does not end an IF or EVALUATE early,
or that an inserted word is in the right place (the compiler rejects a misplaced one); a person must confirm the patch. A rejected patch is not applied; the compiler, not the model, decides whether it
now compiles. Programs the analyzer refuses (EXEC SQL, keyed files, ...) are not COBOL-patched; programs that compile but never
finish, or fail for reasons other than compile errors, are not patched either.

What is still never certified, and why: anything the verifier could not run against GnuCOBOL (database and transaction calls,
keyed files, calls to programs outside the repository, unknown copybook layouts, repaired or uncompilable originals). Only the
verifier certifies; the model's Java is compiled, never trusted. This mode is not reachable from the public site: a visitor
request that sets it is refused (403), and the visitor job strips `DIOCLE_CONVERT_ANYWAY` from its environment. **A hosted engine must set `DIOCLE_HOSTED=1` and a long random `DIOCLE_ADMIN_TOKEN`** (see `deploy/diocle.env.example`): with both unset the admin check is open, and the API then only accepts `convertAnyway` from the machine itself (loopback, no proxy headers). `python -m diocle_converter run --convert-anyway` without `--max-usd` is capped at `REPO_MAX_USD` or $0.25.

See [CLAUDE.md](CLAUDE.md) for contributor rules and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design.

## License

MIT. See [LICENSE](LICENSE).
