SYNTHETIC SAMPLE - written for the Diocle hackathon project.
Fictional company. Not derived from any real system, employer, or client.

# Quillmark synthetic banking data estate

Quillmark Trust & Savings (fictional) is a verification fixture for Diocle's COBOL
modernization demo. Everything here was invented for the hackathon on 28 October
2026. No external datasets, people, organizations, addresses or credentials are used.
The Python tools use only the standard library. There is no Java converter or
product implementation here: Java targets are specifications for Diocle to produce.

## Contents

- `db2/schema.db2.sql`: 15 DB2-style tables, exact-decimal money, composite keys,
  foreign keys, indexes and CHECK constraints. Conservative 1990s SQL style.
- `db2/schema.postgres.sql`: converted schema; `db2/db2-to-postgres.md` enumerates
  every changed type and the retained types' semantics.
- `ims/copybooks/`: five canonical fixed-format COBOL layouts. No Quillmark
  copybooks existed elsewhere when these were created.
- `ims/dbd.md`: documented hierarchy, lengths, offsets, keys and REDEFINES views.
- `ims/java-pojo-spec.md`: field/type/offset/PIC targets, relationships and arithmetic
  contract. Specifications only, without conversion code.
- `tools/generate.py`: seeded entity generation and all three output formats.
- `tools/verify.py`: checksum, byte-length, value, hierarchy, pattern, SQLite and
  optional GnuCOBOL checks. This checks fixtures, not a Diocle Java conversion.
- `tools/check_all.py`: actual repeat-generation and boundary-rate checks.
- `out/small/`: the only committed dataset, under 5,000,000 bytes including headers,
  the manifest, all CSVs, binary extracts, unloads and load script.
- `EDGE_CASES.md`: exact default-small record keys and expected behavior.
- `verification.json`: results from the checks that actually ran.

The tables are CUSTOMER, CUSTOMER_ADDRESS, ACCOUNT, ACCOUNT_HOLDER, PRODUCT,
RATE_TABLE, TRANSACTION, PAYMENT, PAYMENT_BATCH, CARD, CARD_AUTH, FEE_SCHEDULE,
GL_ACCOUNT, GL_POSTING and FRAUD_ALERT. Currency marker ZZZ is fictional.
Balances are account snapshots, not opening balances calculated by replaying the
transaction history. GL_POSTING contains two equal/opposite lines per transaction;
PAYMENT represents every P-type transaction and points to its dated batch.
ACCOUNT_HOLDER includes primary and joint holders, while IMS nests accounts only
under their primary customer. There are no routing, tax, contact or other real-bank
identifier columns. Account numbers use `99Q` plus seven serial digits. Cards use
six leading zeroes plus a serial and an intentionally incorrect Luhn digit.

## Generate

Run from the repository root with Python 3.10 or later. Output directories must
be empty and inside this data folder. The generator refuses to overwrite files.
The committed small output already exists, so use a fresh preview directory:

```sh
python3 samples/quillmark/data/tools/generate.py --seed 20261028 --scale small --out samples/quillmark/data/.work/small-preview
python3 samples/quillmark/data/tools/generate.py --seed 20261028 --scale medium
python3 samples/quillmark/data/tools/generate.py --seed 20261028 --scale large
```

| Scale | Customers | Accounts | Transactions | Default location |
|---|---:|---:|---:|---|
| small | 1,000 | 1,500 | 10,000 | out/small |
| medium | 50,000 | 75,000 | 1,000,000 | out/medium |
| large | 200,000 | 300,000 | 5,000,000 | out/large |

Generation streams transactions to all formats in one pass and keeps only customer/
account planning state in memory. Output can be substantial at medium/large scale.
The scoped `.gitignore` re-includes `out/small/` despite the repository's global
`out/` exclusion, and excludes `out/medium/`, `out/large/`, all other out subfolders,
and `.work/`. The scoped `.gitattributes` preserves generated output bytes across
Git checkouts. Do not force-add ignored output. No large run is claimed in this task.

`--edge-rate 0.02` is the default. For any positive rate, mandatory anchor fixtures
are always included; additional negative/zero balances, missing segments, long
names, dormant accounts and alerts are sampled at that probability per eligible
entity/event. This is not a promise that exactly 2% of all rows are anomalous.
`--edge-rate 0` disables injected anchors and random anomalies; normal signed
transactions, date boundaries, duplicate word-list names, nullable notes and P/F
variants still exist. `--edge-rate 1` is supported and checked too. Same seed,
scale, rate, sources and Python runtime give byte-identical output. Changing scale
changes transaction allocation, so discover edge transaction keys in that output's
manifest rather than reusing the small-scale keys.

## File formats

Every file begins with the two synthetic statements above, using the format's
comment syntax in SQL, Python, COBOL and .gitignore. CSV and binary data have two
literal ASCII notice lines ending in LF. JSON cannot contain comments: its first
member is `_notice` containing the same two statements. These notices are metadata,
not data records, and are excluded from row/segment counts and control totals.

**CSV:** `csv/<table>.csv`, ASCII, comma-separated, LF terminated, standard CSV
quoting. After the two notice lines, the third line is the column header. Monetary
values have exactly two decimal places; annual rates have four. Dates are ISO;
timestamps have no zone. `\N` means SQL NULL; an empty field means the empty string;
spaces are significant. The generator never uses literal `\N` as user text.

**Fixed extracts:** `fixed/<segment>.bin`. Skip the two notice lines (135 bytes),
then read consecutive payloads with no separators or line endings. Never split
these files on LF: COMP-3 bytes may themselves equal LF. Text is ASCII, and money
is binary packed decimal. Signed positive/negative nibbles are C/D; unsigned rate
uses F. The implied decimal point occupies no storage. There is no native-endian
binary integer or alignment padding in these layouts.

| Segment | Bytes per payload | Corresponding CSV |
|---|---:|---|
| CUSTROOT | 43 | customer |
| ADDRSEG | 57 | customer_address |
| ACCTSEG | 41 | account |
| CARDSEG | 45 | card |
| TXNSEG | 47 | transaction |

**IMS unload:** `ims/hierarchy.unload`. Skip the same notice, then read an 8-byte
ASCII code (right padded with spaces) and the corresponding fixed-size payload.
No additional length word or separator is present. Each CUSTROOT precedes its
ADDRSEG and ACCTSEG children; each account precedes CARDSEG and TXNSEG children.
TX-TYPE selects P, F or I views over the same 12-byte TX-DETAIL area. See DBD tables.

`fixed/orphan_acctseg.bin` and `ims/orphan.unload` contain the **same one** deliberate
orphan in two formats. They are separate quarantine fixtures; they are excluded
from all valid CSVs and valid hierarchy counts. They are not two different orphans.
With edge rate zero these two files are absent. The manifest records this exception
under `quarantined_segment_counts` rather than silently reconciling it away.

**Manifest:** `manifest.json` contains generation parameters, valid counts for all
15 tables and five segments, quarantined counts, segment lengths, signed balance
sum, every day's signed transaction sum/count, all monetary-column totals, exact
interest inputs/results, edge counts and up to 16 example keys per category.
It hashes every other output file with SHA-256. It does not hash itself; the repeat
checker additionally compares the manifest's own bytes and every file's checksum.
There are no timestamps, absolute paths or unordered hash-set iterations in output.

## Load and verify

For PostgreSQL, create an empty test database using your normal local connection
settings, apply the converted schema, then run the generated load script from the
output directory. The script uses psql client-side COPY FROM PROGRAM and Unix
`tail` to skip the notice lines; a standard Unix-like shell is required.

```sh
psql -v ON_ERROR_STOP=1 -f samples/quillmark/data/db2/schema.postgres.sql
cd samples/quillmark/data/out/small
psql -v ON_ERROR_STOP=1 -f load.postgres.sql
```

The script loads all 15 tables in foreign-key order inside a transaction and keeps
empty strings, spaces and NULL distinct. It assumes an empty schema and intentionally
has no DELETE, DROP or TRUNCATE commands. A PostgreSQL server was **not available**
for the recorded checks; neither PostgreSQL nor DB2 execution is claimed.

From the repository root, reproduce the checks that were run:

```sh
python3 samples/quillmark/data/tools/verify.py samples/quillmark/data/out/small
python3 samples/quillmark/data/tools/check_all.py
```

The first command loads every small CSV into an in-memory SQLite database using
the converted DDL with foreign keys enabled. It checks all table counts, every
money-column total, all 91 daily controls, GL pairs, payment links, edge anchors
and rejection of the quarantined orphan. SQLite does not enforce all PostgreSQL
CHAR/VARCHAR/NUMERIC semantics; copybook-derived byte/PIC and CSV-value checks add
coverage. All monetary aggregation uses integer cents, with Decimal checks on the
stored values; no binary-float SUM is used for reconciliation.

Both commands check each fixed record against its canonical copybook, compare its
decoded fields against the CSV, verify the full unload's byte equality and parent
ordering, and scan output for Luhn-valid 16-digit tokens, email, phone and URL
patterns. Structured checks validate every CARD PAN even when adjacent fixed-width
fields prevent a token-regex match, and validate every `99Q` account ID. A decimal
control amount's integer part is not counted as a bare phone number.

If `cobc` is present, the verifier actually compiles a temporary fixed-format COBOL
probe including all five copybooks, checks LENGTH OF, compares real packed bytes
for zero and both signed PIC maxima, and executes COMPUTE ... ROUNDED for the three
interest ties. Without GnuCOBOL it reports that check as not run. This probe does
not claim IMS execution or differential verification of a Java implementation.

`check_all.py` generates small and medium **twice each**, compares the complete
checksum dictionaries (including manifests), checks fresh small against committed
small, verifies medium's binary/CSV/hierarchy/patterns without loading its CSVs,
and loads extra small runs at edge rates zero and one. Temporary outputs and
compiled probes stay under ignored `.work/` and are cleaned up. The final report
is written to `verification.json` only after all checks pass. Large is implemented
but has not been generated or verified for this delivery.

## Edge coverage

See `EDGE_CASES.md` for keys: zero/negative balances, maximum PICs, positive and
negative half-cent ties, leap day, month end, dormant accounts, duplicate-looking
customers, spaces/empty/NULL, missing optional segments, one quarantined orphan,
three REDEFINES variants, truncated display names, zero-transaction accounts and
a daily control that differs under half-even rounding. The source-of-truth daily
sum on 2000-02-29 is 0.03; half-even rounding each record gives 0.02.

## Hackathon milestone

28 October 2026: created the synthetic schemas, canonical IMS layouts, POJO spec,
seeded multi-format generator, small fixture and executed verification recorded
here. All task edits and documentation stay inside `samples/quillmark/data/`.
