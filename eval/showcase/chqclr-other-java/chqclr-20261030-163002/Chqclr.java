import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class Chqclr {
    private static BigDecimal wsTotal = BigDecimal.ZERO;
    private static String wsEof = "N";
    private static List<String> inRecs = new ArrayList<>();
    private static int inIdx = 0;
    private static String curRaw = null;
    private static String clAcct = "          ";
    private static String clNumberStr = "00000000";
    private static BigDecimal clDebit = BigDecimal.ZERO;
    private static BigDecimal clFee = BigDecimal.ZERO;
    private static String clCode = "  ";
    private static List<String> outRecs = new ArrayList<>();
    private static boolean lineMode = true;

    public static void main(String[] args) throws Exception {
        String fIn = System.getenv("DD_CHQIN");
        String fOut = System.getenv("DD_CLROUT");
        if (fIn == null || fOut == null) {
            System.err.println("missing DD");
            System.exit(1);
            return;
        }
        byte[] raw = Files.readAllBytes(Paths.get(fIn));
        boolean hasNl = false;
        for (byte b : raw) {
            if (b == 0x0A) { hasNl = true; break; }
        }
        inRecs = new ArrayList<>();
        if (raw.length == 0) {
            lineMode = true;
        } else if (hasNl) {
            lineMode = true;
            String content = new String(raw, StandardCharsets.ISO_8859_1);
            List<String> lines = new ArrayList<>();
            int start = 0;
            for (int i = 0; i < content.length(); i++) {
                if (content.charAt(i) == '\n') {
                    lines.add(content.substring(start, i));
                    start = i + 1;
                }
            }
            if (start < content.length()) {
                lines.add(content.substring(start));
            }
            for (String ln : lines) {
                String s = ln;
                if (s.endsWith("\r")) s = s.substring(0, s.length() - 1);
                if (s.length() < 40) {
                    StringBuilder sb = new StringBuilder(s);
                    while (sb.length() < 40) sb.append(' ');
                    s = sb.toString();
                } else if (s.length() > 40) {
                    s = s.substring(0, 40);
                }
                inRecs.add(s);
            }
        } else {
            lineMode = false;
            String content = new String(raw, StandardCharsets.ISO_8859_1);
            int off = 0;
            while (off < content.length()) {
                int end = Math.min(off + 40, content.length());
                String chunk = content.substring(off, end);
                if (chunk.length() < 40) {
                    StringBuilder sb = new StringBuilder(chunk);
                    while (sb.length() < 40) sb.append(' ');
                    chunk = sb.toString();
                }
                inRecs.add(chunk);
                off += 40;
            }
        }
        inIdx = 0;
        wsEof = "N";
        wsTotal = BigDecimal.ZERO;
        outRecs = new ArrayList<>();
        p0000Main();
        byte[] outBytes;
        if (lineMode) {
            StringBuilder sb = new StringBuilder();
            for (String r : outRecs) sb.append(r).append('\n');
            outBytes = sb.toString().getBytes(StandardCharsets.ISO_8859_1);
        } else {
            StringBuilder sb = new StringBuilder();
            for (String r : outRecs) sb.append(r);
            outBytes = sb.toString().getBytes(StandardCharsets.ISO_8859_1);
        }
        Files.write(Paths.get(fOut), outBytes);
    }

    private static void p0000Main() throws Exception {
        while (!wsEof.equals("Y")) {
            if (inIdx >= inRecs.size()) {
                wsEof = "Y";
            } else {
                curRaw = inRecs.get(inIdx++);
                p1000Item();
            }
        }
        String edited = formatTotalEdited(wsTotal);
        String line = "CHQCLR NET=" + edited + "\n";
        System.out.write(line.getBytes(StandardCharsets.ISO_8859_1));
        System.out.flush();
    }

    private static void p1000Item() {
        clFee = BigDecimal.ZERO;
        String feeOutStr = "00000";
        char typ = curRaw.charAt(0);
        if (typ == 'C') {
            clAcct = curRaw.substring(1, 11);
            clNumberStr = curRaw.substring(11, 19);
            String amtStr = curRaw.substring(19, 29);
            BigDecimal cqAmt = cobolSignedLeadingVal(amtStr, 2);
            BigDecimal neg = cqAmt.negate();
            clDebit = truncateSigned(neg, 7, 2);
            clCode = "CL";
            feeOutStr = formatUnsigned(clFee, 3, 2);
        } else if (typ == 'R') {
            clAcct = curRaw.substring(1, 11);
            clNumberStr = curRaw.substring(11, 19);
            clDebit = BigDecimal.ZERO;
            String reason = curRaw.substring(19, 21);
            String feeStr = curRaw.substring(21, 26);
            BigDecimal rtFee = cobolUnsignedVal(feeStr, 2);
            if (reason.equals("NS")) {
                BigDecimal doubled = rtFee.multiply(new BigDecimal("2"));
                clFee = truncateUnsigned(doubled, 3, 2);
                feeOutStr = formatUnsigned(clFee, 3, 2);
            } else {
                clFee = rtFee;
                feeOutStr = feeStr;
            }
            clCode = "RT";
        } else {
            clAcct = "          ";
            clNumberStr = "00000000";
            clDebit = BigDecimal.ZERO;
            clFee = BigDecimal.ZERO;
            clCode = "RJ";
        }
        BigDecimal addD = truncateSigned(clDebit, 7, 2);
        BigDecimal addF = truncateUnsigned(clFee, 3, 2);
        wsTotal = wsTotal.add(addD).subtract(addF);
        wsTotal = truncateSigned(wsTotal, 9, 2);
        String debitStr = formatSignedLeading(clDebit, 7, 2);
        String rec = clAcct + clNumberStr + debitStr + feeOutStr + clCode;
        outRecs.add(rec);
    }

    private static boolean isStrictUnsigned(String s) {
        if (s == null || s.isEmpty()) return false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c < '0' || c > '9') return false;
        }
        return true;
    }

    private static BigDecimal cobolUnsignedVal(String s, int dec) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO;
        int n = s.length();
        int[] d = new int[n];
        for (int i = 0; i < n; i++) d[i] = s.charAt(i) & 0x0F;
        if ((n & 1) == 1) {
            for (int i = 0; i + 1 < n - 1; i += 2) {
                if (d[i] > 9 || d[i + 1] > 9) {
                    d[i] = 0;
                    d[i + 1] = 0;
                }
            }
            if (d[n - 1] > 9) d[n - 1] = 0;
        } else {
            for (int i = 1; i + 1 < n - 1; i += 2) {
                if (d[i] > 9 || d[i + 1] > 9) {
                    d[i] = 0;
                    d[i + 1] = 0;
                }
            }
            if (d[0] > 9) d[0] = 0;
            if (d[n - 1] > 9) d[n - 1] = 0;
        }
        BigDecimal v = BigDecimal.ZERO;
        for (int i = 0; i < n; i++) {
            v = v.movePointRight(1).add(BigDecimal.valueOf(d[i]));
        }
        return v.movePointLeft(dec);
    }

    private static BigDecimal cobolSignedLeadingVal(String s, int dec) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO;
        char c0 = s.charAt(0);
        boolean neg = (c0 == '-');
        boolean isSign = (c0 == '-' || c0 == '+');
        String rest = isSign ? s.substring(1) : s;
        int n = rest.length();
        int[] d = new int[n];
        for (int i = 0; i < n; i++) d[i] = rest.charAt(i) & 0x0F;
        if (n > 0) {
            if ((n & 1) == 1) {
                for (int i = 0; i + 1 < n - 1; i += 2) {
                    if (d[i] > 9 || d[i + 1] > 9) {
                        d[i] = 0;
                        d[i + 1] = 0;
                    }
                }
                if (d[n - 1] > 9) d[n - 1] = 0;
            } else {
                for (int i = 1; i + 1 < n - 1; i += 2) {
                    if (d[i] > 9 || d[i + 1] > 9) {
                        d[i] = 0;
                        d[i + 1] = 0;
                    }
                }
                if (d[0] > 9) d[0] = 0;
                if (d[n - 1] > 9) d[n - 1] = 0;
            }
        }
        BigDecimal v = BigDecimal.ZERO;
        for (int i = 0; i < n; i++) {
            v = v.movePointRight(1).add(BigDecimal.valueOf(d[i]));
        }
        BigDecimal r = v.movePointLeft(dec);
        return neg ? r.negate() : r;
    }

    private static BigDecimal parseUnsigned(String s, int dec) {
        if (s == null) return BigDecimal.ZERO;
        String t = s.trim();
        if (t.isEmpty()) return BigDecimal.ZERO;
        try {
            return new BigDecimal(t).movePointLeft(dec);
        } catch (NumberFormatException e) {
            return BigDecimal.ZERO;
        }
    }

    private static BigDecimal parseSignedLeading(String s, int dec) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO;
        char c0 = s.charAt(0);
        boolean hasSign = (c0 == '+' || c0 == '-' || c0 == ' ');
        boolean neg = (c0 == '-');
        String digits;
        if (hasSign) digits = s.substring(1);
        else { digits = s; neg = false; }
        String t = digits.trim();
        if (t.isEmpty()) return BigDecimal.ZERO;
        try {
            BigDecimal v = new BigDecimal(t).movePointLeft(dec);
            return neg ? v.negate() : v;
        } catch (NumberFormatException e) {
            return BigDecimal.ZERO;
        }
    }

    private static BigDecimal truncateUnsigned(BigDecimal v, int intD, int decD) {
        int total = intD + decD;
        BigDecimal scaled = v.movePointRight(decD).setScale(0, RoundingMode.DOWN);
        BigDecimal div = BigDecimal.TEN.pow(total);
        BigDecimal r = scaled.remainder(div);
        if (r.signum() < 0) r = r.abs();
        return r.movePointLeft(decD);
    }

    private static BigDecimal truncateSigned(BigDecimal v, int intD, int decD) {
        int total = intD + decD;
        BigDecimal scaled = v.movePointRight(decD).setScale(0, RoundingMode.DOWN);
        BigDecimal div = BigDecimal.TEN.pow(total);
        BigDecimal r = scaled.remainder(div);
        return r.movePointLeft(decD);
    }

    private static String formatUnsigned(BigDecimal v, int intD, int decD) {
        int total = intD + decD;
        BigDecimal t = truncateUnsigned(v, intD, decD);
        BigDecimal scaled = t.movePointRight(decD).setScale(0, RoundingMode.DOWN);
        String s = scaled.abs().toBigInteger().toString();
        while (s.length() < total) s = "0" + s;
        if (s.length() > total) s = s.substring(s.length() - total);
        return s;
    }

    private static String formatSignedLeading(BigDecimal v, int intD, int decD) {
        int total = intD + decD;
        BigDecimal t = truncateSigned(v, intD, decD);
        BigDecimal scaled = t.movePointRight(decD).setScale(0, RoundingMode.DOWN);
        boolean neg = scaled.signum() < 0;
        String s = scaled.abs().toBigInteger().toString();
        while (s.length() < total) s = "0" + s;
        if (s.length() > total) s = s.substring(s.length() - total);
        return (neg ? "-" : "+") + s;
    }

    private static String formatTotalEdited(BigDecimal v) {
        boolean neg = v.signum() < 0;
        BigDecimal abs = v.abs();
        BigDecimal centsBd = abs.movePointRight(2).setScale(0, RoundingMode.DOWN);
        BigInteger cents = centsBd.toBigInteger();
        BigInteger[] dr = cents.divideAndRemainder(BigInteger.valueOf(100));
        BigInteger ip = dr[0];
        int decVal = dr[1].intValue();
        String rawInt = ip.toString();
        while (rawInt.length() < 10) rawInt = "0" + rawInt;
        if (rawInt.length() > 10) rawInt = rawInt.substring(rawInt.length() - 10);
        String decStr = Integer.toString(decVal);
        while (decStr.length() < 2) decStr = "0" + decStr;
        int first = -1;
        for (int i = 0; i < 10; i++) {
            if (rawInt.charAt(i) != '0') { first = i; break; }
        }
        char[] ed = new char[10];
        for (int i = 0; i < 10; i++) ed[i] = ' ';
        if (!neg) {
            if (first != -1) {
                for (int i = first; i < 10; i++) ed[i] = rawInt.charAt(i);
            } else {
                ed[9] = '0';
            }
        } else {
            if (first == -1) {
                ed[9] = '0';
                ed[8] = '-';
            } else if (first == 0) {
                for (int i = 0; i < 10; i++) ed[i] = rawInt.charAt(i);
            } else {
                for (int i = first; i < 10; i++) ed[i] = rawInt.charAt(i);
                ed[first - 1] = '-';
            }
        }
        return new String(ed) + "." + decStr;
    }
}
