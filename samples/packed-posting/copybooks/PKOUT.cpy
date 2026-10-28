      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * POSTING RESULT, FIXED LENGTH (RECFM=FB, 42 BYTES)
       01  PO-REC.
           05  PO-ACCT                 PIC X(10).
           05  PO-INT                  PIC S9(7)V99 COMP-3.
           05  PO-NEW-BAL              PIC S9(9)V99 COMP-3.
           05  PO-HEADROOM             PIC S9(7)V99
                                       SIGN TRAILING SEPARATE.
           05  PO-ITEM-UNITS           PIC S9(9) COMP.
           05  PO-REVERSAL             PIC S9(5)V99.
