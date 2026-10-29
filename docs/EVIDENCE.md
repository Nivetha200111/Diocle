# Evidence

Everything a judge needs to check Diocle's claims, with links to the raw records. All repositories are the
project's own synthetic estate (Quillmark Trust & Savings is fictional); no client or employer code anywhere.
Model in every run below: **Meta Muse Spark** (`muse-spark-1.3-contributor`, Meta Model API) unless marked.
Costs are estimates from list prices. Every trace link opens the run on the live site, with each agent step,
both verifications and a button that re-runs both programs on a fresh seed.

## End to end: legacy repository → certified pull request → the target's own CI
### quillmark-mainframe → quillmark-java
Delivery `delivery-20261028-201807` · pull request https://github.com/Nivetha200111/quillmark-java/pull/1 · CI `reverify` passed on fresh inputs; merged.

| Program | Held-out match | Repair rounds | Model calls | Est. cost | Model | Trace |
|---|---|---|---|---|---|---|
| ACCTMTCH | 1585/1585 | 0 | 1 | $0.0039 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=acctmtch-20261028-194951) |
| DAYCTRL | 1017/1017 | 0 | 4 | $0.0171 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=dayctrl-20261028-194951) |
| FEESCHD | 1021/1021 | 0 | 4 | $0.0221 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=feeschd-20261028-194951) |
| INTACCR | 1019/1019 | 0 | 4 | $0.0173 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=intaccr-20261028-194951) |
| PKDPOST | 1037/1037 | 0 | 4 | $0.0229 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=pkdpost-20261028-195219) |
| TXNPOST | 1024/1024 | 1 | 10 | $0.0235 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=txnpost-20261028-200111) |

**6 programs certified · 27 model calls · $0.107 estimated.**

### quillmark-legacy → quillmark-modern
Delivery `delivery-20261028-194045` · pull request https://github.com/Nivetha200111/quillmark-modern/pull/3 · CI `reverify` passed on fresh inputs; merged. Under the later byte-exact comparator, INTACCR fails (sign of zero); see PR #4 below.

| Program | Held-out match | Repair rounds | Model calls | Est. cost | Model | Trace |
|---|---|---|---|---|---|---|
| ACCTMTCH | 1585/1585 | 0 | 1 | $0.0046 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=acctmtch-20261028-191523) |
| DAYCTRL | 1017/1017 | 0 | 4 | $0.0185 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=dayctrl-20261028-191523) |
| FEESCHD | 1021/1021 | 0 | 4 | $0.0231 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=feeschd-20261028-191523) |
| INTACCR ⚠ | 1019/1019 | 0 | 4 | $0.0182 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=intaccr-20261028-191523) |
| PKDPOST | 1037/1037 | 1 | 8 | $0.0266 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=pkdpost-20261028-191821) |
| TXNPOST | 1024/1024 | 0 | 4 | $0.0194 | `muse-spark-1.3-contributor` | [trace](https://diocle.vercel.app/#run=txnpost-20261028-192729) |

**6 programs certified · 25 model calls · $0.110 estimated.**

### INTACCR re-delivery, and every certificate under one verifier
After the comparator was made byte-exact, INTACCR was converted again from quillmark-legacy (the repair agent fixed
the negative-zero case itself) and the other five programs' existing Java was **re-certified under the new
verifier with zero model calls** (it already passed). All six certificates are on
[quillmark-modern#4](https://github.com/Nivetha200111/quillmark-modern/pull/4), whose CI re-verifies them with one
pinned verifier.

## Unseen programs (frozen evaluation)
[docs/EVALUATION.md](EVALUATION.md): first run 2 of 4 certified (the old comparator rejected aggregation and
fan-out); re-run with the corrected verifier and fix memory off: **4 of 4 certified, about $0.11**, each passing
five fresh seeds. CHQCLR is where the breaker agent broke code that had passed 1,000 held-out inputs.

## Visitor import through the sandbox
A public import of quillmark-mainframe through the live site (no passcode) certified ACCTMTCH 1585/1585 with every
build and program run in the isolated sandbox. Security reviews and the live attack test: docs/HANDOFF.md.

## Private mode (Meta open weights)
See the section below once the fresh run on Muse Spark Open is recorded.
