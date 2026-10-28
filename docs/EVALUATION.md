# Frozen evaluation on unseen programs

> All programs are **synthetic**, written for this project. Raw results: [`eval/results-eval-freeze-1.json`](../eval/results-eval-freeze-1.json).

## Protocol
- The implementation was frozen at git tag **`eval-freeze-1`** (commit `3eaad85`, Oct 28 19:37 IST). Four COBOL
  programs were then written and committed before any model run (`eval/unseen/`); `eval/samples/` is what the
  analyzer derived from them, unchanged. Nothing in Diocle was tuned to them.
- Each program: `diocle_converter run <sample> --breaker` (translate from scratch, repair agent, held-out
  certification on 1,000 inputs, then the breaker agent). Model **`muse-spark-1.3-contributor`** (Meta Muse Spark,
  hosted). Fix memory **on** (8 to 9 lessons from earlier, different programs). Caps: 60 model calls, 3 rounds.
- Certified programs were then re-verified on five fresh seeds (9001 to 9005), 1,000 random inputs each.
- `eval/run_eval.py` runs the whole protocol; it changes nothing in the product.

## Results as recorded (verifier at `eval-freeze-1`)

| Program | Shape | Certified | Repair rounds | Model calls | Est. cost | Breaker | Fresh seeds |
|---|---|---|---|---|---|---|---|
| FXCONV | one record per input | **yes** | 0 | 4 | $0.023 | 36 attacks, 0 broke | 5/5 pass |
| CHQCLR | one record per input, REDEFINES | **yes** | 1 | 9 | $0.018 | 24 attacks, **2 broke**, repaired | 5/5 pass |
| BRNCHSUM | aggregates many inputs into one record per branch | no | 3 | 60 (cap) | $0.164 | not run | n/a |
| LOANAMRT | writes several schedule records per loan | no | 3 | 60 (cap) | $0.101 | not run | n/a |

**2 of 4 certified, for about $0.31 in total.**

CHQCLR is the clearest case for the breaker: the Java had passed 1,000 held-out inputs, then two designed records
broke it (fee 20.00 vs 0.00; debit -121.23 vs 0.00). The repair agent fixed both and the program re-certified.
Both records carry malformed numeric content (a leading space; letters in a numeric field), so this shows the
Java now agrees with **GnuCOBOL's** handling of bad data, not that it matches IBM Enterprise COBOL.

## Why BRNCHSUM and LOANAMRT failed: the verifier, not the model

An independent review found that the comparator at `eval-freeze-1` paired output records with *inputs*. A program
that aggregates (BRNCHSUM) or fans out (LOANAMRT) writes a different number of records than it reads, so correct
output was reported as "extra output record" or "no original output record". The same review found that numeric
fields were compared by value, so `+00` and `-00` counted as equal.

The comparator now compares the whole output sequence by position, byte for byte (commit `d08064e`). Checking the
**final Java each run left behind** with the corrected comparator, on fresh seeds, no model involved:

| Program | Seed 9001 | Seed 9002 | stdout | exit code |
|---|---|---|---|---|
| BRNCHSUM | 759/759 records | 746/746 | match | match |
| LOANAMRT | 1,698/1,698 | 1,718/1,718 | match | match |
| CHQCLR | 1,004/1,004 | 1,004/1,004 | match | match |
| FXCONV | 1,016/1,016 | 1,016/1,016 | match | match |

So all four final conversions agree with the original on fresh inputs. This is **not** a substitute for a re-run:
during the frozen run the repair agent was steered by wrong feedback for BRNCHSUM and LOANAMRT and spent its
whole budget, and no held-out certification or breaker ran on them under the corrected comparator. A full
re-run with the corrected verifier (new tag) is the follow-up and will be reported here next to these results,
which stay as recorded.

The stricter byte comparison also found a real defect in earlier work: the INTACCR delivered in
[quillmark-modern#3](https://github.com/Nivetha200111/quillmark-modern/pull/3) writes `-000000000` where the COBOL
writes `+000000000` on about 3% of inputs. See the README's correction.

## Limits
- Four programs, all synthetic and written by the same author as the tool; batch, file-in/file-out only.
- The oracle is GnuCOBOL 3.2 with IBM-like settings, not IBM Enterprise COBOL on z/OS. No real mainframe output
  has been compared (golden-file replay exists but has only synthetic golden files).
- Fix memory was on, so results depend on lessons from earlier programs; a memory-off run is not reported.
- "Certified" means agreement on the inputs tried (boundary, random, fixture, designed), not on all inputs.
