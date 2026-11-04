# Walkthrough: every feature, with screenshots

**Video:** https://youtu.be/mF12P8oeOBk · **Live site:** https://diocle.vercel.app · All programs and data are synthetic.

Each picture says where it came from: **live** was captured from the public site on Nov 4, 2026, read-only unless stated; **live, Nov 1** is an earlier capture of a page or GitHub view that has not changed in substance; **recording** is a frame from a recording made during the hackathon, of a real run, on the interface as it was then. Numbers are from those runs; what "certified" means and does not mean is in the [README](../README.md#limits).

## 1. The first screen

The question, one catch and the four steps, with the numbers, the limits and the evidence folded below. The record in the catch is malformed, and the screen says so. *Live.*

![Home page](walkthrough/01-home.jpg)

## 2. Try the sample

The original on GnuCOBOL and the stored Java, one run each, on about 1,000 generated records from a seed chosen now. Free, no model: it re-checks stored Java, it does not convert anything. *Live, button pressed.*

![Try the sample](walkthrough/02-try-the-sample.jpg)

## 3. For banks

What a reviewer gets, what a first pilot would look like, and what is not there yet: no bank has used Diocle, and it has no security audit or compliance certification. *Live.*

![For banks](walkthrough/30-for-banks.jpg)

## 4. Try it live: capped buttons

**Convert a sample now** (Muse Spark translates one bundled program, cap $0.05) and **Read a printout** (Muse Wonder reads one bundled listing, cap $0.10). Below them, a visitor can send their own image of a COBOL listing, and ask a question in their own voice, under [their own caps](FEATURES.md#your-own-voice-and-your-own-image-on-the-live-page-capped-added-nov-2). No free text. *Live; no button pressed. The printout button shows the per-visitor daily limit, already used from this browser.*

![Try it live](walkthrough/03-try-it-live.jpg)

## 5. Read a printout (Muse Wonder)

Muse Wonder reads a photographed COBOL listing back into COBOL; the verifier then compares it with the original. Here: identical on 1,013 of 1,013 output records, $0.054. *Recording, Nov 1, local engine.*

![Read a printout](walkthrough/26-printout.jpg)

## 6. Ask the original program by voice (Muse Voice Transcribe)

A bundled spoken question, or your own under a cap, is transcribed, Muse Spark proposes claims with examples, GnuCOBOL runs the examples, and the answer uses only what was confirmed. *Live; no question asked for this picture.*

![Ask by voice](walkthrough/04-ask-by-voice.jpg)

## 7. Import a repository

Paste a public COBOL repository; each program is analyzed, converted within a small budget and checked, with the delivery and its steps listed. The delivery below the form is Harbor, a fictional bank. *Live, no import started.*

![Import a repository](walkthrough/05-import-a-repository.jpg)

## 8. The dependency tree on an import

Every import gets the analyzer's tree on its delivery page, with no model. Where the server allows it, Muse Image also draws one small part, Muse Wonder reads the drawing back without seeing the graph, and code compares that with the analyzer. Optional and capped. Here, `fzn0x/core-banking-system` (delivery `delivery-20261104-072240`): 4 links, and the drawing of 3 of them matched on attempt 1. Its 2 programs did not certify. *Live, stored delivery.*

![Dependency tree on an import](walkthrough/29-import-tree.jpg)

## 9. Dependency tree and impact view

What calls, copies and runs what, from the analyzer's report, next to a recorded drawing. A drawing is marked as checked only if it is read back and matches exactly, which is not a proof it is correct. Small trees passed; whole-repository drawings did not ([results](DEPENDENCY_TREES.md)). *Live.*

![Dependency tree](walkthrough/27-dependency-tree.jpg)

Select a name to see what depends on it. It covers only the links the analyzer found, so dynamic CALLs and refused programs may be missing. *Live, `MSTREC` selected.*

![Impact view](walkthrough/28-impact-view.jpg)

## 10. Current run

Whatever the engine is running now, or the ways to start something when it is idle. *Live, idle.*

![Current run](walkthrough/07-current-run.jpg)

## 11. Agent replay

One stored run, step by step, by role. It is a replay of a recorded run, and the page says so. *Live.*

![Agent replay](walkthrough/08-agent-replay.jpg)

## 12. Run history

Every run the engine has kept, including failed and interrupted ones. *Live.*

![Run history](walkthrough/09-run-history.jpg)

## 13. What one run did and did not establish

Run `chqclr-20261028-214355`. Each check is listed apart, and a check that did not happen says "not run". *Live.*

![Checks in a run](walkthrough/10-run-checks.jpg)

## 14. The breaker agent

Muse Spark designs inputs aimed at Java that already passed; each is run through both programs. These two records are malformed: letters or a space in a numeric field. *Live, stored run.*

![Breaker agent](walkthrough/11-breaker.jpg)

## 15. COBOL next to Java, and the copybooks as SQL

The original and its copybooks beside the Java, with a `schema.sql` tab generated with no model and checked by a SQLite round trip. *Live, stored run.*

![COBOL, Java and SQL](walkthrough/12-cobol-java-sql.jpg)

## 16. Which Meta model did what

Every model call is logged by role, with tokens and estimated cost. Unused roles say so. *Live, stored run.*

![Models in a run](walkthrough/13-models-in-run.jpg)

## 17. Private mode on open weights (Muse Spark Open)

The same agents on Muse Spark Open, served by Fireworks: INTACCR certified on 1,027 output records. One public run; partner inference, not hardware we control. *Live, stored run.*

![Private mode](walkthrough/15-private-mode.jpg)

## 18. How strong is this verification? (mutation testing)

Small faults are seeded into a copy of the Java to see whether the inputs would notice. No model. This stored report is from Oct 30, on the old CHQCLR records; [the re-test is explained here](SHOWCASE_CHQCLR.md). *Live.*

![Mutation testing](walkthrough/14-mutation.jpg)

## 19. Verified documentation

A model writes a behaviour spec as claims with examples; the original COBOL decides each one. Confirmed means on the examples tried. *Live, Nov 1, stored run.*

![Behaviour spec](walkthrough/16-verified-documentation.jpg)

## 20. Embedded SQL subset, on a stand-in

A stated subset of EXEC SQL, with final table contents compared. SQLite stands in for DB2: not DB2-verified. *Live, stored run.*

![DB2 subset on SQLite](walkthrough/17-db2-subset.jpg)

## 21. Evidence: cost scoreboard

Raw model spend across certified runs, from the engine's own records. Compute, hosting and human review are not measured. *Live.*

![Scoreboard](walkthrough/18-scoreboard.jpg)

## 22. Evidence: what is verified, and what is not

The coverage matrix, by kind of mainframe artifact, including what is partial, on a stand-in or unsupported. *Live.*

![Coverage matrix](walkthrough/19-coverage.jpg)

## 23. Evidence: the showcased catch, with its limits

The CHQCLR story, including that the inputs were malformed and the weakness we found in our own check. *Live.*

![Evidence on the breaker](walkthrough/20-evidence-breaker.jpg)

## 24. Evidence: Meta vs Meta

Three Meta models attack the same Java, on 10 synthetic programs, once each, and GnuCOBOL decides every result: Muse Spark broke 4 ($0.11), Muse Spark Open 2 ($1.18), Muse Wonder 5 ($4.20). One attack each, so [this is not a ranking](META_TOURNAMENT.md). *Live, recorded results.*

![Meta vs Meta](walkthrough/31-meta-vs-meta.jpg)

## 25. Evidence: a blind test

COBOL no fix had seen, including the public repository of Norway's retired national pension system: 2 of the 4 programs Diocle could test certified, and 2 did not. Blind means only that no fix or tuning was made for these repositories, which were chosen because the analyzer could test them ([details](BLIND_TEST.md)). *Live, recorded results.*

![Blind test](walkthrough/32-blind-test.jpg)

## 26. Bug of the day

Real catches read from stored runs, each with who caught it, the cost and its caveat. *Live.*

![Bug of the day](walkthrough/21-bug-of-the-day.jpg)

## 27. Delivery: a pull request with reports

Certified programs arrive as an ordinary pull request with an equivalence report per program ([quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4)). *Live, Nov 1.*

![Pull request](walkthrough/22-pull-request.jpg)

## 28. CI in the target repository

The target repository's own CI re-runs the comparison on inputs from a new seed: 6,719 output records, 0 differences. It reuses Diocle's verifier, so it shares its assumptions. *Live, Nov 1.*

![Target repository CI](walkthrough/23-target-repo-ci.jpg)

## 29. Whole-repository build check

Compiles the delivered programs together and checks CALL signatures. This is the Harbor delivery, and the check reports **FAIL**: some CALLs pass the wrong number of arguments. Each program was verified alone, so they were delivered, and the pull request says plainly that they do not fit together. Experimental. *Live.*

![Whole-repository build check](walkthrough/06-build-check.jpg)

## 30. VS Code extension

Check that a COBOL file compiles, then convert and verify it from the editor with your own key, capped in dollars, with the same labels. A local build, not on a marketplace. *Recording, Oct 31, VS Code's web build with the extension, ADDFEE converted for $0.0124.*

![VS Code extension](walkthrough/24-vscode.jpg)

## 31. Muse Code plugin

Diocle as a local plugin for Meta's coding agent. Here Muse Code, running Muse Wonder as its own model, calls the tools and has Muse Spark convert INTACCR: 1,027 of 1,027, about $0.017. The prompt named the tools and conversion was enabled and capped by the owner. Local, not an official Meta integration. *Recording, Oct 31, [transcripts](../editors/muse-code/transcripts/).*

![Muse Code plugin](walkthrough/25-muse-code.jpg)

## 32. In a terminal

**Analyzer, no model** (real output, Nov 1):

```text
$ python -m diocle_analyzer samples/interest-accrual --out report.json
INTACCR    src/INTACCR.cbl              ACCTIN(5 fields) -> INTOUT(5 fields)     convertible
9 findings, 4 dependency edges
```

**Re-verify with no key and no model** (real output, Nov 1). This shows stored Java still matches on fresh records; it is not a new conversion:

```text
$ sh scripts/quickstart.sh --no-key
No-key mode: no model is called. GnuCOBOL compiles the original, then the original and the stored Java run on the same inputs.
PASS  1027/1027 cases match  (stdout matches)
RE-VERIFIED  1027/1027 inputs matched, in 1 s. No model was called.
```

**Audit the evidence, no model** (run `make test` first, which creates that environment): `services/verifier/.venv/bin/python eval/audit_chqclr.py` ([what it found](SHOWCASE_CHQCLR.md)).

## Not pictured, and why

| Feature | Why there is no picture | Where to read about it |
|---|---|---|
| Keyed files (VSAM-style) | No keyed conversion has run on the live site; experimental, Berkeley DB stand-in | [FEATURES](FEATURES.md#keyed-indexed--vsam-ksds-style-files-verified-on-gnucobols-indexed-file-handler) |
| Smallest reproducer | Skipped when a sandbox is configured, so its card is empty on the live engine | [FEATURES](FEATURES.md#smallest-reproducer-and-regression-tests) |
| JCL job check | Command line only (`run-job`), and it spends model credits | [README](DETAILS.md#whole-jcl-job-verification-v1-one-sort-step-feeding-one-cobol-step) |
| Creating a target repository, convert anyway | Local or admin only | [FEATURES](FEATURES.md#let-diocle-create-the-target-repository-local-or-admin-only) |
| Notepad++ script | Its Notepad++ API calls are untested | [README](../editors/notepadpp/README.md) |
| MCP server, fix memory, swarm, escalation tiers | Command line and agent behaviour rather than a screen | [README](DETAILS.md#which-model-does-what), [`services/mcp`](../services/mcp/README.md) |
