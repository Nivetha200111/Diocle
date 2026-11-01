import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class Acctmtch {
    private static BufferedReader mstReader;
    private static BufferedReader txnReader;
    private static OutputStream newOut;
    private static OutputStream excOut;
    private static String msAcctId = "        ";
    private static BigDecimal msBalance = BigDecimal.ZERO.setScale(2);
    private static String msStatus = "    ";
    private static String txAcctId = "        ";
    private static BigDecimal txAmount = BigDecimal.ZERO.setScale(2);
    private static String txType = " ";
    private static String wsMstKey = "        ";
    private static boolean wsMstHigh = false;
    private static String wsTxnKey = "        ";
    private static boolean wsTxnHigh = false;
    private static BigDecimal wsBalance = BigDecimal.ZERO.setScale(2);
    private static int wsCount = 0;
    private static int wsExcCnt = 0;
    private static int wsNewCnt = 0;
    private static String nmAcctId = "        ";
    private static BigDecimal nmBalance = BigDecimal.ZERO.setScale(2);
    private static String nmStatus = "    ";
    private static int nmTxnCount = 0;
    private static String exAcctId = "        ";
    private static BigDecimal exAmount = BigDecimal.ZERO.setScale(2);
    private static String exReason = "            ";

    public static void main(String[] args) throws Exception {
        p0000Main();
    }

    // 0000-MAIN
    private static void p0000Main() throws Exception {
        String mstPath = System.getenv("DD_MSTIN");
        String txnPath = System.getenv("DD_TXNIN");
        String newPath = System.getenv("DD_NEWMST");
        String excPath = System.getenv("DD_EXCOUT");
        Charset latin1 = StandardCharsets.ISO_8859_1;
        mstReader = new BufferedReader(new InputStreamReader(new FileInputStream(mstPath), latin1));
        txnReader = new BufferedReader(new InputStreamReader(new FileInputStream(txnPath), latin1));
        newOut = new FileOutputStream(newPath);
        excOut = new FileOutputStream(excPath);
        p8100ReadMst();
        p8200ReadTxn();
        while (!(wsMstHigh && wsTxnHigh)) {
            p2000Match();
        }
        mstReader.close();
        txnReader.close();
        newOut.close();
        excOut.close();
        String line = "ACCTMTCH NEW=" + formatComp7(wsNewCnt) + " EXC=" + formatComp7(wsExcCnt);
        System.out.println(line);
        if (wsExcCnt > 0) {
            System.exit(4);
        }
    }

    // 2000-MATCH
    private static void p2000Match() throws Exception {
        int cmp = compareKeys(wsTxnKey, wsTxnHigh, wsMstKey, wsMstHigh);
        if (cmp < 0) {
            exAcctId = txAcctId;
            exAmount = txAmount;
            exReason = padRight("NO ACCOUNT", 12);
            p7000WriteExc();
            p8200ReadTxn();
        } else if (cmp == 0) {
            p3000Apply();
            p8200ReadTxn();
        } else {
            p4000WriteMaster();
            p8100ReadMst();
        }
    }

    // 3000-APPLY
    private static void p3000Apply() throws Exception {
        if ("FRZN".equals(msStatus)) {
            exAcctId = txAcctId;
            exAmount = txAmount;
            exReason = padRight("FROZEN", 12);
            p7000WriteExc();
        } else if ("C".equals(txType)) {
            wsBalance = truncBalance(wsBalance.add(txAmount));
            wsCount = (wsCount + 1) % 10000;
        } else if ("D".equals(txType)) {
            wsBalance = truncBalance(wsBalance.subtract(txAmount));
            wsCount = (wsCount + 1) % 10000;
        } else {
            exAcctId = txAcctId;
            exAmount = txAmount;
            exReason = padRight("BAD TYPE", 12);
            p7000WriteExc();
        }
    }

    // 4000-WRITE-MASTER
    private static void p4000WriteMaster() throws Exception {
        nmAcctId = msAcctId;
        nmBalance = wsBalance;
        nmStatus = msStatus;
        nmTxnCount = wsCount;
        String rec = nmAcctId + formatSignedSeparate(nmBalance, 9) + nmStatus + formatCount4(nmTxnCount);
        writeLine(newOut, rec);
        wsNewCnt = (wsNewCnt + 1) % 10000000;
    }

    // 7000-WRITE-EXC
    private static void p7000WriteExc() throws Exception {
        String rec = exAcctId + formatSignedSeparate(exAmount, 7) + exReason;
        writeLine(excOut, rec);
        wsExcCnt = (wsExcCnt + 1) % 10000000;
    }

    // 8100-READ-MST
    private static void p8100ReadMst() throws Exception {
        String line = mstReader.readLine();
        if (line == null) {
            wsMstHigh = true;
            wsMstKey = "\u00FF\u00FF\u00FF\u00FF\u00FF\u00FF\u00FF\u00FF";
        } else {
            if (line.length() < 24) {
                line = line + " ".repeat(24 - line.length());
            } else if (line.length() > 24) {
                line = line.substring(0, 24);
            }
            msAcctId = line.substring(0, 8);
            String balStr = line.substring(8, 20);
            msStatus = line.substring(20, 24);
            wsMstKey = msAcctId;
            wsMstHigh = false;
            msBalance = parseSignedSeparate(balStr);
            wsBalance = msBalance;
            wsCount = 0;
        }
    }

    // 8200-READ-TXN
    private static void p8200ReadTxn() throws Exception {
        String line = txnReader.readLine();
        if (line == null) {
            wsTxnHigh = true;
            wsTxnKey = "\u00FF\u00FF\u00FF\u00FF\u00FF\u00FF\u00FF\u00FF";
        } else {
            if (line.length() < 19) {
                line = line + " ".repeat(19 - line.length());
            } else if (line.length() > 19) {
                line = line.substring(0, 19);
            }
            txAcctId = line.substring(0, 8);
            String amtStr = line.substring(8, 18);
            txType = line.substring(18, 19);
            wsTxnKey = txAcctId;
            wsTxnHigh = false;
            txAmount = parseSignedSeparate(amtStr);
        }
    }

    private static int compareKeys(String txnKey, boolean txnHigh, String mstKey, boolean mstHigh) {
        if (txnHigh && mstHigh) {
            return 0;
        }
        if (txnHigh) {
            return 1;
        }
        if (mstHigh) {
            return -1;
        }
        if ("EBCDIC".equals(System.getenv("DIOCLE_COLLATION"))) {
            Charset ebcdic = Charset.forName("Cp037");
            byte[] a = txnKey.getBytes(ebcdic);
            byte[] b = mstKey.getBytes(ebcdic);
            int n = Math.min(a.length, b.length);
            for (int i = 0; i < n; i++) {
                int av = a[i] & 0xFF;
                int bv = b[i] & 0xFF;
                if (av != bv) {
                    return av - bv;
                }
            }
            return a.length - b.length;
        } else {
            return txnKey.compareTo(mstKey);
        }
    }

    private static BigDecimal parseSignedSeparate(String f) {
        if (f == null || f.isEmpty()) {
            return BigDecimal.ZERO.setScale(2);
        }
        char sc = f.charAt(0);
        boolean neg = (sc == '-');
        String digits = f.substring(1);
        StringBuilder sb = new StringBuilder(digits.length());
        for (int i = 0; i < digits.length(); i++) {
            char c = digits.charAt(i);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            } else if (c == ' ') {
                sb.append('0');
            } else {
                sb.append(c);
            }
        }
        String d = sb.toString();
        if (d.isEmpty()) {
            d = "0";
        }
        BigInteger unscaled;
        try {
            unscaled = new BigInteger(d);
        } catch (NumberFormatException e) {
            unscaled = BigInteger.ZERO;
        }
        BigDecimal v = new BigDecimal(unscaled, 2);
        if (neg) {
            v = v.negate();
        }
        return v;
    }

    private static String formatSignedSeparate(BigDecimal v, int intDigits) {
        int total = intDigits + 2;
        BigDecimal s = v.setScale(2, RoundingMode.DOWN);
        BigInteger unscaled = s.unscaledValue();
        boolean neg = unscaled.signum() < 0;
        String digits = unscaled.abs().toString();
        if (digits.length() > total) {
            digits = digits.substring(digits.length() - total);
        } else if (digits.length() < total) {
            digits = "0".repeat(total - digits.length()) + digits;
        }
        return (neg ? "-" : "+") + digits;
    }

    private static BigDecimal truncBalance(BigDecimal v) {
        BigDecimal s = v.setScale(2, RoundingMode.DOWN);
        BigInteger unscaled = s.unscaledValue();
        if (unscaled.abs().toString().length() <= 11) {
            return s;
        }
        BigInteger mod = BigInteger.TEN.pow(11);
        boolean neg = unscaled.signum() < 0;
        BigInteger abs = unscaled.abs().mod(mod);
        if (abs.equals(BigInteger.ZERO)) {
            return BigDecimal.ZERO.setScale(2);
        }
        BigDecimal r = new BigDecimal(abs, 2);
        return neg ? r.negate() : r;
    }

    private static String formatCount4(int v) {
        int t = v % 10000;
        if (t < 0) {
            t += 10000;
        }
        String s = Integer.toString(t);
        if (s.length() < 4) {
            s = "0".repeat(4 - s.length()) + s;
        }
        return s;
    }

    private static String formatComp7(int v) {
        int t = v % 10000000;
        if (t < 0) {
            t += 10000000;
        }
        String s = Integer.toString(t);
        if (s.length() < 7) {
            s = "0".repeat(7 - s.length()) + s;
        }
        return s;
    }

    private static String padRight(String s, int n) {
        if (s.length() >= n) {
            return s.substring(0, n);
        }
        return s + " ".repeat(n - s.length());
    }

    private static void writeLine(OutputStream out, String rec) throws Exception {
        out.write(rec.getBytes(StandardCharsets.ISO_8859_1));
        out.write('\n');
    }
}
