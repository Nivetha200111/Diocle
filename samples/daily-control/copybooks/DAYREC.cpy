      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * DAILY ACCRUAL INPUT: ONE ACCOUNT PER RECORD (30 BYTES)
       01  DAY-REC.
           05  DAY-ACCT-ID             PIC X(10).
           05  DAY-PRINCIPAL           PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  DAY-RATE                PIC 9V9(4).
           05  DAY-DAYS                PIC 9(3).
