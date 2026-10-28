      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * POSTING INPUT: ONE TRANSACTION AGAINST ONE ACCOUNT (37 BYTES)
       01  TXN-REC.
           05  TXN-ID                  PIC X(9).
           05  TXN-TYPE                PIC X.
               88  TXN-PAYMENT         VALUE 'P'.
               88  TXN-FEE             VALUE 'F'.
               88  TXN-INTEREST        VALUE 'I'.
           05  TXN-AMOUNT              PIC S9(7)V99
                                       SIGN LEADING SEPARATE.
           05  TXN-BALANCE             PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  TXN-OD-LIMIT            PIC 9(5).
