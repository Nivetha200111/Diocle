# contracts

Shared JSON Schemas defining hand-offs between modules: analysis-report, conversion-output (draft), verification-report, run, delivery, certificate and sql-schema (copybooks as SQL tables with their SQLite round-trip proof) and transcription (a printout image transcribed to COBOL, gated by the compiler and a differential run; v0.1).

Change contracts first, then implementations.

compile-check v0.1 (answer of the sandbox's compile-only job, run before any model call).

Recent additive changes: run v0.14 and delivery v0.4 (convert-anyway: `assurance` certified | certified-against-repaired-cobol | compiled-unverified | failed, `assuranceReason`, `cobolRepair`), analysis-report v0.5 (file direction `io`, program `displayOnly` and `resolvedCalls`), verification-report v0.8 (stdout result, `runs.stdoutCompared`, `runs.files.updated`), sql-schema direction `io`.

behavior-claims v0.1 (verified documentation: plain-English claims about a COBOL program, each with examples that GnuCOBOL runs on the original; claims are `confirmed on the examples tried`, `refuted` with the actual value, or `unchecked`; the model never decides). Run v0.13 carries it as the optional `behavior` field and adds the `behavior` event type; older runs stay valid.
