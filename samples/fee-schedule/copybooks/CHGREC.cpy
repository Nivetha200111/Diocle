      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * MONTHLY CHARGE RESULT (38 BYTES)
       01  CHG-REC.
           05  CHG-ACCT-ID             PIC X(10).
           05  CHG-BASE                PIC S9(3)V99
                                       SIGN LEADING SEPARATE.
           05  CHG-TXN-FEE             PIC S9(3)V99
                                       SIGN LEADING SEPARATE.
           05  CHG-OD-INT              PIC S9(5)V99
                                       SIGN LEADING SEPARATE.
           05  CHG-TOTAL               PIC S9(3)V99
                                       SIGN LEADING SEPARATE.
           05  CHG-CODE                PIC XX.
