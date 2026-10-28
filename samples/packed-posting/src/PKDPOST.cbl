      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * PKDPOST - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   READS THE PACKED ACCOUNT EXTRACT (DD PKIN, RECFM=FB) AND
      *   WRITES ONE POSTING RESULT PER ACCOUNT (DD PKOUT, RECFM=FB).
      *   FIELDS ARE COMP-3, BINARY, COMP-5, OVERPUNCH SIGNED DISPLAY
      *   AND A P-SCALED LIMIT HELD IN HUNDREDS.
      * CHANGE HISTORY (FICTIONAL)
      *   1993-06-01 GRT  INITIAL VERSION
      *   1997-02-17 GRT  CREDIT LIMIT HEADROOM
      *   2002-09-30 LMS  ITEM UNITS FROM THE NATIVE BINARY COUNTER
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PKDPOST.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT PK-FILE ASSIGN TO PKIN
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-PK-STATUS.
           SELECT PO-FILE ASSIGN TO PKOUT
               ORGANIZATION IS SEQUENTIAL
               FILE STATUS IS WS-PO-STATUS.
       DATA DIVISION.
       FILE SECTION.
       FD  PK-FILE.
       COPY PKACCT.
       FD  PO-FILE.
       COPY PKOUT.
       WORKING-STORAGE SECTION.
       01  WS-PK-STATUS                PIC XX.
       01  WS-PO-STATUS                PIC XX.
       01  WS-EOF-FLAG                 PIC X VALUE 'N'.
           88  END-OF-ACCOUNTS         VALUE 'Y'.
       01  WS-INT                      PIC S9(7)V99 COMP-3.
       01  WS-NEW-BAL                  PIC S9(9)V99 COMP-3.
       01  WS-READ-CNT                 PIC 9(7) COMP VALUE 0.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT PK-FILE
           OPEN OUTPUT PO-FILE
           PERFORM 8000-READ
           PERFORM 2000-POST UNTIL END-OF-ACCOUNTS
           CLOSE PK-FILE PO-FILE
           DISPLAY 'PKDPOST READ=' WS-READ-CNT
           STOP RUN.

      * INTEREST ROUNDED HALF AWAY FROM ZERO; NEGATIVE DAYS REVERSE IT.
      * THE NEW BALANCE TRUNCATES; THE HEADROOM CAN OVERFLOW SILENTLY.
       2000-POST.
           ADD 1 TO WS-READ-CNT
           COMPUTE WS-INT ROUNDED =
               PK-BAL * PK-RATE * PK-DAYS / 365
           COMPUTE WS-NEW-BAL = PK-BAL + WS-INT + PK-ADJ
           MOVE PK-ACCT    TO PO-ACCT
           MOVE WS-INT     TO PO-INT
           MOVE WS-NEW-BAL TO PO-NEW-BAL
           COMPUTE PO-HEADROOM = PK-LIMIT - WS-NEW-BAL
           COMPUTE PO-ITEM-UNITS = PK-ITEMS * 1000
           COMPUTE PO-REVERSAL = ZERO - PK-ADJ
           WRITE PO-REC
           PERFORM 8000-READ.

       8000-READ.
           READ PK-FILE
               AT END
                   SET END-OF-ACCOUNTS TO TRUE
           END-READ.
