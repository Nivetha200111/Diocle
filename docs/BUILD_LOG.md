# Build log

What was built during the Meta Global AI Developer Hackathon (Oct 27 to Nov 4 2026), the decisions behind it, and what went wrong along the way. The programs in the measurement and the deliveries are synthetic; public repositories used as test input are named where they appear. Commit history is the detailed record; this is the readable summary.

## Oct 27: plan
- Chose the Indie Developer track and "Build for Your World". The problem comes from firsthand experience with large COBOL migrations: converted code re-checked by hand, and manual fix-rebuild-rescan cycles for code-quality findings.
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
- Delivery: legacy repo → certified pull request with an equivalence report per program; the target repo's CI re-runs the check on fresh inputs.
- Dashboard: Live runs and Delivery show real data; deliveries can be started from the dashboard.

**Hardening after two independent code reviews**
- Programs under test no longer inherit model API keys; reverify trusts only what CI pins (legacy repo, Diocle branch, layouts re-derived from copybooks).
- Data formats checked byte for byte against GnuCOBOL: COMP-3, COMP, COMP-5, COMP-1/2, overpunch and separate signs, P scaling, OCCURS, REDEFINES, fixed-length records.
- Pinned clock, RETURN-CODE comparison, EBCDIC collation, CALLed subprograms, multi-file programs (match-merge), golden-file replay with a layout-aware EBCDIC and IBM hex-float codec.
- Programs Diocle cannot run (CICS, DB2, VSAM update, dynamic CALL, SYNC, OCCURS DEPENDING ON) are reported, not passed through.

**Mistakes found and fixed (kept here on purpose)**
- Code past column 72 is silently ignored by COBOL compilers; it cut `/ 365` to `/ 36` in a sample. Now an analyzer finding.
- The oracle initially ran GnuCOBOL without IBM's TRUNC(STD) and DISPLAY defaults, so a "10-digit counter" behaviour that IBM COBOL does not have was treated as correct, and fix memory learned it. The oracle was corrected, the lesson pruned, and the delivery redone: six programs, CI green on 6,714 fresh output records ([quillmark-modern#3](https://github.com/Nivetha200111/quillmark-modern/pull/3)).
- The breaker was reported as unproven until it found a defect other inputs missed. It has: in the frozen evaluation, CHQCLR's Java had passed 1,004 held-out inputs when the breaker designed two records that broke it (fee 20.00 vs 0.00, debit -121.23 vs 0.00); the repair agent fixed both and it re-certified on 1,006 fresh inputs. Both records carry malformed numeric data, so this shows agreement with GnuCOBOL on bad data, not proven IBM behaviour.
- The byte-exact comparator (Oct 28) found that the INTACCR in quillmark-modern#3 wrote `-000000000` where COBOL wrote `+000000000`. Re-delivered in [quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4), now the canonical delivery: six programs, CI green on 6,719 fresh output records.

**Demo estates**
- `quillmark-legacy` (simple layout) and `quillmark-mainframe` (an export of z/OS libraries: extension-less members, cataloged PROCs, DFSORT and IDCAMS cards, DB2, CICS, IMS, EBCDIC extracts), with `quillmark-modern` and `quillmark-java` as targets.

## Oct 29: SQL schema, guard and whole jobs
- Copybooks to SQL tables, proven by a byte-exact SQLite round trip (`GET /runs/{id}/schema`, schema.sql next to the Java).
- Guard agent: a deterministic policy before Java runs, and a Muse Spark Open review that can revoke a certification, never grant one.
- Independent cross-check on open weights (`--crosscheck`, CLI only) and whole JCL job v1.

## Oct 30: more ways in, more ways to check
- Printout intake (Muse Wonder), asking the original by voice (Muse Voice Transcribe), keyed files on a Berkeley DB stand-in, and a stated DB2 subset on a SQLite stand-in.
- Compile precheck before any model spend on visitor imports, a smallest-reproducer tool, and mutation testing of the verification itself.
- A scheduled uptime check of the site, the engine and one certified run.

## Oct 31: feature lock
- Hard feature lock until judging ends: fixes with a reviewer pass, docs, the video and submission chores only. Later additions that needed the owner's exception say so below.
- Muse Code run transcripts recorded, feature manuals moved out of the README, and a judge page put at the top of it.

## Nov 1: auditing our own evidence
- Classified all 54 stored breaks: 30 on malformed data, 15 on a negative-zero sign byte, 9 from a round with no Java output. None shows a wrong amount on a well-formed record, so the wording that implied one was replaced.
- **What went wrong:** the generator gave CHQCLR near-identical records (zero amounts behind a REDEFINES), and the attack compared output records but not printed totals, so it missed a wrong total in one stored private-mode Java. Both fixed; flat text records stay a stated limit.
- Certificates now state their scope. One public AWS CardDemo program (`CBCUS01C`) went through conversion and the checks, with a thin result stated: 5 of 40 seeded faults detected.
- The video was re-cut with only the owner's own recorded voice.

## Nov 2: re-measurement and capped uploads
- Re-measured the attack with both fixes under a plan written first: 4 of 10 again, the same four programs, about $0.18.
- Visitors may ask in their own voice and send their own image, under separate caps, after two security reviews (an owner-approved exception to the lock). A kill switch turns it off.
- README cut to a short front page, with the rest in `docs/DETAILS.md`. Commit messages were rewritten to drop co-author lines; code, dates and authors did not change.

## Nov 2 to 3: a public repository we did not write
- Ran every program in the Open Mainframe Project's COBOL course under a protocol pinned first, then a second pass on the 16 that did not compile. 11 of 32 certified (9 on fixed input, 2 against a repaired copy), for $1.42.
- 11 of the 13 not certified use `WRITE ... AFTER ADVANCING`, where GnuCOBOL writes the advancing into the file as bytes. Checked program by program afterwards: our verifier refused even identical Java on those files, and our prompts had no rule for it. Fixed.
- A third pass on those 13, not a blind test because the fix answered this same course's failures, certified 9: 8 against a repaired copy, 1 on fixed input, for $0.64. The two earlier passes stand as recorded: [EXTERNAL_ESTATE.md](EXTERNAL_ESTATE.md#third-pass-results-nov-3-2026-mac).

## Nov 3 to 4: a blind test
- Pinned three repositories no fix had seen, then ran them in the sandbox for $0.29. On COBOL from the repository of Norway's retired national pension system, 2 of 4 testable programs certified with no patch to the COBOL, after the repair agent fixed the first Java, on narrow generated inputs, and 2 did not. Results: [BLIND_TEST.md](BLIND_TEST.md).

## Nov 4: Meta vs Meta, dependency trees, a shorter site
- Three models attacked the same Java under a pinned protocol, for $5.48: [META_TOURNAMENT.md](META_TOURNAMENT.md).
- Muse Image draws dependency trees from the analyzer's links, and Muse Wonder reads them back: [DEPENDENCY_TREES.md](DEPENDENCY_TREES.md).
- The site's text was cut heavily, its retro theme kept and made more readable, and a page added for banks' teams, with its limits as visible as the rest.

## Still open (as of Nov 2, 2026)
- A review of the converted Java by an experienced COBOL maintainer (not done).
- Breaker test on a narrow defect that ordinary testing misses (`samples/loyalty-waiver`): the breaker found nothing on LOYWAIVE in the headline measurement (0 broke of 24 tried); no narrow defect was planted, so this stays open.

Done since (Oct 28 to Oct 31): frozen evaluation (`eval-freeze-1` 2 of 4, then `eval-freeze-2` 4 of 4 with the corrected verifier, both in `docs/EVALUATION.md`); hosting; front page with COBOL next to certified Java and a public re-verify button; evidence page. Since Oct 31: the demo video is linked from the README.
