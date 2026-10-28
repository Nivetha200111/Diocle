      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * DAYCTRL - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   DAILY INTEREST ACCRUAL WITH A RUNNING CONTROL TOTAL FOR THE
      *   GENERAL LEDGER RECONCILIATION (DD DAYIN -> DD CTLOUT).
      *   EACH ACCOUNT'S INTEREST IS ROUNDED BEFORE IT IS ADDED, SO THE
      *   CONTROL TOTAL EQUALS THE SUM OF THE POSTED AMOUNTS.
      * CHANGE HISTORY (FICTIONAL)
      *   1997-09-15 KTB  INITIAL VERSION
      *   2000-03-01 KTB  LEAP-DAY RECONCILIATION FIX: ROUND PER RECORD
      *   2005-10-24 JWE  FLAG ACCRUALS LOST TO ROUNDING
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DAYCTRL.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT DAY-FILE ASSIGN TO DAYIN
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-DAY-STATUS.
           SELECT CTL-FILE ASSIGN TO CTLOUT
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-CTL-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  DAY-FILE.
       COPY DAYREC.
       FD  CTL-FILE.
       COPY CTLREC.
       WORKING-STORAGE SECTION.
       01  WS-DAY-STATUS               PIC XX.
       01  WS-CTL-STATUS               PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-ACCOUNTS         VALUE 'Y'.
       01  WS-INTEREST                 PIC S9(7)V99 COMP-3.
       01  WS-CTL-TOTAL                PIC S9(11)V99 COMP-3 VALUE 0.
       01  WS-CTL-EDIT                 PIC -(11)9.99.
       01  WS-COUNTERS.
           05  WS-READ-CNT             PIC 9(7) COMP VALUE 0.
           05  WS-LOST-CNT             PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2000-PROCESS UNTIL END-OF-ACCOUNTS
           PERFORM 9000-TERM
           STOP RUN.

       1000-INIT.
           OPEN INPUT DAY-FILE
           IF WS-DAY-STATUS NOT = '00'
               DISPLAY 'DAYCTRL OPEN DAYIN FAILED ' WS-DAY-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN OUTPUT CTL-FILE
           IF WS-CTL-STATUS NOT = '00'
               DISPLAY 'DAYCTRL OPEN CTLOUT FAILED ' WS-CTL-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 8000-READ.

       2000-PROCESS.
           ADD 1 TO WS-READ-CNT
           PERFORM 3000-ACCRUE
           PERFORM 5000-WRITE-RESULT
           PERFORM 8000-READ.

      * SIMPLE INTEREST, ACTUAL/365, ROUNDED PER ACCOUNT. OVERDRAWN
      * PRINCIPALS ACCRUE NEGATIVE INTEREST AT THE SAME RATE.
       3000-ACCRUE.
           COMPUTE WS-INTEREST ROUNDED =
               DAY-PRINCIPAL * DAY-RATE * DAY-DAYS / 365
           ADD WS-INTEREST TO WS-CTL-TOTAL
           IF WS-INTEREST = ZERO AND DAY-PRINCIPAL NOT = ZERO
              AND DAY-RATE NOT = ZERO AND DAY-DAYS NOT = ZERO
               MOVE 'Z' TO CTL-FLAG
               ADD 1 TO WS-LOST-CNT
           ELSE
               MOVE '-' TO CTL-FLAG
           END-IF.

       5000-WRITE-RESULT.
           MOVE DAY-ACCT-ID  TO CTL-ACCT-ID
           MOVE WS-INTEREST  TO CTL-INTEREST
           MOVE WS-CTL-TOTAL TO CTL-RUN-TOTAL
           WRITE CTL-REC.

       8000-READ.
           READ DAY-FILE
               AT END
                   SET END-OF-ACCOUNTS TO TRUE
           END-READ.

       9000-TERM.
           CLOSE DAY-FILE CTL-FILE
           MOVE WS-CTL-TOTAL TO WS-CTL-EDIT
           DISPLAY 'DAYCTRL ACCOUNTS=' WS-READ-CNT
                   ' LOST=' WS-LOST-CNT
                   ' CONTROL=' WS-CTL-EDIT.
