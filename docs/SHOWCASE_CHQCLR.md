# One run end to end: CHQCLR, and an audit of the evidence behind it

CHQCLR is a synthetic cheque-clearing batch program: cheques debit, returns reverse and charge a fee, and an insufficient-funds (NSF) return's fee is doubled. It is the program the site and the video lead with. This page says what happened, what can be reproduced today, and what is weaker than the headline suggests. Audit: `eval/audit_chqclr.py` (no model call); results: `eval/results-chqclr-audit-20261101.json`; every stored Java is in `eval/showcase/`.

## The story, from run `chqclr-20261028-214355` (stored; Muse Spark `muse-spark-1.3-contributor`, fix memory on, 9 calls, $0.0176 at list prices)

| Step | What happened | Decided by | Can you re-run it? |
|---|---|---|---|
| 1. Original | `CHQCLR.cbl` compiled with GnuCOBOL 3.2 (IBM TRUNC(STD) and DISPLAY defaults, EBCDIC order). sha256 `09f098c7...` | Compiler | Yes |
| 2. Java passes the ordinary check | Muse Spark translated it. One run of each program on a generated file: 204 of 204 output records, then held-out seed 4242: 1,004 of 1,004. **Weak for this program, see below** | Byte comparison | The first Java was **not stored**, so no; the counts are in the run's events |
| 3. The breaking input | Muse Spark as breaker designed `RACCT00000200000008NS 1000YYYYYYYYYYYYYY`: a return, reason `NS`, fee ` 1000`, a space where `PIC 9(3)V99` expects a digit. Its reason: "Fee with leading space is zero in Java but may be nonzero in COBOL." Output: **COBOL `CL-FEE` 20.00, Java 0.00.** A second input, letters in an amount (`+0000AB123`): COBOL `-121.23`, Java `0.00`. These were 2 of the 10 inputs in the first attack round. The run record's "24" counts every attack input including replays; 22 are distinct | Byte comparison | COBOL side: yes. Java side: the stored difference only, as above |
| 4. The repair | Certification withdrawn. The repair agent read the COBOL, patched the two number parsers to read digits by low nibble as GnuCOBOL does, compiled and re-tested | Muse Spark proposes; comparison checks | The repaired Java is checked in |
| 5. Re-verification | Fresh held-out seed 4243: 1,006 of 1,006 output records (1,000 random, 4 boundary, the 2 breaks), then a new attack of 12 inputs: none differed. Certified | Byte comparison | Similar, not identical: Try the sample uses new records and, after the engine deploy, the fixed generator |
| 6. Evidence | Run record, events, breaker attempts, verification reports, Java, provenance. Copies of the Java and attempts: `eval/showcase/chqclr-20261028-214355/` | | `python eval/audit_chqclr.py` |

**What this does and does not show.** The record is **malformed**, not an ordinary transaction. Why it matters: in this one record the original charges a fee and the Java silently charges none, and a generated well-formed record could never show that. What it does not show: which is right, or what IBM Enterprise COBOL does (it may treat this differently or stop). The Java now agrees with GnuCOBOL's handling of bad data; that is all.

## What the audit found

**1. The stored breaks reproduce.** On the original and the repaired Java today, both records produce the same bytes as each other, and the original's output is the one stored (`20.00`; `-121.23`).

**2. "Passed 1,004" was weak here.** The record is a type byte plus a 39-byte body shared by two REDEFINES views, and the generator filled the body with a placeholder. Those records had zero amounts and fees: 204 and 1,004 generated records gave 3 distinct output records (the 1,006-record file 5, the extra two being the breaker's). A Java that never charged an NSF fee would have passed. CHQCLR was the only program among the 15 with a body like this. **Fixed** in `services/verifier/diocle_verifier/inputs.py`, with a test that plants exactly that Java. Stored counts are unchanged and are labelled on the run page. **Not fixed:** a flat text record gets the same kind of placeholder, which is what the [Harbor delivery](../README.md#not-supported-yet) mostly got.

**3. On real values, six of seven stored Javas hold, and the seventh shows why this matters.** On 1,000 valid records (seed 20261101: 478 cheques, 428 returns, 94 other type bytes; 473 non-zero debits, 339 non-zero fees): six stored Javas matched, including the **not-certified** Oct 30 run's. The seventh, `chqclr-20261101-142844` (Muse Spark Open, private mode, not certified), writes the same records but prints a wrong total: `NET= -88298037.41` vs the COBOL's `-88199037.41`. On a single valid return, `NS60000`: COBOL `-200.00`, Java `-1200.00`, because the Java does not truncate the doubled fee in its running total. The old placeholder records could not show that. Its breaker tried `NS60000` and recorded no break, because until Nov 1 **the attack compared output records only, not display output**. That is fixed too (`services/converter/diocle_converter/breaker.py`), and it means "survived" in stored runs is about output records. With the fixed generator, the showcased Java matched on five seeds: 1,004 of 1,004.

**4. The certified Java still differs on a record nobody attacked with.** `R` plus 39 spaces, a return with a blank body. COBOL writes the fee as spaces (`MOVE` between identical fields), the Java as `00000`. The record is malformed. Found while chasing a generic note in the live mutation report that this Java disagreed on one of its extra inputs. Not fixed: this is what "certified on the inputs tried" means, and re-running the model for a nicer story is not the point.

**5. What stored breaks are.** 54 distinct counterexamples across every run folder on the author's machine and the public run list ([list](../eval/results-stored-breaks-20261101.json)): 30 malformed numeric fields, 15 negative zero at an overflow boundary (same value, different bytes), 9 from one round where the Java wrote no records, so no record is shown responsible. None shows a wrong amount on a well-formed record, partly because of finding 3's flaw. Value errors on well-formed records do happen (INTACCR's first Java wrote balance `369589314.78` where COBOL wrote `9589314.78`), and the ordinary checks catch those when their records reach them.

## CHQCLR across runs: certified or not depends on the run

| Run | Settings | Breaker: differed / tried (all malformed) | Result |
|---|---|---|---|
| `chqclr-20261028-214355` (frozen evaluation, live) | Fix memory on, 8 earlier lessons | 2 / 24 | Certified after one repair cycle |
| `chqclr-20261028-234854` (`eval-freeze-2`) | Fix memory off | 6 / 28 | Certified after one repair cycle |
| `chqclr-20261030-163002` (controlled measurement) | Fix memory off, policy-only guard, default caps | 12 / 24 | **Not certified**: one repair cycle did not fix it within the caps |
| `chqclr-20261101-004628` (the six-agent replay in the video) | Fix memory on, 10 lessons; cross-check and guard review on | 3 / 22 | Certified |
| `chqclr-20261101-002207` | Fix memory on, 0 lessons used | 13 / 30, 9 of them a round with no Java output | **Not certified** |
| `chqclr-20261101-142844` | Private mode: Muse Spark Open in every role, fix memory off | 2 / 14 | **Not certified** |
| `chqclr-20261101-162541` | Fix memory off; cross-check (12 inputs, 0 differed) and guard review on | 0 / 13 | Certified |

Four of seven certified. We did not isolate which setting mattered, and each run's breaker designed different inputs; seven runs of one program do not make a rate. Only `chqclr-20261028-214355` is on the public run list; the others are local folders, and all seven Javas are checked in. "Tried" counts attack inputs including replays.

## The mutation report, read properly (live report: 14 of 35 detected, 21 survived, 5 did not compile)

The score looked low. Re-testing the same 40 seeded faults on other inputs (`--mutants`, no model):

| Input set | Faults detected of 35 |
|---|---|
| The stored run's generated records (placeholder bodies) | 14 |
| The fixed generator, 1,000 records | 20 |
| 1,000 well-formed records (audit) | 21 |
| The stored breaker's 22 designed records | 22 |
| 11 cheques of the largest amount (9-digit total) | 17 |
| 120 cheques of the largest amount (total overflows) | 18 |
| One small cheque (single-digit total) | 19 |
| **Any of the above** | **26** |

The sets overlap, and the last three are tiny and were aimed at survivors after seeing them, so read the "any" as a floor for what is reachable, not as what a certification run detects. Two faults were caught only by the old placeholder records (`m033`, `m034`, the path for a net total of exactly zero): the fixed generator does not reach that path by chance, so it is not simply better in every respect.

**The 9 no set detected, in three groups:**

| Faults | What they change | Why nothing noticed |
|---|---|---|
| `m001`, `m010`, `m014` | The scale of a `BigDecimal` zero | Value-preserving here: later arithmetic and truncation normalise it |
| `m024`, `m028`, `m029` | The rounding mode in `setScale(decD, ...)` | No rounding happens: parsed values already have that scale |
| `m004`, `m005`, `m009` | The reader's line-sequential fallback and its partial-last-record branch | Not reached by whole fixed-length files, which is what the verifier writes for this program |

Reachable but not caught by a normal check: `m026` (dropping the running total's overflow needs a total past 9 integer digits, about 101 maximum-size cheques) and `m038` (a total with one integer digit). Those are real coverage gaps of the generated records, not defects found in the Java.

The grouping of the 9 is by reading the code, not a proof, and the denominator is unchanged: 35 compiled, none removed. It is not a confidence score. The operator set is a sample of realistic faults, and five mutants that did not compile are artefacts of the tool (for example `equalsIgnoreCase` on a `BigInteger`).

## Why adversarial inputs, in this light

The honest argument is narrower than "AI code is wrong" and more useful: a generated test only reaches inputs its generator can produce. Here it could not produce dirty fields or, by chance, exact overflow boundaries, and for one record shape it did not even produce real numbers. A model reading the COBOL designed inputs in those places, and a deterministic comparison judged each. That found differences a large generated test did not, on 4 of 10 attackable translations in the measurement. It did not find everything: see findings 3 and 4.
