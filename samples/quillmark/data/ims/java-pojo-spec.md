SYNTHETIC SAMPLE - written for the Diocle hackathon project.
Fictional company. Not derived from any real system, employer, or client.

# Java target POJO specification (no implementation)

This is a specification for Diocle to convert and verify, not Java conversion code.
Offsets and PICs come from the canonical IMS copybooks. Preserve ASCII spaces in
String properties, including the trailing spaces in displayName, street and city.
No implicit `trim()`. Dates must parse strictly as ISO calendar dates. Monetary values
must use BigDecimal with the declared scale; never binary float or double. IDs and
the deliberately invalid PAN remain String values, preserving leading zeroes.
Source bytes have no representation of SQL NULL: ADDRSEG note NULL, empty, and two
spaces all map to eight spaces. Native CSV is authoritative for that distinction.
CUSTOMER.fullName is CSV-only; displayName is fullName truncated to 24 ASCII bytes
and padded to 24. A POJO based only on this source cannot recover fullName.

Each class below represents exactly one payload. Primary parent/child references
are resolved using the source IDs; the separate orphan must produce a missing-parent
verification result. Lists for absent optional segments or zero children are empty.
There is no code here that converts or verifies a Diocle target implementation.

## CustomerRoot (CUSTROOT)

| Property | Java type | Source field | Offset | Bytes | PIC / usage |
|---|---|---|---:|---:|---|
| customerId | String | CR-CUSTOMER-ID | 1 | 7 | X(7) |
| displayName | String | CR-DISPLAY-NAME | 8 | 24 | X(24) |
| kind | String | CR-KIND | 32 | 1 | X |
| openDate | java.time.LocalDate | CR-OPEN-DATE | 33 | 10 | X(10) |
| status | String | CR-STATUS | 43 | 1 | X |

## AddressSegment (ADDRSEG)

| Property | Java type | Source field | Offset | Bytes | PIC / usage |
|---|---|---|---:|---:|---|
| customerId | String | AD-CUSTOMER-ID | 1 | 7 | X(7) |
| addressSequence | int | AD-SEQ | 8 | 2 | 9(2) |
| street | String | AD-STREET | 10 | 24 | X(24) |
| city | String | AD-CITY | 34 | 16 | X(16) |
| deliveryNote | String | AD-NOTE | 50 | 8 | X(8) |

## AccountSegment (ACCTSEG)

| Property | Java type | Source field | Offset | Bytes | PIC / usage |
|---|---|---|---:|---:|---|
| accountNo | String | AC-ACCOUNT-NO | 1 | 10 | X(10) |
| customerId | String | AC-CUSTOMER-ID | 11 | 7 | X(7) |
| productId | String | AC-PRODUCT-ID | 18 | 4 | X(4) |
| balance | java.math.BigDecimal | AC-BALANCE | 22 | 6 | S9(9)V99 COMP-3 |
| annualRate | java.math.BigDecimal | AC-RATE | 28 | 3 | 9V9(4) COMP-3 |
| openDate | java.time.LocalDate | AC-OPEN-DATE | 31 | 10 | X(10) |
| status | String | AC-STATUS | 41 | 1 | X |

## CardSegment (CARDSEG)

| Property | Java type | Source field | Offset | Bytes | PIC / usage |
|---|---|---|---:|---:|---|
| cardId | String | CA-CARD-ID | 1 | 8 | X(8) |
| accountNo | String | CA-ACCOUNT-NO | 9 | 10 | X(10) |
| invalidPan | String | CA-INVALID-PAN | 19 | 16 | X(16) |
| expiryDate | java.time.LocalDate | CA-EXPIRY-DATE | 35 | 10 | X(10) |
| status | String | CA-STATUS | 45 | 1 | X |

## TransactionSegment (TXNSEG)

| Property | Java type | Source field | Offset | Bytes | PIC / usage |
|---|---|---|---:|---:|---|
| txnId | String | TX-TXN-ID | 1 | 9 | X(9) |
| accountNo | String | TX-ACCOUNT-NO | 10 | 10 | X(10) |
| postedDate | java.time.LocalDate | TX-POSTED-DATE | 20 | 10 | X(10) |
| amount | java.math.BigDecimal | TX-AMOUNT | 30 | 5 | S9(7)V99 COMP-3 |
| type | String | TX-TYPE | 35 | 1 | X |
| detailRaw | String | TX-DETAIL | 36 | 12 | X(12) |

## Transaction detail union

Keep detailRaw (String, all 12 bytes) and a typed detail property selected by type.
Both representations must agree. The classes below are nested value specifications.

| Type | Detail class | Field | Java type | Source PIC | Offset | Bytes |
|---|---|---|---|---|---:|---:|
| P | PaymentDetail | direction | String | X | 36 | 1 |
| P | PaymentDetail | channel | String | X(3) | 37 | 3 |
| P | PaymentDetail | reference | String | X(8) | 40 | 8 |
| F | FeeDetail | feeCode | String | X(4) | 36 | 4 |
| F | FeeDetail | reserved | String | X(8) | 40 | 8 |
| I | InterestDetail | accrualDays | int | 9(3) | 36 | 3 |
| I | InterestDetail | rounding | String | X | 39 | 1 |
| I | InterestDetail | reserved | String | X(8) | 40 | 8 |

## Relationships and arithmetic contract

CustomerRoot: addresses List<AddressSegment>, accounts List<AccountSegment>.
AccountSegment: cards List<CardSegment>, transactions List<TransactionSegment>.
These collections are target relationships, not extra bytes in any source record.

Interest reference: principal * annualRate * days / 365, then round the signed
result to two decimal places with BigDecimal RoundingMode.HALF_UP (ties away from
zero, matching this fixture's COBOL ROUNDED). Round each record before summing.
The generator supplies expected amounts and exact inputs in manifest.json; Diocle
must independently verify converted behavior against the COBOL source it produces.
No rounding or conversion implementation is supplied in this POJO spec.
