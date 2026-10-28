      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * LOYWAIVE - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   MONTHLY SERVICE FEE OF 4.50, WAIVED FOR LOYAL CUSTOMERS: AN
      *   AVERAGE BALANCE OF AT LEAST 5000.00 OR TEN YEARS' TENURE.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. LOYWAIVE.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT LY-FILE ASSIGN TO LOYIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT LO-FILE ASSIGN TO LOYOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  LY-FILE.
       COPY LOYIN.
       FD  LO-FILE.
       COPY LOYOUT.
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT LY-FILE OUTPUT LO-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ LY-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM 1000-FEE
               END-READ
           END-PERFORM
           CLOSE LY-FILE LO-FILE
           STOP RUN.

       1000-FEE.
           MOVE LY-ACCT TO LO-ACCT
           IF LY-BALANCE NOT < 5000.00 OR LY-TENURE-MONTHS NOT < 120
               MOVE ZERO TO LO-FEE
               MOVE 'WV' TO LO-CODE
           ELSE
               MOVE 4.50 TO LO-FEE
               MOVE 'CH' TO LO-CODE
           END-IF
           WRITE LO-REC.
