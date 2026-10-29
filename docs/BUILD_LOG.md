# Build log

What was built during the Meta Global AI Developer Hackathon (Oct 27 to Nov 4 2026), the decisions behind it, and what went wrong along the way. All programs and data are synthetic. Commit history is the detailed record; this is the readable summary.

## Oct 27: plan
- Chose the Indie Developer track and "Build for Your World". The problem comes from firsthand experience on a large COBOL migration at a payments company: hundreds of people re-checking converted code by hand, and manual fix-rebuild-rescan cycles for code-quality findings.
- Repositioned from "AI converts COBOL" to **a verification layer for AI-written code**: conversion is an input, agreement with the original program is the product.
- Rules fixed in `CLAUDE.md`: Meta models only in the product, hard caps on every model loop, contracts before code, synthetic data only.

## Oct 28: from a working loop to a delivery pipeline
**Core loop**
- Verifier: compile the original with GnuCOBOL, run both sides on boundary, random and fixture inputs, diff every field.
- Converter: Muse Spark repair agent with tools (read, patch, compile, re-test), certified on 1,000 held-out inputs. First real run: a naive port at 78.9% repaired to 100% for about $0.02.
- Smoke-tested both Meta backends (Muse Spark hosted, Muse Spark Open on Fireworks); private mode certified the same program in 7 calls.

**Agentic features**
- Proof-gated fix memory (lessons stored only after held-out certification). Measured over 18 runs on three programs: about 30% lower cost and 37% less model time on average; single runs vary, so this is pilot evidence.
- Breaker agent (designs inputs to break certified Java), swarm mode (parallel agents share certified lessons mid-run), skill export, MCP server.

**Delivery**
- Analyzer: layouts from copybooks, file wiring through SELECT/FD/OPEN and JCL, GitHub import with an owner allowlist.
- Delivery: legacy repo → certified pull request with a certificate per program; the target repo's CI re-runs the check on fresh inputs.
- Dashboard: Live runs and Delivery show real data; deliveries can be started from the dashboard.

**Hardening after two independent code reviews**
- Programs under test no longer inherit model API keys; reverify trusts only what CI pins (legacy repo, Diocle branch, layouts re-derived from copybooks).
- Data formats checked byte for byte against GnuCOBOL: COMP-3, COMP, COMP-5, COMP-1/2, overpunch and separate signs, P scaling, OCCURS, REDEFINES, fixed-length records.
- Pinned clock, RETURN-CODE comparison, EBCDIC collation, CALLed subprograms, multi-file programs (match-merge), golden-file replay with a layout-aware EBCDIC and IBM hex-float codec.
- Programs Diocle cannot run (CICS, DB2, VSAM update, dynamic CALL, SYNC, OCCURS DEPENDING ON) are reported, not passed through.

**Mistakes found and fixed (kept here on purpose)**
- Code past column 72 is silently ignored by COBOL compilers; it cut `/ 365` to `/ 36` in a sample. Now an analyzer finding.
- The oracle initially ran GnuCOBOL without IBM's TRUNC(STD) and DISPLAY defaults, so a "10-digit counter" behaviour that IBM COBOL does not have was treated as correct, and fix memory learned it. The oracle was corrected, the lesson pruned, and the delivery redone: six programs, CI green on 6,714 fresh inputs ([quillmark-modern#3](https://github.com/Nivetha200111/quillmark-modern/pull/3)).
- The breaker was reported as unproven until it found a defect other inputs missed. It has: in the frozen evaluation, CHQCLR's Java had passed 1,004 held-out inputs when the breaker designed two records that broke it (fee 20.00 vs 0.00, debit -121.23 vs 0.00); the repair agent fixed both and it re-certified on 1,006 fresh inputs. Both records carry malformed numeric data, so this shows agreement with GnuCOBOL on bad data, not proven IBM behaviour.
- The byte-exact comparator (Oct 28) found that the INTACCR in quillmark-modern#3 wrote `-000000000` where COBOL wrote `+000000000`. Re-delivered in [quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4), now the canonical delivery: six programs, CI green on 6,719 fresh inputs.

**Demo estates**
- `quillmark-legacy` (simple layout) and `quillmark-mainframe` (an export of z/OS libraries: extension-less members, cataloged PROCs, DFSORT and IDCAMS cards, DB2, CICS, IMS, EBCDIC extracts), with `quillmark-modern` and `quillmark-java` as targets.

## Still open
- Breaker test on a narrow defect that ordinary testing misses (`samples/loyalty-waiver`).
- Demo video; a review from a COBOL maintainer.

Done since: frozen evaluation (`eval-freeze-1` 2 of 4, then `eval-freeze-2` 4 of 4 with the corrected verifier, both in `docs/EVALUATION.md`); hosting; front page with COBOL next to certified Java and a public re-verify button; evidence page.
