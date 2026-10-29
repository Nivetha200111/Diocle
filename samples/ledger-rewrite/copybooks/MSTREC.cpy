      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * ACCOUNT MASTER, UPDATED IN PLACE (26 BYTES)
       01  MST-REC.
           05  MST-ACCT-ID             PIC X(8).
           05  MST-STATUS              PIC X.
               88  MST-ACTIVE          VALUE 'A'.
               88  MST-CLOSED          VALUE 'C'.
               88  MST-OVERDRAWN       VALUE 'O'.
           05  MST-BALANCE             PIC S9(7)V99.
           05  MST-RATE                PIC 9V9(4).
           05  MST-FEE-CNT             PIC 9(3).
