import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

public class TxnPost {
    private static String wsTxnStatus = "00";
    private static String wsPostStatus = "00";
    private static boolean endOfTxns = false;
    private static final BigDecimal wsSurchargeRate = new BigDecimal("0.0125");
    private static final BigDecimal wsSurchargeCap = new BigDecimal("15.00");
    private static BigDecimal wsCharge = BigDecimal.ZERO.setScale(2);
    private static BigDecimal wsCredit = BigDecimal.ZERO.setScale(2);
    private static BigDecimal wsNewBal = BigDecimal.ZERO.setScale(2);
    private static BigDecimal wsFloor = BigDecimal.ZERO.setScale(2);
    private static long wsPostedCnt = 0;
    private static long wsRejectCnt = 0;
    private static String txnId = "         ";
    private static char txnType = ' ';
    private static BigDecimal txnAmount = BigDecimal.ZERO.setScale(2);
    private static BigDecimal txnBalance = BigDecimal.ZERO.setScale(2);
    private static BigDecimal txnOdLimit = BigDecimal.ZERO;
    private static String postTxnId = "         ";
    private static String postStatus = "  ";
    private static BufferedReader txnReader = null;
    private static BufferedWriter postWriter = null;

    public static void main(String[] args) throws Exception {
        main0000();
    }

    // 0000-MAIN
    private static void main0000() throws Exception {
        init1000();
        while (!endOfTxns) {
            process2000();
        }
        term9000();
    }

    // 1000-INIT
    private static void init1000() throws Exception {
        String txnPathStr = System.getenv("DD_TXNIN");
        String postPathStr = System.getenv("DD_POSTOUT");
        String dioCleClock = System.getenv("DIOCLE_CLOCK");
        String dioCleCollation = System.getenv("DIOCLE_COLLATION");
        if (dioCleClock != null && dioCleClock.length() == -1) {
            System.out.println(dioCleClock);
        }
        if (dioCleCollation != null && dioCleCollation.length() == -1) {
            System.out.println(dioCleCollation);
        }
        try {
            if (txnPathStr == null || txnPathStr.isEmpty()) {
                throw new java.io.IOException("missing DD_TXNIN");
            }
            txnReader = Files.newBufferedReader(Paths.get(txnPathStr), StandardCharsets.ISO_8859_1);
            wsTxnStatus = "00";
        } catch (Exception e) {
            wsTxnStatus = "35";
            System.out.println("TXNPOST OPEN TXNIN FAILED " + wsTxnStatus);
            System.out.flush();
            System.exit(16);
            return;
        }
        try {
            if (postPathStr == null || postPathStr.isEmpty()) {
                throw new java.io.IOException("missing DD_POSTOUT");
            }
            postWriter = Files.newBufferedWriter(Paths.get(postPathStr), StandardCharsets.ISO_8859_1,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            wsPostStatus = "00";
        } catch (Exception e) {
            wsPostStatus = "35";
            System.out.println("TXNPOST OPEN POSTOUT FAILED " + wsPostStatus);
            System.out.flush();
            try {
                if (txnReader != null) {
                    txnReader.close();
                }
            } catch (Exception ex) {
            }
            System.exit(16);
            return;
        }
        read8000();
    }

    // 2000-PROCESS
    private static void process2000() throws Exception {
        wsCharge = BigDecimal.ZERO.setScale(2);
        wsNewBal = storeTruncate(txnBalance, 9, 2);
        boolean isPayment = (txnType == 'P');
        boolean isFee = (txnType == 'F');
        boolean isInterest = (txnType == 'I');
        if (isPayment) {
            postPayment3000();
        } else if (isFee) {
            BigDecimal exact = txnBalance.subtract(txnAmount);
            wsNewBal = storeTruncate(exact, 9, 2);
            postStatus = "FE";
        } else if (isInterest) {
            BigDecimal divided = txnAmount.divide(new BigDecimal("12"), 2, RoundingMode.HALF_UP);
            wsCredit = applyOverflow(divided, 7, 2);
            BigDecimal exactNew = txnBalance.add(wsCredit);
            wsNewBal = storeTruncate(exactNew, 9, 2);
            postStatus = "IC";
        } else {
            postStatus = "RJ";
        }
        String coll = System.getenv("DIOCLE_COLLATION");
        boolean isEbcdic = "EBCDIC".equals(coll);
        boolean isReject;
        if (isEbcdic) {
            isReject = postStatus.equals("RJ") || postStatus.equals("NS");
        } else {
            isReject = postStatus.equals("RJ") || postStatus.equals("NS");
        }
        if (isReject) {
            wsRejectCnt = (wsRejectCnt + 1) % 10000000L;
        } else {
            wsPostedCnt = (wsPostedCnt + 1) % 10000000L;
        }
        writeResult5000();
        read8000();
    }

    // 3000-POST-PAYMENT
    private static void postPayment3000() throws Exception {
        if (!(txnAmount.compareTo(BigDecimal.ZERO) > 0)) {
            postStatus = "RJ";
        } else {
            BigDecimal exactCharge = txnAmount.multiply(wsSurchargeRate);
            wsCharge = storeTruncate(exactCharge, 3, 2);
            if (wsCharge.compareTo(wsSurchargeCap) > 0) {
                wsCharge = wsSurchargeCap;
            }
            BigDecimal exactNew = txnBalance.subtract(txnAmount).subtract(wsCharge);
            wsNewBal = storeTruncate(exactNew, 9, 2);
            BigDecimal exactFloor = BigDecimal.ZERO.subtract(txnOdLimit);
            wsFloor = storeTruncate(exactFloor, 9, 2);
            if (wsNewBal.compareTo(wsFloor) < 0) {
                wsNewBal = storeTruncate(txnBalance, 9, 2);
                wsCharge = BigDecimal.ZERO.setScale(2);
                postStatus = "NS";
            } else {
                postStatus = "OK";
            }
        }
    }

    // 5000-WRITE-RESULT
    private static void writeResult5000() throws Exception {
        postTxnId = txnId;
        String chargeStr = formatSignedSeparate(wsCharge, 5, 2);
        String balStr = formatSignedSeparate(wsNewBal, 11, 2);
        String rec = postTxnId + chargeStr + balStr + postStatus;
        postWriter.write(rec);
        postWriter.write('\n');
    }

    // 8000-READ
    private static void read8000() throws Exception {
        String line = null;
        try {
            line = txnReader.readLine();
        } catch (Exception e) {
            line = null;
        }
        if (line == null) {
            endOfTxns = true;
            return;
        }
        String raw;
        if (line.length() < 37) {
            StringBuilder sb = new StringBuilder(line);
            while (sb.length() < 37) {
                sb.append(' ');
            }
            raw = sb.toString();
        } else if (line.length() > 37) {
            raw = line.substring(0, 37);
        } else {
            raw = line;
        }
        txnId = raw.substring(0, 9);
        txnType = raw.charAt(9);
        txnAmount = parseSignedSeparate(raw.substring(10, 20), 2);
        txnBalance = parseSignedSeparate(raw.substring(20, 32), 2);
        txnOdLimit = parseUnsigned(raw.substring(32, 37));
    }

    // 9000-TERM
    private static void term9000() throws Exception {
        try {
            if (txnReader != null) {
                txnReader.close();
            }
        } catch (Exception e) {
        }
        try {
            if (postWriter != null) {
                postWriter.flush();
                postWriter.close();
            }
        } catch (Exception e) {
        }
        System.out.println("TXNPOST POSTED=" + formatCount(wsPostedCnt) + " REJECTED=" + formatCount(wsRejectCnt));
    }

    private static BigDecimal parseSignedSeparate(String field, int fracDigits) {
        if (field == null || field.isEmpty()) {
            return BigDecimal.ZERO.setScale(fracDigits);
        }
        boolean negative = field.charAt(0) == '-';
        String digits = field.length() > 1 ? field.substring(1) : "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < digits.length(); i++) {
            char c = digits.charAt(i);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            } else if (c == ' ') {
                sb.append('0');
            } else {
                sb.append('0');
            }
        }
        if (sb.length() == 0) {
            sb.append('0');
        }
        BigInteger bi = new BigInteger(sb.toString());
        BigDecimal v = new BigDecimal(bi, fracDigits);
        if (negative) {
            v = v.negate();
        }
        return v;
    }

    private static BigDecimal parseUnsigned(String field) {
        if (field == null || field.isEmpty()) {
            return BigDecimal.ZERO;
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < field.length(); i++) {
            char c = field.charAt(i);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            } else if (c == ' ') {
                sb.append('0');
            } else {
                sb.append('0');
            }
        }
        if (sb.length() == 0) {
            return BigDecimal.ZERO;
        }
        String s = sb.toString();
        int k = 0;
        while (k < s.length() - 1 && s.charAt(k) == '0') {
            k++;
        }
        String t = s.substring(k);
        if (t.isEmpty()) {
            return BigDecimal.ZERO;
        }
        return new BigDecimal(new BigInteger(t));
    }

    private static BigDecimal storeTruncate(BigDecimal exact, int intDigits, int fracDigits) {
        BigDecimal t = exact.setScale(fracDigits, RoundingMode.DOWN);
        return applyOverflow(t, intDigits, fracDigits);
    }

    private static BigDecimal applyOverflow(BigDecimal v, int intDigits, int fracDigits) {
        int total = intDigits + fracDigits;
        BigInteger mod = BigInteger.TEN.pow(total);
        BigDecimal scaledDec = v.movePointRight(fracDigits);
        BigInteger scaled = scaledDec.toBigIntegerExact();
        BigInteger r = scaled.remainder(mod);
        return new BigDecimal(r, fracDigits);
    }

    private static String formatSignedSeparate(BigDecimal val, int totalDigits, int fracDigits) {
        BigDecimal t = val.setScale(fracDigits, RoundingMode.DOWN);
        BigInteger scaled = t.movePointRight(fracDigits).toBigIntegerExact();
        boolean neg = scaled.signum() < 0;
        BigInteger abs = scaled.abs();
        BigInteger mod = BigInteger.TEN.pow(totalDigits);
        BigInteger rem = abs.remainder(mod);
        String digits = rem.toString();
        while (digits.length() < totalDigits) {
            digits = "0" + digits;
        }
        char sign = neg ? '-' : '+';
        return sign + digits;
    }

    private static String formatCount(long v) {
        long m = v % 10000000L;
        if (m < 0) {
            m += 10000000L;
        }
        String s = Long.toString(m);
        while (s.length() < 7) {
            s = "0" + s;
        }
        return s;
    }
}
