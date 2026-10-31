      * SYNTHETIC: written for Diocle's tests (Quillmark, fictional).
       01  ACCT-REC.
           05  ACCT-ID             PIC X(6).
           05  ACCT-TYPE           PIC X.
               88  ACCT-SAVINGS    VALUE 'S'.
               88  ACCT-CHECKING   VALUE 'C'.
           05  ACCT-BAL            PIC S9(7)V99 SIGN LEADING SEPARATE.
