import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;

public class Chqclr {
    private BigDecimal wsTotal = BigDecimal.ZERO;
    private String curRec;
    private String clAcct;
    private String clNumberStr;
    private BigDecimal clDebitVal;
    private String clDebitStr;
    private BigDecimal clFeeVal;
    private String clFeeStr;
    private String clCode;
    private BufferedWriter clWriter;

    public static void main(String[] args) throws Exception {
        Chqclr p = new Chqclr();
        p.p0000Main();
    }

    private void p0000Main() throws Exception {
        String inPath = System.getenv("DD_CHQIN");
        String outPath = System.getenv("DD_CLROUT");
        java.io.FileInputStream fis = new java.io.FileInputStream(inPath);
        byte[] all = fis.readAllBytes();
        fis.close();
        clWriter = null;
        java.io.FileOutputStream fos = new java.io.FileOutputStream(outPath);
        int off = 0;
        while (off + 40 <= all.length) {
            curRec = new String(all, off, 40, StandardCharsets.ISO_8859_1);
            off += 40;
            p1000Item();
            String outRec = clAcct + clNumberStr + clDebitStr + clFeeStr + clCode;
            byte[] outBytes = outRec.getBytes(StandardCharsets.ISO_8859_1);
            // ensure exactly 35 bytes
            if (outBytes.length != 35) {
                byte[] fixed = new byte[35];
                for (int i = 0; i < 35; i++) fixed[i] = (byte) ' ';
                int cp = Math.min(outBytes.length, 35);
                System.arraycopy(outBytes, 0, fixed, 0, cp);
                outBytes = fixed;
            }
            fos.write(outBytes);
        }
        // trailing partial record (short read) padded with spaces, as COBOL would see
        if (off < all.length) {
            byte[] last = new byte[40];
            for (int i = 0; i < 40; i++) last[i] = (byte) ' ';
            System.arraycopy(all, off, last, 0, all.length - off);
            curRec = new String(last, StandardCharsets.ISO_8859_1);
            p1000Item();
            String outRec = clAcct + clNumberStr + clDebitStr + clFeeStr + clCode;
            byte[] outBytes = outRec.getBytes(StandardCharsets.ISO_8859_1);
            if (outBytes.length != 35) {
                byte[] fixed = new byte[35];
                for (int i = 0; i < 35; i++) fixed[i] = (byte) ' ';
                int cp = Math.min(outBytes.length, 35);
                System.arraycopy(outBytes, 0, fixed, 0, cp);
                outBytes = fixed;
            }
            fos.write(outBytes);
        }
        fos.close();
        String ed = formatTotalEd(wsTotal);
        System.out.println("CHQCLR NET=" + ed);
    }

    private void p1000Item() {
        clFeeVal = BigDecimal.ZERO;
        clFeeStr = formatUnsigned(BigDecimal.ZERO, 3, 2);
        String cqType = curRec.substring(0, 1);
        if (cqType.equals("C")) {
            String cqAcct = curRec.substring(1, 11);
            String cqNumberRaw = curRec.substring(11, 19);
            String cqAmountRaw = curRec.substring(19, 29);
            BigDecimal cqAmount = parseSignedLeadingSeparate(cqAmountRaw, 7, 2);
            BigDecimal cqNumberVal = parseUnsigned(cqNumberRaw, 8, 0);
            clAcct = cqAcct;
            clNumberStr = cqNumberRaw;
            BigDecimal v = BigDecimal.ZERO.subtract(cqAmount);
            v = truncateSigned(v, 7, 2);
            clDebitVal = v;
            clDebitStr = formatSignedLeadingSeparate(v, 7, 2);
            clFeeVal = BigDecimal.ZERO;
            clFeeStr = formatUnsigned(BigDecimal.ZERO, 3, 2);
            clCode = "CL";
        } else if (cqType.equals("R")) {
            String rtAcct = curRec.substring(1, 11);
            String rtNumberRaw = curRec.substring(11, 19);
            String rtReason = curRec.substring(19, 21);
            String rtFeeRaw = curRec.substring(21, 26);
            BigDecimal rtFee = parseUnsigned(rtFeeRaw, 3, 2);
            clAcct = rtAcct;
            clNumberStr = rtNumberRaw;
            clDebitVal = BigDecimal.ZERO;
            clDebitStr = formatSignedLeadingSeparate(BigDecimal.ZERO, 7, 2);
            BigDecimal fee;
            if (rtReason.equals("NS")) {
                fee = rtFee.multiply(BigDecimal.valueOf(2));
                fee = truncateUnsigned(fee, 3, 2);
                clFeeVal = fee;
                clFeeStr = formatUnsigned(fee, 3, 2);
            } else {
                clFeeVal = rtFee;
                clFeeStr = rtFeeRaw;
            }
            clCode = "RT";
        } else {
            clAcct = "          ";
            clNumberStr = formatUnsigned(BigDecimal.ZERO, 8, 0);
            clDebitVal = BigDecimal.ZERO;
            clDebitStr = formatSignedLeadingSeparate(BigDecimal.ZERO, 7, 2);
            clFeeVal = BigDecimal.ZERO;
            clFeeStr = formatUnsigned(BigDecimal.ZERO, 3, 2);
            clCode = "RJ";
        }
        wsTotal = wsTotal.add(clDebitVal);
        wsTotal = truncateWs(wsTotal);
        wsTotal = wsTotal.subtract(clFeeVal);
        wsTotal = truncateWs(wsTotal);
    }

    private static BigDecimal parseUnsigned(String s, int intDigits, int fracDigits) {
        int total = intDigits + fracDigits;
        byte[] b = s.getBytes(StandardCharsets.ISO_8859_1);
        BigInteger unscaled = BigInteger.ZERO;
        for (int i = 0; i < total; i++) {
            int c;
            if (i < b.length) c = b[i] & 0xFF;
            else c = 0x20;
            int d = c & 0x0F;
            unscaled = unscaled.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
        }
        return new BigDecimal(unscaled, fracDigits);
    }

    private static BigDecimal parseSignedLeadingSeparate(String s, int intDigits, int fracDigits) {
        int total = 1 + intDigits + fracDigits;
        byte[] b = s.getBytes(StandardCharsets.ISO_8859_1);
        byte[] buf = new byte[total];
        for (int i = 0; i < total; i++) {
            if (i < b.length) buf[i] = b[i];
            else buf[i] = (byte) ' ';
        }
        int c0 = buf[0] & 0xFF;
        boolean negative = (c0 == (byte) '-');
        boolean hasSign = (c0 == (byte) '+' || c0 == (byte) '-' || c0 == (byte) ' ');
        BigInteger unscaled = BigInteger.ZERO;
        if (hasSign) {
            for (int i = 1; i < total; i++) {
                int d = (buf[i] & 0x0F);
                unscaled = unscaled.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
            }
        } else {
            for (int i = 0; i < total; i++) {
                int d = (buf[i] & 0x0F);
                unscaled = unscaled.multiply(BigInteger.TEN).add(BigInteger.valueOf(d));
            }
        }
        BigDecimal v = new BigDecimal(unscaled, fracDigits);
        if (negative) v = v.negate();
        return v;
    }

    private static BigDecimal truncateTo(BigDecimal v, int intDigits, int fracDigits, boolean signed) {
        BigDecimal t = v.setScale(fracDigits, RoundingMode.DOWN);
        BigInteger unscaled = t.movePointRight(fracDigits).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        BigInteger r = unscaled.remainder(mod);
        return new BigDecimal(r, fracDigits);
    }

    private static BigDecimal truncateSigned(BigDecimal v, int intDigits, int fracDigits) {
        return truncateTo(v, intDigits, fracDigits, true);
    }

    private static BigDecimal truncateUnsigned(BigDecimal v, int intDigits, int fracDigits) {
        BigDecimal t = v.setScale(fracDigits, RoundingMode.DOWN);
        if (t.signum() < 0) t = t.negate();
        BigInteger unscaled = t.movePointRight(fracDigits).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        BigInteger r = unscaled.remainder(mod);
        if (r.signum() < 0) r = r.add(mod);
        return new BigDecimal(r, fracDigits);
    }

    private static BigDecimal truncateWs(BigDecimal v) {
        BigDecimal t = v.setScale(2, RoundingMode.DOWN);
        BigInteger unscaled = t.movePointRight(2).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(11);
        BigInteger r = unscaled.remainder(mod);
        return new BigDecimal(r, 2);
    }

    private static String formatUnsigned(BigDecimal v, int intDigits, int fracDigits) {
        BigDecimal t = v.setScale(fracDigits, RoundingMode.DOWN);
        if (t.signum() < 0) t = t.negate();
        BigInteger unscaled = t.movePointRight(fracDigits).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        BigInteger r = unscaled.remainder(mod);
        if (r.signum() < 0) r = r.add(mod);
        String s = r.toString();
        int need = intDigits + fracDigits;
        if (s.length() < need) s = "0".repeat(need - s.length()) + s;
        else if (s.length() > need) s = s.substring(s.length() - need);
        return s;
    }

    private static String formatSignedLeadingSeparate(BigDecimal v, int intDigits, int fracDigits) {
        boolean negative = v.signum() < 0;
        BigDecimal a = negative ? v.negate() : v;
        a = a.setScale(fracDigits, RoundingMode.DOWN);
        BigInteger unscaled = a.movePointRight(fracDigits).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        BigInteger r = unscaled.remainder(mod);
        String digits = r.toString();
        int need = intDigits + fracDigits;
        if (digits.length() < need) digits = "0".repeat(need - digits.length()) + digits;
        else if (digits.length() > need) digits = digits.substring(digits.length() - need);
        char sign = negative ? '-' : '+';
        return sign + digits;
    }

    private static String formatTotalEd(BigDecimal total) {
        BigDecimal t = total.setScale(2, RoundingMode.DOWN);
        boolean negative = t.signum() < 0;
        BigDecimal a = negative ? t.negate() : t;
        BigInteger unscaled = a.movePointRight(2).toBigIntegerExact();
        BigInteger[] divRem = unscaled.divideAndRemainder(BigInteger.valueOf(100));
        BigInteger intPart = divRem[0];
        int frac = divRem[1].intValue();
        String intStr = intPart.toString();
        if (intStr.length() < 10) intStr = "0".repeat(10 - intStr.length()) + intStr;
        else if (intStr.length() > 10) intStr = intStr.substring(intStr.length() - 10);
        String fracStr = String.format("%02d", frac);
        int firstNz = -1;
        for (int i = 0; i < 10; i++) {
            if (intStr.charAt(i) != '0') { firstNz = i; break; }
        }
        String intOut;
        if (firstNz == -1) {
            intOut = " ".repeat(9) + "0";
        } else if (!negative) {
            intOut = " ".repeat(firstNz) + intStr.substring(firstNz);
        } else {
            intOut = " ".repeat(firstNz - 1) + "-" + intStr.substring(firstNz);
        }
        return intOut + "." + fracStr;
    }
}
