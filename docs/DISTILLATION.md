# Verified distillation: Muse Spark Open to Muse Glimmer

> **Status: PLAN, written and committed before any model call.** Results are appended at the end and nothing above "Results" changes after the first call, except a dated entry under "Deviations".
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
| Generated programs | 60 |
| Training tokens | 3,000,000 (at the host's $3 per 1M managed rate, at most $9 if the free offer does not apply) |
| Deployment | Needs the owner's OK with a stated dollar limit, wall-clock limit enforced by the script, deleted when the script ends, scale-to-zero after 5 minutes as a backstop |

## Stated limits

- The dataset is small. Meta's post-training guide suggests roughly 500 or more examples.
- Fireworks trains the student, and the tuned model runs only on a paid dedicated deployment. It is not on the public site, and no public button uses it.
- Trained on low reasoning effort outputs with no reasoning traces, so it learns answers, not reasoning.
- Nothing here says that a tuned model is safe to use unverified. Its Java goes through the same differential test as any other.

## Deviations

None yet.

## Results

Not run yet.
