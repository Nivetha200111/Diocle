      * SYNTHETIC SAMPLE - written for the Diocle hackathon project.
      * Fictional company. Not derived from any real system.
      *----------------------------------------------------------------
      * FEECALC - PAYMENT FEE MODULE, CALLED BY FEEPOST (FICTIONAL)
      *   1.5 PERCENT OF A POSITIVE PAYMENT, ROUNDED, WITH A MINIMUM OF
      *   1.00. REFUNDS (ZERO OR NEGATIVE) PAY NO FEE.
      *----------------------------------------------------------------
       IDENTIFICATION DIVISION.
       PROGRAM-ID. FEECALC.
       DATA DIVISION.
       LINKAGE SECTION.
       01  L-AMOUNT                    PIC S9(5)V99
                                       SIGN LEADING SEPARATE.
       01  L-FEE                       PIC S9(5)V99.
       PROCEDURE DIVISION USING L-AMOUNT L-FEE.
       0000-MAIN.
           IF L-AMOUNT > 0
               COMPUTE L-FEE ROUNDED = L-AMOUNT * 0.015
               IF L-FEE < 1.00
                   MOVE 1.00 TO L-FEE
               END-IF
           ELSE
               MOVE 0 TO L-FEE
           END-IF
           GOBACK.
