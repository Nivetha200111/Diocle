      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * DYNQRY - A PROGRAM THE SQL VERIFIER REFUSES, ON PURPOSE
      *   IT BUILDS ITS STATEMENT AT RUN TIME (PREPARE / EXECUTE), WHICH
      *   IS OUTSIDE THE VERIFIED SUBSET. THE ANALYZER SAYS SO WITH THE
      *   EXACT LINE; IT IS NEVER GUESSED AT.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. DYNQRY.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT RPT-FILE ASSIGN TO RPTOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  RPT-FILE.
       01  RPT-REC                     PIC X(40).
       WORKING-STORAGE SECTION.
           EXEC SQL INCLUDE SQLCA END-EXEC.
           EXEC SQL DECLARE ACCOUNTS TABLE
               ( ACCT_ID      CHAR(8)       NOT NULL,
                 BALANCE      DECIMAL(9,2)  NOT NULL
               ) END-EXEC.
       01  WS-STMT                     PIC X(80).
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN OUTPUT RPT-FILE
           MOVE 'DELETE FROM ACCOUNTS WHERE BALANCE < 0' TO WS-STMT
           EXEC SQL PREPARE S1 FROM :WS-STMT END-EXEC
           EXEC SQL EXECUTE S1 END-EXEC
           MOVE 'DONE' TO RPT-REC
           WRITE RPT-REC
           CLOSE RPT-FILE
           STOP RUN.
