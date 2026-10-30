---
name: diocle
description: Use when the user wants to analyze, convert or check legacy COBOL with Diocle (COBOL to Java, verified against GnuCOBOL), or asks what Diocle can convert, or to read a Diocle run.
---

# Diocle: COBOL to Java, checked against the original

Diocle proves a Java conversion behaves like the original COBOL by compiling the COBOL with GnuCOBOL and running both on the
same generated inputs. These tools are local (an MCP server named `diocle`). They are not an official Meta integration.

## Tools

- `diocle_analyze(path)`: free. Layouts, files, risk flags, and the refusal reason if a program cannot be verified.
- `diocle_coverage()`: free. What Diocle converts and what it refuses, with reasons.
- `diocle_verify_stored(sample)`: free, no model. Re-verifies a sample's checked-in certified Java (`samples/<name>/certified-java`).
- `diocle_convert(sample, max_usd?)`: REAL MODEL MONEY on the owner's Meta key. Disabled unless the owner turned it on.
- `diocle_explain(run)`: free. Plain-English summary of `runs/<id>`.
- `diocle_mutation_report(run)`: free. Reads a stored mutation report, if there is one.
- `diocle_live_run(run_id?)`: free, read-only GET to the public Diocle site (for example `chqclr-20261028-214355`).

## Workflow (follow in order, do not skip steps)

1. **Analyze.** Call `diocle_analyze` on the path. Summarize the programs, the files and fields, and the highest-severity risk flags.
2. **Explain refusals.** If a program is not convertible, give the reason in plain words (call `diocle_coverage` if useful) and stop.
   Do not try to convert it another way and do not claim it can be verified.
3. **Ask before spending.** Before `diocle_convert`, tell the user it spends real money (typically USD 0.02 to 0.05, capped at the
   `max_usd` you pass, default 0.10, hard maximum 0.25) and wait for an explicit yes in the conversation. Never decide this yourself.
   Never ask for, pass or print an API key; the owner's key comes from their environment.
4. **Convert** with `diocle_convert` only after consent. If it answers that it is disabled, report that and tell the user how the owner
   enables it (README of the plugin); do not look for a way around it.
5. **Verify.** For a stored conversion, call `diocle_verify_stored`. After a convert, read the result and `diocle_explain` the run.
6. **Report honestly.** Say what was tested: "the Java matched the GnuCOBOL original on N of N generated inputs". Say it is
   **matched on the tested inputs, not proven equivalent**, and that GnuCOBOL is the oracle (it can differ from IBM COBOL in edge
   cases). Quote counts, cost and seed from the tool result; never invent them. If something failed, say so first.

## Rules

- Paths must be inside the Diocle repository; the tools refuse anything else. Do not retry with tricks.
- Only synthetic samples (`samples/`) are bundled. Never paste real client code or data into a prompt.
- Do not call a tool twice to get a "better" result. Report what it returned.
