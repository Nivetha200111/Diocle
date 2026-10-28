      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * ACCTMTCH - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   CLASSIC SEQUENTIAL MATCH-MERGE: APPLIES THE DAY'S SORTED
      *   TRANSACTIONS (DD TXNIN) TO THE SORTED ACCOUNT MASTER (DD
      *   MSTIN), WRITES THE NEW MASTER (DD NEWMST) AND AN EXCEPTION
      *   REPORT (DD EXCOUT) FOR UNKNOWN ACCOUNTS, FROZEN ACCOUNTS AND
      *   UNKNOWN TRANSACTION TYPES.
      * CHANGE HISTORY (FICTIONAL)
      *   1991-04-08 HBK  INITIAL VERSION
      *   1996-10-21 HBK  FROZEN ACCOUNTS REJECT TRANSACTIONS
      *   2001-03-05 SDV  RETURN CODE 4 WHEN ANY EXCEPTION IS WRITTEN
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTMTCH.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT MST-FILE ASSIGN TO MSTIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT TXN-FILE ASSIGN TO TXNIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT NEW-FILE ASSIGN TO NEWMST
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT EXC-FILE ASSIGN TO EXCOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  MST-FILE.
       COPY MSTREC.
       FD  TXN-FILE.
       COPY TXREC.
       FD  NEW-FILE.
       COPY NEWMST.
       FD  EXC-FILE.
       COPY EXCREC.
       WORKING-STORAGE SECTION.
       01  WS-MST-KEY                  PIC X(8).
       01  WS-TXN-KEY                  PIC X(8).
       01  WS-BALANCE                  PIC S9(9)V99 COMP-3.
       01  WS-COUNT                    PIC 9(4).
       01  WS-EXC-CNT                  PIC 9(7) COMP VALUE 0.
       01  WS-NEW-CNT                  PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT MST-FILE TXN-FILE
           OPEN OUTPUT NEW-FILE EXC-FILE
           PERFORM 8100-READ-MST
           PERFORM 8200-READ-TXN
           PERFORM 2000-MATCH
               UNTIL WS-MST-KEY = HIGH-VALUES
                 AND WS-TXN-KEY = HIGH-VALUES
           CLOSE MST-FILE TXN-FILE NEW-FILE EXC-FILE
           DISPLAY 'ACCTMTCH NEW=' WS-NEW-CNT ' EXC=' WS-EXC-CNT
           IF WS-EXC-CNT > 0
               MOVE 4 TO RETURN-CODE
           END-IF
           STOP RUN.

      * KEYS ARE COMPARED IN THE PROGRAM'S COLLATING SEQUENCE: ON THE
      * MAINFRAME THAT IS EBCDIC, SO DIGITS SORT AFTER LETTERS.
       2000-MATCH.
           EVALUATE TRUE
               WHEN WS-TXN-KEY < WS-MST-KEY
                   MOVE TX-ACCT-ID TO EX-ACCT-ID
                   MOVE TX-AMOUNT  TO EX-AMOUNT
                   MOVE 'NO ACCOUNT' TO EX-REASON
                   PERFORM 7000-WRITE-EXC
                   PERFORM 8200-READ-TXN
               WHEN WS-TXN-KEY = WS-MST-KEY
                   PERFORM 3000-APPLY
                   PERFORM 8200-READ-TXN
               WHEN OTHER
                   PERFORM 4000-WRITE-MASTER
                   PERFORM 8100-READ-MST
           END-EVALUATE.

       3000-APPLY.
           IF MS-FROZEN
               MOVE TX-ACCT-ID TO EX-ACCT-ID
               MOVE TX-AMOUNT  TO EX-AMOUNT
               MOVE 'FROZEN' TO EX-REASON
               PERFORM 7000-WRITE-EXC
           ELSE
               EVALUATE TRUE
                   WHEN TX-CREDIT
                       ADD TX-AMOUNT TO WS-BALANCE
                       ADD 1 TO WS-COUNT
                   WHEN TX-DEBIT
                       SUBTRACT TX-AMOUNT FROM WS-BALANCE
                       ADD 1 TO WS-COUNT
                   WHEN OTHER
                       MOVE TX-ACCT-ID TO EX-ACCT-ID
                       MOVE TX-AMOUNT  TO EX-AMOUNT
                       MOVE 'BAD TYPE' TO EX-REASON
                       PERFORM 7000-WRITE-EXC
               END-EVALUATE
           END-IF.

       4000-WRITE-MASTER.
           MOVE MS-ACCT-ID TO NM-ACCT-ID
           MOVE WS-BALANCE TO NM-BALANCE
           MOVE MS-STATUS  TO NM-STATUS
           MOVE WS-COUNT   TO NM-TXN-COUNT
           WRITE NM-REC
           ADD 1 TO WS-NEW-CNT.

       7000-WRITE-EXC.
           WRITE EX-REC
           ADD 1 TO WS-EXC-CNT.

       8100-READ-MST.
           READ MST-FILE
               AT END
                   MOVE HIGH-VALUES TO WS-MST-KEY
               NOT AT END
                   MOVE MS-ACCT-ID TO WS-MST-KEY
                   MOVE MS-BALANCE TO WS-BALANCE
                   MOVE ZERO TO WS-COUNT
           END-READ.

       8200-READ-TXN.
           READ TXN-FILE
               AT END
                   MOVE HIGH-VALUES TO WS-TXN-KEY
               NOT AT END
                   MOVE TX-ACCT-ID TO WS-TXN-KEY
           END-READ.
