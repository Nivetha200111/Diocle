SYNTHETIC SAMPLE - written for the Diocle hackathon project.
Fictional company. Not derived from any real system, employer, or client.

# Edge-case ledger

These keys refer to the committed **small** dataset: seed 20261028, edge rate 0.02.
For other configurations, use `manifest.json` → `edge_cases` (counts and example
keys) and `controls.interest_rounding` (exact transaction keys and inputs).
Positive rates always include the mandatory anchors below; the probability governs
additional anomalies. Zero disables deliberate anchors. Anchors remain present at
rate one, including the duplicate pair and space/empty/NULL examples.

| Case | Default-small record key(s) | Expected observation |
|---|---|---|
| Zero balance | ACCOUNT 99Q0000005 | Signed packed balance decodes to 0.00; zero is not NULL. |
| Negative balance | ACCOUNT 99Q0000002 | -36.50; preserve the COMP-3 D sign. |
| Balance PIC maximum | ACCOUNT 99Q0000004 | 999999999.99 fits S9(9)V99 in six packed bytes and NUMERIC(11,2). |
| Signed transaction PIC maxima | TRANSACTION T00000022 / T00000029 | +9999999.99 / -9999999.99; preserve signs, no overflow, five packed bytes. |
| Positive half-cent | T00000001, account 99Q0000001 | 36.50 × 0.0500 / 365 = 0.005000 → 0.01 with COBOL ROUNDED. |
| Negative half-cent | T00000008, account 99Q0000002 | -36.50 × 0.0500 / 365 = -0.005000 → -0.01, away from zero. |
| Additional positive tie | T00000015, account 99Q0000003 | 182.50 × 0.0500 / 365 = 0.025000 → 0.03; half-even gives 0.02. |
| Leap day | T00000001 / T00000008 / T00000015 | POSTED_DATE 2000-02-29. CARD expiry 2004-02-29 is also a valid leap day. |
| Month end | T00000022 / T00000029 | POSTED_DATE 2001-01-31; further January, February and March ends appear in the manifest examples. |
| Dormant account | ACCOUNT 99Q0000006 | STATUS D; present in ACCOUNT/ACCTSEG with zero transactions. |
| Active account with no transactions | ACCOUNT 99Q0000007 | STATUS A; no TXNSEG children; do not fabricate a transaction. |
| Duplicate-looking customers | CUSTOMER C000008 / C000009 | Same invented full/display name, different keys. Never deduplicate solely by name. |
| Trailing spaces versus empty versus NULL | CUSTOMER_ADDRESS C000001/01, C000003/01, C000002/01 respectively | Delivery notes are two spaces, empty string and SQL NULL. CSV distinguishes all three. |
| Missing optional address | CUSTOMER C000011 | Root is present; ADDRSEG and CUSTOMER_ADDRESS row are absent. |
| Missing optional card | ACCOUNT 99Q0000008 | Account is present; CARDSEG and CARD row are absent. |
| Orphan child | ACCTSEG 99Q9999999 → missing C999999 | One intentional orphan, present only in fixed/orphan_acctseg.bin and ims/orphan.unload. Reject/quarantine it. |
| Payment REDEFINES variant | TXNSEG T00000002 | Type P, 12-byte detail = direction, SIM channel and an 8-byte invented reference. |
| Fee REDEFINES variant | TXNSEG T00000005 | Type F, detail = QF01 plus eight spaces, amount -2.50. |
| Interest REDEFINES variant | TXNSEG T00000001 | Type I, detail = 001R plus eight spaces. Same storage as P/F, not appended fields. |
| Name truncation | CUSTOMER C000010 | Full invented name exceeds 24 ASCII bytes; DISPLAY_NAME is exactly fullName[:24]. Full name remains in CSV. |
| Deliberately invalid card checksum | CARD K0000001 and every other card | 16 digits, six leading zeroes, deliberately wrong Luhn digit; must not become valid during conversion. |

## Rounding-sensitive daily control

The only transactions on 2000-02-29 are the three interest anchors above. Compute
the exact daily interest independently for each account, then apply COBOL COMPUTE
... ROUNDED to a signed S9(7)V99 target. This is ties away from zero, equivalent to
BigDecimal HALF_UP for these signed decimal inputs. No implicit float arithmetic.

| Method | First interest | Second interest | Third interest | Daily sum |
|---|---:|---:|---:|---:|
| COBOL ROUNDED, per record | 0.01 | -0.01 | 0.03 | **0.03** |
| Half-even, per record | 0.00 | -0.00 | 0.02 | 0.02 |
| Truncate toward zero, per record | 0.00 | -0.00 | 0.02 | 0.02 |

The positive/negative 0.005 pair cancels at day level; the third tie is deliberate
so the **daily** control also catches half-even/truncation. The manifest includes
the exact principal, rate, days, divisor, raw value, COBOL result and half-even
counterexample for each record. The verifier compiles and runs a GnuCOBOL probe
when available; its executed status is recorded in verification.json.

## Intentional information loss and reconciliation boundaries

PIC X(8) cannot distinguish source NULL, empty string and spaces: all three note
examples become eight spaces in ADDRSEG. Likewise CUSTROOT contains only the
truncated display name, not the full VARCHAR name. These are explicit mappings,
not evidence that an arbitrary converter may trim strings or discard information
in CSV-to-SQL or Java targets. Compare each representation using its documented
projection, and preserve the richer fields where they exist.

The orphan's parent does not exist at any supported scale (the highest customer
serial is 200000). Its balance is zero, but it must still be rejected. It is absent
from relational CSVs and the valid hierarchy. Manifest quarantine counts report one
ACCTSEG, not two, because fixed and unload files are two views of the same entity.
All valid CSV foreign keys must load successfully, and the orphan is additionally
inserted during SQLite verification to confirm that the FK rejects it.

Dormant and active-empty accounts contribute their balances to the snapshot total
and no rows to transaction totals. Snapshot balances are not a replay of this
transaction window. Per-day controls use signed amounts (not absolute values).
GL_POSTING lines net to zero per transaction and globally, independently of the
customer transaction total. Keep all zero controls as explicit zeroes.
