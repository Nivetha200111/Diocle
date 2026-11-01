import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;

public class Chqclr {
    private byte[] cqBytes = new byte[0];
    private int cqPos = 0;
    private ByteArrayOutputStream clOut = new ByteArrayOutputStream();
    private byte[] cqRec = new byte[40];
    private byte[] clRec = new byte[35];
    private BigDecimal wsTotal = BigDecimal.ZERO;
    private boolean wsEof = false;

    public static void main(String[] args) throws Exception {
        Chqclr p = new Chqclr();
        p.p0000Main();
    }

    private void p0000Main() throws Exception {
        String inPath = System.getenv("DD_CHQIN");
        String outPath = System.getenv("DD_CLROUT");
        byte[] inBytes = new byte[0];
        if (inPath != null) {
            try {
                inBytes = Files.readAllBytes(Paths.get(inPath));
            } catch (Exception e) {
                inBytes = new byte[0];
            }
        }
        this.cqBytes = inBytes;
        this.cqPos = 0;
        this.clOut = new ByteArrayOutputStream();
        this.wsEof = false;
        while (!wsEof) {
            if (cqPos + 40 <= cqBytes.length) {
                System.arraycopy(cqBytes, cqPos, cqRec, 0, 40);
                cqPos += 40;
                p1000Item();
            } else if (cqPos < cqBytes.length) {
                int rem = cqBytes.length - cqPos;
                Arrays.fill(cqRec, (byte) ' ');
                System.arraycopy(cqBytes, cqPos, cqRec, 0, rem);
                cqPos = cqBytes.length;
                p1000Item();
            } else {
                wsEof = true;
            }
        }
        if (outPath != null) {
            Files.write(Paths.get(outPath), clOut.toByteArray());
        }
        String ed = formatTotalEd(wsTotal);
        System.out.println("CHQCLR NET=" + ed);
    }

    private void p1000Item() throws Exception {
        Arrays.fill(clRec, (byte) ' ');
        formatUnsigned(BigDecimal.ZERO, clRec, 28, 5, 2);
        byte type = cqRec[0];
        if (type == (byte) 'C') {
            System.arraycopy(cqRec, 1, clRec, 0, 10);
            System.arraycopy(cqRec, 11, clRec, 10, 8);
            BigDecimal amt = parseSignedSeparate(cqRec, 19, 10, 2);
            BigDecimal debit = BigDecimal.ZERO.subtract(amt);
            debit = truncToSigned(debit, 9, 2);
            formatSignedSeparate(debit, clRec, 18, 10, 2);
            clRec[33] = (byte) 'C';
            clRec[34] = (byte) 'L';
            BigDecimal debitVal = parseSignedSeparate(clRec, 18, 10, 2);
            BigDecimal feeVal = parseUnsigned(clRec, 28, 5, 2);
            wsTotal = truncWs(wsTotal.add(debitVal).subtract(feeVal));
        } else if (type == (byte) 'R') {
            System.arraycopy(cqRec, 1, clRec, 0, 10);
            System.arraycopy(cqRec, 11, clRec, 10, 8);
            formatSignedSeparate(BigDecimal.ZERO, clRec, 18, 10, 2);
            BigDecimal rtFee = parseUnsigned(cqRec, 21, 5, 2);
            boolean isNsf = (cqRec[19] == (byte) 'N' && cqRec[20] == (byte) 'S');
            BigDecimal clFee;
            if (isNsf) {
                clFee = rtFee.multiply(BigDecimal.valueOf(2));
            } else {
                clFee = rtFee;
            }
            formatUnsigned(clFee, clRec, 28, 5, 2);
            clRec[33] = (byte) 'R';
            clRec[34] = (byte) 'T';
            BigDecimal debitVal = parseSignedSeparate(clRec, 18, 10, 2);
            BigDecimal feeVal = parseUnsigned(clRec, 28, 5, 2);
            wsTotal = truncWs(wsTotal.add(debitVal).subtract(feeVal));
        } else {
            Arrays.fill(clRec, 0, 10, (byte) ' ');
            for (int i = 10; i < 18; i++) clRec[i] = (byte) '0';
            formatSignedSeparate(BigDecimal.ZERO, clRec, 18, 10, 2);
            clRec[33] = (byte) 'R';
            clRec[34] = (byte) 'J';
            BigDecimal debitVal = parseSignedSeparate(clRec, 18, 10, 2);
            BigDecimal feeVal = parseUnsigned(clRec, 28, 5, 2);
            wsTotal = truncWs(wsTotal.add(debitVal).subtract(feeVal));
        }
        clOut.write(clRec, 0, 35);
    }

    private static BigDecimal parseSignedSeparate(byte[] buf, int off, int len, int decimals) {
        boolean neg = (buf[off] == (byte) '-');
        java.math.BigInteger unscaled = java.math.BigInteger.ZERO;
        java.math.BigInteger ten = java.math.BigInteger.TEN;
        for (int i = 1; i < len; i++) {
            int d = buf[off + i] & 0x0F;
            unscaled = unscaled.multiply(ten).add(java.math.BigInteger.valueOf(d));
        }
        BigDecimal v = new BigDecimal(unscaled).movePointLeft(decimals);
        return neg ? v.negate() : v;
    }

    private static BigDecimal parseUnsigned(byte[] buf, int off, int lenDigits, int decimals) {
        java.math.BigInteger unscaled = java.math.BigInteger.ZERO;
        java.math.BigInteger ten = java.math.BigInteger.TEN;
        for (int i = 0; i < lenDigits; i++) {
            int d = buf[off + i] & 0x0F;
            unscaled = unscaled.multiply(ten).add(java.math.BigInteger.valueOf(d));
        }
        return new BigDecimal(unscaled).movePointLeft(decimals);
    }

    private static void formatSignedSeparate(BigDecimal v, byte[] buf, int off, int len, int decimals) {
        BigInteger scaled = v.movePointRight(decimals).setScale(0, RoundingMode.DOWN).toBigInteger();
        boolean neg = scaled.signum() < 0;
        BigInteger abs = scaled.abs();
        BigInteger base = BigInteger.TEN.pow(len - 1);
        BigInteger low = abs.mod(base);
        String d = low.toString();
        while (d.length() < len - 1) d = "0" + d;
        buf[off] = (byte) (neg ? '-' : '+');
        for (int i = 0; i < len - 1; i++) buf[off + 1 + i] = (byte) d.charAt(i);
    }

    private static void formatUnsigned(BigDecimal v, byte[] buf, int off, int lenDigits, int decimals) {
        BigInteger scaled = v.movePointRight(decimals).setScale(0, RoundingMode.DOWN).toBigInteger().abs();
        BigInteger base = BigInteger.TEN.pow(lenDigits);
        BigInteger low = scaled.mod(base);
        String d = low.toString();
        while (d.length() < lenDigits) d = "0" + d;
        for (int i = 0; i < lenDigits; i++) buf[off + i] = (byte) d.charAt(i);
    }

    private static BigDecimal truncToSigned(BigDecimal v, int totalDigits, int decimals) {
        BigInteger scaled = v.movePointRight(decimals).setScale(0, RoundingMode.DOWN).toBigInteger();
        if (scaled.equals(BigInteger.ZERO)) return BigDecimal.ZERO;
        boolean neg = scaled.signum() < 0;
        BigInteger base = BigInteger.TEN.pow(totalDigits);
        BigInteger low = scaled.abs().mod(base);
        if (low.equals(BigInteger.ZERO)) return BigDecimal.ZERO;
        BigInteger ns = neg ? low.negate() : low;
        return new BigDecimal(ns).movePointLeft(decimals);
    }

    private static BigDecimal truncWs(BigDecimal v) {
        BigInteger scaled = v.movePointRight(2).setScale(0, RoundingMode.DOWN).toBigInteger();
        if (scaled.equals(BigInteger.ZERO)) return BigDecimal.ZERO;
        boolean neg = scaled.signum() < 0;
        BigInteger base = BigInteger.TEN.pow(11);
        BigInteger low = scaled.abs().mod(base);
        if (low.equals(BigInteger.ZERO)) return BigDecimal.ZERO;
        BigInteger ns = neg ? low.negate() : low;
        return new BigDecimal(ns).movePointLeft(2);
    }

    private static String formatTotalEd(BigDecimal v) {
        boolean neg = v.signum() < 0;
        BigDecimal abs = v.abs();
        BigInteger scaled = abs.movePointRight(2).setScale(0, RoundingMode.DOWN).toBigInteger();
        BigInteger[] dr = scaled.divideAndRemainder(BigInteger.valueOf(100));
        BigInteger intPart = dr[0];
        int frac = dr[1].intValue();
        String s = intPart.toString();
        while (s.length() < 10) s = "0" + s;
        if (s.length() > 10) s = s.substring(s.length() - 10);
        char[] f = s.toCharArray();
        int first = 9;
        for (int i = 0; i < 10; i++) {
            if (f[i] != '0') { first = i; break; }
            if (i == 9) first = 9;
        }
        for (int i = 0; i < first; i++) f[i] = ' ';
        if (neg) {
            if (first > 0) f[first - 1] = '-';
            else f[0] = '-';
        }
        String fracStr = frac < 10 ? "0" + frac : Integer.toString(frac);
        return new String(f) + "." + fracStr;
    }
}
