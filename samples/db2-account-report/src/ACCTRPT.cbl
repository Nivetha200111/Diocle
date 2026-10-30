      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * ACCTRPT - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   POSTS A DAY'S ADJUSTMENTS (DD ACCTIN) TO TABLE ACCOUNTS:
      *   SELECT THE BALANCE, REJECT AN ADJUSTMENT THAT WOULD PASS THE
      *   OVERDRAFT LIMIT (NULL LIMIT = NONE ALLOWED), UPDATE THE
      *   BALANCE AND INSERT AN AUDIT ROW. COMMIT EVERY 50 ACCOUNTS.
      *   THEN LIST EVERY ACCOUNT UNDER 100.00 WITH A CURSOR (DD RPTOUT).
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTRPT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT RPT-FILE ASSIGN TO RPTOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-FILE.
       COPY ACCTIN.
       FD  RPT-FILE.
       COPY RPTREC.
       WORKING-STORAGE SECTION.
           EXEC SQL INCLUDE SQLCA END-EXEC.
           EXEC SQL INCLUDE ACCTDCL END-EXEC.
       01  WS-EOF                      PIC X VALUE 'N'.
           88  END-OF-ACCTS            VALUE 'Y'.
       01  WS-BAL                      PIC S9(7)V99 COMP-3.
       01  WS-LIMIT                    PIC S9(7)V99 COMP-3.
       01  WS-LIMIT-IND                PIC S9(4) COMP.
       01  WS-NEW                      PIC S9(7)V99 COMP-3.
       01  WS-FLOOR                    PIC S9(7)V99 COMP-3.
       01  WS-LOW                      PIC S9(7)V99 COMP-3 VALUE 100.00.
       01  WS-SEQ                      PIC S9(9) COMP VALUE 1.
       01  WS-DONE                     PIC 9(5) COMP VALUE 0.
       01  WS-LOW-ID                   PIC X(8).
       01  WS-LOW-BAL                  PIC S9(7)V99 COMP-3.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT ACCT-FILE
           OPEN OUTPUT RPT-FILE
           PERFORM 8000-READ
           PERFORM 1000-POST UNTIL END-OF-ACCTS
           EXEC SQL COMMIT END-EXEC
           PERFORM 3000-LOW-BALANCES
           CLOSE ACCT-FILE RPT-FILE
           STOP RUN.

       1000-POST.
           MOVE SPACES TO RPT-REC
           MOVE AI-ACCT-ID TO RPT-ACCT
           EXEC SQL
               SELECT BALANCE, LIMIT_AMT
                 INTO :WS-BAL, :WS-LIMIT :WS-LIMIT-IND
                 FROM ACCOUNTS
                WHERE ACCT_ID = :AI-ACCT-ID
           END-EXEC
           EVALUATE SQLCODE
               WHEN 0
                   PERFORM 2000-APPLY
               WHEN 100
                   MOVE 'NOACCT' TO RPT-TAG
                   MOVE ZERO TO RPT-OLD RPT-NEW
                   MOVE SQLCODE TO RPT-CODE
                   WRITE RPT-REC
               WHEN OTHER
                   MOVE 'SQLERR' TO RPT-TAG
                   MOVE ZERO TO RPT-OLD RPT-NEW
                   MOVE SQLCODE TO RPT-CODE
                   WRITE RPT-REC
                   MOVE 8 TO RETURN-CODE
           END-EVALUATE
           ADD 1 TO WS-DONE
           IF WS-DONE > 49
               EXEC SQL COMMIT END-EXEC
               MOVE 0 TO WS-DONE
           END-IF
           PERFORM 8000-READ.

       2000-APPLY.
           COMPUTE WS-NEW = WS-BAL + AI-AMOUNT
           MOVE ZERO TO WS-FLOOR
           IF WS-LIMIT-IND >= 0
               COMPUTE WS-FLOOR = 0 - WS-LIMIT
           END-IF
           MOVE WS-BAL TO RPT-OLD
           IF WS-NEW < WS-FLOOR
               MOVE 'REJECT' TO RPT-TAG
               MOVE WS-BAL TO RPT-NEW
               MOVE ZERO TO RPT-CODE
               WRITE RPT-REC
           ELSE
               EXEC SQL
                   UPDATE ACCOUNTS
                      SET BALANCE = BALANCE + :AI-AMOUNT
                    WHERE ACCT_ID = :AI-ACCT-ID
               END-EXEC
               IF SQLCODE = 0
                   EXEC SQL
                       INSERT INTO AUDIT
                           (AUDIT_SEQ, ACCT_ID, OLD_BAL, NEW_BAL)
                       VALUES (:WS-SEQ, :AI-ACCT-ID, :WS-BAL, :WS-NEW)
                   END-EXEC
                   ADD 1 TO WS-SEQ
               END-IF
               MOVE 'POSTED' TO RPT-TAG
               MOVE WS-NEW TO RPT-NEW
               MOVE SQLCODE TO RPT-CODE
               WRITE RPT-REC
           END-IF.

       3000-LOW-BALANCES.
           EXEC SQL
               DECLARE LOWCUR CURSOR FOR
                   SELECT ACCT_ID, BALANCE FROM ACCOUNTS
                    WHERE BALANCE < :WS-LOW
                    ORDER BY ACCT_ID
           END-EXEC
           EXEC SQL OPEN LOWCUR END-EXEC
           EXEC SQL FETCH LOWCUR INTO :WS-LOW-ID, :WS-LOW-BAL
           END-EXEC
           PERFORM UNTIL SQLCODE NOT = 0
               MOVE SPACES TO RPT-REC
               MOVE 'LOWBAL' TO RPT-TAG
               MOVE WS-LOW-ID TO RPT-ACCT
               MOVE WS-LOW-BAL TO RPT-OLD RPT-NEW
               MOVE SQLCODE TO RPT-CODE
               WRITE RPT-REC
               EXEC SQL FETCH LOWCUR INTO :WS-LOW-ID, :WS-LOW-BAL
               END-EXEC
           END-PERFORM
           MOVE SPACES TO RPT-REC
           MOVE 'ENDCUR' TO RPT-TAG
           MOVE ZERO TO RPT-OLD RPT-NEW
           MOVE SQLCODE TO RPT-CODE
           WRITE RPT-REC
           EXEC SQL CLOSE LOWCUR END-EXEC
           EXEC SQL COMMIT END-EXEC.

       8000-READ.
           READ ACCT-FILE
               AT END SET END-OF-ACCTS TO TRUE
           END-READ.
