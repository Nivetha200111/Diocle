      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * CUSTUPD - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   APPLIES A DAY'S CUSTOMER UPDATES (DD TRANIN: A=ADD, C=CHANGE
      *   BALANCE AND NAME, D=DELETE) TO THE KEYED CUSTOMER MASTER
      *   (DD CUSTMAST, INDEXED, ONE RECORD KEY). EVERY FILE STATUS IS
      *   CHECKED; A FAILED UPDATE IS WRITTEN TO THE REJECT REPORT
      *   (DD REJOUT). A LAST PASS WITH START / READ NEXT ADDS UP THE
      *   MASTER FROM ID '999999' UPWARD INTO A SUMMARY LINE.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CUSTUPD.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT TRAN-FILE ASSIGN TO TRANIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT CUST-FILE ASSIGN TO CUSTMAST
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS CM-CUST-ID
               FILE STATUS IS WS-CUST-STATUS.
           SELECT REJ-FILE ASSIGN TO REJOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  TRAN-FILE.
       COPY TRNREC.
       FD  CUST-FILE.
       COPY CUSTREC.
       FD  REJ-FILE.
       COPY REJREC.
       WORKING-STORAGE SECTION.
       01  WS-CUST-STATUS              PIC XX.
       01  WS-EOF                      PIC X VALUE 'N'.
           88  END-OF-TRANS            VALUE 'Y'.
       01  WS-COUNT                    PIC 9(5) VALUE 0.
       01  WS-TOTAL                    PIC S9(9)V99 VALUE 0.
       01  WS-COUNT-OUT                PIC 9(5).
       01  WS-TOTAL-OUT                PIC -9(9).99.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT TRAN-FILE
           OPEN I-O CUST-FILE
           IF WS-CUST-STATUS NOT = '00'
               DISPLAY 'CUSTMAST OPEN FAILED ' WS-CUST-STATUS
               MOVE 12 TO RETURN-CODE
               STOP RUN
           END-IF
           OPEN OUTPUT REJ-FILE
           PERFORM 8000-READ
           PERFORM 1000-APPLY UNTIL END-OF-TRANS
           PERFORM 3000-SUMMARY
           CLOSE TRAN-FILE CUST-FILE REJ-FILE
           STOP RUN.
       1000-APPLY.
           EVALUATE TRUE
               WHEN TR-ADD
                   PERFORM 1100-ADD
               WHEN TR-CHANGE
                   PERFORM 1200-CHANGE
               WHEN TR-DELETE
                   PERFORM 1300-DELETE
               WHEN OTHER
                   MOVE 'BAD CODE    ' TO RJ-REASON
                   PERFORM 2000-REJECT
           END-EVALUATE
           PERFORM 8000-READ.
       1100-ADD.
           MOVE 'AA' TO CM-REGION
           MOVE TR-CUST-ID TO CM-CUST-ID
           MOVE TR-NAME TO CM-NAME
           MOVE TR-AMOUNT TO CM-BALANCE
           MOVE 'N' TO CM-STATUS
           WRITE CUST-REC
           IF WS-CUST-STATUS = '22'
               MOVE 'DUPLICATE   ' TO RJ-REASON
               PERFORM 2000-REJECT
           ELSE
               IF WS-CUST-STATUS NOT = '00'
                   MOVE 'WRITE ERROR ' TO RJ-REASON
                   PERFORM 2000-REJECT
               END-IF
           END-IF.
       1200-CHANGE.
           MOVE TR-CUST-ID TO CM-CUST-ID
           READ CUST-FILE
           IF WS-CUST-STATUS = '23'
               MOVE 'NOT FOUND   ' TO RJ-REASON
               PERFORM 2000-REJECT
           ELSE
               IF WS-CUST-STATUS NOT = '00'
                   MOVE 'READ ERROR  ' TO RJ-REASON
                   PERFORM 2000-REJECT
               ELSE
                   ADD TR-AMOUNT TO CM-BALANCE
                   MOVE TR-NAME TO CM-NAME
                   MOVE 'C' TO CM-STATUS
                   REWRITE CUST-REC
                   IF WS-CUST-STATUS NOT = '00'
                       MOVE 'REWRITE ERR ' TO RJ-REASON
                       PERFORM 2000-REJECT
                   END-IF
               END-IF
           END-IF.
       1300-DELETE.
           MOVE TR-CUST-ID TO CM-CUST-ID
           DELETE CUST-FILE
           IF WS-CUST-STATUS = '23'
               MOVE 'NOT FOUND   ' TO RJ-REASON
               PERFORM 2000-REJECT
           ELSE
               IF WS-CUST-STATUS NOT = '00'
                   MOVE 'DELETE ERROR' TO RJ-REASON
                   PERFORM 2000-REJECT
               END-IF
           END-IF.
       2000-REJECT.
           MOVE 'REJECT' TO RJ-TAG
           MOVE TR-CUST-ID TO RJ-CUST-ID
           MOVE TR-CODE TO RJ-CODE
           MOVE WS-CUST-STATUS TO RJ-STATUS
           WRITE REJ-REC.
       3000-SUMMARY.
           MOVE '999999' TO CM-CUST-ID
           START CUST-FILE KEY IS >= CM-CUST-ID
               INVALID KEY
                   MOVE 'NO RECORDS  ' TO RJ-REASON
                   MOVE 'SUMARY' TO RJ-TAG
                   MOVE SPACES TO RJ-CUST-ID
                   MOVE SPACE TO RJ-CODE
                   MOVE WS-CUST-STATUS TO RJ-STATUS
                   WRITE REJ-REC
           END-START
           IF WS-CUST-STATUS = '00'
               PERFORM 3100-NEXT UNTIL WS-CUST-STATUS NOT = '00'
               MOVE WS-COUNT TO WS-COUNT-OUT
               MOVE WS-TOTAL TO WS-TOTAL-OUT
               MOVE 'SUMARY' TO RJ-TAG
               MOVE WS-COUNT-OUT TO RJ-CUST-ID
               MOVE SPACE TO RJ-CODE
               MOVE WS-TOTAL-OUT TO RJ-REASON
               MOVE WS-CUST-STATUS TO RJ-STATUS
               WRITE REJ-REC
           END-IF.
       3100-NEXT.
           READ CUST-FILE NEXT
           IF WS-CUST-STATUS = '00'
               ADD 1 TO WS-COUNT
               ADD CM-BALANCE TO WS-TOTAL
           END-IF.
       8000-READ.
           READ TRAN-FILE
               AT END SET END-OF-TRANS TO TRUE
           END-READ.
