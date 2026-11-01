# Evaluate Diocle on one program: a short packet for a prospective user

**Status: no outside evaluation has happened yet.** No customer, pilot, interview or endorsement exists. This page is what the author would hand to a modernization lead or systems integrator; their result, if they run it, is the validation that is still outstanding.

**The decision it supports:** should I accept this AI-written Java for this COBOL batch program, or send it back, and where should my reviewers look?

**Use your own public or synthetic program.** Do not send employer or client code to a hosted service. Run locally: your code goes only to the model host you configure (Meta Model API, or Muse Spark Open on a partner host).

## What you do today, and what changes

| | Today | With Diocle |
|---|---|---|
| Is the Java the same? | Hand review or sampling, plus whatever tests someone writes | Original (GnuCOBOL) and Java run on the same generated records; every output byte, display line and exit code compared |
| Inputs nobody thought of | Depends on the reviewer | A model designs inputs aimed at Java that already passed; every one is run through both programs |
| When they differ | Ticket to a developer | Repair agent patches and re-tests; re-checked on records it never saw and attacked again |
| Evidence for sign-off | Review notes | A run record, an equivalence report per program, and CI that re-runs the comparison on fresh inputs |

## What the report does not decide

- **Another runtime.** GnuCOBOL is not IBM Enterprise COBOL. If you can capture real mainframe output, golden-file replay judges against that (not yet tried on real mainframe output).
- **Every input.** Agreement on the inputs tried is not formal equivalence. Generated records are well-formed; bad data is exercised only by what the breaker designs.
- **Scope.** Batch programs, mainly sequential files. CICS, dynamic CALL and others are refused with a reason. DB2 and VSAM subsets run on SQLite and Berkeley DB stand-ins.
- **People and systems.** Code review, data migration, downstream integration, operations and acceptance stay with you.

## Thirty minutes, on your machine

1. **Prerequisites (2 min):** `sh scripts/quickstart.sh --check`, or the Docker commands in the README.
2. **See the check work with no key (1 min):** `sh scripts/quickstart.sh --no-key`. It re-verifies a stored conversion on fresh records. No model is called; this shows the comparison, not a new translation.
3. **Convert one bundled sample with your key (3 min, a few cents):** `sh scripts/quickstart.sh`. Capped at $0.10.
4. **Your own program:** see [Running on your own repo](FEATURES.md#running-on-your-own-repo-local-your-own-key). Add `--breaker`. Bring your own Java instead of translating, to audit another tool's output: `services/mcp` `certify_conversion`.
5. **Read the run:** which checks ran, which did not, what differed, what was repaired.

## What we would like to learn from you

Answer these from your run; a "no" is as useful as a "yes".

1. Did the analyzer accept your program, or refuse it for a reason you consider fair?
2. Did the comparison or the attack surface a difference you would have wanted to know about? Which kind (bad data, boundary, ordinary value)?
3. Would you change your review because of the report? What would you still check by hand?
4. What would have to be true before you relied on this on IBM Enterprise COBOL output?
5. How long did it take, and what did it cost you beyond the model spend the run reports? (Diocle measures model spend only.)

Send results, or a refusal you think is wrong, as a GitHub issue. Please leave out any client names, code and data.
