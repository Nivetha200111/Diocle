      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
      * BRNCHSUM - CONTROL-BREAK SUMMARY BY BRANCH (INPUT SORTED BY
      *   BRANCH): COUNT, TOTAL, ROUNDED AVERAGE AND OVERDRAWN COUNT,
      *   THEN A GRAND TOTAL LINE WITH BRANCH 'ALL '.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. BRNCHSUM.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT BA-FILE ASSIGN TO BRIN.
           SELECT BS-FILE ASSIGN TO BROUT.
       DATA DIVISION.
       FILE SECTION.
       FD  BA-FILE RECORDING MODE IS F.
       COPY BRACCT.
       FD  BS-FILE RECORDING MODE IS F.
       COPY BRSUM.
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
       01  WS-PREV                     PIC X(4) VALUE SPACES.
       01  WS-COUNT                    PIC 9(4) COMP-3 VALUE 0.
       01  WS-TOTAL                    PIC S9(11)V99 COMP-3 VALUE 0.
       01  WS-OD                       PIC 9(3) COMP-3 VALUE 0.
       01  WS-AVG                      PIC S9(9)V99 COMP-3.
       01  WS-ALL-COUNT                PIC 9(4) COMP-3 VALUE 0.
       01  WS-ALL-TOTAL                PIC S9(11)V99 COMP-3 VALUE 0.
       01  WS-ALL-OD                   PIC 9(3) COMP-3 VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT BA-FILE OUTPUT BS-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ BA-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM 1000-ACCOUNT
               END-READ
           END-PERFORM
           IF WS-COUNT > 0
               PERFORM 2000-BREAK
           END-IF
           MOVE 'ALL ' TO BS-BRANCH
           MOVE WS-ALL-COUNT TO BS-COUNT
           MOVE WS-ALL-TOTAL TO BS-TOTAL
           IF WS-ALL-COUNT > 0
               COMPUTE WS-AVG ROUNDED = WS-ALL-TOTAL / WS-ALL-COUNT
           ELSE
               MOVE ZERO TO WS-AVG
           END-IF
           MOVE WS-AVG TO BS-AVERAGE
           MOVE WS-ALL-OD TO BS-OVERDRAWN
           WRITE BS-REC
           CLOSE BA-FILE BS-FILE
           STOP RUN.

       1000-ACCOUNT.
           IF BA-BRANCH NOT = WS-PREV AND WS-COUNT > 0
               PERFORM 2000-BREAK
           END-IF
           MOVE BA-BRANCH TO WS-PREV
           ADD 1 TO WS-COUNT WS-ALL-COUNT
           ADD BA-BALANCE TO WS-TOTAL WS-ALL-TOTAL
           IF BA-BALANCE < 0
               ADD 1 TO WS-OD WS-ALL-OD
           END-IF.

       2000-BREAK.
           MOVE WS-PREV TO BS-BRANCH
           MOVE WS-COUNT TO BS-COUNT
           MOVE WS-TOTAL TO BS-TOTAL
           COMPUTE WS-AVG ROUNDED = WS-TOTAL / WS-COUNT
           MOVE WS-AVG TO BS-AVERAGE
           MOVE WS-OD TO BS-OVERDRAWN
           WRITE BS-REC
           MOVE ZERO TO WS-COUNT WS-TOTAL WS-OD.
