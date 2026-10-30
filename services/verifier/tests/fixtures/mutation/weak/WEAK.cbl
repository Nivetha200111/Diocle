      * SYNTHETIC test sample for mutation testing: a flat fee with a threshold at exactly 500.00.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. WEAK.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT IN-FILE ASSIGN TO WKIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT OUT-FILE ASSIGN TO WKOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  IN-FILE.
       01  IN-REC.
           05  IN-ID    PIC X(4).
           05  IN-AMT   PIC 9(3)V99.
       FD  OUT-FILE.
       01  OUT-REC.
           05  OUT-ID   PIC X(4).
           05  OUT-FEE  PIC 9(3)V99.
       WORKING-STORAGE SECTION.
       01  WS-EOF       PIC X VALUE 'N'.
       PROCEDURE DIVISION.
           OPEN INPUT IN-FILE OUTPUT OUT-FILE
           PERFORM UNTIL WS-EOF = 'Y'
               READ IN-FILE
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END
                       MOVE IN-ID TO OUT-ID
                       IF IN-AMT > 500.00
                           MOVE 50.00 TO OUT-FEE
                       ELSE
                           MOVE 5.00 TO OUT-FEE
                       END-IF
                       WRITE OUT-REC
               END-READ
           END-PERFORM
           CLOSE IN-FILE OUT-FILE
           STOP RUN.
