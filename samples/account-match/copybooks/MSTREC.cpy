      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      * ACCOUNT MASTER, SORTED BY ACCOUNT ID (24 BYTES)
       01  MS-REC.
           05  MS-ACCT-ID              PIC X(8).
           05  MS-BALANCE              PIC S9(9)V99
                                       SIGN LEADING SEPARATE.
           05  MS-STATUS               PIC X(4).
               88  MS-FROZEN           VALUE 'FRZN'.
               88  MS-ACTIVE           VALUE 'ACTV'.
