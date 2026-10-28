      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * ACCRUAL RESULT WITH RUNNING CONTROL TOTAL (35 BYTES)
       01  CTL-REC.
           05  CTL-ACCT-ID             PIC X(10).
           05  CTL-INTEREST            PIC S9(7)V99
                                       SIGN LEADING SEPARATE.
           05  CTL-RUN-TOTAL           PIC S9(11)V99
                                       SIGN LEADING SEPARATE.
           05  CTL-FLAG                PIC X.
