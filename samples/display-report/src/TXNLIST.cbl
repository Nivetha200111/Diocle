      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * TXNLIST - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   OPERATOR LISTING OF THE DAY'S TRANSACTIONS (DD TXNIN). IT
      *   WRITES NO FILE: THE LISTING GOES TO THE JOB LOG WITH DISPLAY.
      *   CREDITS AND DEBITS ARE TOTALLED; ANY TRANSACTION OF ANOTHER
      *   TYPE IS LISTED AS REJECTED AND SETS RETURN-CODE 4.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TXNLIST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TXN-FILE ASSIGN TO TXNIN
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-TXN-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  TXN-FILE.
       COPY TXNREC.
       WORKING-STORAGE SECTION.
       01  WS-TXN-STATUS               PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-TXNS             VALUE 'Y'.
       01  WS-AMT-EDIT                 PIC -(5)9.99.
       01  WS-TOT-EDIT                 PIC -(9)9.99.
       01  WS-CREDITS                  PIC S9(9)V99 VALUE 0.
       01  WS-DEBITS                   PIC S9(9)V99 VALUE 0.
       01  WS-COUNTERS.
           05  WS-LISTED-CNT           PIC 9(7) COMP VALUE 0.
           05  WS-REJECTED-CNT         PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT TXN-FILE
           IF WS-TXN-STATUS NOT = '00'
               DISPLAY 'TXNLIST OPEN TXNIN FAILED ' WS-TXN-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           DISPLAY 'TXNLIST DAILY LISTING'
           PERFORM 8000-READ
           PERFORM 2000-LIST UNTIL END-OF-TXNS
           CLOSE TXN-FILE
           PERFORM 9000-SUMMARY
           STOP RUN.

       2000-LIST.
           ADD 1 TO WS-LISTED-CNT
           MOVE TXN-AMOUNT TO WS-AMT-EDIT
           EVALUATE TRUE
               WHEN TXN-CREDIT
                   ADD TXN-AMOUNT TO WS-CREDITS
                   DISPLAY TXN-ID ' CR ' WS-AMT-EDIT
               WHEN TXN-DEBIT
                   ADD TXN-AMOUNT TO WS-DEBITS
                   DISPLAY TXN-ID ' DB ' WS-AMT-EDIT
               WHEN OTHER
                   ADD 1 TO WS-REJECTED-CNT
                   DISPLAY TXN-ID ' ?? ' WS-AMT-EDIT ' REJECTED'
           END-EVALUATE
           PERFORM 8000-READ.

       9000-SUMMARY.
           MOVE WS-CREDITS TO WS-TOT-EDIT
           DISPLAY 'CREDITS ' WS-TOT-EDIT
           MOVE WS-DEBITS TO WS-TOT-EDIT
           DISPLAY 'DEBITS  ' WS-TOT-EDIT
           DISPLAY 'LISTED ' WS-LISTED-CNT ' REJECTED ' WS-REJECTED-CNT
           IF WS-REJECTED-CNT > 0
               MOVE 4 TO RETURN-CODE
           END-IF.

       8000-READ.
           READ TXN-FILE
               AT END SET END-OF-TXNS TO TRUE
           END-READ.
