# Golden files (synthetic demo)

**SYNTHETIC.** Written for the Diocle hackathon project; no real system or data.

Golden-file replay answers "your oracle is GnuCOBOL, not the mainframe": when a sample has captured mainframe files, the converted Java is judged against **the mainframe's output** on those inputs, and Diocle reports separately whether GnuCOBOL agreed with the mainframe. Where they disagree, the mainframe wins.

| File | What it is |
|---|---|
| `input.ebcdic` | Input records exactly as they sit on z/OS: fixed length (RECFM=FB, 33 bytes), cp037 text, zoned digits with the sign in the zone nibble, packed and binary bytes as is, COMP-5 big-endian. |
| `expected.ebcdic` | The output records the production run wrote (RECFM=FB, 42 bytes). |

**What these particular files are:** five synthetic accounts, converted to EBCDIC with Diocle's codec, and an expected output **produced by GnuCOBOL** and converted to EBCDIC. So here they only exercise the replay and codec path; they cannot show a mainframe-vs-GnuCOBOL difference. In a real migration, both files come from the bank's own mainframe run of the program, and they become the authority. `services/verifier/tests/test_golden.py` shows the mainframe winning when GnuCOBOL drifts.
