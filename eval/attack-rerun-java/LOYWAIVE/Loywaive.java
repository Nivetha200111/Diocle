import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.math.BigDecimal;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class Loywaive {
    private static String wsEof = "N";
    private static String lyAcct = "";
    private static BigDecimal lyBalance = BigDecimal.ZERO;
    private static int lyTenureMonths = 0;
    private static String loAcct = "";
    private static BigDecimal loFee = BigDecimal.ZERO;
    private static String loCode = "";
    private static BufferedReader lyReader = null;
    private static BufferedWriter loWriter = null;
    private static boolean ebcdicMode = false;

    public static void main(String[] args) throws Exception {
        _0000Main();
    }

    // 0000-MAIN
    private static void _0000Main() throws Exception {
        String lyPath = System.getenv("DD_LOYIN");
        String loPath = System.getenv("DD_LOYOUT");
        String clockEnv = System.getenv("DIOCLE_CLOCK");
        String collEnv = System.getenv("DIOCLE_COLLATION");
        ebcdicMode = "EBCDIC".equals(collEnv);
        if (lyPath == null || loPath == null) {
            throw new IllegalStateException("Missing DD env");
        }
        lyReader = new BufferedReader(new InputStreamReader(new FileInputStream(lyPath), StandardCharsets.ISO_8859_1));
        loWriter = new BufferedWriter(new OutputStreamWriter(new FileOutputStream(loPath), StandardCharsets.ISO_8859_1));
        wsEof = "N";
        while (!isEof()) {
            String line = lyReader.readLine();
            if (line == null) {
                wsEof = "Y";
            } else {
                String rec = padOrTruncate(line, 21);
                lyAcct = rec.substring(0, 8);
                String balField = rec.substring(8, 18);
                String tenField = rec.substring(18, 21);
                lyBalance = parseBalance(balField);
                lyTenureMonths = parseTenure(tenField);
                _1000Fee();
            }
        }
        lyReader.close();
        loWriter.close();
    }

    // 1000-FEE
    private static void _1000Fee() throws Exception {
        loAcct = lyAcct;
        BigDecimal limit = new BigDecimal("5000.00");
        boolean waived = lyBalance.compareTo(limit) >= 0 || lyTenureMonths >= 120;
        if (waived) {
            loFee = BigDecimal.ZERO;
            loCode = "WV";
        } else {
            loFee = new BigDecimal("4.50");
            loCode = "CH";
        }
        String feeText = formatFee(loFee);
        String out = loAcct + feeText + loCode;
        loWriter.write(out);
        loWriter.write("\n");
    }

    private static boolean isEof() {
        if (ebcdicMode) {
            return compareAlpha(wsEof, "Y") == 0;
        }
        return wsEof.equals("Y");
    }

    private static int compareAlpha(String a, String b) {
        if (ebcdicMode) {
            Charset eb = Charset.forName("Cp037");
            byte[] ab = a.getBytes(eb);
            byte[] bb = b.getBytes(eb);
            int n = Math.min(ab.length, bb.length);
            for (int i = 0; i < n; i++) {
                int av = ab[i] & 0xFF;
                int bv = bb[i] & 0xFF;
                if (av != bv) {
                    return av - bv;
                }
            }
            return ab.length - bb.length;
        }
        return a.compareTo(b);
    }

    private static String padOrTruncate(String s, int len) {
        if (s.length() == len) {
            return s;
        }
        if (s.length() < len) {
            StringBuilder sb = new StringBuilder(s);
            while (sb.length() < len) {
                sb.append(' ');
            }
            return sb.toString();
        }
        return s.substring(0, len);
    }

    private static BigDecimal parseBalance(String f) {
        char sc = f.charAt(0);
        int sign = (sc == '-') ? -1 : 1;
        String digs = f.substring(1);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < digs.length(); i++) {
            char c = digs.charAt(i);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            } else if (c == ' ') {
                sb.append('0');
            } else {
                sb.append('0');
            }
        }
        String num = sb.toString();
        if (num.isEmpty()) {
            num = "0";
        }
        BigDecimal v = new BigDecimal(num).movePointLeft(2);
        if (sign < 0) {
            v = v.negate();
        }
        return v;
    }

    private static int parseTenure(String f) {
        String t = f.trim();
        if (t.isEmpty()) {
            return 0;
        }
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < t.length(); i++) {
            char c = t.charAt(i);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            }
        }
        if (sb.length() == 0) {
            return 0;
        }
        return Integer.parseInt(sb.toString());
    }

    private static String formatFee(BigDecimal fee) {
        int cents = fee.movePointRight(2).intValueExact();
        String s = Integer.toString(cents);
        while (s.length() < 4) {
            s = "0" + s;
        }
        return s;
    }
}
