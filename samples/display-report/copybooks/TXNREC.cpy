      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * TRANSACTION LISTING INPUT (15 BYTES, LINE SEQUENTIAL)
       01  TXN-REC.
           05  TXN-ID                  PIC X(6).
           05  TXN-TYPE                PIC X.
               88  TXN-CREDIT          VALUE 'C'.
               88  TXN-DEBIT           VALUE 'D'.
           05  TXN-AMOUNT              PIC S9(5)V99
                                       SIGN LEADING SEPARATE.
