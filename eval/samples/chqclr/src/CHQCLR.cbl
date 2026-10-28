      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
      * CHQCLR - CHEQUE CLEARING: CHEQUES DEBIT, RETURNS REVERSE AND
      *   CHARGE A FEE (NSF FEES ARE DOUBLED), OTHER TYPES REJECTED.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CHQCLR.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT CQ-FILE ASSIGN TO CHQIN.
           SELECT CL-FILE ASSIGN TO CLROUT.
       DATA DIVISION.
       FILE SECTION.
       FD  CQ-FILE RECORDING MODE IS F.
       COPY CHQREC.
       FD  CL-FILE RECORDING MODE IS F.
       COPY CLRREC.
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
       01  WS-TOTAL                    PIC S9(9)V99 COMP-3 VALUE 0.
       01  WS-TOTAL-ED                 PIC -(9)9.99.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT CQ-FILE OUTPUT CL-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ CQ-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM 1000-ITEM
               END-READ
           END-PERFORM
           CLOSE CQ-FILE CL-FILE
           MOVE WS-TOTAL TO WS-TOTAL-ED
           DISPLAY 'CHQCLR NET=' WS-TOTAL-ED
           STOP RUN.

       1000-ITEM.
           MOVE ZERO TO CL-FEE
           EVALUATE TRUE
               WHEN CQ-CHEQUE
                   MOVE CQ-ACCT   TO CL-ACCT
                   MOVE CQ-NUMBER TO CL-NUMBER
                   COMPUTE CL-DEBIT = ZERO - CQ-AMOUNT
                   MOVE 'CL' TO CL-CODE
               WHEN CQ-RETURN
                   MOVE RT-ACCT   TO CL-ACCT
                   MOVE RT-NUMBER TO CL-NUMBER
                   MOVE ZERO TO CL-DEBIT
                   IF RT-NSF
                       COMPUTE CL-FEE = RT-FEE * 2
                   ELSE
                       MOVE RT-FEE TO CL-FEE
                   END-IF
                   MOVE 'RT' TO CL-CODE
               WHEN OTHER
                   MOVE SPACES TO CL-ACCT
                   MOVE ZERO TO CL-NUMBER CL-DEBIT
                   MOVE 'RJ' TO CL-CODE
           END-EVALUATE
           ADD CL-DEBIT TO WS-TOTAL
           SUBTRACT CL-FEE FROM WS-TOTAL
           WRITE CL-REC.
