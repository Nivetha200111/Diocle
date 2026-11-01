import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class Chqclr {
    private BigDecimal wsTotal = BigDecimal.ZERO.setScale(2);
    private List<String> inRecs = new ArrayList<>();
    private List<String> outRecs = new ArrayList<>();
    private boolean lineMode = false;
    private String curCqRec;

    public static void main(String[] args) throws Exception {
        Chqclr p = new Chqclr();
        p.p0000Main();
    }

    private void p0000Main() throws Exception {
        String inPath = System.getenv("DD_CHQIN");
        String outPath = System.getenv("DD_CLROUT");
        if (inPath == null || outPath == null) {
            throw new IllegalStateException("DD_CHQIN / DD_CLROUT not set");
        }
        byte[] all = Files.readAllBytes(Paths.get(inPath));
        for (byte b : all) {
            if (b == 0x0A || b == 0x0D) { lineMode = true; break; }
        }
        inRecs.clear();
        outRecs.clear();
        if (all.length != 0) {
            if (lineMode) {
                String s = new String(all, StandardCharsets.ISO_8859_1);
                String[] parts = s.split("\r\n|\n|\r", -1);
                boolean endsNl = all[all.length - 1] == 0x0A || all[all.length - 1] == 0x0D;
                int limit = endsNl ? parts.length - 1 : parts.length;
                for (int i = 0; i < limit; i++) {
                    String line = parts[i];
                    if (line.length() > 40) line = line.substring(0, 40);
                    else if (line.length() < 40) line = line + " ".repeat(40 - line.length());
                    inRecs.add(line);
                }
            } else {
                int recLen = 40;
                int n = all.length / recLen;
                for (int i = 0; i < n; i++) {
                    String r = new String(all, i * recLen, recLen, StandardCharsets.ISO_8859_1);
                    inRecs.add(r);
                }
                int rem = all.length % recLen;
                if (rem != 0) {
                    String r = new String(all, n * recLen, rem, StandardCharsets.ISO_8859_1);
                    r = r + " ".repeat(recLen - rem);
                    inRecs.add(r);
                }
            }
        }
        wsTotal = BigDecimal.ZERO.setScale(2);
        for (String r : inRecs) {
            curCqRec = r;
            p1000Item();
        }
        if (lineMode) {
            StringBuilder sb = new StringBuilder();
            for (String r : outRecs) sb.append(r).append('\n');
            Files.write(Paths.get(outPath), sb.toString().getBytes(StandardCharsets.ISO_8859_1));
        } else {
            StringBuilder sb = new StringBuilder();
            for (String r : outRecs) sb.append(r);
            Files.write(Paths.get(outPath), sb.toString().getBytes(StandardCharsets.ISO_8859_1));
        }
        String ed = formatTotalEd(wsTotal);
        String line = "CHQCLR NET=" + ed;
        System.out.write((line + "\n").getBytes(StandardCharsets.ISO_8859_1));
        System.out.flush();
    }

    private void p1000Item() {
        String rec = curCqRec;
        char typ = rec.charAt(0);
        String clAcct;
        String clNum;
        String clDebStr;
        String clFeeStr;
        String clCode;
        BigDecimal clDebBd;
        BigDecimal clFeeBd;
        if (typ == 'C') {
            clAcct = rec.substring(1, 11);
            clNum = rec.substring(11, 19);
            String amtStr = rec.substring(19, 29);
            BigDecimal amt = parseSignLeadingSeparate(amtStr, 7, 2);
            BigDecimal deb = truncSigned(amt.negate(), 7, 2);
            clDebBd = deb;
            clDebStr = formatSignLeadingSeparate(deb, 7, 2);
            clFeeBd = BigDecimal.ZERO.setScale(2);
            clFeeStr = "00000";
            clCode = "CL";
        } else if (typ == 'R') {
            clAcct = rec.substring(1, 11);
            clNum = rec.substring(11, 19);
            String reason = rec.substring(19, 21);
            String feeStr = rec.substring(21, 26);
            BigDecimal fee = parseDisplayUnsigned(feeStr, 2);
            BigDecimal outFee;
            if (reason.equals("NS")) {
                outFee = truncUnsigned(fee.multiply(BigDecimal.valueOf(2)), 3, 2);
            } else {
                outFee = truncUnsigned(fee, 3, 2);
            }
            clFeeBd = outFee;
            clFeeStr = formatDisplayUnsigned(outFee, 3, 2);
            clDebBd = BigDecimal.ZERO.setScale(2);
            clDebStr = formatSignLeadingSeparate(clDebBd, 7, 2);
            clCode = "RT";
        } else {
            clAcct = "          ";
            clNum = "00000000";
            clDebBd = BigDecimal.ZERO.setScale(2);
            clDebStr = formatSignLeadingSeparate(clDebBd, 7, 2);
            clFeeBd = BigDecimal.ZERO.setScale(2);
            clFeeStr = "00000";
            clCode = "RJ";
        }
        wsTotal = truncSigned(wsTotal.add(clDebBd), 9, 2);
        wsTotal = truncSigned(wsTotal.subtract(clFeeBd), 9, 2);
        outRecs.add(clAcct + clNum + clDebStr + clFeeStr + clCode);
    }

    private static BigDecimal parseSignLeadingSeparate(String s, int intD, int decD) {
        char sc = s.charAt(0);
        String digits = s.substring(1);
        BigInteger bi = BigInteger.ZERO;
        for (int i = 0; i < digits.length(); i++) {
            int d = digits.charAt(i) & 0x0F;
            bi = bi.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
        }
        BigDecimal v = new BigDecimal(bi).movePointLeft(decD);
        if (sc == '-') v = v.negate();
        return v.setScale(decD);
    }

    private static BigDecimal parseDisplayUnsigned(String s, int decD) {
        BigInteger bi = BigInteger.ZERO;
        for (int i = 0; i < s.length(); i++) {
            int d = s.charAt(i) & 0x0F;
            bi = bi.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
        }
        return new BigDecimal(bi).movePointLeft(decD).setScale(decD);
    }

    private static BigDecimal truncSigned(BigDecimal v, int intD, int decD) {
        BigDecimal t = v.setScale(decD, RoundingMode.DOWN);
        BigInteger scaled = t.movePointRight(decD).toBigIntegerExact();
        if (scaled.equals(BigInteger.ZERO)) return BigDecimal.ZERO.setScale(decD);
        boolean neg = scaled.signum() < 0;
        BigInteger mod = BigInteger.TEN.pow(intD + decD);
        BigInteger low = scaled.abs().mod(mod);
        if (low.equals(BigInteger.ZERO)) return BigDecimal.ZERO.setScale(decD);
        BigDecimal r = new BigDecimal(low).movePointLeft(decD).setScale(decD);
        return neg ? r.negate() : r;
    }

    private static BigDecimal truncUnsigned(BigDecimal v, int intD, int decD) {
        BigDecimal t = v.setScale(decD, RoundingMode.DOWN);
        if (t.signum() < 0) t = t.negate();
        BigInteger scaled = t.movePointRight(decD).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intD + decD);
        BigInteger low = scaled.mod(mod);
        return new BigDecimal(low).movePointLeft(decD).setScale(decD);
    }

    private static String formatSignLeadingSeparate(BigDecimal v, int intD, int decD) {
        BigDecimal t = truncSigned(v, intD, decD);
        BigInteger scaled = t.movePointRight(decD).toBigIntegerExact();
        boolean neg = scaled.signum() < 0;
        String digits = scaled.abs().toString();
        int total = intD + decD;
        while (digits.length() < total) digits = "0" + digits;
        char sign = neg ? '-' : '+';
        return sign + digits;
    }

    private static String formatDisplayUnsigned(BigDecimal v, int intD, int decD) {
        BigDecimal t = truncUnsigned(v, intD, decD);
        BigInteger scaled = t.movePointRight(decD).toBigIntegerExact();
        String digits = scaled.toString();
        int total = intD + decD;
        while (digits.length() < total) digits = "0" + digits;
        return digits;
    }

    private static String formatTotalEd(BigDecimal total) {
        BigDecimal t = truncSigned(total, 9, 2);
        boolean neg = t.signum() < 0;
        BigDecimal abs = t.abs();
        BigInteger scaled = abs.movePointRight(2).toBigIntegerExact();
        BigInteger[] dr = scaled.divideAndRemainder(BigInteger.valueOf(100));
        BigInteger intPart = dr[0];
        int cents = dr[1].intValue();
        String int10 = intPart.toString();
        while (int10.length() < 10) int10 = "0" + int10;
        String frac2 = cents < 10 ? "0" + cents : Integer.toString(cents);
        char[] ic = int10.toCharArray();
        char[] out = new char[10];
        if (intPart.equals(BigInteger.ZERO)) {
            for (int i = 0; i < 9; i++) out[i] = ' ';
            out[9] = '0';
            if (neg) out[8] = '-';
        } else {
            int first = 0;
            while (first < 10 && ic[first] == '0') first++;
            for (int i = 0; i < 10; i++) out[i] = ic[i];
            for (int i = 0; i < 9; i++) {
                if (i < first) {
                    if (neg && i == first - 1) out[i] = '-';
                    else out[i] = ' ';
                }
            }
        }
        return new String(out) + "." + frac2;
    }
}
