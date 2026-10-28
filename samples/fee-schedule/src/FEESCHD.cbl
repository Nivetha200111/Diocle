      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * FEESCHD - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   MONTHLY ACCOUNT CHARGES BY PRODUCT (DD FEEIN -> DD CHGOUT):
      *   BASE FEE, EXCESS TRANSACTION FEE AND OVERDRAFT INTEREST ON A
      *   NEGATIVE AVERAGE BALANCE. BASIC AND PLUS TOTALS ARE CAPPED.
      * CHANGE HISTORY (FICTIONAL)
      *   1995-02-20 PQA  INITIAL VERSION
      *   2001-07-09 PQA  BALANCE WAIVER OF THE BASE FEE
      *   2006-01-16 RMV  OVERDRAFT INTEREST AT 18.99 PERCENT
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FEESCHD.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEE-FILE ASSIGN TO FEEIN
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-FEE-STATUS.
           SELECT CHG-FILE ASSIGN TO CHGOUT
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-CHG-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  FEE-FILE.
       COPY FEEREC.
       FD  CHG-FILE.
       COPY CHGREC.
       WORKING-STORAGE SECTION.
       01  WS-FEE-STATUS               PIC XX.
       01  WS-CHG-STATUS               PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-ACCOUNTS         VALUE 'Y'.
       01  WS-WAIVER-BAL               PIC S9(9)V99 COMP-3
                                       VALUE 5000.00.
       01  WS-PER-TXN                  PIC 9V99 VALUE 0.35.
       01  WS-OD-RATE                  PIC 9V9(4) VALUE 0.1899.
       01  WS-CAP                      PIC S9(3)V99 COMP-3
                                       VALUE 40.00.
       01  WS-BASE                     PIC S9(3)V99 COMP-3.
       01  WS-FREE-TXNS                PIC 9(4) COMP-3.
       01  WS-EXCESS                   PIC S9(5) COMP-3.
       01  WS-TXN-FEE                  PIC S9(3)V99 COMP-3.
       01  WS-OD-INT                   PIC S9(5)V99 COMP-3.
       01  WS-TOTAL                    PIC S9(3)V99 COMP-3.
       01  WS-CODE                     PIC XX.
       01  WS-COUNTERS.
           05  WS-READ-CNT             PIC 9(7) COMP VALUE 0.
           05  WS-CAPPED-CNT           PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2000-PROCESS UNTIL END-OF-ACCOUNTS
           PERFORM 9000-TERM
           STOP RUN.

       1000-INIT.
           OPEN INPUT FEE-FILE
           IF WS-FEE-STATUS NOT = '00'
               DISPLAY 'FEESCHD OPEN FEEIN FAILED ' WS-FEE-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN OUTPUT CHG-FILE
           IF WS-CHG-STATUS NOT = '00'
               DISPLAY 'FEESCHD OPEN CHGOUT FAILED ' WS-CHG-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 8000-READ.

       2000-PROCESS.
           ADD 1 TO WS-READ-CNT
           MOVE 'OK' TO WS-CODE
           PERFORM 3000-BASE-FEE
           PERFORM 4000-TXN-FEE
           PERFORM 5000-OD-INTEREST
           PERFORM 6000-TOTAL
           PERFORM 7000-WRITE-RESULT
           PERFORM 8000-READ.

      * BASE FEE BY PRODUCT. WAIVED WHEN THE AVERAGE BALANCE IS AT OR
      * ABOVE THE WAIVER BALANCE.
       3000-BASE-FEE.
           EVALUATE TRUE
               WHEN PRODUCT-BASIC
                   MOVE 6.00 TO WS-BASE
                   MOVE 10   TO WS-FREE-TXNS
               WHEN PRODUCT-PLUS
                   MOVE 3.50 TO WS-BASE
                   MOVE 25   TO WS-FREE-TXNS
               WHEN OTHER
                   MOVE ZERO TO WS-BASE
                   MOVE 9999 TO WS-FREE-TXNS
           END-EVALUATE
           IF FEE-AVG-BAL NOT < WS-WAIVER-BAL AND WS-BASE > ZERO
               MOVE ZERO TO WS-BASE
               MOVE 'WV' TO WS-CODE
           END-IF.

       4000-TXN-FEE.
           COMPUTE WS-EXCESS = FEE-TXN-COUNT - WS-FREE-TXNS
           IF WS-EXCESS > ZERO
               COMPUTE WS-TXN-FEE = WS-EXCESS * WS-PER-TXN
           ELSE
               MOVE ZERO TO WS-TXN-FEE
           END-IF.

      * OVERDRAFT INTEREST: 18.99 PERCENT A YEAR ON A NEGATIVE AVERAGE
      * BALANCE FOR THE DAYS IN THE MONTH, ROUNDED, CHARGED POSITIVE.
       5000-OD-INTEREST.
           IF FEE-AVG-BAL < ZERO
               COMPUTE WS-OD-INT ROUNDED =
                   ZERO - FEE-AVG-BAL * WS-OD-RATE
                   * FEE-MONTH-DAYS / 365
           ELSE
               MOVE ZERO TO WS-OD-INT
           END-IF.

      * THE TOTAL IS ACCUMULATED IN S9(3)V99. BASIC AND PLUS TOTALS ARE
      * CAPPED; PRIVATE IS NOT.
       6000-TOTAL.
           COMPUTE WS-TOTAL = WS-BASE + WS-TXN-FEE + WS-OD-INT
           IF NOT PRODUCT-PRIVATE AND WS-TOTAL > WS-CAP
               MOVE WS-CAP TO WS-TOTAL
               MOVE 'CP' TO WS-CODE
               ADD 1 TO WS-CAPPED-CNT
           END-IF.

       7000-WRITE-RESULT.
           MOVE FEE-ACCT-ID TO CHG-ACCT-ID
           MOVE WS-BASE     TO CHG-BASE
           MOVE WS-TXN-FEE  TO CHG-TXN-FEE
           MOVE WS-OD-INT   TO CHG-OD-INT
           MOVE WS-TOTAL    TO CHG-TOTAL
           MOVE WS-CODE     TO CHG-CODE
           WRITE CHG-REC.

       8000-READ.
           READ FEE-FILE
               AT END
                   SET END-OF-ACCOUNTS TO TRUE
           END-READ.

       9000-TERM.
           CLOSE FEE-FILE CHG-FILE
           DISPLAY 'FEESCHD ACCOUNTS=' WS-READ-CNT
                   ' CAPPED=' WS-CAPPED-CNT.
