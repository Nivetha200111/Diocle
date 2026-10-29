# contracts

Shared JSON Schemas defining hand-offs between modules: analysis-report, conversion-output (draft), verification-report, run, delivery, certificate and sql-schema (copybooks as SQL tables with their SQLite round-trip proof) and transcription (a printout image transcribed to COBOL, gated by the compiler and a differential run; v0.1).

Change contracts first, then implementations.

compile-check v0.1 (answer of the sandbox's compile-only job, run before any model call).

Recent additive changes: analysis-report v0.5 (file direction `io`, program `displayOnly` and `resolvedCalls`), verification-report v0.8 (stdout result, `runs.stdoutCompared`, `runs.files.updated`), sql-schema direction `io`.
