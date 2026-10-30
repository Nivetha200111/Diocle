      * SYNTHETIC SAMPLE - written for the Diocle convert-anyway demo.
      * Fictional company. Not derived from any real system.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. SQLRPT.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
           EXEC SQL INCLUDE SQLCA END-EXEC.
       01  WS-ACCT-ID                  PIC X(8) VALUE 'A0000001'.
       01  WS-BALANCE                  PIC S9(7)V99 COMP-3.
       PROCEDURE DIVISION.
       0000-MAIN.
           EXEC SQL
               SELECT BALANCE INTO :WS-BALANCE
                 FROM ACCOUNTS WHERE ACCT_ID = :WS-ACCT-ID
           END-EXEC
           IF SQLCODE = 0
               DISPLAY 'BALANCE FOUND'
           ELSE
               DISPLAY 'NOT FOUND'
           END-IF
           STOP RUN.
