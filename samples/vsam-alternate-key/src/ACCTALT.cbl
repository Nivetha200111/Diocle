      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * ACCTALT - QUILLMARK TRUST & SAVINGS (FICTIONAL)
      *   LISTS ACCOUNTS BY OWNER THROUGH AN ALTERNATE RECORD KEY.
      *   REFUSED ON PURPOSE: ALTERNATE KEYS ARE NOT IN THE VERIFIED
      *   KEYED-FILE SUBSET (ksds-subset-1); THE ANALYZER SAYS SO.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. ACCTALT.
       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT ACCT-FILE ASSIGN TO ACCTMST
               ORGANIZATION IS INDEXED
               ACCESS MODE IS DYNAMIC
               RECORD KEY IS AM-ACCT-ID
               ALTERNATE RECORD KEY IS AM-OWNER WITH DUPLICATES
               FILE STATUS IS WS-STATUS.
           SELECT LIST-FILE ASSIGN TO ACCTLST
               ORGANIZATION IS LINE SEQUENTIAL.
       DATA DIVISION.
       FILE SECTION.
       FD  ACCT-FILE.
       COPY ACCTMST.
       FD  LIST-FILE.
       01  LIST-REC                    PIC X(30).
       WORKING-STORAGE SECTION.
       01  WS-STATUS                   PIC XX.
       PROCEDURE DIVISION.
       0000-MAIN.
           OPEN INPUT ACCT-FILE
           OPEN OUTPUT LIST-FILE
           MOVE 'SMITH' TO AM-OWNER
           START ACCT-FILE KEY IS = AM-OWNER
               INVALID KEY CONTINUE
           END-START
           PERFORM UNTIL WS-STATUS NOT = '00'
               READ ACCT-FILE NEXT
               IF WS-STATUS = '00'
                   MOVE AM-OWNER TO LIST-REC
                   WRITE LIST-REC
               END-IF
           END-PERFORM
           CLOSE ACCT-FILE LIST-FILE
           STOP RUN.
