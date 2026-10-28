---
name: cobol-to-java-semantics
description: Reproduce GnuCOBOL arithmetic and record formatting exactly when translating COBOL batch programs to Java. Use when converting or reviewing COBOL-to-Java code, especially COMPUTE, ROUNDED, PIC clauses, SIGN LEADING SEPARATE fields, COMP counters and fixed-width records.
---

# COBOL to Java: semantics proven against GnuCOBOL

Diocle's repair agent wrote these lessons while fixing conversions of synthetic sample programs. Each one was kept only after the fixed Java matched the original COBOL, compiled with GnuCOBOL 3.2 (-std=ibm), on 1,000 held-out inputs.

Treat them as rules of thumb, not proof: after converting, run the original and the Java on the same inputs and compare every output field.

## Lessons

### COMPUTE truncation
- **COBOL:** COMPUTE without ROUNDED truncates the exact decimal result toward zero to the receiving scale.
- **Java:** Do exact scaled-integer multiply/divide with truncation toward zero; never use double or Math.round.
- *Learned from TXNPOST, run `txn-posting-20261028-172552`*

### Boundary comparison strictness
- **COBOL:** A negated comparison of the form NOT < is true when the value equals the limit.
- **Java:** Implement such threshold tests as greater-or-equal / strict less-than, not strict greater-than.
- *Learned from FEESCHD, run `fee-schedule-20261028-172910`*

### COMPUTE ROUNDED ties
- **COBOL:** A COMPUTE with ROUNDED on an exact halfway value rounds away from zero, including negatives; binary floating point can place the tie on the wrong side.
- **Java:** Do the computation with scaled integers/BigDecimal and apply HALF_UP (increment magnitude when twice remainder >= divisor); never use double or Math.round.
- *Learned from DAYCTRL, run `daily-control-20261028-173205`*

### Rounded-sum control total
- **COBOL:** When each record amount is rounded before adding to a running total, the total equals the sum of posted rounded amounts, not the sum of exact values.
- **Java:** Round each record to cents first with exact integer arithmetic, then accumulate the rounded cents.
- *Learned from DAYCTRL, run `daily-control-20261028-173205`*

### COMP-3 picture overflow
- **COBOL:** Storing into a fixed-precision packed/signed decimal keeps only low-order digits modulo 10^n, with zero staying positive, before later compares or arithmetic.
- **Java:** Reduce every intermediate store modulo 10^totalDigits preserving truncated sign with positive zero before further use.
- *Learned from DAYCTRL, run `daily-control-20261028-173205`*

### Display field overflow
- **COBOL:** Moving a numeric value to a fixed-width sign-leading-separate display keeps sign plus low-order zero-padded digits truncated modulo 10^width at exact field width.
- **Java:** Format sign plus zero-padded absolute value truncated modulo 10^width to the fixed field width.
- *Learned from DAYCTRL, run `daily-control-20261028-173205`*

### DISPLAY width and decimal exactness
- **COBOL:** DISPLAY of binary counters and edited numerics uses wider zero-padded or space-padded widths than the picture digit count, with sign handling for edited pictures.
- **Java:** Match observed DISPLAY widths with explicit zero-padded counters and space-padded edited-numeric formatting.
- *Learned from DAYCTRL, run `daily-control-20261028-173205`*

### COMP counter DISPLAY width
- **COBOL:** DISPLAY of a binary COMP integer renders with a wider zero-padded decimal width than the digit count in its PICTURE.
- **Java:** Format binary counters with an explicit wider zero-padded width matching observed output instead of using the PICTURE digit count.
- *Learned from DAYCTRL, run `dayctrl-20261028-174138`*

## Always
- Use `java.math.BigDecimal` for every decimal value; never `float`, `double` or `Math.round`.
- Never special-case particular inputs or expected outputs.
