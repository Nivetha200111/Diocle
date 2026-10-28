      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
      * CLEARING ITEM: CHEQUE OR RETURN, SHARING ONE 39-BYTE BODY
       01  CQ-REC.
           05  CQ-TYPE                 PIC X.
               88  CQ-CHEQUE           VALUE 'C'.
               88  CQ-RETURN           VALUE 'R'.
           05  CQ-BODY                 PIC X(39).
           05  CQ-CHEQUE-BODY REDEFINES CQ-BODY.
               10  CQ-ACCT             PIC X(10).
               10  CQ-NUMBER           PIC 9(8).
               10  CQ-AMOUNT           PIC S9(7)V99
                                       SIGN LEADING SEPARATE.
               10  CQ-DATE             PIC 9(8).
               10  FILLER              PIC X(3).
           05  CQ-RETURN-BODY REDEFINES CQ-BODY.
               10  RT-ACCT             PIC X(10).
               10  RT-NUMBER           PIC 9(8).
               10  RT-REASON           PIC X(2).
                   88  RT-NSF          VALUE 'NS'.
                   88  RT-STOPPED      VALUE 'SP'.
               10  RT-FEE              PIC 9(3)V99.
               10  FILLER              PIC X(14).
