# External estate: COBOL Programming Course, run as found

> **Status Nov 3, 2026: three dated passes have run.** [The first two](#conversion-phase-nov-2-to-3-2026-mac) stand as recorded.
> [The third](#third-pass-results-nov-3-2026-mac) ran after a product fix made in response to this same course's failures, so it
> is **not a blind test**, and it certified 9 of the 13 the earlier passes did not (8 against repaired COBOL, 1 as distributed on
> fixed input).
>
> **Status when pinned: PROTOCOL PINNED Nov 2, 2026, before any model call against this estate, and corrected the same
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
  (Open Mainframe Project, Linux Foundation). Licence: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/),
  by its authors, the Open Mainframe Project community.
- Pinned commit: `780b1c9624e066b9d784a738896e493282c5fbf4` (2026-10-15, "Merge pull request #349").
- Inventory at that commit: **32 COBOL sources** — 25 `.cobol` under
  `COBOL Programming Course #2 - Learning COBOL/Labs/cbl/`, 5 `.cbl` under Course #3 (the DB2 labs
  `CBLDB21`–`CBLDB23` and the Debugging challenge pair), and `DEPTPAY.CBL` / `EMPPAY.CBL` under
  Course #4. The runner enumerates programs from the analyzer's report, not from this list, so the
  published denominator is the analyzer's count.
- No estate source file is committed to this repository (same rule as CardDemo): the clone and the derived
  samples live in git-ignored `runs/external-estate/`; only results and this write-up are committed. The second-pass
  results publish each patch as a diff, so they reproduce short excerpts of the course's programs (138 of 2,439
  lines), shown with the patch's changes, under the licence above.

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

## Second pass (pinned Nov 2, 2026, after the first pass found the gap and before this pass ran)

The first pass stands as recorded in `eval/results-external-estate.json`. In it, 16 programs stopped before any
comparison because their original does not compile under GnuCOBOL: 15 have `PROGRAM-ID.    CBL0001` with no closing
period, which GnuCOBOL rejects under every `-std`, and `PAYROL0X` has a type error. A compile-only check with no model
call showed that adding the period lets 11 of the 15 compile. The other 4 fail on errors in the source itself
(`CBL0002`, `CBL0007`, `CBL0009`, `CBL0012`).

- **No product change.** This pass runs the same 16 through the converter's existing `--convert-anyway`, added to the
  flags above. It may patch an original that does not compile, within fixed limits (`cobolrepair.py`: a missing period,
  one small identifier correction, or one added word per line), and never overwrites the file.
- **What a result means.** The label is **certified against repaired COBOL**, never plain certified: the Java matched
  the patched copy under GnuCOBOL, not the file as distributed. Each result publishes the patch. Nothing checks that a
  corrected identifier is what the author meant, so a person must still confirm it. A program that cannot be patched,
  or whose Java differs, is reported as not certified.
- **Which programs.** Only those 16. Refused and not-converted programs keep those outcomes, and the rest are reported
  as `not in this pass`, with their result in the first pass.
- **Everything else as in the protocol above:** the pinned commit, `--breaker --no-memory`, normal caps, $0.40 per
  program, four at a time, one pass, no tuning. The owner approved a separate $2 ceiling.
- **Run:** `caffeinate -i services/verifier/.venv/bin/python eval/run_external_estate.py --second-pass --max-total-usd 2.00 --workers 4`.
  Results: `eval/results-external-estate-second-pass.json`. Both passes are published together.

## Third pass (protocol pinned Nov 3, 2026, before any model call of this pass)

> **Not a blind test.** This pass re-runs programs after a product fix made in response to this same course's failures.
> Wherever a result of it is quoted, it must say so. It does not replace, and may not be added silently to, the two passes
> above, whose results stand as recorded and are never overwritten. The numbers in this section were written before it ran,
> from stored Java and a compiler, with no model call. Only this note and the heading changed afterwards.
> [Its results are below](#third-pass-results-nov-3-2026-mac).

### What was checked first (Nov 3, no model calls)

GnuCOBOL 3.2 under the verifier's flags, on small synthetic programs (`services/verifier/tests/test_write_advancing.py`):
the advancing goes into the file as bytes, on fixed-length SEQUENTIAL files too. On a SEQUENTIAL file, four 4-byte `WRITE`s
with the second `AFTER ADVANCING 1 LINE` give `AAAA\nBBBBCCCC\n`. `0x0D` stands in for 0 LINES and `0x0C` for PAGE, and one
`0x0A` closes a file whose last advance was AFTER, even an implicit close at `STOP RUN`.

The write-up above calls the cause a gap in the translator and repair prompts. **That was only part of it. The verifier
itself could not certify these programs.** It cuts a fixed-length output into pieces of the record length and refused any
piece of another length, and these files never end on a whole record, so the last piece was short on both sides. Java whose
bytes were identical to GnuCOBOL's was refused with "converted record is 2 bytes, expected 62: a field overflowed". The
repair agent spent its budget on a difference that no Java could remove.

Taking each stored final Java, changing only newline writes and left-over probe lines in a scratch copy, and running the real
verifier on 1,000 generated records (the edits are not published, and they are ours, not the model's, so this shows the
cause and is not a certification):

| Program | Output bytes after those edits | Verifier before the fix | After it | What else differs |
|---|---|---:|---:|---|
| `CBL0004` | identical | 1,021 of 1,022 | passes | Its last repair step added a throwing debug line, so the final check exited 1: confirmed |
| `CBL0005` | identical | 1,021 of 1,022 | passes | Nothing |
| `CBL0006` | identical | 1,022 of 1,023 | passes | Nothing |
| `CBL0008` | identical | 1,023 of 1,024 | passes | Nothing |
| `CBL0011` | identical | 1,023 of 1,024 | passes | Nothing |
| `CBL006A` | identical | 1,022 of 1,023 | passes | Nothing |
| `CBL0106C` | identical | 37 of 38 | passes | Its last patch did not compile; removing that line was one of the edits. The original ends early, exit 232, on its own table check |
| `COBOL` | identical | 13 of 14 | passes | The agent's stored Java wrote a stray `ABCDE`; removing it was one of the edits |
| `CBL0010` | differ | 398 of 1,024 | 398 of 1,024 | A separate defect: edited amounts lose the `$` |
| `CBL0012` | differ | 1,022 of 1,024 | 1,023 of 1,024 | A separate defect: an edited total keeps a digit the picture drops |
| `CBL0106` | differ | 1,021 of 1,024 | 1,021 of 1,024 | A separate defect: the original overruns an `OCCURS 5` table and overwrites its own storage, which the Java does not reproduce |
| `CBL0033` | not tested | | | No `ADVANCING`. The ordinary check matched; breaker inputs differ. Not explained by this |
| `CBL0015` | not tested | | | No file to compare: the original never ends. Not explained by this |

So **this cause blocked 11 of the 13**: in all 11 the original's output is no whole number of records, so no Java could have
certified. It is the whole difference in 8 of them, on stored Java. In 3 there is a second defect as well, and the other 2 of
the 13 have nothing to do with it. The fix is not expected to certify those 5. That is an expectation, not a result.

### What changed

- **Verifier.** Identical bytes are not refused for their length. The only pairs this newly accepts are byte-identical ones.
  Output text lines now end at a newline byte and nothing else, carriage returns are compared, and a missing final newline
  fails the last record: before, a Java writing `0x0A` where GnuCOBOL wrote a form feed, or dropping a `0x0D`, certified on
  LINE SEQUENTIAL. That makes the check stricter on every LINE SEQUENTIAL program. Re-verifying the stored runs at a fixed
  seed changed no outcome. Nothing was normalized. Trailing spaces on text output stay the one stated leniency.
- **Translator and repair prompts.** They state the rule above, tested against the compiler's real bytes, only if the program
  has a `WRITE` with `AFTER` or `BEFORE`. For every other program both prompts are unchanged byte for byte, and a test pins
  that (`services/converter/tests/test_advancing_prompt.py`), so earlier measurements still describe the same prompts.
- **Hand-written proof.** A synthetic program's correct Java certifies through the real verifier on both file organizations.
  Java that ignores the newlines, drops only the closing one, or writes a newline for a form feed fails.

**The target is GnuCOBOL's file, not IBM's.** IBM documents its `ADV` option as carrying the print control in a byte of the
record (IBM's compiler was not tested), so these Java programs reproduce what GnuCOBOL writes, not a mainframe print file. A
person must decide which of them a downstream consumer needs.

### Protocol (fixed before the run)

- **Which programs.** Only the 13 not certified in the earlier passes: `CBL0004`, `CBL0005`, `CBL0006`, `CBL0008`, `CBL0010`,
  `CBL0011`, `CBL0012`, `CBL0015`, `CBL0033`, `CBL006A`, `CBL0106`, `CBL0106C`, `COBOL`. All the others are reported as
  `not in this pass` or keep their refused or not-converted outcome, with their result in the earlier passes.
- **Against what.** These 11 do not compile as distributed, so each can only be **certified against repaired COBOL**, never
  plain certified, with its patch published and to be confirmed by a person: `CBL0004`, `CBL0005`, `CBL0006`, `CBL0008`,
  `CBL0010`, `CBL0011`, `CBL0012`, `CBL0033`, `CBL006A`, `CBL0106`, `CBL0106C`. `COBOL` and `CBL0015` compile as
  distributed, so `--convert-anyway` leaves them unpatched. If `CBL0015`'s Java cannot be compared because the original never
  ends, the outcome is `compiled, not verified`.
- **Settings.** The pinned commit above, a fresh import, `--breaker --no-memory --convert-anyway`, normal caps, $0.40 per
  program, four at a time, one pass, no tuning during it. **Ceiling $2.00**, which needs the owner's OK before the run. The
  same 13 cost about $1.19 in the earlier passes. A program the ceiling leaves no room for is reported as `not run`.
- **Fresh seeds.** 9001 to 9005, as above. What a certification rests on stays as narrow as the measured table says: 2 of 10
  input fields vary, and `COBOL` has fixed input. The split is reported as before.
- **Counts.** On these files a comparison count is of pieces of the record length, not records (`CBL0004`: 1,022 pieces for
  1,021 records; `COBOL`'s `PRTLINE`: 13 pieces for 10 records), and is quoted as pieces.
- **Reporting.** Results go to a new file, `eval/results-external-estate-third-pass.json`, whose `pass` says this is not a
  blind test and whose `blindTest` is `false`. The runner refuses to overwrite any results file. Published results list the
  three passes separately, with no merged headline that hides which pass or which label a program's result came from.
- **Run:** `sh scripts/test.sh --no-install`, then
  `caffeinate -i services/verifier/.venv/bin/python eval/run_external_estate.py --third-pass --max-total-usd 2.00 --workers 4`.

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

### Conversion phase (Nov 2 to 3, 2026, Mac)

Both passes ran to the end with no resume and no restart. They cost **$1.42** in estimated model spend (rounded): $0.25 for the first (Diocle commit `6ccc86b`, branch `external-estate`) and $1.18 for the second (`7bc8bc8`, branch `estate-second-pass`). Raw records, including each patch: [`eval/results-external-estate.json`](../eval/results-external-estate.json) and [`eval/results-external-estate-second-pass.json`](../eval/results-external-estate-second-pass.json).

| Final result of the 32 programs | Count | Programs |
|---|---:|---|
| Certified against the file as distributed | 9 | `CBL0013`, `CBL0014`, `CBLC2`, `DEPTPAY`, `EMPPAY`, `HELLO`, `PAYROL00`, `SRCHBIN`, `SRCHSER` |
| Certified against repaired COBOL | 2 | `CBL0001`, `CBL0002` |
| Not certified: the Java differed or did not finish | 13 | `CBL0004`, `CBL0005`, `CBL0006`, `CBL0008`, `CBL0010`, `CBL0011`, `CBL0012`, `CBL0015`, `CBL0033`, `CBL006A`, `CBL0106`, `CBL0106C`, `COBOL` |
| Original does not compile and could not be patched | 3 | `CBL0007`, `CBL0009`, `PAYROL0X` |
| Refused, with the reason | 4 | `ADDAMT`, `CBLDB21`, `CBLDB22`, `CBLDB23` |
| Not converted (duplicate PROGRAM-ID) | 1 | `CBLC1` |

**So 11 of 32 certified, and what that rests on is narrow.** The 9 rest on one comparison on fixed input, because their inputs never vary. `CBL0001` and `CBL0002` vary 2 of 10 input fields and took 24 and 23 attacks with no difference, but they matched a patched copy, not the file as distributed. `CBL0001` needed the missing period. `CBL0002` needed a two-line model patch that a person must still confirm. All 11 had a guard review verdict of pass. No program in this repository was certified as distributed on inputs that vary.

The first pass stands as recorded. In it, `CBL0015` did not finish within 120 seconds (the original loops forever), and `COBOL` used all 60 calls and reached 13 of 14.

#### Second pass, the 16 that did not compile

| Program | Result | Patch: method, lines | Comparison | `AFTER ADVANCING` | Model calls | Cost |
|---|---|---|---|:---:|---:|---:|
| `CBL0001` | **certified against repaired COBOL** | deterministic, 1 | 24 attacks, 0 differed; 5 of 5 fresh seeds passed | no | 5 | $0.024 |
| `CBL0002` | **certified against repaired COBOL** | model, 2 | 23 attacks, 0 differed; 5 of 5 fresh seeds passed | no | 10 | $0.027 |
| `CBL0004` | not certified | deterministic, 1 | final check 1,021 of 1,022, and the Java exited 1 on a debug exception the repair agent left in | yes | 60 | $0.122 |
| `CBL0005` | not certified | deterministic, 1 | 221 of 222 at best, 3 of 1,022 after the last patch | yes | 60 | $0.093 |
| `CBL0006` | not certified | deterministic, 1 | 1,022 of 1,023 | yes | 60 | $0.104 |
| `CBL0007` | COBOL could not be patched | model, 2 | no comparison | yes | 9 | $0.009 |
| `CBL0008` | not certified | deterministic, 1 | 1,022 of 1,024 at best, 2 of 1,024 after the last patch | yes | 60 | $0.114 |
| `CBL0009` | COBOL could not be patched | model, 3 | no comparison | yes | 9 | $0.006 |
| `CBL0010` | not certified | deterministic, 1 | 403 of 1,024 | yes | 60 | $0.108 |
| `CBL0011` | not certified | deterministic, 1 | 1,022 of 1,024 at best, 3 of 1,024 after the last patch | yes | 60 | $0.090 |
| `CBL0012` | not certified | model, 2 | 1,022 of 1,024 | yes | 60 | $0.099 |
| `CBL0033` | not certified | deterministic, 1 | 45 of 45, then 15 of 15 breaker inputs differed | no | 23 | $0.059 |
| `CBL006A` | not certified | deterministic, 1 | 1,022 of 1,023 | yes | 60 | $0.103 |
| `PAYROL0X` | COBOL could not be patched | model, 0 | no comparison | no | 6 | $0.005 |
| `CBL0106` | not certified | deterministic, 1 | 1,021 of 1,024 | yes | 60 | $0.123 |
| `CBL0106C` | not certified | deterministic, 1 | 37 of 38 at best, then the last patch did not compile | yes | 60 | $0.091 |

"At best" and the closest-match counts below come from the run logs, which are not committed; the results files hold the final comparison.

How to read the raw file:

- **`certified: false` on `CBL0001` and `CBL0002`** is by design: plain certified is reserved for the original file. Read `outcome`, "certified against repaired COBOL". Their `assuranceReason` says "Muse changed" a line even where the patch `method` is `deterministic`; `method` is the correct one.
- **`compiled, not verified`** is the runner's level for the three programs in the "could not be patched" row. The COBOL never compiled, so nothing was compared.
- **`45/45 cases matched` for `CBL0033`** sits beside the words "still differs". The ordinary check matched on all 45 cases compared, and the breaker's inputs then differed. The log's "1000 held-out inputs" is the number the code asks for; the comparison counted 45. The product's wording was left as it ran, and is listed as a fix to make.

### What the failures have in common

> **Correction, Nov 3, 2026.** This section and the next were written before the program-by-program check, and are kept as
> written. Two statements in them do not hold. "The comparison was correct to refuse these" is wrong: the verifier refused
> even Java whose bytes were identical to GnuCOBOL's, so no Java could have certified these 11. "The translator and the repair
> agent have no rule" was only part of the cause. The results of the two passes are unchanged.
> [What the check found](#what-was-checked-first-nov-3-no-model-calls).

**11 of the 13 not-certified programs use `WRITE ... AFTER ADVANCING`. None of the 11 certified programs does.** The other two are `CBL0015` and `CBL0033`. `CBL0007` and `CBL0009` also use it but never reached a comparison.

GnuCOBOL 3.2 (`-std=ibm`) writes extra newlines when a fixed-length sequential file uses it. A small test program, four `WRITE`s of a 4-byte record with the second `AFTER ADVANCING 1 LINES`, produces:

```
AAAA\n    BBBBCCCC\n
```

That is a newline before the advanced record and another at close, with the records that follow shifted. It fits the mismatches: `original Account` against `converted Accoun`, and a last output record of 1 byte against an expected 62. Ten of these 11 came within 1 to 3 records of matching at some point (all but `CBL0010`). All 11 used their 60 model calls without matching, and on some a last patch made the result far worse.

This is a correlation plus one reproduced mechanism. A second check found the same newlines in the output of patched `CBL0006`. It was not tested program by program, and it does not show the rest of each Java is right. It is GnuCOBOL's behaviour, and IBM's compiler was not tested. The comparison was correct to refuse these: the bytes do differ.

### What this shows, and what it does not

- **Shown:** on a public repository we did not write, Diocle accounted for all 32 programs, certified 11, and did not certify 13: 12 whose Java did not match, and `CBL0015`, whose original never ends. Its failures were reported rather than hidden.
- **Not shown:** that Diocle works on any repository. This is one repository of small teaching programs, one model, one pass of each kind, and thin inputs (see the table above). A confirmed false certification or a missed defect was not measured here.
- **Likely gap:** the translator and the repair agent have no rule for how GnuCOBOL writes `AFTER ADVANCING`. No fix is part of these results.

### Third pass results (Nov 3, 2026, Mac)

> **Not a blind test.** The fix was made in response to these programs' failures, and these are the same programs. It says that
> after the fix, 9 of the 11 `ADVANCING` programs certified on the course that prompted it, on one new translation each, so it
> cannot separate the fix from differences between translations. It says nothing about a repository the fix has not seen.

**9 of the 13 certified: 8 against repaired COBOL, and `COBOL` as distributed on fixed input.** The pass cost **$0.64** of estimated model spend, under the $2 ceiling, at Diocle commit `b473fea`. Raw records, including each patch: [`eval/results-external-estate-third-pass.json`](../eval/results-external-estate-third-pass.json). They publish patches as diffs, the same kind of short excerpts as the second pass, under the licence above.

The run stopped once on a model provider failure (HTTP 502) and resumed with the same settings and commit, as item 9 of the protocol allows. `CBL0010` and `CBL0106` were converted again, and $0.12 of the $0.64 went on their stopped conversions. The table shows the final conversion of each. Neither stopped conversion was certified, but they got further than the table shows: `CBL0010`'s reached 1,024 of 1,024 and then 11 of 11 breaker inputs differed, and `CBL0106`'s started at 222 of 224, where the final one started at 128 of 224.

| Program | Result | Patch: method, lines | Breaker: attacks, differed | Each of 5 fresh seeds, pieces compared | Model calls | Cost |
|---|---|---|---:|---:|---:|---:|
| `CBL0004` | **certified against repaired COBOL** | deterministic, 1 | 17, 0 | 1,022 | 5 | $0.031 |
| `CBL0005` | **certified against repaired COBOL** | deterministic, 1 | 32, 0 | 1,022 | 5 | $0.025 |
| `CBL0006` | **certified against repaired COBOL** | deterministic, 1 | 32, 0 | 1,023 | 5 | $0.027 |
| `CBL0008` | **certified against repaired COBOL** | deterministic, 1 | 32, 12, then one repair fixed it | 1,024 | 24 | $0.055 |
| `CBL0011` | **certified against repaired COBOL** | deterministic, 1 | 35, 0 | 1,024 | 14 | $0.046 |
| `CBL0012` | **certified against repaired COBOL** | model, 2 | 33, 0 | 1,024 | 20 | $0.053 |
| `CBL006A` | **certified against repaired COBOL** | deterministic, 1 | 30, 0 | 1,023 | 5 | $0.031 |
| `CBL0106C` | **certified against repaired COBOL**, guard review `flag` | deterministic, 1 | 18, 0 | 38 to 57 | 5 | $0.040 |
| `COBOL` | **certified as distributed, inputs never vary** | none | skipped: `multi-file program`, with no input to attack | 14 | 12 | $0.035 |
| `CBL0010` | not certified | deterministic, 1 | not reached | 1,022 of 1,024 in the final check | 60 | $0.084 |
| `CBL0033` | not certified | deterministic, 1 | 22, 22 | 45 of 45, then the breaker's inputs differed | 23 | $0.044 |
| `CBL0106` | not certified | deterministic, 1 (in the run's events; the results file has none, as the run stopped first) | not reached | 222 of 224 at best, then the Java did not finish within 120 seconds | 21 | $0.051 |
| `CBL0015` | compiled, not verified | none | not reached | the original never ends, so nothing to compare | 1 | $0.001 |

"At best" comes from the run log, which is not committed. All 9 passed all 5 seeds, 9001 to 9005.

**Against what the protocol expected.** All 8 programs whose stored Java was explained entirely by this cause certified. `CBL0012` also certified, although the protocol did not expect it to: its new translation showed the same edited-total defect in round 1 (1,023 of 1,024), and the repair agent fixed it by round 2. `CBL0010`, `CBL0106`, `CBL0033` and `CBL0015` stayed uncertified, as expected. `CBL0010`'s 2 differing pieces are its totals line (`$83,446,477.92` from the COBOL, `657,293,582.36` from the Java) and its last piece, one newline short.

#### All 32 programs, by label and pass

| Result | Count | Programs | From |
|---|---:|---|---|
| Certified as distributed, on fixed input | 10 | `CBL0013`, `CBL0014`, `CBLC2`, `DEPTPAY`, `EMPPAY`, `HELLO`, `PAYROL00`, `SRCHBIN`, `SRCHSER`; `COBOL` | First pass; third pass |
| Certified against repaired COBOL, inputs vary, attacked | 10 | `CBL0001`, `CBL0002`; `CBL0004`, `CBL0005`, `CBL0006`, `CBL0008`, `CBL0011`, `CBL0012`, `CBL006A`, `CBL0106C` | Second pass; third pass |
| Not certified | 3 | `CBL0010`, `CBL0033`, `CBL0106` | Third pass |
| Original never ends, nothing to compare | 1 | `CBL0015` | Third pass |
| Original does not compile and could not be patched | 3 | `CBL0007`, `CBL0009`, `PAYROL0X` | Second pass |
| Refused, with the reason | 4 | `ADDAMT`, `CBLDB21`, `CBLDB22`, `CBLDB23` | First pass |
| Not converted (duplicate PROGRAM-ID) | 1 | `CBLC1` | First pass |

All three passes cost **$2.07** of estimated model spend, rounded: $0.25, $1.18 and $0.64. This table may be quoted only with its split and with the third pass named as not a blind test.

#### What the 9 rest on

- **Still none on real variety as distributed.** No program in this repository is certified as distributed on inputs that vary. The 8 matched a patched copy under GnuCOBOL, and a person must still confirm each patch. 7 of them add the missing period. `CBL0012`'s two-line model patch also changes `CURRENT-DATA` to `CURRENT-DATE`.
- **Thin inputs.** On the 8, 2 of 10 input fields vary with the seed. Generated records still cannot reach the free-text tests in `CBL0006`, `CBL006A` and `CBL0106C`; only the breaker's inputs can.
- **The 8 are not 8 independent programs.** They are lessons built on one account report. Against `CBL0004`'s 163 lines, a plain `diff` of the other 7 shows 12 to 107 changed lines on the two sides together. In the spot check below, `CBL0008`, `CBL0011` and `CBL0012` wrote the same bytes.
- **`CBL0106C` is compared on a short run.** Both sides stop with exit 232 on the program's own table check, so each fresh seed compares only 38 to 57 pieces, and its certification compared 35. Its guard review was `flag`, for creating a parent directory, the only certification in any pass without a guard review of `pass`.
- **`COBOL` is one comparison.** 14 pieces on fixed input, and no breaker.
- **GnuCOBOL's file, not IBM's.** As the protocol states, these Java programs reproduce what GnuCOBOL writes. A person must decide whether a downstream consumer needs that or a mainframe print file.

**One spot check, outside the protocol.** For all 9, we ran the certified Java and the compiled COBOL by hand on seed 20261103, which no run used, with 1,016 generated records (`COBOL` has no input), then compared whole output files, exit codes and stdout directly. All 9 were identical. This used the verifier's generator and build commands but not its comparison. The script is not committed, and one seed adds little beyond the 5 above.

**`CBL0008` is the only certified program where an attack landed.** 12 of the breaker's inputs differed on an edited balance: `$00,002,026.1` from the COBOL, `$2,026.1` from the Java. The repair agent fixed it in one cycle, and the program then passed the fresh seeds.

How to read the raw file: `certified: false` and `status: not-certified` on the 8 are by design, because plain certified is reserved for the original file, so read `outcome`. `CBL0033`'s "45/45 cases matched" sits beside "still differs" for the reason given above. `CBLC1` appears as `program: "CBL0006"`, the PROGRAM-ID it shares, with the outcome `not converted`.
