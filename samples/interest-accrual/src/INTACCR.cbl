      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * INTACCR - DAILY INTEREST ACCRUAL AND MAINTENANCE FEE
      *   READS THE ACCOUNT EXTRACT (DD ACCTIN), COMPUTES ACCRUED
      *   INTEREST AND FEES, WRITES ONE RESULT PER ACCOUNT (DD INTOUT).
      * CHANGE HISTORY (FICTIONAL)
      *   1994-03-11 RJK  INITIAL VERSION
      *   1998-11-02 MTP  OVERDRAFT PENALTY RATE ADDED
      *   2003-06-19 RJK  PREMIUM TIER FEE WAIVER
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. INTACCR.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTIN
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-ACCT-STATUS.
           SELECT OUT-FILE ASSIGN TO INTOUT
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-OUT-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-FILE.
       COPY ACCTREC.
       FD  OUT-FILE.
       COPY INTREC.
       WORKING-STORAGE SECTION.
       01  WS-ACCT-STATUS              PIC XX.
       01  WS-OUT-STATUS               PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-ACCOUNTS         VALUE 'Y'.
       01  WS-PENALTY-RATE             PIC 9V9(4) VALUE 0.0500.
       01  WS-FEE-FLOOR                PIC S9(5)V99 COMP-3
                                       VALUE 1000.00.
       01  WS-FEE-CAP                  PIC S9(5)V99 COMP-3
                                       VALUE 25.00.
       01  WS-INTEREST                 PIC S9(7)V99 COMP-3.
       01  WS-FEE                      PIC S9(5)V99 COMP-3.
       01  WS-NEW-BAL                  PIC S9(9)V99 COMP-3.
       01  WS-COUNTERS.
           05  WS-READ-CNT             PIC 9(7) COMP VALUE 0.
           05  WS-WRITE-CNT            PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2000-PROCESS UNTIL END-OF-ACCOUNTS
           PERFORM 9000-TERM
           STOP RUN.

       1000-INIT.
           OPEN INPUT ACCT-FILE
           IF WS-ACCT-STATUS NOT = '00'
               DISPLAY 'INTACCR OPEN ACCTIN FAILED ' WS-ACCT-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN OUTPUT OUT-FILE
           IF WS-OUT-STATUS NOT = '00'
               DISPLAY 'INTACCR OPEN INTOUT FAILED ' WS-OUT-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 8000-READ.

       2000-PROCESS.
           ADD 1 TO WS-READ-CNT
           PERFORM 3000-CALC-INTEREST
           PERFORM 4000-CALC-FEE
           PERFORM 5000-WRITE-RESULT
           PERFORM 8000-READ.

      * SIMPLE DAILY INTEREST, ACTUAL/365. CREDIT BALANCES EARN THE
      * ACCOUNT RATE; OVERDRAWN BALANCES ARE CHARGED RATE + PENALTY.
       3000-CALC-INTEREST.
           EVALUATE TRUE
               WHEN ACCT-BALANCE > ZERO
                   COMPUTE WS-INTEREST ROUNDED =
                       ACCT-BALANCE * ACCT-RATE * ACCT-DAYS / 365
               WHEN ACCT-BALANCE < ZERO
                   COMPUTE WS-INTEREST ROUNDED =
                       ACCT-BALANCE * (ACCT-RATE + WS-PENALTY-RATE)
                       * ACCT-DAYS / 365
               WHEN OTHER
                   MOVE ZERO TO WS-INTEREST
           END-EVALUATE.

      * MAINTENANCE FEE: 0.15 PERCENT OF THE SHORTFALL BELOW THE FLOOR,
      * TRUNCATED TO THE CENT, CAPPED. PREMIUM TIER IS WAIVED.
       4000-CALC-FEE.
           MOVE ZERO TO WS-FEE
           IF NOT ACCT-TIER-PREMIUM
              AND ACCT-BALANCE < WS-FEE-FLOOR
               COMPUTE WS-FEE =
                   (WS-FEE-FLOOR - ACCT-BALANCE) * 0.0015
               IF WS-FEE > WS-FEE-CAP
                   MOVE WS-FEE-CAP TO WS-FEE
               END-IF
           END-IF.

       5000-WRITE-RESULT.
           COMPUTE WS-NEW-BAL = ACCT-BALANCE + WS-INTEREST - WS-FEE
           MOVE ACCT-ID     TO OUT-ACCT-ID
           MOVE WS-INTEREST TO OUT-INTEREST
           MOVE WS-FEE      TO OUT-FEE
           MOVE WS-NEW-BAL  TO OUT-NEW-BAL
           EVALUATE TRUE
               WHEN WS-NEW-BAL < ZERO
                   MOVE 'OD' TO OUT-STATUS
               WHEN WS-FEE > ZERO
                   MOVE 'FE' TO OUT-STATUS
               WHEN OTHER
                   MOVE 'OK' TO OUT-STATUS
           END-EVALUATE
           WRITE OUT-REC
           ADD 1 TO WS-WRITE-CNT.

       8000-READ.
           READ ACCT-FILE
               AT END
                   SET END-OF-ACCOUNTS TO TRUE
           END-READ.

       9000-TERM.
           CLOSE ACCT-FILE OUT-FILE
           DISPLAY 'INTACCR READ=' WS-READ-CNT ' WRITTEN=' WS-WRITE-CNT.
