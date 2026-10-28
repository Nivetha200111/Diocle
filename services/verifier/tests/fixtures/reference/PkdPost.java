// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// Faithful Java port of samples/packed-posting/src/PKDPOST.cbl, used to prove the verifier handles
// fixed-length records with COMP-3, COMP, COMP-5, overpunch and P-scaled fields byte for byte.
import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;

public class PkdPost {
    static final int IN_LEN = 33;

    public static void main(String[] args) throws Exception {
        byte[] in = Files.readAllBytes(Path.of(System.getenv("DD_PKIN")));
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int read = 0;
        for (int off = 0; off + IN_LEN <= in.length; off += IN_LEN) {
            read++;
            BigDecimal bal = unpack(in, off + 10, 6, 2);
            BigDecimal rate = unpack(in, off + 16, 3, 4);
            BigDecimal days = new BigDecimal(binary(in, off + 19, 2, false));
            BigDecimal adj = overpunch(in, off + 21, 7, 2);
            BigDecimal limit = new BigDecimal(new String(in, off + 28, 3, "ISO-8859-1")).multiply(BigDecimal.valueOf(100));
            long items = binary(in, off + 31, 2, true);

            BigDecimal interest = truncateHigh(bal.multiply(rate).multiply(days)
                    .divide(BigDecimal.valueOf(365), 2, RoundingMode.HALF_UP), 7);
            BigDecimal newBal = truncateHigh(bal.add(interest).add(adj), 9);
            BigDecimal headroom = truncateHigh(limit.subtract(newBal), 7);
            long units = items * 1000;
            BigDecimal reversal = truncateHigh(adj.negate(), 5);

            out.write(in, off, 10);
            out.write(pack(interest, 5));
            out.write(pack(newBal, 6));
            out.write(trailingSeparate(headroom, 9));
            out.write(toBigEndian(units, 4));
            out.write(overpunchOut(reversal, 7));
        }
        Files.write(Path.of(System.getenv("DD_PKOUT")), out.toByteArray());
        System.out.println("PKDPOST READ=" + String.format("%010d", read));
    }

    static BigDecimal truncateHigh(BigDecimal v, int integerDigits) {
        BigDecimal limit = BigDecimal.TEN.pow(integerDigits);
        BigDecimal r = v.abs().remainder(limit);
        return v.signum() < 0 ? r.negate() : r;
    }

    static BigDecimal unpack(byte[] b, int off, int len, int scale) {
        StringBuilder digits = new StringBuilder();
        for (int i = 0; i < len; i++) {
            int x = b[off + i] & 0xFF;
            digits.append(x >> 4);
            if (i < len - 1) digits.append(x & 0x0F);
        }
        int sign = b[off + len - 1] & 0x0F;
        BigDecimal v = new BigDecimal(new BigInteger(digits.toString()), scale);
        return (sign == 0x0D || sign == 0x0B) ? v.negate() : v;
    }

    static byte[] pack(BigDecimal v, int len) {
        String digits = v.abs().movePointRight(2).toBigInteger().toString();
        int width = len * 2 - 1;
        digits = "0".repeat(width - digits.length()) + digits;
        byte[] out = new byte[len];
        int sign = v.signum() < 0 ? 0x0D : 0x0C;
        for (int i = 0; i < len; i++) {
            int hi = digits.charAt(2 * i) - '0';
            int lo = (2 * i + 1 < width) ? digits.charAt(2 * i + 1) - '0' : sign;
            out[i] = (byte) ((hi << 4) | lo);
        }
        return out;
    }

    static long binary(byte[] b, int off, int len, boolean littleEndian) {
        long v = 0;
        for (int i = 0; i < len; i++) {
            int idx = littleEndian ? off + len - 1 - i : off + i;
            v = (v << 8) | (b[idx] & 0xFF);
        }
        long signBit = 1L << (len * 8 - 1);
        return (v & signBit) != 0 ? v - (signBit << 1) : v;
    }

    static byte[] toBigEndian(long v, int len) {
        byte[] out = new byte[len];
        for (int i = len - 1; i >= 0; i--) {
            out[i] = (byte) (v & 0xFF);
            v >>= 8;
        }
        return out;
    }

    static BigDecimal overpunch(byte[] b, int off, int len, int scale) {
        char[] c = new String(b, off, len, java.nio.charset.StandardCharsets.ISO_8859_1).toCharArray();
        boolean negative = false;
        char last = c[len - 1];
        if (last >= 'p' && last <= 'y') {
            negative = true;
            c[len - 1] = (char) (last - 0x40);
        }
        BigDecimal v = new BigDecimal(new BigInteger(new String(c)), scale);
        return negative ? v.negate() : v;
    }

    static byte[] overpunchOut(BigDecimal v, int digits) {
        String s = v.abs().movePointRight(2).toBigInteger().toString();
        s = "0".repeat(digits - s.length()) + s;
        char last = s.charAt(digits - 1);
        if (v.signum() < 0) last = (char) (last + 0x40);
        return (s.substring(0, digits - 1) + last).getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
    }

    static byte[] trailingSeparate(BigDecimal v, int digits) {
        String s = v.abs().movePointRight(2).toBigInteger().toString();
        s = "0".repeat(digits - s.length()) + s + (v.signum() < 0 ? "-" : "+");
        return s.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
    }
}
