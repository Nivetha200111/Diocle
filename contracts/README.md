# contracts

Shared JSON Schemas defining hand-offs between modules: analysis-report, conversion-output (draft), verification-report, run, delivery, certificate and sql-schema (copybooks as SQL tables with their SQLite round-trip proof) and transcription (a printout image transcribed to COBOL, gated by the compiler and a differential run; v0.1).

Change contracts first, then implementations.

live-sample v0.1 (the two public "try it live" buttons: request, job and config status; the request is a name from a fixed list) and run v0.16 (`sampleRun`, additive: a run started by the live button; absent on all other runs).

compile-check v0.1 (answer of the sandbox's compile-only job, run before any model call).

Recent additive changes: delivery v0.5 (`createTarget` {name, owner, visibility} in the request and the record, `targetCreated`: the delivery creates its own target repository; admin only, private by default), analysis-report v0.6 (program `sql`: tables with their schema source, classified statements, cursors and the exact refusal reason for EXEC SQL; subset `db2-subset-1`) and verification-report v0.9 (`runs.database`: engine, version, subset, per-table row counts and first mismatch; one `table:NAME` result per table, inputSource `database`; the engine is a SQLite stand-in, never real DB2), run v0.14 and delivery v0.4 (convert-anyway: `assurance` certified | certified-against-repaired-cobol | compiled-unverified | failed, `assuranceReason`, `cobolRepair`), analysis-report v0.5 (file direction `io`, program `displayOnly` and `resolvedCalls`), verification-report v0.8 (stdout result, `runs.stdoutCompared`, `runs.files.updated`), sql-schema direction `io`.

behavior-claims v0.1 (verified documentation: plain-English claims about a COBOL program, each with examples that GnuCOBOL runs on the original; claims are `confirmed on the examples tried`, `refuted` with the actual value, or `unchecked`; the model never decides). Run v0.13 carries it as the optional `behavior` field and adds the `behavior` event type; older runs stay valid.
