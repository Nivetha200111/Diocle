# Meta vs Meta: three models attack the same Java

> **Status: PROTOCOL PINNED Nov 4, 2026, before any model call of this test.** Results will be added below and published whatever they show.

## The question

Do Meta's models find different breaks in the same AI-written Java? Each attacker designs inputs from the COBOL and the Java. GnuCOBOL and the JVM run both programs on those inputs, and only that comparison decides whether an input broke the Java. No model judges another.

## Setup

- **Attackers:** Muse Spark (`muse-spark-1.3-contributor`, Meta Model API), Muse Spark Open (`accounts/fireworks/models/muse-spark-open`, Fireworks) and Muse Wonder (`muse-wonder-1.0`, Meta Model API). They use the same breaker prompt and schema, at most 3 rounds of up to 12 inputs, and stop at the first round that breaks the Java.
- **The Java is fixed:** `eval/attack-rerun-java/`, written by Muse Spark on Nov 2, on the 10 synthetic programs the re-measurement could attack: `CHQCLR`, `FXCONV`, `LOANAMRT`, `INTACCR`, `TXNPOST`, `FEESCHD`, `FEEPOST`, `DAYCTRL`, `PKDPOST`, `LOYWAIVE`. A free check on Nov 4 (seed 8803) found all 10 still pass 1,000 generated records.
- **One attack** per attacker per program, with no repair and no tuning. A provider failure is recorded as not run. It is not a result about the Java.
- **Ceiling $10.00, approved by the owner.** Hard cap per attack: $0.10 Muse Spark, $0.60 Muse Spark Open, $1.40 Muse Wonder. The cheapest attacker goes first, so the ceiling can only cut the dearest. An attack the ceiling leaves no room for is reported as `not run`.
- **Run:** `eval/meta_tournament.py --max-total-usd 10 --workers 4`. Results: `eval/results-meta-tournament.json`, never overwritten. Reported per program and per attacker: inputs tried, inputs that broke the Java, the output fields that differed, cost, and which programs only one model broke.

## What it cannot show

- **No winner is claimed.** One attack per model on 10 synthetic programs cannot rank models. Each is non-deterministic, and a model that stops at its first break tries fewer inputs.
- **Not blind for Muse Spark:** four of these programs are already known to break under it (`CHQCLR`, `DAYCTRL`, `INTACCR`, `TXNPOST`), and Muse Spark wrote the Java.
- **Field counts are coarse.** A shared field does not prove the same bug, and different fields do not prove different bugs.
- **A break is a byte difference under GnuCOBOL,** not a claim about IBM's compiler or a wrong amount on a well-formed record, unless a result says so.
- Muse Spark Open runs on partner inference, not hardware we control.

## Results

_Not run yet._
