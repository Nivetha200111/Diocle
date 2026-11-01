import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

public class FeeSchd {
    private BufferedReader feeReader = null;
    private BufferedWriter chgWriter = null;
    private String wsFeeStatus = "00";
    private String wsChgStatus = "00";
    private boolean endOfAccounts = false;

    private BigDecimal wsWaiverBal = new BigDecimal("5000.00");
    private BigDecimal wsPerTxn = new BigDecimal("0.35");
    private BigDecimal wsOdRate = new BigDecimal("0.1899");
    private BigDecimal wsCap = new BigDecimal("40.00");
    private BigDecimal wsBase = BigDecimal.ZERO.setScale(2);
    private int wsFreeTxns = 0;
    private int wsExcess = 0;
    private BigDecimal wsTxnFee = BigDecimal.ZERO.setScale(2);
    private BigDecimal wsOdInt = BigDecimal.ZERO.setScale(2);
    private BigDecimal wsTotal = BigDecimal.ZERO.setScale(2);
    private String wsCode = "OK";
    private long wsReadCnt = 0;
    private long wsCappedCnt = 0;

    private String feeAcctId = "          ";
    private char feeProduct = ' ';
    private BigDecimal feeAvgBal = BigDecimal.ZERO.setScale(2);
    private int feeTxnCount = 0;
    private int feeMonthDays = 0;

    public static void main(String[] args) throws Exception {
        FeeSchd prog = new FeeSchd();
        prog.p0000Main();
    }

    private void p0000Main() throws Exception {
        p1000Init();
        while (!endOfAccounts) {
            p2000Process();
        }
        p9000Term();
    }

    private void p1000Init() throws Exception {
        String feePath = System.getenv("DD_FEEIN");
        String chgPath = System.getenv("DD_CHGOUT");
        if (feePath == null || feePath.isEmpty()) {
            wsFeeStatus = "35";
            System.out.println("FEESCHD OPEN FEEIN FAILED " + wsFeeStatus);
            System.exit(16);
        }
        try {
            Path p = Paths.get(feePath);
            feeReader = Files.newBufferedReader(p, StandardCharsets.ISO_8859_1);
            wsFeeStatus = "00";
        } catch (Exception e) {
            wsFeeStatus = "35";
            System.out.println("FEESCHD OPEN FEEIN FAILED " + wsFeeStatus);
            System.exit(16);
        }
        if (chgPath == null || chgPath.isEmpty()) {
            wsChgStatus = "35";
            System.out.println("FEESCHD OPEN CHGOUT FAILED " + wsChgStatus);
            try { if (feeReader != null) feeReader.close(); } catch (Exception x) {}
            System.exit(16);
        }
        try {
            Path p2 = Paths.get(chgPath);
            if (p2.getParent() != null) {
                try { Files.createDirectories(p2.getParent()); } catch (Exception x) {}
            }
            chgWriter = Files.newBufferedWriter(p2, StandardCharsets.ISO_8859_1);
            wsChgStatus = "00";
        } catch (Exception e) {
            wsChgStatus = "35";
            System.out.println("FEESCHD OPEN CHGOUT FAILED " + wsChgStatus);
            try { if (feeReader != null) feeReader.close(); } catch (Exception x) {}
            System.exit(16);
        }
        p8000Read();
    }

    private void p2000Process() throws Exception {
        wsReadCnt = truncCounter(wsReadCnt + 1);
        wsCode = "OK";
        p3000BaseFee();
        p4000TxnFee();
        p5000OdInterest();
        p6000Total();
        p7000WriteResult();
        p8000Read();
    }

    private void p3000BaseFee() {
        boolean isBasic = (feeProduct == 'A');
        boolean isPlus = (feeProduct == 'B');
        if (isBasic) {
            wsBase = new BigDecimal("6.00");
            wsFreeTxns = 10;
        } else if (isPlus) {
            wsBase = new BigDecimal("3.50");
            wsFreeTxns = 25;
        } else {
            wsBase = BigDecimal.ZERO.setScale(2);
            wsFreeTxns = 9999;
        }
        if (feeAvgBal.compareTo(wsWaiverBal) >= 0 && wsBase.compareTo(BigDecimal.ZERO) > 0) {
            wsBase = BigDecimal.ZERO.setScale(2);
            wsCode = "WV";
        }
    }

    private void p4000TxnFee() {
        BigDecimal diff = BigDecimal.valueOf((long) feeTxnCount).subtract(BigDecimal.valueOf((long) wsFreeTxns));
        BigDecimal e = truncDecimal(diff, 5, 0);
        wsExcess = e.intValueExact();
        if (wsExcess > 0) {
            BigDecimal prod = BigDecimal.valueOf((long) wsExcess).multiply(wsPerTxn);
            wsTxnFee = truncDecimal(prod, 3, 2);
        } else {
            wsTxnFee = BigDecimal.ZERO.setScale(2);
        }
    }

    private void p5000OdInterest() {
        if (feeAvgBal.compareTo(BigDecimal.ZERO) < 0) {
            BigDecimal neg = feeAvgBal.negate();
            BigDecimal num = neg.multiply(wsOdRate).multiply(BigDecimal.valueOf((long) feeMonthDays));
            BigDecimal div = num.divide(BigDecimal.valueOf(365L), 30, RoundingMode.HALF_UP);
            wsOdInt = roundDecimal(div, 5, 2);
        } else {
            wsOdInt = BigDecimal.ZERO.setScale(2);
        }
    }

    private void p6000Total() {
        BigDecimal sum = wsBase.add(wsTxnFee).add(wsOdInt);
        wsTotal = truncDecimal(sum, 3, 2);
        boolean isPrivate = (feeProduct == 'C');
        if (!isPrivate && wsTotal.compareTo(wsCap) > 0) {
            wsTotal = new BigDecimal("40.00");
            wsCode = "CP";
            wsCappedCnt = truncCounter(wsCappedCnt + 1);
        }
    }

    private void p7000WriteResult() throws Exception {
        StringBuilder sb = new StringBuilder(38);
        sb.append(feeAcctId);
        sb.append(formatSigned(wsBase, 3, 2));
        sb.append(formatSigned(wsTxnFee, 3, 2));
        sb.append(formatSigned(wsOdInt, 5, 2));
        sb.append(formatSigned(wsTotal, 3, 2));
        sb.append(wsCode);
        String line = sb.toString();
        chgWriter.write(line);
        chgWriter.write("\n");
    }

    private void p8000Read() throws Exception {
        String line = null;
        try {
            line = feeReader.readLine();
        } catch (Exception e) {
            line = null;
        }
        if (line == null) {
            endOfAccounts = true;
            return;
        }
        if (line.length() < 29) {
            StringBuilder sb = new StringBuilder(line);
            while (sb.length() < 29) sb.append(' ');
            line = sb.toString();
        } else if (line.length() > 29) {
            line = line.substring(0, 29);
        }
        feeAcctId = line.substring(0, 10);
        feeProduct = line.charAt(10);
        String sBal = line.substring(11, 23);
        String sTxn = line.substring(23, 27);
        String sDays = line.substring(27, 29);
        feeAvgBal = parseSignedLeading(sBal, 9, 2);
        feeTxnCount = parseUnsigned(sTxn);
        feeMonthDays = parseUnsigned(sDays);
    }

    private void p9000Term() throws Exception {
        try { if (feeReader != null) feeReader.close(); } catch (Exception e) {}
        try { if (chgWriter != null) { chgWriter.flush(); chgWriter.close(); } } catch (Exception e) {}
        System.out.println("FEESCHD ACCOUNTS=" + format7(wsReadCnt) + " CAPPED=" + format7(wsCappedCnt));
    }

    private static BigDecimal truncDecimal(BigDecimal v, int intDigits, int fracDigits) {
        BigDecimal t = v.setScale(fracDigits, RoundingMode.DOWN);
        BigDecimal scaled = t.movePointRight(fracDigits);
        BigInteger bi;
        try {
            bi = scaled.toBigIntegerExact();
        } catch (Exception e) {
            bi = scaled.setScale(0, RoundingMode.DOWN).toBigInteger();
        }
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        boolean neg = bi.signum() < 0;
        BigInteger abs = bi.abs().mod(mod);
        BigInteger resBi = neg ? abs.negate() : abs;
        BigDecimal res = new BigDecimal(resBi).movePointLeft(fracDigits).setScale(fracDigits, RoundingMode.UNNECESSARY);
        if (res.compareTo(BigDecimal.ZERO) == 0) {
            res = BigDecimal.ZERO.setScale(fracDigits, RoundingMode.UNNECESSARY);
        }
        return res;
    }

    private static BigDecimal roundDecimal(BigDecimal v, int intDigits, int fracDigits) {
        BigDecimal r = v.setScale(fracDigits, RoundingMode.HALF_UP);
        BigDecimal scaled = r.movePointRight(fracDigits);
        BigInteger bi;
        try {
            bi = scaled.toBigIntegerExact();
        } catch (Exception e) {
            bi = scaled.setScale(0, RoundingMode.HALF_UP).toBigInteger();
        }
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        boolean neg = bi.signum() < 0;
        BigInteger abs = bi.abs().mod(mod);
        BigInteger resBi = neg ? abs.negate() : abs;
        BigDecimal res = new BigDecimal(resBi).movePointLeft(fracDigits).setScale(fracDigits, RoundingMode.UNNECESSARY);
        if (res.compareTo(BigDecimal.ZERO) == 0) {
            res = BigDecimal.ZERO.setScale(fracDigits, RoundingMode.UNNECESSARY);
        }
        return res;
    }

    private static String formatSigned(BigDecimal v, int intDigits, int fracDigits) {
        BigDecimal t = v.setScale(fracDigits, RoundingMode.UNNECESSARY);
        char sign = t.signum() < 0 ? '-' : '+';
        BigDecimal abs = t.abs();
        BigInteger scaled = abs.movePointRight(fracDigits).toBigIntegerExact();
        String digits = scaled.toString();
        int total = intDigits + fracDigits;
        while (digits.length() < total) digits = "0" + digits;
        if (digits.length() > total) digits = digits.substring(digits.length() - total);
        return sign + digits;
    }

    private static BigDecimal parseSignedLeading(String s, int intDigits, int fracDigits) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO.setScale(fracDigits);
        char c0 = s.charAt(0);
        int sign = 1;
        String digits;
        if (c0 == '+') {
            digits = s.substring(1);
        } else if (c0 == '-') {
            sign = -1;
            digits = s.substring(1);
        } else if (c0 == ' ') {
            digits = s.substring(1);
        } else {
            digits = s;
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < digits.length(); i++) {
            char c = digits.charAt(i);
            if (c >= '0' && c <= '9') sb.append(c);
            else if (c == ' ') sb.append('0');
            else sb.append(c);
        }
        String d = sb.toString();
        if (d.isEmpty()) d = "0";
        BigDecimal scaled;
        try {
            scaled = new BigDecimal(d);
        } catch (Exception e) {
            scaled = BigDecimal.ZERO;
        }
        BigDecimal v = scaled.movePointLeft(fracDigits).setScale(fracDigits, RoundingMode.UNNECESSARY);
        if (sign < 0) v = v.negate();
        return v;
    }

    private static int parseUnsigned(String s) {
        if (s == null) return 0;
        String t = s.trim();
        if (t.isEmpty()) return 0;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < t.length(); i++) {
            char c = t.charAt(i);
            if (c >= '0' && c <= '9') sb.append(c);
        }
        if (sb.length() == 0) return 0;
        try {
            return Integer.parseInt(sb.toString());
        } catch (Exception e) {
            return 0;
        }
    }

    private static long truncCounter(long v) {
        long m = 10000000L;
        long r = v % m;
        if (r < 0) r += m;
        return r;
    }

    private static String format7(long v) {
        long r = v % 10000000L;
        if (r < 0) r += 10000000L;
        String s = Long.toString(r);
        while (s.length() < 7) s = "0" + s;
        if (s.length() > 7) s = s.substring(s.length() - 7);
        return s;
    }
}
