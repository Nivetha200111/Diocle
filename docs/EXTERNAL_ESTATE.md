# External estate: COBOL Programming Course, run as found

> **Status: PROTOCOL PINNED Nov 2, 2026, before any model call against this estate. Analysis phase
> run Nov 2 (see Results); conversion not yet run.** Results go in the Results section and in
> `eval/results-external-estate.json`; the protocol below does not change afterwards. Until the
> conversion results exist, Diocle has **no** external-estate conversion claim.

## Why

Every program Diocle has certified so far is synthetic and was written by Diocle's author (the frozen
evaluation in [EVALUATION.md](EVALUATION.md), the Quillmark estates, CardDemo's `CBCUS01C` aside). That
caps what the results prove: a judge cannot tell "works" from "works on the author's programs". This run
tests Diocle on a complete external codebase it was not written or tuned for, and publishes the outcome
whatever it is.

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
   - **certified** — `diocle_converter run <sample> --breaker --no-memory` reached certification
     (held-out 1,000 inputs, then the breaker), run id recorded;
   - **not certified** — conversion ran and did not certify within the normal caps, error recorded.
3. Fix memory **off** (`--no-memory`): nothing learned from earlier programs may help, and nothing from
   this estate is learned. Normal caps (rule 10): 60 calls/run, 20/round, 3 rounds, breaker as in the
   frozen evaluation. No cap is raised for a failing program.
4. **No tuning afterwards.** If a program fails, the converter, analyzer and verifier are not changed in
   response on this branch. A later re-run after product changes is a separate, dated result; this one
   stands as recorded.
5. Certified programs are re-verified on the five fresh seeds 9001–9005 (1,000 random inputs each),
   as in `eval/run_eval.py`.
6. Runner: `eval/run_external_estate.py` (mirrors `eval/run_eval.py`; writes
   `eval/results-external-estate.json`, refusing to overwrite it). Needs the Mac toolchain
   (GnuCOBOL 3.2, JDK, `.env` keys), like every real conversion.
7. Cost is reported as recorded in the run files (list-price estimates), with the total for the estate.

## How to run it (Mac)

```
cd services/analyzer && .venv/bin/python -m pytest -q   # the tree under test is green first
cd ../.. && services/verifier/.venv/bin/python eval/run_external_estate.py
```

Then fill in the results section below from `eval/results-external-estate.json` and link this page from
`docs/EVIDENCE.md` and the live Evidence page. Do not edit the protocol above after the run.

## Results

### Analysis phase (Nov 2, 2026, Windows; no model calls)

The estate was cloned, checked out at the pinned commit above (verified `780b1c9…` locally), and analyzed
with `diocle_analyzer` exactly as the protocol states (the GitHub import on the Mac will pin the same
commit in its report). Raw report: `runs/external-estate/report.json` (git-ignored, regenerable).

**32 programs: 28 convertible, 4 refused.** The analyzer wrote 27 samples — `CBLC1.cobol` shares
PROGRAM-ID `CBL0006` with `CBL0006.cobol`, so it is the same program and is counted once, not twice
(the runner records it as a duplicate; see `eval/run_external_estate.py`).

| Refused program | Reason (analyzer, verbatim) |
|---|---|
| `ADDAMT` | ACCEPT reads the console: a DISPLAY-only program is compared on stdout, and its console input cannot be varied |
| `CBLDB21` | EXEC SQL outside the verified subset (db2-subset-1): table name Z#####T is outside the subset (letters, digits and underscores) |
| `CBLDB22` | EXEC SQL outside the verified subset (db2-subset-1): table name Z#####T is outside the subset |
| `CBLDB23` | EXEC SQL outside the verified subset (db2-subset-1): table name Z#####T is outside the subset |

(The `Z#####T` names are student-ID placeholders in the course's DB2 labs, so these three refusals are
the analyzer declining programs that are not runnable as distributed, not a conversion failure.)

### Conversion phase

_Not run yet._ The 27 distinct convertible programs convert on the Mac with
`eval/run_external_estate.py` (GnuCOBOL, JDK and model keys are not on the Windows machine). Certified /
not-certified outcomes, run ids, fresh-seed re-verification and total cost go here and in
`eval/results-external-estate.json` when that run exists. Nothing about conversion is claimed until then.
