      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * PACKED ACCOUNT EXTRACT, FIXED LENGTH (RECFM=FB, 33 BYTES)
       01  PK-REC.
           05  PK-ACCT                 PIC X(10).
           05  PK-BAL                  PIC S9(9)V99 COMP-3.
           05  PK-RATE                 PIC 9V9(4) COMP-3.
           05  PK-DAYS                 PIC S9(4) COMP.
           05  PK-ADJ                  PIC S9(5)V99.
           05  PK-LIMIT                PIC 9(3)PP.
           05  PK-ITEMS                PIC S9(4) COMP-5.
