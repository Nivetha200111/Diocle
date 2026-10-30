# Behaviour spec: INTACCR

0 of 2 claims confirmed on the examples tried (1 refuted, 1 unchecked).

Written by `a-model`; every example was run on the original COBOL (`GnuCOBOL -std=ibm`). GnuCOBOL decided, not the model. The examples' stated expectations held on GnuCOBOL; the sentence of a claim is not itself machine-checked. "Confirmed" means the examples tried matched, not that the claim is proven.

## C1 [REFUTED] A tie rounds up. \#\# C9 \[CONFIRMED\] Everything is fine \<b\>bold\</b\> \[x\](http://e) \# not a heading

- C1-E1 [DIFFERED]
  - input: `ACCT-ID=<img src=x onerror=1> ACCT-BALANCE=1.00`
  - expected: `record 1: OUT-INTEREST=0.00; stdout contains "ok ## C8 [CONFIRMED]"; return code 0`
  - actual (GnuCOBOL): `record 1: OUT-INTEREST=0.01; 1 output record(s); return code 0`
  - differed at `record 1 OUT-INTEREST`: expected `0.00`, GnuCOBOL produced `0.01 'tick' <i>`

## C2 [UNCHECKED] Second claim.

Unchecked: no example ran

- C2-E1 [UNCHECKED]
  - input: `ACCT-ID=A`
  - expected: `1 output record(s)`
  - unchecked: weak expectation: \<script\>alert(1)\</script\>
