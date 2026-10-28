SYNTHETIC SAMPLE - written for the Diocle hackathon project.
Fictional company. Not derived from any real system, employer, or client.

# IMS hierarchical fixture definition

DBD-like documentation only; this is not executable IMS DBDGEN source.
All byte offsets below are **1-based and inclusive**, relative to the segment
payload, excluding the file notice and 8-byte segment-code prefix. The canonical
layouts are the fixed-format copybooks in `copybooks/`. Text is ASCII, not EBCDIC;
packed fields are ordinary big-endian COMP-3 digit nibbles, signed C/D and unsigned F.
There are no RDWs, BDWs, delimiter bytes, alignment padding, or IMS system fields.

```text
DBD NAME=QMKDB, ACCESS=HIDAM-LIKE (documentation)
  SEGM NAME=CUSTROOT, PARENT=0,       BYTES=43, KEY=CR-CUSTOMER-ID
    SEGM NAME=ADDRSEG, PARENT=CUSTROOT, BYTES=57, KEY=AD-SEQ
    SEGM NAME=ACCTSEG, PARENT=CUSTROOT, BYTES=41, KEY=AC-ACCOUNT-NO
      SEGM NAME=CARDSEG, PARENT=ACCTSEG, BYTES=45, KEY=CA-CARD-ID
      SEGM NAME=TXNSEG,  PARENT=ACCTSEG, BYTES=47, KEY=TX-TXN-ID
```

ADDRSEG's local key is ADDRESS_SEQ; the full relational key includes CUSTOMER_ID.
Each account has one primary customer in the hierarchy; joint holders are represented
only in ACCOUNT_HOLDER. Each account's CARDSEG precedes its TXNSEG children.
ADDRSEG is emitted before all account children of that root. Missing addresses and
cards are allowed. Dormant and deliberately idle accounts have no TXNSEG children.
All roots and all sibling keys are unique; the separate orphan fixture deliberately
violates parent existence and must be rejected or quarantined.

## CUSTROOT: 43 bytes

| Field | Offset | Bytes | PIC / usage | Local key |
|---|---:|---:|---|---|
| CR-CUSTOMER-ID | 1 | 7 | X(7) | yes |
| CR-DISPLAY-NAME | 8 | 24 | X(24) |  |
| CR-KIND | 32 | 1 | X |  |
| CR-OPEN-DATE | 33 | 10 | X(10) |  |
| CR-STATUS | 43 | 1 | X |  |

## ADDRSEG: 57 bytes

| Field | Offset | Bytes | PIC / usage | Local key |
|---|---:|---:|---|---|
| AD-CUSTOMER-ID | 1 | 7 | X(7) |  |
| AD-SEQ | 8 | 2 | 9(2) | yes |
| AD-STREET | 10 | 24 | X(24) |  |
| AD-CITY | 34 | 16 | X(16) |  |
| AD-NOTE | 50 | 8 | X(8) |  |

## ACCTSEG: 41 bytes

| Field | Offset | Bytes | PIC / usage | Local key |
|---|---:|---:|---|---|
| AC-ACCOUNT-NO | 1 | 10 | X(10) | yes |
| AC-CUSTOMER-ID | 11 | 7 | X(7) |  |
| AC-PRODUCT-ID | 18 | 4 | X(4) |  |
| AC-BALANCE | 22 | 6 | S9(9)V99 COMP-3 |  |
| AC-RATE | 28 | 3 | 9V9(4) COMP-3 |  |
| AC-OPEN-DATE | 31 | 10 | X(10) |  |
| AC-STATUS | 41 | 1 | X |  |

## CARDSEG: 45 bytes

| Field | Offset | Bytes | PIC / usage | Local key |
|---|---:|---:|---|---|
| CA-CARD-ID | 1 | 8 | X(8) | yes |
| CA-ACCOUNT-NO | 9 | 10 | X(10) |  |
| CA-INVALID-PAN | 19 | 16 | X(16) |  |
| CA-EXPIRY-DATE | 35 | 10 | X(10) |  |
| CA-STATUS | 45 | 1 | X |  |

## TXNSEG: 47 bytes

| Field | Offset | Bytes | PIC / usage | Local key |
|---|---:|---:|---|---|
| TX-TXN-ID | 1 | 9 | X(9) | yes |
| TX-ACCOUNT-NO | 10 | 10 | X(10) |  |
| TX-POSTED-DATE | 20 | 10 | X(10) |  |
| TX-AMOUNT | 30 | 5 | S9(7)V99 COMP-3 |  |
| TX-TYPE | 35 | 1 | X |  |
| TX-DETAIL | 36 | 12 | X(12) |  |

TX-TYPE at byte 35 selects exactly one view over TX-DETAIL, bytes 36–47.
REDEFINES adds no storage. Unknown type bytes must fail verification.

| Type | View / field | Offset | Bytes | PIC |
|---|---|---:|---:|---|
| P | TX-PAYMENT / TX-DIRECTION | 36 | 1 | X |
| P | TX-PAYMENT / TX-CHANNEL | 37 | 3 | X(3) |
| P | TX-PAYMENT / TX-REFERENCE | 40 | 8 | X(8) |
| F | TX-FEE / TX-FEE-CODE | 36 | 4 | X(4) |
| F | TX-FEE / TX-FEE-RESERVED | 40 | 8 | X(8) |
| I | TX-INTEREST / TX-ACCRUAL-DAYS | 36 | 3 | 9(3) |
| I | TX-INTEREST / TX-ROUNDING | 39 | 1 | X |
| I | TX-INTEREST / TX-INT-RESERVED | 40 | 8 | X(8) |

P = synthetic payment, F = fee, I = interest. Reserved bytes contain spaces.
For I, days = 001 and rounding marker R means COBOL COMPUTE ... ROUNDED.
