      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
       01  FX-REC.
           05  FX-ID                   PIC X(8).
           05  FX-CCY                  PIC X(3).
               88  FX-KNOWN-CCY        VALUE 'USD' 'EUR' 'GBP'
                                             'JPY' 'INR' 'CHF'.
           05  FX-AMOUNT               PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
