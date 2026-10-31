      *================================================================*
      * DIOCLE STAND-IN FOR CEE3ABD (abnormal termination).            *
      * NOT IBM Language Environment. Written for Diocle; linked into  *
      * the GnuCOBOL build of an original program that CALLs CEE3ABD   *
      * when the repository does not define a CEE3ABD program itself.  *
      * Behaviour (the converted Java must do exactly the same):       *
      *  - the run ends here, with exit code 16;                       *
      *  - files still open are closed as at STOP RUN, so records      *
      *    already written are kept; DISPLAY output so far is kept;    *
      *  - 'CEE3ABD abend code <n>' is written to stderr (<n> is the   *
      *    first argument, no leading zeros, '-' when negative).       *
      * The verifier compares exit code, stdout and output files, not  *
      * stderr. TIMING (the second argument) is accepted and ignored.  *
      *================================================================*
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEE3ABD.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  DIO-CODE                PIC -(9)9.
       LINKAGE SECTION.
       01  DIO-ABCODE              PIC S9(9) BINARY.
       01  DIO-TIMING              PIC S9(9) BINARY.
       PROCEDURE DIVISION USING DIO-ABCODE DIO-TIMING.
           IF ADDRESS OF DIO-ABCODE = NULL
               DISPLAY 'CEE3ABD abend code ?' UPON SYSERR
           ELSE
               MOVE DIO-ABCODE TO DIO-CODE
               DISPLAY 'CEE3ABD abend code ' FUNCTION TRIM(DIO-CODE)
                   UPON SYSERR
           END-IF
           MOVE 16 TO RETURN-CODE
           STOP RUN.
