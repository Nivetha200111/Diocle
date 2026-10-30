      * DCLGEN-STYLE MEMBER FOR TABLE ACCOUNTS (SYNTHETIC)
           EXEC SQL DECLARE ACCOUNTS TABLE
               ( ACCT_ID      CHAR(8)       NOT NULL,
                 STATUS       CHAR(1)       NOT NULL,
                 BALANCE      DECIMAL(9,2)  NOT NULL,
                 LIMIT_AMT    DECIMAL(9,2)
               ) END-EXEC.
       01  DCLACCOUNTS.
           10  ACCT-ID                 PIC X(8).
           10  ACCT-STATUS             PIC X(1).
           10  ACCT-BALANCE            PIC S9(7)V99 COMP-3.
           10  ACCT-LIMIT              PIC S9(7)V99 COMP-3.
