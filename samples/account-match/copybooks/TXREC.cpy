      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * DAILY TRANSACTIONS, SORTED BY ACCOUNT ID (19 BYTES)
       01  TX-REC.
           05  TX-ACCT-ID              PIC X(8).
           05  TX-AMOUNT               PIC S9(7)V99
                                       SIGN LEADING SEPARATE.
           05  TX-TYPE                 PIC X.
               88  TX-CREDIT           VALUE 'C'.
               88  TX-DEBIT            VALUE 'D'.
