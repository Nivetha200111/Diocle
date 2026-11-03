# Blind test on repositories the fix never saw

> **Status Nov 4, 2026: run once on Nov 3 to 4, with no resume. [Results](#results) are below.**
>
> **When pinned: PROTOCOL PINNED Nov 3, 2026, before any model call against these repositories.** Results will be added below and in
> their own files. The protocol does not change afterwards, and the results are published whatever they show.

## Why

The [course repository's third pass](EXTERNAL_ESTATE.md#third-pass-results-nov-3-2026-mac) is not a blind test: its fix answered
that course's failures. This test runs the product as it stands on code that played no part in that fix.

## The repositories, pinned

| Repository | Commit | Licence | What it is | Programs the analyzer can test |
|---|---|---|---|---|
| [navikt/DSF](https://github.com/navikt/DSF) | `faade4961e316c89e8c312456bae411c63f1c482` | MIT | Norway's national pension system. Its README says the system ran in production from 1967 to 2018 and is written in PL/I. These are its COBOL sources, and this test does not establish what role each played | 4 |
| [fzn0x/core-banking-system](https://github.com/fzn0x/core-banking-system) | `770860d4a11f1d203b0369456d867108097a550f` | MIT | A simplified core banking demonstration | 2 |
| [ibmdbbdev/Samples](https://github.com/ibmdbbdev/Samples) | `61a1a20f495203bdb16d4c74a5a076f4fbfc379b` | Apache-2.0 | IBM samples: a mortgage payment program and 11 very small programs | 12 |

No source file from these repositories is committed. Published patches can reproduce short excerpts under the licences above.
Any person's name in a published excerpt is replaced with `[name]`. Excerpts from `navikt/DSF`: Copyright 2010 NAV (Arbeids- og velferdsdirektoratet), MIT licence, see `LICENSE.md` at the pinned commit. The excerpt from `ibmdbbdev/Samples` is under Apache-2.0.

## How they were chosen, and what that means

Permissively licensed public COBOL repositories were listed from GitHub search, and 12 were run through the analyzer, with no model
call, on Nov 3: the three above, plus `etalab/taxe-fonciere`, `shamrice/COBOL-Examples`, `harshiljethava/IBM-mainframe`,
`dinodev76/GC-Examples`, `IBM/zopeneditor-sample`, `Astalaseven/cobol`, `continuous-copilot/modernize-legacy-cobol-app`,
`avishek-sen-gupta/cobol-rekt` and `IBM/Bank-of-Z`. Seven had no program Diocle can test, mostly because they write no output file,
read the console or use CICS. That is itself a limit of the product. `dinodev76/GC-Examples` had one such program, and
`avishek-sen-gupta/cobol-rekt` had toy control-flow test programs, so neither was used.

So these three were **chosen because the analyzer can test some of their programs**, which favours Diocle. The author also read
program headers and the analyzer's plan while choosing. "Blind" means only this: no fix or tuning was made in response to these
repositories, before or during the run.

## Protocol

- **Every program is accounted for,** as certified, certified against repaired COBOL, not certified, refused with its reason, not
  converted, or not run. Each repository is reported on its own, and the 11 very small IBM programs are never counted as evidence of
  anything beyond themselves.
- **Settings.** Diocle at the commit recorded in each results file, Muse Spark, `--breaker --no-memory --convert-anyway`, normal caps
  (60 calls a run, 20 a round, 3 rounds), $0.40 per program, one run per program. `--convert-anyway` patches only an original that
  does not compile, and that result is labelled certified against repaired COBOL, never plain certified.
- **Where it runs.** Every build and run of these programs happens in Diocle's sandbox container (image built from the commit that pinned these repositories: GnuCOBOL 3.2.0, OpenJDK 21), the same design as the live engine: no secrets, no shared files, a read-only filesystem and no route to the internet. The Mac holds the model key and only runs `javac -proc:none` on model-written Java, which compiles it and runs nothing. The `cobc` and `java` versions in the results header are the Mac's; `ranIn` states the sandbox's.
- **Fresh seeds.** 9001 to 9005 on every certified program.
- **What a certification rests on, measured before the run.** On DSF, these programs read two input files, so the breaker cannot
  attack them. A new seed changes 25 of 33 input fields on `FO04D101`, 6 of 10 on `LIST1X`, 3 of 9 on `TELL-TRANS` and 1 of 7 on
  `LISTMRK`. `REPORT-GEN` varies 2 of 4 fields and `INIT-DB` has no input. The IBM programs have fixed input. Results must keep this split.
- **Ceiling $2.00, approved by the owner:** $0.90 for DSF, $0.50 for core-banking-system, $0.60 for the IBM samples. A program the
  ceiling leaves no room for is reported as `not run`.
- **No tuning.** No product change, re-run or changed setting in response to a result. A resume is allowed only after a provider
  failure, and is reported. A later fix would need a separately labelled pass.
- **Run:** with `DIOCLE_SANDBOX_URL` pointing at that container, `eval/run_external_estate.py --blind <repository> --max-total-usd <ceiling>`. Results go to `eval/results-blind-*.json`,
  and the runner refuses to overwrite one.

## What it cannot show

GnuCOBOL is not IBM Enterprise COBOL, and generated inputs are not the real pension register or real production data. A certification
here does not show these programs were modernized, only that the Java matched on the inputs tried. Three small repositories do not
show that Diocle works on any repository.

## Results

All three ran to the end on Nov 3 to 4, with no resume or restart, for **$0.29** of estimated model spend (rounded) under the $2.00 ceiling, at Diocle commit `e10d003`. Raw records: [`results-blind-navikt-dsf.json`](../eval/results-blind-navikt-dsf.json), [`results-blind-fzn0x-core-banking-system.json`](../eval/results-blind-fzn0x-core-banking-system.json), [`results-blind-ibmdbbdev-samples.json`](../eval/results-blind-ibmdbbdev-samples.json). One person's name in a published patch was replaced with `[name]`, as the protocol says. The Mac slept for about 12 minutes during `REPORT-GEN`, so its time includes that.

| Repository | COBOL sources | Certified with the COBOL as distributed | Not certified | Original could not be patched to compile | Refused | Not converted | Cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| `navikt/DSF` | 7 | 2 | 1 | 1 | 2 | 1 | $0.143 |
| `fzn0x/core-banking-system` | 4 | 0 | 2 | 0 | 2 | 0 | $0.090 |
| `ibmdbbdev/Samples` | 17 | 11 (very small) | 0 | 1 | 5 | 0 | $0.055 |

No result is merged across these repositories into one number. No program here was certified against a repaired copy.

### navikt/DSF

| Program | Result | Inputs a new seed changes | Each of 5 fresh seeds | Model calls | Cost |
|---|---|---:|---:|---:|---:|
| `LISTMRK` | **certified as distributed** | 1 of 7 fields | passed, about 12,000 output records compared, from about 1,000 input records | 12 | $0.027 |
| `LIST1X` | **certified as distributed** | 6 of 10 fields | passed, about 12,000 output records compared, from about 1,000 input records | 22 | $0.059 |
| `FO04D101` | not certified | 25 of 33 fields | not reached | 60 | $0.049 |
| `TELL-TRANS` (`PLUKKFR`) | original could not be patched to compile | | not reached | 9 | $0.007 |
| `FO04F1X1`, `R001BYDL` | refused: they CALL programs not in the repository | | | | |
| `TELL-TRANS` (`PLUKKFRN`) | not converted: another source holds this PROGRAM-ID | | | | |

- **`LISTMRK` and `LIST1X`** are small programs, about 100 and 135 lines, and both use `WRITE ... AFTER ADVANCING`, the construct the course's fix addressed, in code that fix never saw. They matched the original on the inputs tried, and their guard reviews passed. They read two input files, so the breaker could not attack them, and `LISTMRK`'s test is narrow. The first Java differed on 694 of 2,444 and 787 of 2,512 output records, and the repair agent fixed that in one round.
- **`FO04D101`, the largest, did not certify.** Its original also needed a two-line model patch to compile (`NULL` as a paragraph name). It reads its parameter with `ACCEPT`, and the verifier closes standard input, so the parameter was blank. In the final check the patched original printed the blank parameter and `PARAM ER GALT` and stopped without writing a record, so the generated files, including the 25 varied fields, were never read. The Java printed that text in EBCDIC bytes, but that is not why it failed: no certification round compared any output record, including round 2, when stdout matched.

### fzn0x/core-banking-system

Neither testable program certified, and neither reached a useful comparison. On `INIT-DB`, both sides printed `Database initialized.`, but the verifier saw 0 output records from each in the final check, so nothing was compared. The source assigns its file to the literal name `ACCOUNTS.DAT`, the likely reason. The guard refused two earlier versions of the Java for how they read environment variables, but not the final one. On `REPORT-GEN`, the original stopped with exit code 1 in the final check because GnuCOBOL could not find `ACCOUNTS.DAT` (status 35), so the generated input never reached it. It printed nothing and wrote no output file, so there was nothing to compare. These are gaps in how Diocle handled these programs and their inputs. They say nothing about whether the programs are correct.

### ibmdbbdev/Samples

The 11 certifications are `HELLO` and programs of about 6 lines, on fixed input. They show the pipeline ran and nothing more. `EPSMPMT`, IBM's 154-line mortgage payment example and the only larger testable program here, could not be patched to compile.

### What this shows, and what it does not

- **Shown:** on COBOL sources from the repository of a retired national pension system, in code the course's fix never saw, 2 of the 4 programs Diocle could test certified with no patch to the COBOL, after the repair agent fixed the first Java, and 2 did not. The sandbox ran every program.
- **Not shown:** that Diocle works on any repository. `fzn0x/core-banking-system` certified none, and `ibmdbbdev/Samples` only its very small programs. The inputs are generated, not real pension records. GnuCOBOL is not IBM Enterprise COBOL. The role these programs played in the pension system, including whether they ran in production, is not established, most of that system is PL/I, and nobody at NAV was involved.
- **Selection:** these repositories were chosen because the analyzer could test some of their programs, and 7 of the 12 checked had nothing it could test.
- **No fix was made** in response to these results.
