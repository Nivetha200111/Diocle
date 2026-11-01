import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;

public class Chqclr {
    private BigDecimal wsTotal = new BigDecimal(BigInteger.ZERO, 2);
    private byte[] curCq;
    private byte[] curCl;
    private ByteArrayOutputStream outBuf = new ByteArrayOutputStream();

    public static void main(String[] args) throws Exception {
        Chqclr p = new Chqclr();
        p.m0000Main();
    }

    private void m0000Main() throws Exception {
        String inStr = System.getenv("DD_CHQIN");
        String outStr = System.getenv("DD_CLROUT");
        byte[] all = new byte[0];
        if (inStr != null) {
            Path inPath = Paths.get(inStr);
            try {
                all = Files.readAllBytes(inPath);
            } catch (java.io.IOException e) {
                all = new byte[0];
            }
        }
        int pos = 0;
        while (pos < all.length) {
            int rem = all.length - pos;
            byte[] rec = new byte[40];
            if (rem >= 40) {
                System.arraycopy(all, pos, rec, 0, 40);
                pos += 40;
            } else {
                System.arraycopy(all, pos, rec, 0, rem);
                Arrays.fill(rec, rem, 40, (byte) ' ');
                pos = all.length;
            }
            curCq = rec;
            m1000Item();
        }
        if (outStr != null) {
            Path outPath = Paths.get(outStr);
            Path parent = outPath.getParent();
            if (parent != null) {
                try {
                    Files.createDirectories(parent);
                } catch (java.io.IOException ignored) {
                }
            }
            Files.write(outPath, outBuf.toByteArray());
        }
        String edited = formatTotalEdited(wsTotal);
        String line = "CHQCLR NET=" + edited + "\n";
        System.out.write(line.getBytes(StandardCharsets.ISO_8859_1));
    }

    private void m1000Item() {
        curCl = new byte[35];
        Arrays.fill(curCl, (byte) ' ');
        Arrays.fill(curCl, 28, 33, (byte) '0');
        int type = curCq[0] & 0xFF;
        if (type == 'C') {
            System.arraycopy(curCq, 1, curCl, 0, 10);
            System.arraycopy(curCq, 11, curCl, 10, 8);
            BigDecimal amt = parseSignedSeparate(curCq, 19, 7, 2);
            BigDecimal debit = BigDecimal.ZERO.setScale(2).subtract(amt);
            formatSignedSeparate(debit, curCl, 18, 7, 2);
            curCl[33] = (byte) 'C';
            curCl[34] = (byte) 'L';
        } else if (type == 'R') {
            System.arraycopy(curCq, 1, curCl, 0, 10);
            System.arraycopy(curCq, 11, curCl, 10, 8);
            formatSignedSeparate(BigDecimal.ZERO.setScale(2), curCl, 18, 7, 2);
            boolean nsf = ((curCq[19] & 0xFF) == 'N') && ((curCq[20] & 0xFF) == 'S');
            if (nsf) {
                BigDecimal fee = parseUnsigned(curCq, 21, 5, 2);
                BigDecimal doubled = fee.multiply(BigDecimal.valueOf(2));
                formatUnsigned(doubled, curCl, 28, 3, 2);
            } else {
                System.arraycopy(curCq, 21, curCl, 28, 5);
            }
            curCl[33] = (byte) 'R';
            curCl[34] = (byte) 'T';
        } else {
            Arrays.fill(curCl, 0, 10, (byte) ' ');
            Arrays.fill(curCl, 10, 18, (byte) '0');
            formatSignedSeparate(BigDecimal.ZERO.setScale(2), curCl, 18, 7, 2);
            curCl[33] = (byte) 'R';
            curCl[34] = (byte) 'J';
        }
        BigDecimal debitVal = parseSignedSeparate(curCl, 18, 7, 2);
        BigDecimal feeVal = parseUnsigned(curCl, 28, 5, 2);
        wsTotal = truncateWs(wsTotal.add(debitVal));
        wsTotal = truncateWs(wsTotal.subtract(feeVal));
        outBuf.write(curCl, 0, 35);
    }

    private static BigDecimal parseSignedSeparate(byte[] buf, int off, int intDigits, int decDigits) {
        int total = intDigits + decDigits;
        char s = (char) (buf[off] & 0xFF);
        boolean neg = (s == '-');
        StringBuilder sb = new StringBuilder(total);
        for (int i = 1; i <= total; i++) {
            char c = (char) (buf[off + i] & 0xFF);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            } else {
                sb.append('0');
            }
        }
        BigInteger bi = new BigInteger(sb.toString());
        BigDecimal v = new BigDecimal(bi, decDigits);
        if (neg) {
            v = v.negate();
        }
        return v.setScale(decDigits);
    }

    private static void formatSignedSeparate(BigDecimal val, byte[] buf, int off, int intDigits, int decDigits) {
        int total = intDigits + decDigits;
        BigInteger mod = BigInteger.TEN.pow(total);
        BigDecimal v = val.setScale(decDigits, RoundingMode.DOWN);
        BigInteger scaled = v.unscaledValue();
        boolean neg = scaled.signum() < 0;
        BigInteger abs = scaled.abs().mod(mod);
        if (abs.equals(BigInteger.ZERO)) {
            neg = false;
        }
        String s = abs.toString();
        int pad = total - s.length();
        buf[off] = (byte) (neg ? '-' : '+');
        for (int i = 0; i < pad; i++) {
            buf[off + 1 + i] = (byte) '0';
        }
        for (int i = 0; i < s.length(); i++) {
            buf[off + 1 + pad + i] = (byte) s.charAt(i);
        }
    }

    private static BigDecimal parseUnsigned(byte[] buf, int off, int len, int decDigits) {
        StringBuilder sb = new StringBuilder(len);
        for (int i = 0; i < len; i++) {
            char c = (char) (buf[off + i] & 0xFF);
            if (c >= '0' && c <= '9') {
                sb.append(c);
            } else {
                sb.append('0');
            }
        }
        BigInteger bi = new BigInteger(sb.toString());
        return new BigDecimal(bi, decDigits).setScale(decDigits);
    }

    private static void formatUnsigned(BigDecimal val, byte[] buf, int off, int intDigits, int decDigits) {
        int total = intDigits + decDigits;
        BigInteger mod = BigInteger.TEN.pow(total);
        BigDecimal v = val.setScale(decDigits, RoundingMode.DOWN);
        BigInteger scaled = v.unscaledValue();
        BigInteger abs = scaled.abs().mod(mod);
        String s = abs.toString();
        int pad = total - s.length();
        for (int i = 0; i < pad; i++) {
            buf[off + i] = (byte) '0';
        }
        for (int i = 0; i < s.length(); i++) {
            buf[off + pad + i] = (byte) s.charAt(i);
        }
    }

    private static BigDecimal truncateWs(BigDecimal v) {
        BigDecimal vv = v.setScale(2, RoundingMode.DOWN);
        BigInteger scaled = vv.unscaledValue();
        BigInteger mod = BigInteger.TEN.pow(11);
        boolean neg = scaled.signum() < 0;
        BigInteger abs = scaled.abs().mod(mod);
        BigInteger res = neg ? abs.negate() : abs;
        if (abs.equals(BigInteger.ZERO)) {
            res = BigInteger.ZERO;
        }
        return new BigDecimal(res, 2);
    }

    private static String formatTotalEdited(BigDecimal total) {
        boolean neg = total.signum() < 0;
        BigDecimal abs = total.abs().setScale(2, RoundingMode.DOWN);
        BigInteger scaled = abs.unscaledValue();
        BigInteger intPart = scaled.divide(BigInteger.valueOf(100));
        int frac = scaled.mod(BigInteger.valueOf(100)).intValue();
        String intStr = intPart.toString();
        String padded;
        if (intStr.length() >= 10) {
            padded = intStr.substring(intStr.length() - 10);
        } else {
            StringBuilder sb = new StringBuilder(10);
            for (int i = 0; i < 10 - intStr.length(); i++) {
                sb.append('0');
            }
            sb.append(intStr);
            padded = sb.toString();
        }
        char[] out = new char[10];
        if (padded.equals("0000000000")) {
            Arrays.fill(out, ' ');
            out[9] = '0';
        } else {
            int msb = -1;
            for (int i = 0; i < 10; i++) {
                if (padded.charAt(i) != '0') {
                    msb = i;
                    break;
                }
            }
            Arrays.fill(out, ' ');
            for (int i = msb; i < 10; i++) {
                out[i] = padded.charAt(i);
            }
            if (neg && msb > 0) {
                out[msb - 1] = '-';
            }
        }
        String fracStr = (frac < 10 ? "0" : "") + frac;
        return new String(out) + "." + fracStr;
    }
}
