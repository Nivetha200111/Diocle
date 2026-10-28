      * SYNTHETIC - written for the Diocle evaluation (unseen programs).
      * Fictional company. Not derived from any real system.
       01  BA-REC.
           05  BA-BRANCH               PIC X(4).
               88  BA-NORTH            VALUE 'N001' 'N002'.
               88  BA-SOUTH            VALUE 'S001'.
               88  BA-WEST             VALUE 'W001'.
           05  BA-ACCT                 PIC X(8).
           05  BA-BALANCE              PIC S9(9)V99 COMP-3.
