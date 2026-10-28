---
name: cobol-to-java-semantics
description: Reproduce GnuCOBOL arithmetic and record formatting exactly when translating COBOL batch programs to Java. Use when converting or reviewing COBOL-to-Java code, especially COMPUTE, ROUNDED, PIC clauses, SIGN LEADING SEPARATE fields, COMP counters and fixed-width records.
---

# COBOL to Java: semantics proven against GnuCOBOL

Diocle's repair agent wrote these lessons while fixing real conversions. Each one was kept only after the fixed Java matched the original COBOL, compiled with GnuCOBOL 3.2 (-std=ibm), on 1,000 held-out inputs.

Treat them as rules of thumb, not proof: after converting, run the original and the Java on the same inputs and compare every output field.

## Lessons

### Rounded-sum control total
- **COBOL:** A per-record rounded amount is what is added to a running control total, not the unrounded exact value.
- **Java:** Round each record to cents first with exact integer arithmetic, then accumulate the rounded cents.
- *Learned from DAYCTRL, run `daily-control-20261028-172218`*

### COMPUTE truncation
- **COBOL:** COMPUTE without ROUNDED truncates the exact decimal result toward zero to the receiving scale.
- **Java:** Do exact scaled-integer multiply/divide with truncation toward zero; never use double or Math.round.
- *Learned from TXNPOST, run `txn-posting-20261028-172552`*

### Boundary comparison strictness
- **COBOL:** A negated comparison of the form NOT < is true when the value equals the limit.
- **Java:** Implement such threshold tests as greater-or-equal / strict less-than, not strict greater-than.
- *Learned from FEESCHD, run `fee-schedule-20261028-172910`*

### COMP-3 picture overflow
- **COBOL:** Storing into a fixed-precision packed/signed decimal keeps only low-order digits modulo 10^n with zero staying positive, before any later compare or arithmetic.
- **Java:** Reduce every intermediate store modulo 10^totalDigits preserving truncated sign with positive zero before further use.
- *Learned from FEESCHD, run `fee-schedule-20261028-172910`*

### Display field overflow
- **COBOL:** Moving a numeric value to a fixed-width sign-leading-separate display keeps sign plus low-order zero-padded digits truncated modulo 10^width to the exact field width.
- **Java:** Format sign plus zero-padded absolute value truncated modulo 10^width to the fixed field width.
- *Learned from FEESCHD, run `fee-schedule-20261028-172910`*

### COMPUTE ROUNDED ties
- **COBOL:** COMPUTE with ROUNDED on an exact halfway rounds away from zero, including for negative results, and binary floating point can misplace the tie.
- **Java:** Compute truncated quotient and remainder from scaled integers and increment magnitude when 2*|remainder| >= divisor.
- *Learned from FEESCHD, run `fee-schedule-20261028-172910`*

### DISPLAY width and decimal exactness
- **COBOL:** DISPLAY of a binary (COMP) integer uses enough characters to show the full binary value range with zero-padding, wider than the digit count in its PICTURE.
- **Java:** Format such counters with explicit zero-padding to the observed DISPLAY width (e.g. 10 digits) rather than the PICTURE digit count, preserving modulo wrap of the binary value.
- *Learned from FEESCHD, run `feeschd-20261028-173051`*

## Always
- Use `java.math.BigDecimal` for every decimal value; never `float`, `double` or `Math.round`.
- Never special-case particular inputs or expected outputs.
