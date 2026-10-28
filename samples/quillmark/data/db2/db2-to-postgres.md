SYNTHETIC SAMPLE - written for the Diocle hackathon project.
Fictional company. Not derived from any real system, employer, or client.

# DB2-style to PostgreSQL mapping

The source is a conservative DB2-style 1990s DDL fixture, not a claim that DDL was
executed on a particular DB2 release. The converted schema preserves all 15 tables,
column sizes, keys, constraints, and indexes. No identities, sequences or implicit
key generation are introduced. TRANSACTION is quoted in both schemas because its
name conflicts with SQL transaction syntax. PostgreSQL folds all other unquoted
identifiers to lower case; CSV headers remain uppercase and the load script uses
an explicit matching column list.

Every changed type occurrence is listed here. DECIMAL and NUMERIC are exact-decimal
synonyms in PostgreSQL; spelling NUMERIC explicitly identifies the converted side.
Precision and scale are unchanged, including signed negative amounts and PIC maxima.

| Column | Source DB2-style type | Target PostgreSQL type | Why |
|---|---|---|---|
| RATE_TABLE.ANNUAL_RATE | DECIMAL(5,4) | NUMERIC(5,4) | Exact decimal, same precision and scale |
| ACCOUNT.BALANCE | DECIMAL(11,2) | NUMERIC(11,2) | Exact decimal, same precision and scale |
| ACCOUNT.ANNUAL_RATE | DECIMAL(5,4) | NUMERIC(5,4) | Exact decimal, same precision and scale |
| TRANSACTION.AMOUNT | DECIMAL(9,2) | NUMERIC(9,2) | Exact decimal, same precision and scale |
| PAYMENT.AMOUNT | DECIMAL(9,2) | NUMERIC(9,2) | Exact decimal, same precision and scale |
| CARD_AUTH.AMOUNT | DECIMAL(9,2) | NUMERIC(9,2) | Exact decimal, same precision and scale |
| FEE_SCHEDULE.AMOUNT | DECIMAL(7,2) | NUMERIC(7,2) | Exact decimal, same precision and scale |
| GL_POSTING.AMOUNT | DECIMAL(9,2) | NUMERIC(9,2) | Exact decimal, same precision and scale |

All other source types are retained verbatim:

| Source | Target | Behavioral considerations |
|---|---|---|
| CHAR(n) | CHAR(n) | Fixed-width blank padding retained. Comparisons may ignore trailing blanks; use byte-aware extraction checks too. |
| VARCHAR(n) | VARCHAR(n) | Empty string, spaces and NULL are distinct in these fixtures; never normalize them silently. |
| SMALLINT | SMALLINT | Signed 16-bit integer; composite address and posting keys retain their ranges. |
| INTEGER | INTEGER | Signed 32-bit integer; CARD_AUTH sequence fits. |
| DATE | DATE | Gregorian ISO dates; leap-day and month-end values stay dates. No time-zone conversion. |
| TIMESTAMP | TIMESTAMP | PostgreSQL timestamp without time zone; fixtures have whole seconds. No implicit local-zone conversion or precision loss here. |

No money uses a vendor MONEY type. Annual rate is DECIMAL/NUMERIC(5,4), matching
9V9(4); balance is (11,2), matching S9(9)V99; transaction amounts are (9,2), matching
S9(7)V99. COMP-3 is a file encoding, not an SQL type, and is described in ims/dbd.md.
ZZZ is a fictitious currency marker. The schema deliberately has no bank routing,
BIN, IBAN, SWIFT, tax-ID, phone, email, or URL columns. INVALID_PAN is a fixture token
with leading zeroes and a deliberately wrong Luhn digit, not a bank-issued number.

The SQLite verification fallback executes the converted DDL with foreign keys on.
SQLite accepts these declared types but does not enforce CHAR padding, VARCHAR
lengths, or NUMERIC precision like PostgreSQL. Independent file/PIC checks and
integer-cent aggregates address the fixture checks; they do not certify PostgreSQL
or DB2 server compatibility. See verification.json for what actually ran.
