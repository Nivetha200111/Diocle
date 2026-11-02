# External estate: COBOL Programming Course, run as found

> **Status: PROTOCOL PINNED Nov 2, 2026, before any model call against this estate, and corrected the same
> day after a read-only review, still before any model call. Analysis phase run Nov 2 (see Results);
> conversion not yet run.** Results go in the Results section and in
> `eval/results-external-estate.json`; the protocol below does not change afterwards. Until the
> conversion results exist, Diocle has **no** external-estate conversion claim.

## Why

Every program Diocle has certified so far is synthetic and was written by Diocle's author (the frozen
evaluation in [EVALUATION.md](EVALUATION.md), the Quillmark estates, CardDemo's `CBCUS01C` aside). That
caps what the results prove: a judge cannot tell "works" from "works on the author's programs". This run
tests Diocle on a complete external codebase it was not written or tuned for, and publishes the outcome
whatever it is.

**What it cannot show.** One repository does not show that Diocle works on any repository. This one is a
teaching course, with small programs and no CICS, and Diocle refuses whole classes of real code (CICS, IMS,
and more; see the README). It also tests some programs far less than others, as the Results section measures
before the run. The result is evidence about these programs at this commit.

## The estate

- Repository: [openmainframeproject/cobol-programming-course](https://github.com/openmainframeproject/cobol-programming-course)
  (Open Mainframe Project, Linux Foundation). Licence: see the repository's `LICENSE`.
- Pinned commit: `780b1c9624e066b9d784a738896e493282c5fbf4` (2026-10-15, "Merge pull request #349").
- Inventory at that commit: **32 COBOL sources** — 25 `.cobol` under
  `COBOL Programming Course #2 - Learning COBOL/Labs/cbl/`, 5 `.cbl` under Course #3 (the DB2 labs
  `CBLDB21`–`CBLDB23` and the Debugging challenge pair), and `DEPTPAY.CBL` / `EMPPAY.CBL` under
  Course #4. The runner enumerates programs from the analyzer's report, not from this list, so the
  published denominator is the analyzer's count.
- No estate source is committed to this repository (same rule as CardDemo): the clone and the derived
  samples live in git-ignored `runs/external-estate/`; only results and this write-up are committed.

## Protocol (fixed before the run)

1. Import once, as found:
   `DIOCLE_IMPORT_OWNERS=openmainframeproject .venv/bin/python -m diocle_analyzer https://github.com/openmainframeproject/cobol-programming-course --out runs/external-estate/report.json --samples-dir runs/external-estate/samples`
   (services/analyzer; the analyzer pins the commit it analyzed in the report).
2. Every program in the report is accounted for, in one table, with exactly one outcome:
   - **refused** — the analyzer's `notConvertibleReason`, quoted verbatim;
   - **certified** — `diocle_converter run <sample> --breaker --no-memory` reached certification, run id
     recorded. What that certification rests on differs by program, so it is always reported as one of three:
     *inputs vary, attacked*; *inputs vary, not attacked*; or *inputs never vary* (a new seed changes nothing,
     so this is one comparison on fixed input, however many seeds are run);
   - **not certified** — conversion ran and did not certify within the normal caps, or timed out; the
     converter's error and last events recorded;
   - **not converted** — another source holds its PROGRAM-ID, so the analyzer wrote no sample for it;
   - **not run** — no sample was written, or the spending ceiling was reached first.
   Every converted program also records what was exercised: its shape, input files, how many fields a new seed
   changes, and whether the breaker ran or why it was skipped. The headline may not quote a certified count
   without that split.
3. Fix memory **off** (`--no-memory`): nothing learned from earlier programs may help, and nothing from
   this estate is learned. Normal caps (rule 10): 60 calls/run, 20/round, 3 rounds, breaker as in the
   frozen evaluation. No cap is raised for a failing program.
4. **No tuning afterwards.** If a program fails, the converter, analyzer and verifier are not changed in
   response on this branch. A later re-run after product changes is a separate, dated result; this one
   stands as recorded.
5. Certified programs are re-verified on the five fresh seeds 9001–9005, as in `eval/run_eval.py`: 1,000 generated
   records each where a program reads records. A program with no input gets the same one comparison each time.
6. Runner: `eval/run_external_estate.py` (mirrors `eval/run_eval.py`; writes
   `eval/results-external-estate.json`, refusing to overwrite it). Needs the Mac toolchain
   (GnuCOBOL 3.2, JDK, `.env` keys), like every real conversion. It records the `cobc` and `java` versions: this
   Mac has JDK 27, while CI uses JDK 21.
7. Cost is reported as recorded in the run files (list-price estimates), with the total for the estate, including
   runs that were stopped or restarted. A stopped run's record can miss its last calls, so the total is an
   estimate, and if any run's price is unknown the results say so.
8. **Limits of the run itself.** The owner approved a total ceiling of $2 (`--max-total-usd 2.00`). Each program
   has a hard $0.40 limit (`--max-usd 0.40`, the converter's fail-closed cap; the dearest conversion in the
   evaluations cost $0.1642). Reaching it during translation or repair means not certified; reaching it during the
   breaker or guard review leaves the certification standing, with what ran shown in the results, and certifications
   without a passed guard review are listed. A program starts only if the spend
   so far plus $0.40 for each conversion running, itself included, stays within $2; the rest are reported as not
   run. A conversion is stopped after 150 minutes (the longest on record is 125.6). Four conversions run at a time
   (`--workers 4`), which changes the elapsed time and no setting of any program.
9. **One pass.** Results are saved after every program. A program that has a result is never re-run. A run may
   resume only with the same settings and the same Diocle commit, and only for programs with no result. A conversion
   stopped before it had a result (Ctrl-C, a killed run, or a model provider failure, which stops the run because an
   outage says nothing about the program) is converted again; its spend stays counted, and the results list it under
   `restartedPrograms` and count the resumes. An unfinished run is published only if labelled as partial.
10. **Public and private output.** The results file holds outcomes, the converter's own error text and events,
   scrubbed of local paths. Full converter output stays in git-ignored `runs/external-estate/logs/`, because
   provider messages can echo account details. A real run refuses uncommitted changes, a missing compiler or
   unreadable settings before anything starts.

## How to run it (Mac)

```
sh scripts/test.sh --no-install                          # the tree under test is green first
services/verifier/.venv/bin/python eval/run_external_estate.py --plan   # what would be exercised; no model calls
caffeinate -i services/verifier/.venv/bin/python eval/run_external_estate.py --max-total-usd 2.00 --workers 4
```

Then fill in the results section below from `eval/results-external-estate.json` and link this page from
`docs/EVIDENCE.md` and the live Evidence page. Do not edit the protocol above after the run.

## Results

### Analysis phase (Nov 2, 2026, Windows; no model calls)

The estate was cloned, checked out at the pinned commit above (verified `780b1c9…` locally), and analyzed
with `diocle_analyzer` exactly as the protocol states (the GitHub import on the Mac will pin the same
commit in its report). Raw report: `runs/external-estate/report.json` (git-ignored, regenerable).

**32 programs: 28 convertible, 4 refused.** The analyzer wrote 27 samples. `CBLC1.cobol` shares PROGRAM-ID
`CBL0006` with `CBL0006.cobol` but is a different program: it counts New York clients, `CBL0006` counts Virginia.
The analyzer keeps the first file per PROGRAM-ID, so **`CBLC1` is not converted**, and is reported that way.

| Refused program | Reason (analyzer, verbatim) |
|---|---|
| `ADDAMT` | ACCEPT reads the console: a DISPLAY-only program is compared on stdout, and its console input cannot be varied |
| `CBLDB21` | EXEC SQL outside the verified subset (db2-subset-1): line 53: line 53: table name Z#####T is outside the subset (letters, digits and underscores) |
| `CBLDB22` | EXEC SQL outside the verified subset (db2-subset-1): line 70: line 70: table name Z#####T is outside the subset (letters, digits and underscores) |
| `CBLDB23` | EXEC SQL outside the verified subset (db2-subset-1): line 67: line 67: table name Z#####T is outside the subset (letters, digits and underscores) |

(The `Z#####T` names are student-ID placeholders in the course's DB2 labs, so these three refusals are
the analyzer declining programs that are not runnable as distributed, not a conversion failure.)

### What the run can exercise, measured before it (Nov 2, 2026, Mac; no model calls)

From `eval/run_external_estate.py --plan`, which uses the verifier's own generator. A field counts as varied only
if a new seed changes it. Unconstrained alphanumeric fields get placeholders that number the record
(`C00000000000001`), the same under every seed.

| Programs | Count | What a certification would rest on |
|---|---:|---|
| `CBL0001`, `CBL0002`, `CBL0004` to `CBL0012`, `CBL0033`, `CBL006A`, `CBL0106`, `CBL0106C` | 15 | One input and one output file. Only 2 of 10 input fields change with the seed (`ACCT-LIMIT`, `ACCT-BALANCE`). The breaker can run |
| `CBL0013`, `CBL0014`, `CBL0015`, `CBLC2`, `COBOL`, `DEPTPAY`, `EMPPAY`, `HELLO`, `PAYROL00`, `PAYROL0X` | 10 | No input file at all: one comparison on fixed input. No breaker |
| `SRCHBIN`, `SRCHSER` | 2 | An input file, but its one field is a placeholder, so a new seed changes nothing. No breaker |

So **12 of the 27 can only be certified on fixed input**, and the 15 others vary little. Generated records also
cannot reach the free-text tests in `CBL0006`, `CBL0106`, `CBL0106C` (`USA-STATE = 'Virginia'`) and `CBL006A`
(`'new York'`), because `USA-STATE` only ever holds a placeholder. On those four, only inputs the breaker designs
can reach that branch.

This is reported rather than fixed, because the run tests the product as found. Teaching programs like these need
real data files or constrained values to be tested well, which is a finding in itself.

### Conversion phase

_Not run yet._ The 27 distinct convertible programs convert on the Mac with
`eval/run_external_estate.py` (GnuCOBOL, JDK and model keys are not on the Windows machine). Certified /
not-certified outcomes, run ids, fresh-seed re-verification and total cost go here and in
`eval/results-external-estate.json` when that run exists. Nothing about conversion is claimed until then.
