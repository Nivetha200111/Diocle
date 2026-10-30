      * SYNTHETIC SAMPLE - written for the Diocle convert-anyway demo.
      * Fictional company. Not derived from any real system.
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ADDFEE.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-IN ASSIGN TO ACCTIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT ACCT-OUT ASSIGN TO ACCTOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-IN.
       COPY ACCTIN.
       FD  ACCT-OUT.
       COPY ACCTOUT.
       WORKING-STORAGE SECTION.
       01  WS-EOF                      PIC X VALUE 'N'.
           88  AT-END                  VALUE 'Y'.
       01  WS-FEE                      PIC 9(3)V99.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT ACCT-IN
           OPEN OUTPUT ACCT-OUT
           PERFORM UNTIL AT-END
               READ ACCT-IN
                   AT END SET AT-END TO TRUE
                   NOT AT END PERFORM 1000-CHARGE
               END-READ
           END-PERFORM
           CLOSE ACCT-IN ACCT-OUT
           STOP RUN.
       1000-CHARGE.
           COMPUTE WS-FEE ROUNDED = AI-AMOUNT * 0.015
           MOVE AI-ACCT-ID TO AO-ACCT-ID
           MOVE AI-AMOUNT TO AO-AMOUNT
           MOVE WS-FEE TO AO-FEE
           WRITE ACCT-OUT-REC.
