# Blind test on repositories the fix never saw

> **Status: PROTOCOL PINNED Nov 3, 2026, before any model call against these repositories.** Results will be added below and in
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
Any person's name in a published excerpt is replaced with `[name]`.

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

_Not run yet._
