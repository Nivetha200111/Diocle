      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * MONTHLY FEE INPUT: ONE ACCOUNT PER RECORD (29 BYTES)
       01  FEE-REC.
           05  FEE-ACCT-ID             PIC X(10).
           05  FEE-PRODUCT             PIC X.
               88  PRODUCT-BASIC       VALUE 'A'.
               88  PRODUCT-PLUS        VALUE 'B'.
               88  PRODUCT-PRIVATE     VALUE 'C'.
           05  FEE-AVG-BAL             PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  FEE-TXN-COUNT           PIC 9(4).
           05  FEE-MONTH-DAYS          PIC 9(2).
