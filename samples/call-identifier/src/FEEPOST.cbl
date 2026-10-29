      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * FEEPOST - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   POSTS PAYMENTS (DD PAYIN -> DD POSTOUT) AND ASKS THE FEE
      *   MODULE FOR EACH ONE. THE MODULE NAME IS HELD IN A DATA ITEM
      *   (CALL IDENTIFIER) BUT IT ONLY EVER HOLDS THE ONE LITERAL, SO
      *   THE TARGET IS KNOWN WITHOUT RUNNING THE PROGRAM.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FEEPOST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT PAY-FILE ASSIGN TO PAYIN
               ORGANIZATION IS LINE SEQUENTIAL.
           SELECT POST-FILE ASSIGN TO POSTOUT
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  PAY-FILE.
       COPY TXNREC.
       FD  POST-FILE.
       COPY POSTREC.
       WORKING-STORAGE SECTION.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-PAYMENTS         VALUE 'Y'.
       01  WS-FEE-PGM                  PIC X(8) VALUE 'FEECALC'.
       01  WS-FEE                      PIC S9(5)V99.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT PAY-FILE
           OPEN OUTPUT POST-FILE
           MOVE
               'FEECALC'
               TO WS-FEE-PGM
           PERFORM 8000-READ
           PERFORM 2000-POST UNTIL END-OF-PAYMENTS
           CLOSE PAY-FILE POST-FILE
           STOP RUN.

       2000-POST.
           CALL WS-FEE-PGM USING PAY-AMOUNT WS-FEE
           MOVE PAY-ID TO POST-ID
           MOVE PAY-AMOUNT TO POST-AMOUNT
           MOVE WS-FEE TO POST-FEE
           WRITE POST-REC
           PERFORM 8000-READ.

       8000-READ.
           READ PAY-FILE
               AT END SET END-OF-PAYMENTS TO TRUE
           END-READ.
