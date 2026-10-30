-- SYNTHETIC. Quillmark Trust & Savings (fictional): audit trail written by ACCTRPT.
CREATE TABLE AUDIT (
    AUDIT_SEQ   INTEGER       NOT NULL PRIMARY KEY,
    ACCT_ID     CHAR(8)       NOT NULL,
    OLD_BAL     DECIMAL(9,2)  NOT NULL,
    NEW_BAL     DECIMAL(9,2)  NOT NULL
);
