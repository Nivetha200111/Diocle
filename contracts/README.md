# contracts

Shared JSON Schemas defining hand-offs between modules: analysis-report, conversion-output (draft), verification-report, run, delivery, certificate and sql-schema (copybooks as SQL tables with their SQLite round-trip proof) and transcription (a printout image transcribed to COBOL, gated by the compiler and a differential run; v0.1).

voice-question v0.1 ("Ask the original program": a transcribed spoken question, at most three proposed claims reusing behavior-claims v0.1, GnuCOBOL verdicts, an answer assembled from confirmed claims only, costs and caps; request is two names from fixed lists, job and config status shapes).

Change contracts first, then implementations.

live-sample v0.1 (the two public "try it live" buttons: request, job and config status; the request is a name from a fixed list) and run v0.16 (`sampleRun`, additive: a run started by the live button; absent on all other runs).

build-report v0.1 (whole-repository build check: all converted Java compiled together, copybook drift, CALL resolution and USING compatibility, dependency graph, verdict pass | fail | warn; `scope.notChecked` states what it did not look at) and delivery v0.6 (`buildCheck`, additive).

compile-check v0.1 (answer of the sandbox's compile-only job, run before any model call).

Recent additive changes: analysis-report v0.7 (file `keyed`: ORGANIZATION INDEXED facts in the verified subset `ksds-subset-1`, or the exact refusal) and verification-report v0.10 (`runs.keyed`: per keyed file, records seeded and final on each side, first mismatching key; one `keyed:DD` result per file, inputSource `keyed`; checked on GnuCOBOL's INDEXED handler, never IBM VSAM), delivery v0.5 (`createTarget` {name, owner, visibility} in the request and the record, `targetCreated`: the delivery creates its own target repository; admin only, private by default), analysis-report v0.6 (program `sql`: tables with their schema source, classified statements, cursors and the exact refusal reason for EXEC SQL; subset `db2-subset-1`) and verification-report v0.9 (`runs.database`: engine, version, subset, per-table row counts and first mismatch; one `table:NAME` result per table, inputSource `database`; the engine is a SQLite stand-in, never real DB2), run v0.14 and delivery v0.4 (convert-anyway: `assurance` certified | certified-against-repaired-cobol | compiled-unverified | failed, `assuranceReason`, `cobolRepair`), analysis-report v0.5 (file direction `io`, program `displayOnly` and `resolvedCalls`), verification-report v0.8 (stdout result, `runs.stdoutCompared`, `runs.files.updated`), sql-schema direction `io`.

behavior-claims v0.1 (verified documentation: plain-English claims about a COBOL program, each with examples that GnuCOBOL runs on the original; claims are `confirmed on the examples tried`, `refuted` with the actual value, or `unchecked`; the model never decides). Run v0.13 carries it as the optional `behavior` field and adds the `behavior` event type; older runs stay valid.

minimal-reproducer v0.1 (the smallest input on which the Java still differs from the original COBOL, found by record-level delta debugging and field-level simplification with no model call; reduction stats, the named input fields, original vs translated output, an optional suspected cause labelled `explanation, not proof`, and a self-contained regression case the verifier replays against any Java). Run v0.18 adds the optional `reproducers` summaries; older runs stay valid. Examples: `contracts/examples/minimal-reproducer.*.json`.

`contracts/examples/minimal-reproducer.chqclr-nsf-fee.json` is a REAL output, not hand-written: CHQCLR's breaker input (the NSF return fee) minimized with `--strict` against a Java made by re-introducing the pre-fix defect (a one-line change in the repaired Java's two number parsers: any non-digit makes the whole field 0). The run's original pre-fix Java was not stored.

minimal-reproducer v0.1 additive: `signatureMode` (`strict` = same differing output fields and values as the original failure, `fields` = same field(s) only, values may differ) and optional `origin` (e.g. a defect re-created by hand). The CHQCLR example is marked as a rebuilt defect in its own `origin`.
