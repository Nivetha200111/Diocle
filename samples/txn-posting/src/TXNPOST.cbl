      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * TXNPOST - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   POSTS ONE TRANSACTION PER RECORD AGAINST THE BALANCE CARRIED
      *   ON THE RECORD (DD TXNIN), WRITES ONE RESULT (DD POSTOUT).
      *   P = OUTGOING PAYMENT (SURCHARGE, OVERDRAFT LIMIT CHECK)
      *   F = FEE DEBIT, I = MONTHLY INTEREST CREDIT (ANNUAL / 12)
      * CHANGE HISTORY (FICTIONAL)
      *   1996-05-02 DLW  INITIAL VERSION
      *   1999-12-14 DLW  PAYMENT SURCHARGE AND CAP
      *   2004-08-30 HSN  OVERDRAFT LIMIT CHECK
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. TXNPOST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TXN-FILE ASSIGN TO TXNIN
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-TXN-STATUS.
           SELECT POST-FILE ASSIGN TO POSTOUT
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-POST-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  TXN-FILE.
       COPY TXNREC.
       FD  POST-FILE.
       COPY POSTREC.
       WORKING-STORAGE SECTION.
       01  WS-TXN-STATUS               PIC XX.
       01  WS-POST-STATUS              PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-TXNS             VALUE 'Y'.
       01  WS-SURCHARGE-RATE           PIC V9(4) VALUE .0125.
       01  WS-SURCHARGE-CAP            PIC S9(3)V99 COMP-3
                                       VALUE 15.00.
       01  WS-CHARGE                   PIC S9(3)V99 COMP-3.
       01  WS-CREDIT                   PIC S9(7)V99 COMP-3.
       01  WS-NEW-BAL                  PIC S9(9)V99 COMP-3.
       01  WS-FLOOR                    PIC S9(9)V99 COMP-3.
       01  WS-COUNTERS.
           05  WS-POSTED-CNT           PIC 9(7) COMP VALUE 0.
           05  WS-REJECT-CNT           PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           PERFORM 1000-INIT
           PERFORM 2000-PROCESS UNTIL END-OF-TXNS
           PERFORM 9000-TERM
           STOP RUN.

       1000-INIT.
           OPEN INPUT TXN-FILE
           IF WS-TXN-STATUS NOT = '00'
               DISPLAY 'TXNPOST OPEN TXNIN FAILED ' WS-TXN-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN OUTPUT POST-FILE
           IF WS-POST-STATUS NOT = '00'
               DISPLAY 'TXNPOST OPEN POSTOUT FAILED ' WS-POST-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 8000-READ.

       2000-PROCESS.
           MOVE ZERO TO WS-CHARGE
           MOVE TXN-BALANCE TO WS-NEW-BAL
           EVALUATE TRUE
               WHEN TXN-PAYMENT
                   PERFORM 3000-POST-PAYMENT
               WHEN TXN-FEE
                   COMPUTE WS-NEW-BAL = TXN-BALANCE - TXN-AMOUNT
                   MOVE 'FE' TO POST-STATUS
               WHEN TXN-INTEREST
                   COMPUTE WS-CREDIT ROUNDED = TXN-AMOUNT / 12
                   COMPUTE WS-NEW-BAL = TXN-BALANCE + WS-CREDIT
                   MOVE 'IC' TO POST-STATUS
               WHEN OTHER
                   MOVE 'RJ' TO POST-STATUS
           END-EVALUATE
           IF POST-STATUS = 'RJ' OR POST-STATUS = 'NS'
               ADD 1 TO WS-REJECT-CNT
           ELSE
               ADD 1 TO WS-POSTED-CNT
           END-IF
           PERFORM 5000-WRITE-RESULT
           PERFORM 8000-READ.

      * SURCHARGE IS 1.25 PERCENT, TRUNCATED TO THE CENT, THEN CAPPED.
      * A PAYMENT MAY TAKE THE BALANCE DOWN TO EXACTLY -OD-LIMIT, NOT
      * BELOW IT. REFUSED PAYMENTS LEAVE THE BALANCE AND CHARGE AS-IS.
       3000-POST-PAYMENT.
           IF TXN-AMOUNT NOT > ZERO
               MOVE 'RJ' TO POST-STATUS
           ELSE
               COMPUTE WS-CHARGE = TXN-AMOUNT * WS-SURCHARGE-RATE
               IF WS-CHARGE > WS-SURCHARGE-CAP
                   MOVE WS-SURCHARGE-CAP TO WS-CHARGE
               END-IF
               COMPUTE WS-NEW-BAL =
                   TXN-BALANCE - TXN-AMOUNT - WS-CHARGE
               COMPUTE WS-FLOOR = ZERO - TXN-OD-LIMIT
               IF WS-NEW-BAL < WS-FLOOR
                   MOVE TXN-BALANCE TO WS-NEW-BAL
                   MOVE ZERO TO WS-CHARGE
                   MOVE 'NS' TO POST-STATUS
               ELSE
                   MOVE 'OK' TO POST-STATUS
               END-IF
           END-IF.

       5000-WRITE-RESULT.
           MOVE TXN-ID     TO POST-TXN-ID
           MOVE WS-CHARGE  TO POST-CHARGE
           MOVE WS-NEW-BAL TO POST-NEW-BAL
           WRITE POST-REC.

       8000-READ.
           READ TXN-FILE
               AT END
                   SET END-OF-TXNS TO TRUE
           END-READ.

       9000-TERM.
           CLOSE TXN-FILE POST-FILE
           DISPLAY 'TXNPOST POSTED=' WS-POSTED-CNT
                   ' REJECTED=' WS-REJECT-CNT.
