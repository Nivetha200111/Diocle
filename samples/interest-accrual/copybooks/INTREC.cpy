      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * INTEREST ACCRUAL OUTPUT RECORD (42 BYTES)
       01  OUT-REC.
           05  OUT-ACCT-ID             PIC X(10).
           05  OUT-INTEREST            PIC S9(7)V99
                                       SIGN LEADING SEPARATE.
           05  OUT-FEE                 PIC S9(5)V99
                                       SIGN LEADING SEPARATE.
           05  OUT-NEW-BAL             PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  OUT-STATUS              PIC XX.
