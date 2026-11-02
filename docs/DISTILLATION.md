# Verified distillation: Muse Spark Open to Muse Glimmer

> **Status: dataset built, tuning blocked, nothing evaluated (Nov 2, 2026).** The host refuses dataset uploads on this account, so no tuned model exists. See "Results".
> The plan below was written and committed before any model call. Results are appended at the end and nothing above "Results" changes after the first call, except a dated entry under "Deviations".
> All programs are **synthetic**. This is a small experiment, not a benchmark of general COBOL.

**Built with Muse Spark Open.** The tuned model described here is a Derivative under the Muse Model License: it is trained on outputs of Muse Spark Open. It is not part of the default product path.

## The question

Can a small open-weights model learn COBOL-to-Java translation from a large one, when every training example has first been checked against the original program by GnuCOBOL? We measure one thing: does tuning change how often Muse Glimmer's first translation matches the COBOL?

## What is teacher, what is student

| Part | Choice | Why |
|---|---|---|
| Teacher | Muse Spark Open on Fireworks (`OPEN_MODEL_*`) | The Muse Model License grants the right to fine-tune and distill, and says Meta claims no ownership of outputs |
| Student | Muse Glimmer 30B (`accounts/fireworks/models/muse-glimmer-30b`), LoRA | Apache 2.0, open weights. Its training is on a partner host; a 24 GB Mac has no documented training path |
| Not used | Hosted Muse Spark outputs | Section 10.1(ix) of the Meta Model API terms restricts using Outputs to train or distill models that compete with Meta's, and restricts collecting Outputs to build such training sets. Every stored certified run except the private-mode ones is hosted output, so **none of them is training data**. The code refuses an example if any call behind it was not Muse Spark Open |

## The gates: what may become a training example

Programs come from two places: the repository's synthetic samples plus the three Quarrystone Valley programs (without embedded SQL or keyed files, whose prompts and drivers differ), and new synthetic programs written by the teacher to a fixed list of topics. A program must pass every gate. The report counts what each gate rejects.

1. **It builds and the analyzer accepts it.** A generated program that the analyzer refuses is dropped, and so is one that touches any file but INFILE and OUTFILE or uses CALL, ACCEPT or EXEC: it is compiled and run on the owner's machine.
2. **The oracle can see it.** An input record of one flat `PIC X(n)` field is refused: generated inputs for it do not vary, so a pass means little ([DETAILS.md](DETAILS.md)). This excludes the Harbor Trust estate, which is also near-duplicate (shingle similarity up to 0.97 between its programs).
3. **It is not a cousin of a held-out program.** Shingle similarity against each held-out program must stay below 0.30. Generated programs must also stay below 0.60 against each other.
4. **The teacher's Java passes.** First translation only, no repair, no memory, policy gate first, then 1,000 generated inputs on seed 7701: same exit code, every output record and stdout equal, at least 100 records compared.

Passing these gates does not prove a translation correct. Generated inputs are well-formed, and the breaker is not run on training examples.

## Held out

**BRNCHSUM, CHQCLR, FXCONV, LOANAMRT** (`eval/samples/`). These are the four frozen programs of [EVALUATION.md](EVALUATION.md) and the "unseen" group of [MEASUREMENT.md](MEASUREMENT.md). They appear in no training or validation line, and the dataset step fails if one does. The teacher is not run on them.

## Training

One Fireworks supervised fine-tuning job: LoRA rank 8 (the host's default), host's default learning rate, 3 epochs. The prompt in every line is built by the same function the translator uses, so training and serving prompts cannot drift. The target is the translator's JSON answer. Reasoning traces are not included. No second job is run after the evaluation has been seen.

## Evaluation

Base Muse Glimmer and tuned Muse Glimmer run on **one** Fireworks deployment with the adapter loaded as an add-on, so the two differ only by the adapter.

- Same harness as MEASUREMENT.md: 3 first translations per held-out program per model, no repair, no breaker, no memory, 1,000 held-out inputs on seed 8801, same pass rule. The Java safety policy runs before each build.
- Primary number: attempts passed out of 12, base vs tuned.
- Also reported: programs with at least one pass, attempts that compile, and failures by kind.
- Every attempt is reported. An attempt lost to infrastructure gets one re-run and is logged.

With 12 attempts per model on 4 programs, a small gap is noise. We will state the numbers and will not claim an improvement unless tuned passes at least 3 more attempts than base. Even then it is an observation on four programs.

The Muse Spark figures in MEASUREMENT.md are context only: same harness, different date and a different model tier.

## Caps (rule 10)

| Cap | Value |
|---|---|
| Teacher spend, whole harvest | $8.00, no new unit past $7.00 |
| Teacher spend per program | $0.25 |
| Generated programs | 60 (raised to 120, see Deviations) |
| Training tokens | 3,000,000 (at the host's $3 per 1M managed rate, at most $9 if the free offer does not apply) |
| Deployment | Needs the owner's OK with a stated dollar limit, wall-clock limit enforced by the script, deleted when the script ends, scale-to-zero after 5 minutes as a backstop |

## Stated limits

- The dataset is small. Meta's post-training guide suggests roughly 500 or more examples.
- Fireworks trains the student, and the tuned model runs only on a paid dedicated deployment. It is not on the public site, and no public button uses it.
- Trained on low reasoning effort outputs with no reasoning traces, so it learns answers, not reasoning.
- Nothing here says that a tuned model is safe to use unverified. Its Java goes through the same differential test as any other.

## Deviations

- **Nov 2, after a three-unit pilot and before the harvest ($0.028, one program passed, two generated programs refused).** The refusals came from the gates, not the teacher: the analyzer does not read the valid quoted form `COPY "X".`, so the generator's prompt now asks for the unquoted form; the CALL check also matched data names, and no longer does. The analyzer is unchanged. The pilot cost a translation about $0.013 rather than the estimate of about $0.10, so the generated-program cap went from 60 to 120 (every distinct topic pair), to get closer to Meta's suggested dataset size. The dollar caps did not change. The pilot's two generated units are dropped from the gate counts and their cost stays in the spend.
- **Nov 2, after the first harvest ($2.72, 13 examples: 4 repository, 9 generated) and before any training.** 89 of the 105 refused generated programs that could be checked did not compile with `cobc`, nearly all from the generator's prompt: 52 had a wrapper 01 above a COPY whose copybook already has one, 23 a column-7 error, and its packed-decimal topic asked for packed data in LINE SEQUENTIAL files, which the analyzer rightly refuses. So: a stricter prompt, a free `cobc` syntax check before a translation is paid for (new gate `does-not-compile`), and one chance for the teacher to fix its own compile errors. A second pass retries only generated programs whose Java never met a real comparison. **A program whose Java differed on real records stays rejected, and the oracle is unchanged.** First-pass counts stay in the report as `firstPassRejected`. The dollar caps did not change.
- **Nov 2, after a reviewer pass, before any tuning or evaluation.** Fixes to code that had not yet been used on a paid deployment: a host error now counts as lost to the host, not as a failed translation (a 404 from an adapter not yet loaded would have read as tuned 0 of 12); both models must answer one small call before any attempt starts; `--approve-usd` now covers every run of the evaluation, not each one; a run that ended uncleanly stops a resume until checked; the deployment is deleted on more exit paths; the account name is removed from logs and refused in result files; the COBOL containment check now also reads copybooks. None of this changes a training example, and the dataset hash is unchanged.
- **Corrections to what the plan says.**
  - The context line under "Evaluation" is too loose. MEASUREMENT.md used hosted `muse-spark-1.3-contributor` at medium effort; this evaluation is a different model family on a different host at low effort, so it is **not a baseline** here.
  - The $8.00 and $0.25 caps are checked before each unit or call, so units in flight could pass them. Actual spend stayed inside both: $5.75 in total, and the dearest unit cost $0.044.
  - The 0.60 similarity gate compared only finished programs, so programs in flight were not compared. Afterwards, the closest pair among all 97 stored sources was 0.165.
  - The weak-oracle gate did not recognise the analyzer's `io` direction, so LEDGER-REWRITE (5 fields) was wrongly refused. That is the report's single `weak-oracle`. It is fixed for any later harvest, and this one was not re-run.
  - The student model ID is pinned in `eval/distill_glimmer.py` as the plan's choice, with an environment override, as `eval/headline.py` does.
- **Who decided what.** The owner asked for this work on Nov 2 and lifted the feature lock for it. Raising the generated cap to 120 and running the second pass were this session's decisions, reported to the owner, inside the same dollar caps.

## Results

Reported as they stand on Nov 2, 2026. **No model has been tuned and nothing has been evaluated.**

**Harvest ([results](../eval/results-distillation.json), [data](../eval/distill/harvest.json)).** 134 programs went in and **31 became training examples** (4 from the repository, 27 generated). All 133 units that made a model call used Muse Spark Open. Estimated teacher spend: **$5.75** at list prices, of which $2.07 went on the pilot and on first-pass units later retried.

| Outcome | Programs |
|---|---:|
| Passed, in the dataset | 31 |
| Java differed from the COBOL, or the differential test could not complete | 75 |
| Did not compile after one self-fix | 14 |
| Refused by the analyzer or the containment check | 9 |
| Java refused by the safety policy | 3 |
| Flat record (wrongly, see Deviations) | 1 |
| Too few records compared | 1 |

The first pass alone gave 13 examples for $2.72. A low pass rate is expected here: these are first translations at low reasoning effort with no repair, and the gates keep only what passes. This does not measure Muse Spark Open's quality as a translator.

**Dataset ([train.jsonl](../eval/distill/train.jsonl)).** 31 examples, about 200,000 tokens by a rough estimate (601,000 over three epochs), SHA-256 `f565c9197019ce66ac5d3875bd48f65295af29a822495e5e4a5241c5f8f7398c`. The leak check passed against the four held-out programs. This is far below the roughly 500 examples Meta suggests.

**Training: blocked.** Fireworks answers `dataset uploads are temporarily disabled, please contact Fireworks AI to get access` ([record](../eval/distill/training.json)). We do not know whether this is an outage or a limit on this account.

**Evaluation: not run.**
