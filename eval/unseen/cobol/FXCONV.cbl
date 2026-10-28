      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
      * FXCONV - CONVERTS FOREIGN AMOUNTS TO ZZZ (THE FICTIONAL HOME
      *   CURRENCY) WITH A RATE TABLE BUILT FROM LITERALS. UNKNOWN
      *   CURRENCIES ARE REJECTED.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FXCONV.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FX-FILE ASSIGN TO FXIN.
           SELECT FO-FILE ASSIGN TO FXOUT.
       DATA DIVISION.
       FILE SECTION.
       FD  FX-FILE RECORDING MODE IS F.
       COPY FXREC.
       FD  FO-FILE RECORDING MODE IS F.
       COPY FXOUT.
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
       01  WS-RATE-DATA.
           05  FILLER  PIC X(13) VALUE 'USD0083125000'.
           05  FILLER  PIC X(13) VALUE 'EUR0090410000'.
           05  FILLER  PIC X(13) VALUE 'GBP0105333300'.
           05  FILLER  PIC X(13) VALUE 'JPY0000555550'.
           05  FILLER  PIC X(13) VALUE 'INR0000998770'.
       01  WS-RATE-TABLE REDEFINES WS-RATE-DATA.
           05  WS-RATE-ENTRY OCCURS 5 TIMES INDEXED BY RX.
               10  WS-RATE-CCY         PIC X(3).
               10  WS-RATE             PIC 9(4)V9(6).
       01  WS-CONVERTED                PIC S9(11)V99 COMP-3.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT FX-FILE OUTPUT FO-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ FX-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM 1000-CONVERT
               END-READ
           END-PERFORM
           CLOSE FX-FILE FO-FILE
           STOP RUN.

      * CHF IS A KNOWN CURRENCY WITH NO RATE: IT FALLS THROUGH THE
      * SEARCH AND IS REJECTED AS 'NR', NOT 'UC'.
       1000-CONVERT.
           MOVE FX-ID  TO FO-ID
           MOVE FX-CCY TO FO-CCY
           IF NOT FX-KNOWN-CCY
               MOVE ZERO TO FO-ZZZ FO-PRINT
               MOVE 'UC' TO FO-STATUS
           ELSE
               SET RX TO 1
               SEARCH WS-RATE-ENTRY
                   AT END
                       MOVE ZERO TO FO-ZZZ FO-PRINT
                       MOVE 'NR' TO FO-STATUS
                   WHEN WS-RATE-CCY(RX) = FX-CCY
                       COMPUTE WS-CONVERTED ROUNDED =
                           FX-AMOUNT * WS-RATE(RX)
                       MOVE WS-CONVERTED TO FO-ZZZ FO-PRINT
                       MOVE 'OK' TO FO-STATUS
               END-SEARCH
           END-IF
           WRITE FO-REC.
