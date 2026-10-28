      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * ACCOUNT MASTER EXTRACT RECORD (31 BYTES)
       01  ACCT-REC.
           05  ACCT-ID                 PIC X(10).
           05  ACCT-BALANCE            PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  ACCT-RATE               PIC 9V9(4).
           05  ACCT-DAYS               PIC 9(3).
           05  ACCT-TIER               PIC X.
               88  ACCT-TIER-PREMIUM   VALUE 'P'.
