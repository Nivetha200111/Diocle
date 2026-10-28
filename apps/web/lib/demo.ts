export type View =
  | "Overview"
  | "Migrations"
  | "Dependency graph"
  | "Risk findings"
  | "Conversions"
  | "Verification"
  | "Reports"
  | "Settings";
export type Migration = {
  id: string;
  name: string;
  description: string;
  programs: number;
  copybooks: number;
  status: "In progress" | "Completed" | "Needs review";
  progress: number;
  updated: string;
  color: "green" | "purple" | "orange";
  files?: string[];
};

export const initialMigrations: Migration[] = [
  {
    id: "MIG-003",
    name: "Core banking",
    description: "Account management & daily ledger",
    programs: 24,
    copybooks: 8,
    status: "Needs review",
    progress: 75,
    updated: "12 minutes ago",
    color: "green",
  },
  {
    id: "MIG-002",
    name: "Payment processing",
    description: "Transfers, settlements & reconciliation",
    programs: 12,
    copybooks: 5,
    status: "Completed",
    progress: 100,
    updated: "1 hour ago",
    color: "purple",
  },
  {
    id: "MIG-001",
    name: "Fraud detection",
    description: "Transaction monitoring & risk rules",
    programs: 8,
    copybooks: 3,
    status: "In progress",
    progress: 42,
    updated: "2 hours ago",
    color: "orange",
  },
];

export const programs = [
  {
    name: "ACCT-MAIN.cbl",
    description: "Account orchestration",
    lines: 1248,
    dependencies: 4,
    risk: "Low",
    status: "Converted",
  },
  {
    name: "PAYMENT-PROC.cbl",
    description: "Payment processing",
    lines: 864,
    dependencies: 3,
    risk: "High",
    status: "Needs review",
  },
  {
    name: "CUSTOMER.cpy",
    description: "Customer record layout",
    lines: 142,
    dependencies: 0,
    risk: "Low",
    status: "Schema generated",
  },
  {
    name: "BALANCE-CALC.cbl",
    description: "Balance calculation",
    lines: 532,
    dependencies: 2,
    risk: "Medium",
    status: "Converted",
  },
  {
    name: "FRAUD-CHECK.cbl",
    description: "Transaction risk screening",
    lines: 716,
    dependencies: 2,
    risk: "High",
    status: "Needs review",
  },
];

export const findings = [
  {
    id: "RISK-001",
    title: "Payment rounding needs a closer look",
    description:
      "Packed-decimal precision may behave differently when converted to Java. Review the rounding boundary before approving.",
    program: "PAYMENT-PROC.cbl",
    line: 218,
    category: "Payment logic",
    severity: "High",
    example: "COMPUTE WS-NET-AMOUNT ROUNDED = WS-AMOUNT - WS-FEE",
  },
  {
    id: "RISK-002",
    title: "Preserve the fraud threshold boundary",
    description:
      "The original rule uses a strict greater-than comparison. The generated service should preserve the exact threshold.",
    program: "FRAUD-CHECK.cbl",
    line: 94,
    category: "Fraud detection",
    severity: "High",
    example: "IF WS-RISK-SCORE > 85 PERFORM FLAG-TRANSACTION",
  },
  {
    id: "RISK-003",
    title: "Check negative balance handling",
    description:
      "A signed balance field needs an explicit negative-value case in the generated test suite.",
    program: "BALANCE-CALC.cbl",
    line: 156,
    category: "Business logic",
    severity: "Medium",
    example: "05 ACCOUNT-BALANCE PIC S9(11)V99 COMP-3.",
  },
];

export const activities = [
  {
    title: "Core banking is ready for review",
    detail: "3 risk findings need your attention",
    time: "12 min ago",
    kind: "review",
  },
  {
    title: "Payment processing verified",
    detail: "500 of 500 test outputs matched",
    time: "1 hour ago",
    kind: "success",
  },
  {
    title: "12 Java services generated",
    detail: "Payment processing · Conversion",
    time: "1 hour ago",
    kind: "code",
  },
  {
    title: "Fraud detection analysis started",
    detail: "8 programs and 3 copybooks",
    time: "2 hours ago",
    kind: "analysis",
  },
];

export const cobolCode = `       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYMENT-PROC.
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01 WS-AMOUNT     PIC 9(9)V99.
       01 WS-FEE        PIC 9(5)V99.
       01 WS-NET-AMOUNT PIC 9(9)V99.

       PROCEDURE DIVISION.
       PROCESS-PAYMENT.
           COMPUTE WS-NET-AMOUNT ROUNDED
             = WS-AMOUNT - WS-FEE
           DISPLAY WS-NET-AMOUNT
           STOP RUN.`;

export const javaCode = `// Illustrative mock output — not AI-generated
import java.math.BigDecimal;
import java.math.RoundingMode;

public class PaymentService {
    public BigDecimal processPayment(
        BigDecimal amount,
        BigDecimal fee
    ) {
        return amount.subtract(fee)
            .setScale(2, RoundingMode.HALF_UP);
    }
}`;

export const sqlCode = `-- Illustrative schema from CUSTOMER.cpy
CREATE TABLE customers (
    customer_id   CHAR(10) PRIMARY KEY,
    full_name     VARCHAR(60) NOT NULL,
    account_type  CHAR(2) NOT NULL,
    balance       DECIMAL(13, 2) DEFAULT 0,
    opened_at     DATE NOT NULL
);

CREATE INDEX idx_customer_account_type
    ON customers (account_type);`;

export const testCode = `// Illustrative mock output — not executed
@Test
void preservesPaymentRounding() {
    var service = new PaymentService();
    var result = service.processPayment(
        new BigDecimal("100.00"),
        new BigDecimal("2.50")
    );
    assertEquals(new BigDecimal("97.50"), result);
}`;

export const customerCode = `       01 CUSTOMER-RECORD.
          05 CUSTOMER-ID   PIC X(10).
          05 FULL-NAME     PIC X(60).
          05 ACCOUNT-TYPE  PIC X(2).
          05 BALANCE       PIC S9(11)V99
                           COMP-3.
          05 OPENED-AT     PIC 9(8).

       *> Synthetic copybook example.
       *> Date field uses YYYYMMDD.`;

export function downloadFile(
  name: string,
  content: string,
  type = "application/json",
) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function reportFor(migration: Migration) {
  return {
    mock: true,
    disclaimer:
      "Synthetic frontend preview. No analysis, model conversion, compilation, or differential testing has been performed.",
    migration,
    ...(migration.id === "MIG-003"
      ? {
          illustrativeFindings: findings,
          illustrativeVerification: { total: 500, passed: 468, failed: 32 },
        }
      : migration.id === "MIG-002"
        ? {
            illustrativeFindings: [],
            illustrativeVerification: { total: 500, passed: 500, failed: 0 },
          }
        : {
            note: "Preview pipeline is incomplete. No verification report is available.",
          }),
  };
}
