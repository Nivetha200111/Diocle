# Meta vs Meta: three models attack the same Java

> **Status Nov 4, 2026: run once. [Results](#results) are below.**
>
> **When pinned: PROTOCOL PINNED Nov 4, 2026, before any model call of this test.** Results will be added below and published whatever they show.

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

All 30 attacks ran on Nov 4, with no provider failure, for **$5.48** of estimated model spend under the $10 ceiling, at Diocle commit `a3b4e1c`. Raw record, including up to 12 breaking inputs per attack: [`results-meta-tournament.json`](../eval/results-meta-tournament.json). One attack per model per program, so this is not a ranking.

| Attacker | Programs broken, of 10 | Inputs tried | Inputs that broke the Java | Cost |
|---|---:|---:|---:|---:|
| Muse Spark | 4 | 164 | 11 | $0.11 |
| Muse Spark Open | 2 | 234 | 5 | $1.18 |
| Muse Wonder | 5 | 208 | 11 | $4.20 |

| Program | Muse Spark | Muse Spark Open | Muse Wonder | Output fields that differed |
|---|---|---|---|---|
| `CHQCLR` | broke | broke | broke | `CL-FEE` (all three); `CL-DEBIT` (Muse Spark Open only) |
| `DAYCTRL` | broke | broke | broke | `CTL-INTEREST` |
| `INTACCR` | broke | | broke | `OUT-INTEREST` |
| `TXNPOST` | broke | | broke | `POST-NEW-BAL` |
| `PKDPOST` | | | **broke** | `PO-INT` (Muse Wonder only) |
| `FXCONV`, `LOANAMRT`, `FEESCHD`, `FEEPOST`, `LOYWAIVE` | | | | none |

### What this shows

- **The models did not find only the same things.** Muse Wonder alone broke `PKDPOST`, which Muse Spark did not break here or in either earlier measurement. Muse Spark Open alone reached `CL-DEBIT` on `CHQCLR`, by putting a letter in an amount (`original 101.00`, `converted 1.00`).
- **Muse Spark found 4 of Muse Wonder's 5 programs at about 1/40 of the cost.** On these programs, the dearest attacker added one program, and Muse Spark was the cheapest way to find most breaks.
- **Muse Spark Open broke the fewest here,** yet it is the one that reached a different field. This is one attack per program.

### Read these with care

- **The breaks are on malformed numbers or the sign of a zero,** as in the earlier measurements. `PKDPOST`'s is the sign of a zero (`-10000000.00` overflowing, same value, different bytes). `CL-DEBIT` and the other `CHQCLR` breaks are malformed records. None is a wrong amount on a well-formed record. `CHQCLR`'s `original 410.00`, `converted 50.00` is also on a malformed fee.
- **Five programs stayed unbroken by all three.** That does not show they are correct, only that these inputs did not differ.
- **An attack stops at its first breaking round,** so inputs tried are not like for like. Attacks that designed few valid inputs, such as `PKDPOST` (3 to 5), had little to work with.
- **Costs use list prices, and Muse Wonder's price is third-party and unconfirmed.**
- **No winner is claimed,** and nothing here measures translation.
