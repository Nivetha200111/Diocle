      * SYNTHETIC: written for Diocle's tests (Quillmark, fictional).
      * Checks account records; on a blank account id or an input that
      * cannot be opened it abends through IBM LE's CEE3ABD, the way
      * many batch programs end their 9999-ABEND paragraph. Verified
      * with Diocle's CEE3ABD stand-in (services/verifier/standins).
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTCHK.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-IN ASSIGN TO ACCTIN
               ORGANIZATION IS LINE SEQUENTIAL
               FILE STATUS IS WS-IN-STATUS.
           SELECT ACCT-OUT ASSIGN TO ACCTOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-IN.
           COPY ACCTREC.
       FD  ACCT-OUT.
       01  OUT-REC.
           05  OUT-ID              PIC X(6).
           05  OUT-FLAG            PIC X.
           05  OUT-BAL             PIC S9(7)V99 SIGN LEADING SEPARATE.
       WORKING-STORAGE SECTION.
       01  WS-IN-STATUS            PIC XX.
       01  WS-EOF                  PIC X VALUE 'N'.
       01  WS-COUNT                PIC 9(5) COMP VALUE 0.
       01  ABCODE                  PIC S9(9) BINARY.
       01  TIMING                  PIC S9(9) BINARY.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT ACCT-IN
           IF WS-IN-STATUS NOT = '00'
               DISPLAY 'ACCTIN OPEN FAILED ' WS-IN-STATUS
               MOVE 101 TO ABCODE
               PERFORM 9999-ABEND
           END-IF
           OPEN OUTPUT ACCT-OUT
           PERFORM UNTIL WS-EOF = 'Y'
               READ ACCT-IN
                   AT END MOVE 'Y' TO WS-EOF
                   NOT AT END PERFORM 1000-CHECK
               END-READ
           END-PERFORM
           DISPLAY 'ACCOUNTS CHECKED ' WS-COUNT
           CLOSE ACCT-IN ACCT-OUT
           STOP RUN.
       1000-CHECK.
           IF ACCT-ID = SPACES
               DISPLAY 'BLANK ACCOUNT ID AFTER ' WS-COUNT
               MOVE 999 TO ABCODE
               PERFORM 9999-ABEND
           END-IF
           ADD 1 TO WS-COUNT
           MOVE ACCT-ID TO OUT-ID
           MOVE ACCT-BAL TO OUT-BAL
           EVALUATE TRUE
               WHEN ACCT-BAL < 0
                   MOVE 'N' TO OUT-FLAG
               WHEN ACCT-SAVINGS
                   MOVE 'S' TO OUT-FLAG
               WHEN OTHER
                   MOVE 'Y' TO OUT-FLAG
           END-EVALUATE
           WRITE OUT-REC.
       9999-ABEND.
           DISPLAY 'ABENDING PROGRAM'
           MOVE 0 TO TIMING
           CALL 'CEE3ABD' USING ABCODE, TIMING.
