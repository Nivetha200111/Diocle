      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system, employer, or client.

       01  TXNSEG-REC.
           05  TX-TXN-ID                PIC X(9).
           05  TX-ACCOUNT-NO            PIC X(10).
           05  TX-POSTED-DATE           PIC X(10).
           05  TX-AMOUNT                PIC S9(7)V99 COMP-3.
           05  TX-TYPE                  PIC X.
           05  TX-DETAIL                PIC X(12).
           05  TX-PAYMENT REDEFINES TX-DETAIL.
               10  TX-DIRECTION         PIC X.
               10  TX-CHANNEL           PIC X(3).
               10  TX-REFERENCE         PIC X(8).
           05  TX-FEE REDEFINES TX-DETAIL.
               10  TX-FEE-CODE          PIC X(4).
               10  TX-FEE-RESERVED      PIC X(8).
           05  TX-INTEREST REDEFINES TX-DETAIL.
               10  TX-ACCRUAL-DAYS      PIC 9(3).
               10  TX-ROUNDING          PIC X.
               10  TX-INT-RESERVED      PIC X(8).
