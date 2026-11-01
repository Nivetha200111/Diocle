import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class PkdPost {
    private byte[] inData = new byte[0];
    private int inPos = 0;
    private OutputStream poOut;
    private boolean endOfAccounts = false;
    private byte[] curAcct = new byte[10];
    private BigDecimal pkBal = BigDecimal.ZERO;
    private BigDecimal pkRate = BigDecimal.ZERO;
    private int pkDays = 0;
    private BigDecimal pkAdj = BigDecimal.ZERO;
    private int pkLimitDigits = 0;
    private int pkItems = 0;
    private BigDecimal wsInt = BigDecimal.ZERO;
    private BigDecimal wsNewBal = BigDecimal.ZERO;
    private int wsReadCnt = 0;

    public static void main(String[] args) throws Exception {
        new PkdPost().run();
    }

    private void run() throws Exception {
        p0000Main();
    }

    private void p0000Main() throws Exception {
        String pkPath = System.getenv("DD_PKIN");
        String poPath = System.getenv("DD_PKOUT");
        if (pkPath != null) {
            inData = Files.readAllBytes(Path.of(pkPath));
        }
        inPos = 0;
        if (poPath != null) {
            poOut = Files.newOutputStream(Path.of(poPath), StandardOpenOption.CREATE, StandardOpenOption.WRITE, StandardOpenOption.TRUNCATE_EXISTING);
        } else {
            poOut = OutputStream.nullOutputStream();
        }
        wsReadCnt = 0;
        wsInt = BigDecimal.ZERO;
        wsNewBal = BigDecimal.ZERO;
        endOfAccounts = false;
        p8000Read();
        while (!endOfAccounts) {
            p2000Post();
        }
        poOut.close();
        System.out.println("PKDPOST READ=" + String.format("%07d", wsReadCnt));
    }

    private void p2000Post() throws Exception {
        wsReadCnt = (wsReadCnt + 1) % 10000000;
        BigDecimal daysDec = BigDecimal.valueOf((long) pkDays);
        BigDecimal exact = pkBal.multiply(pkRate).multiply(daysDec).divide(BigDecimal.valueOf(365L), 30, RoundingMode.HALF_UP);
        BigDecimal rounded = exact.setScale(2, RoundingMode.HALF_UP);
        wsInt = truncPic(rounded, 7, 2);
        BigDecimal newBalExact = pkBal.add(wsInt).add(pkAdj);
        wsNewBal = truncPic(newBalExact, 9, 2);
        BigDecimal limitDec = BigDecimal.valueOf((long) pkLimitDigits * 100L);
        BigDecimal headExact = limitDec.subtract(wsNewBal);
        BigDecimal poHeadroom = truncPic(headExact, 7, 2);
        BigDecimal itemExact = BigDecimal.valueOf((long) pkItems).multiply(BigDecimal.valueOf(1000L));
        BigDecimal poItemUnits = truncPic(itemExact, 9, 0);
        BigDecimal poReversal = truncPic(pkAdj.negate(), 5, 2);
        byte[] o = new byte[42];
        System.arraycopy(curAcct, 0, o, 0, 10);
        encodeComp3(o, 10, 5, wsInt, 9, 2);
        encodeComp3(o, 15, 6, wsNewBal, 11, 2);
        encodeTrailingSeparate(o, 21, poHeadroom, 9, 2);
        encodeCompBe4(o, 31, poItemUnits.intValueExact());
        encodeOverpunch(o, 35, poReversal, 7, 2);
        poOut.write(o);
        p8000Read();
    }

    private void p8000Read() {
        if (inPos + 33 <= inData.length) {
            byte[] rec = Arrays.copyOfRange(inData, inPos, inPos + 33);
            inPos += 33;
            System.arraycopy(rec, 0, curAcct, 0, 10);
            pkBal = decodeComp3(rec, 10, 6, 2);
            pkRate = decodeComp3(rec, 16, 3, 4);
            pkDays = decodeCompBe2(rec, 19);
            pkAdj = decodeOverpunch(rec, 21, 7, 2);
            pkLimitDigits = decodeLimit(rec, 28);
            pkItems = decodeComp5Le2(rec, 31);
            endOfAccounts = false;
        } else {
            endOfAccounts = true;
        }
    }

    private static BigDecimal decodeComp3(byte[] rec, int off, int len, int scale) {
        BigInteger d = BigInteger.ZERO;
        for (int i = 0; i < len; i++) {
            int u = rec[off + i] & 0xFF;
            int hi = (u >>> 4) & 0x0F;
            int lo = u & 0x0F;
            if (i == len - 1) {
                d = d.multiply(BigInteger.TEN).add(BigInteger.valueOf(hi));
            } else {
                d = d.multiply(BigInteger.TEN).add(BigInteger.valueOf(hi));
                d = d.multiply(BigInteger.TEN).add(BigInteger.valueOf(lo));
            }
        }
        int signNib = rec[off + len - 1] & 0x0F;
        boolean neg = (signNib == 0x0D);
        BigDecimal r = new BigDecimal(d, scale);
        if (neg) {
            r = r.negate();
        }
        return r;
    }

    private static int decodeCompBe2(byte[] rec, int off) {
        int v = ((rec[off] & 0xFF) << 8) | (rec[off + 1] & 0xFF);
        if (v >= 0x8000) {
            v -= 0x10000;
        }
        return v;
    }

    private static int decodeComp5Le2(byte[] rec, int off) {
        int v = (rec[off] & 0xFF) | ((rec[off + 1] & 0xFF) << 8);
        if (v >= 0x8000) {
            v -= 0x10000;
        }
        return v;
    }

    private static BigDecimal decodeOverpunch(byte[] rec, int off, int len, int scale) {
        BigInteger v = BigInteger.ZERO;
        for (int i = 0; i < len - 1; i++) {
            int b = rec[off + i] & 0xFF;
            int dg = b - '0';
            if (dg < 0 || dg > 9) {
                dg = 0;
            }
            v = v.multiply(BigInteger.TEN).add(BigInteger.valueOf(dg));
        }
        int b = rec[off + len - 1] & 0xFF;
        char c = (char) b;
        int lastDigit = 0;
        int sign = 1;
        if (c >= '0' && c <= '9') {
            lastDigit = c - '0';
            sign = 1;
        } else if (c >= 'p' && c <= 'y') {
            lastDigit = c - 'p';
            sign = -1;
        } else if (c >= 'P' && c <= 'Y') {
            lastDigit = c - 'P';
            sign = -1;
        } else if (c == '{') {
            lastDigit = 0;
            sign = 1;
        } else if (c >= 'A' && c <= 'I') {
            lastDigit = c - 'A' + 1;
            sign = 1;
        } else if (c == '}') {
            lastDigit = 0;
            sign = -1;
        } else if (c >= 'J' && c <= 'R') {
            lastDigit = c - 'J' + 1;
            sign = -1;
        } else {
            lastDigit = 0;
            sign = 1;
        }
        v = v.multiply(BigInteger.TEN).add(BigInteger.valueOf(lastDigit));
        if (sign < 0) {
            v = v.negate();
        }
        return new BigDecimal(v, scale);
    }

    private static int decodeLimit(byte[] rec, int off) {
        int v = 0;
        for (int i = 0; i < 3; i++) {
            int b = rec[off + i] & 0xFF;
            int dg = b - '0';
            if (dg < 0 || dg > 9) {
                dg = 0;
            }
            v = v * 10 + dg;
        }
        return v;
    }

    private static BigDecimal truncPic(BigDecimal v, int intDigits, int fracDigits) {
        BigDecimal s = v.setScale(fracDigits, RoundingMode.DOWN);
        BigInteger un = s.movePointRight(fracDigits).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intDigits + fracDigits);
        BigInteger t = un.remainder(mod);
        return new BigDecimal(t, fracDigits);
    }

    private static void encodeComp3(byte[] out, int off, int len, BigDecimal v, int totalDigits, int scale) {
        BigInteger un = v.setScale(scale, RoundingMode.DOWN).movePointRight(scale).toBigIntegerExact();
        boolean neg = un.signum() < 0;
        BigInteger abs = un.abs().remainder(BigInteger.TEN.pow(totalDigits));
        String s = abs.toString();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < totalDigits - s.length(); i++) {
            sb.append('0');
        }
        sb.append(s);
        String digits = sb.toString();
        for (int i = 0; i < len; i++) {
            int hi = digits.charAt(2 * i) - '0';
            int lo;
            if (i == len - 1) {
                lo = neg ? 0x0D : 0x0C;
            } else {
                lo = digits.charAt(2 * i + 1) - '0';
            }
            out[off + i] = (byte) ((hi << 4) | lo);
        }
    }

    private static void encodeCompBe4(byte[] out, int off, int v) {
        out[off] = (byte) (v >>> 24);
        out[off + 1] = (byte) (v >>> 16);
        out[off + 2] = (byte) (v >>> 8);
        out[off + 3] = (byte) v;
    }

    private static void encodeOverpunch(byte[] out, int off, BigDecimal v, int totalDigits, int scale) {
        BigInteger un = v.setScale(scale, RoundingMode.DOWN).movePointRight(scale).toBigIntegerExact();
        boolean neg = un.signum() < 0;
        BigInteger abs = un.abs().remainder(BigInteger.TEN.pow(totalDigits));
        String s = abs.toString();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < totalDigits - s.length(); i++) {
            sb.append('0');
        }
        sb.append(s);
        String digits = sb.toString();
        for (int i = 0; i < totalDigits - 1; i++) {
            out[off + i] = (byte) digits.charAt(i);
        }
        int lastDigit = digits.charAt(totalDigits - 1) - '0';
        if (neg) {
            out[off + totalDigits - 1] = (byte) ('p' + lastDigit);
        } else {
            out[off + totalDigits - 1] = (byte) ('0' + lastDigit);
        }
    }

    private static void encodeTrailingSeparate(byte[] out, int off, BigDecimal v, int totalDigits, int scale) {
        BigInteger un = v.setScale(scale, RoundingMode.DOWN).movePointRight(scale).toBigIntegerExact();
        boolean neg = un.signum() < 0;
        BigInteger abs = un.abs().remainder(BigInteger.TEN.pow(totalDigits));
        String s = abs.toString();
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < totalDigits - s.length(); i++) {
            sb.append('0');
        }
        sb.append(s);
        String digits = sb.toString();
        for (int i = 0; i < totalDigits; i++) {
            out[off + i] = (byte) digits.charAt(i);
        }
        out[off + totalDigits] = (byte) (neg ? '-' : '+');
    }
}
