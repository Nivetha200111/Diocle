      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * LDGRWRT - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   MONTHLY ACCOUNT MASTER UPDATE IN PLACE (DD ACCTMST, OPENED
      *   I-O). EVERY OPEN ACCOUNT EARNS ONE MONTH OF INTEREST; LOW
      *   BALANCES PAY A SERVICE FEE; AN ACCOUNT THAT ENDS BELOW ZERO
      *   IS MARKED OVERDRAWN. CLOSED ACCOUNTS ARE LEFT ALONE.
      *   RETURN-CODE 4 WHEN ANY ACCOUNT ENDED OVERDRAWN.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LDGRWRT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MST-FILE ASSIGN TO ACCTMST
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-MST-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  MST-FILE.
       COPY MSTREC.
       WORKING-STORAGE SECTION.
       01  WS-MST-STATUS               PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-MASTER           VALUE 'Y'.
       01  WS-INTEREST                 PIC S9(7)V99.
       01  WS-FEE                      PIC 9V99 VALUE 2.50.
       01  WS-COUNTERS.
           05  WS-READ-CNT             PIC 9(7) COMP VALUE 0.
           05  WS-UPDATED-CNT          PIC 9(7) COMP VALUE 0.
           05  WS-OVERDRAWN-CNT        PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN I-O MST-FILE
           IF WS-MST-STATUS NOT = '00'
               DISPLAY 'LDGRWRT OPEN ACCTMST FAILED ' WS-MST-STATUS
               MOVE 16 TO RETURN-CODE
               STOP RUN
           END-IF
           PERFORM 8000-READ
           PERFORM 2000-PROCESS UNTIL END-OF-MASTER
           CLOSE MST-FILE
           DISPLAY 'LDGRWRT READ ' WS-READ-CNT ' UPDATED '
               WS-UPDATED-CNT ' OVERDRAWN ' WS-OVERDRAWN-CNT
           IF WS-OVERDRAWN-CNT > 0
               MOVE 4 TO RETURN-CODE
           END-IF
           STOP RUN.

       2000-PROCESS.
           ADD 1 TO WS-READ-CNT
           IF NOT MST-CLOSED
               PERFORM 3000-POST
               REWRITE MST-REC
               ADD 1 TO WS-UPDATED-CNT
           END-IF
           PERFORM 8000-READ.

      * ONE MONTH OF INTEREST, ROUNDED, THEN THE FEE ON LOW POSITIVE
      * BALANCES. NO ON SIZE ERROR: HIGH-ORDER DIGITS DROP SILENTLY.
       3000-POST.
           COMPUTE WS-INTEREST ROUNDED = MST-BALANCE * MST-RATE / 12
           ADD WS-INTEREST TO MST-BALANCE
           IF MST-BALANCE >= 0 AND MST-BALANCE < 100.00
               SUBTRACT WS-FEE FROM MST-BALANCE
               ADD 1 TO MST-FEE-CNT
           END-IF
           IF MST-BALANCE < 0
               MOVE 'O' TO MST-STATUS
               ADD 1 TO WS-OVERDRAWN-CNT
           END-IF.

       8000-READ.
           READ MST-FILE
               AT END SET END-OF-MASTER TO TRUE
           END-READ.
