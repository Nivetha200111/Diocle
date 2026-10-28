      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
      * LOANAMRT - FIRST-YEAR AMORTIZATION SCHEDULE, DECLINING BALANCE
      *   ONE INPUT LOAN PRODUCES UP TO 12 SCHEDULE RECORDS.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOANAMRT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LN-FILE ASSIGN TO LOANIN.
           SELECT AM-FILE ASSIGN TO AMRTOUT.
       DATA DIVISION.
       FILE SECTION.
       FD  LN-FILE RECORDING MODE IS F.
       COPY LOANREC.
       FD  AM-FILE RECORDING MODE IS F.
       COPY AMRTREC.
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
       01  WS-BAL                      PIC S9(9)V99 COMP-3.
       01  WS-PRIN-PART                PIC S9(7)V99 COMP-3.
       01  WS-INT                      PIC S9(7)V99 COMP-3.
       01  WS-YEAR                     PIC 9(4).
       01  WS-MONTH                    PIC 99.
       01  WS-PERIODS                  PIC 9(3).
       01  WS-P                        PIC 9(3).
       01  WS-LOANS                    PIC 9(5) VALUE 0.
       01  WS-REJECTS                  PIC 9(5) VALUE 0.
       01  WS-LINES                    PIC 9(7) VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT LN-FILE OUTPUT AM-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ LN-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM 1000-LOAN
               END-READ
           END-PERFORM
           CLOSE LN-FILE AM-FILE
           DISPLAY 'LOANAMRT LOANS=' WS-LOANS ' REJECTS=' WS-REJECTS
                   ' LINES=' WS-LINES
           STOP RUN.

       1000-LOAN.
           IF LN-TERM = 0 OR LN-PRINCIPAL NOT > 0
              OR LN-START(5:2) < '01' OR LN-START(5:2) > '12'
               ADD 1 TO WS-REJECTS
           ELSE
               ADD 1 TO WS-LOANS
               MOVE LN-PRINCIPAL TO WS-BAL
               COMPUTE WS-PRIN-PART ROUNDED = LN-PRINCIPAL / LN-TERM
               MOVE LN-START(1:4) TO WS-YEAR
               MOVE LN-START(5:2) TO WS-MONTH
               MOVE LN-TERM TO WS-PERIODS
               IF WS-PERIODS > 12
                   MOVE 12 TO WS-PERIODS
               END-IF
               PERFORM 2000-PERIOD VARYING WS-P FROM 1 BY 1
                   UNTIL WS-P > WS-PERIODS
           END-IF.

      * INTEREST ON THE OPENING BALANCE, ROUNDED; THE LAST PERIOD OF THE
      * TERM PAYS WHATEVER PRINCIPAL IS LEFT.
       2000-PERIOD.
           COMPUTE WS-INT ROUNDED = WS-BAL * LN-RATE / 12
           IF WS-P = LN-TERM
               MOVE WS-BAL TO WS-PRIN-PART
           END-IF
           SUBTRACT WS-PRIN-PART FROM WS-BAL
           MOVE LN-ID TO AM-ID
           MOVE WS-P TO AM-PERIOD
           COMPUTE AM-YYYYMM = WS-YEAR * 100 + WS-MONTH
           COMPUTE AM-PAYMENT = WS-PRIN-PART + WS-INT
           MOVE WS-INT TO AM-INTEREST
           MOVE WS-BAL TO AM-BALANCE
           WRITE AM-REC
           ADD 1 TO WS-LINES
           ADD 1 TO WS-MONTH
           IF WS-MONTH > 12
               MOVE 1 TO WS-MONTH
               ADD 1 TO WS-YEAR
           END-IF.
