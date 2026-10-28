      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * POSTING RESULT (29 BYTES)
       01  POST-REC.
           05  POST-TXN-ID             PIC X(9).
           05  POST-CHARGE             PIC S9(3)V99
                                       SIGN LEADING SEPARATE.
           05  POST-NEW-BAL            PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  POST-STATUS             PIC XX.
