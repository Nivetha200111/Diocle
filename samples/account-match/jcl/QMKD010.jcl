//* SYNTHETIC SAMPLE - written for the Diocle hackathon project.
//* Fictional company. Not derived from any real system.
//QMKD010  JOB (QMK0001),'DAILY CYCLE',CLASS=A,MSGCLASS=X,
//             NOTIFY=&SYSUID,REGION=0M
//*-------------------------------------------------------------------
//* QUILLMARK TRUST & SAVINGS (FICTIONAL) - DAILY BATCH CYCLE (v1 SLICE)
//* SORT TRANSACTIONS, THEN MATCH-MERGE THE MASTER.
//* Trimmed from the full daily cycle to the SORT+COBOL shape that
//* analyzer v1 job-level conversion supports (one SORT step feeding
//* one COBOL step). The full cycle also runs INT020/CTL030 behind
//* COND= gates; those stay out of scope for now, see jcl.py.
//*-------------------------------------------------------------------
//JOBLIB   DD DSN=QMK.PROD.LOADLIB,DISP=SHR
//SORT005  EXEC PGM=SORT
//SORTIN   DD DSN=QMK.PROD.TXN.DAILY,DISP=SHR
//SORTOUT  DD DSN=QMK.PROD.TXN.SORTED,
//            DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,
//            SPACE=(TRK,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=19,BLKSIZE=0)
//SYSIN    DD DSN=QMK.PROD.CNTLLIB(SORTTXN),DISP=SHR
//SYSOUT   DD SYSOUT=*
//MTCH010  EXEC PGM=ACCTMTCH
//MSTIN    DD DSN=QMK.PROD.ACCT.MASTER(0),DISP=SHR
//TXNIN    DD DSN=QMK.PROD.TXN.SORTED,DISP=(OLD,DELETE)
//NEWMST   DD DSN=QMK.PROD.ACCT.MASTER(+1),
//            DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,
//            SPACE=(TRK,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=28,BLKSIZE=0)
//EXCOUT   DD DSN=QMK.PROD.TXN.EXCEPTIONS(+1),
//            DISP=(NEW,CATLG,DELETE),UNIT=SYSDA,
//            SPACE=(TRK,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=30,BLKSIZE=0)
//SYSOUT   DD SYSOUT=*
