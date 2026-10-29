import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Hand-written Java port of LDGRWRT (a test fixture, not model output): the account master is read from
 * DD_ACCTMST, updated record by record, and written back to the same path, like OPEN I-O plus REWRITE.
 */
public class LdgrWrt {
    static final int RECORD = 26;
    static final BigInteger NINE_DIGITS = BigInteger.TEN.pow(9);

    public static void main(String[] args) throws Exception {
        Path path = Path.of(System.getenv("DD_ACCTMST"));
        byte[] data = Files.readAllBytes(path);
        int read = 0, updated = 0, overdrawn = 0;
        for (int at = 0; at + RECORD <= data.length; at += RECORD) {
            read++;
            if (data[at + 8] == 'C') {
                continue;
            }
            BigDecimal balance = zoned(data, at + 9, 9, 2);
            BigDecimal rate = new BigDecimal(new String(data, at + 18, 5, StandardCharsets.ISO_8859_1)).movePointLeft(4);
            int feeCount = Integer.parseInt(new String(data, at + 23, 3, StandardCharsets.ISO_8859_1));

            BigDecimal interest = balance.multiply(rate).divide(BigDecimal.valueOf(12), 2, RoundingMode.HALF_UP);
            balance = fit(balance.add(interest));
            if (balance.signum() >= 0 && balance.compareTo(new BigDecimal("100.00")) < 0) {
                balance = fit(balance.subtract(new BigDecimal("2.50")));
                feeCount = (feeCount + 1) % 1000;
            }
            if (balance.signum() < 0) {
                data[at + 8] = 'O';
                overdrawn++;
            }
            put(data, at + 9, zonedBytes(balance, 9, 2));
            put(data, at + 23, String.format("%03d", feeCount).getBytes(StandardCharsets.ISO_8859_1));
            updated++;
        }
        Files.write(path, data);
        System.out.printf("LDGRWRT READ %07d UPDATED %07d OVERDRAWN %07d%n", read, updated, overdrawn);
        if (overdrawn > 0) {
            System.exit(4);
        }
    }

    /** PIC S9(7)V99 keeps nine digits: high-order digits are dropped silently (no ON SIZE ERROR). */
    static BigDecimal fit(BigDecimal v) {
        BigInteger units = v.movePointRight(2).toBigIntegerExact().abs().mod(NINE_DIGITS);
        BigDecimal r = new BigDecimal(units).movePointLeft(2);
        return v.signum() < 0 ? r.negate() : r;
    }

    /** Signed DISPLAY, sign in the last digit: negative digit d is the character d + 0x40 ('p'..'y'). */
    static BigDecimal zoned(byte[] b, int off, int len, int scale) {
        int last = b[off + len - 1] & 0xff;
        boolean negative = last >= 'p' && last <= 'y';
        StringBuilder digits = new StringBuilder();
        for (int i = 0; i < len - 1; i++) {
            digits.append((char) b[off + i]);
        }
        digits.append((char) (negative ? last - 0x40 : last));
        BigDecimal v = new BigDecimal(new BigInteger(digits.toString()), scale);
        return negative ? v.negate() : v;
    }

    static byte[] zonedBytes(BigDecimal v, int len, int scale) {
        String digits = String.format("%0" + len + "d", v.abs().movePointRight(scale).toBigIntegerExact());
        byte[] out = digits.getBytes(StandardCharsets.ISO_8859_1);
        if (v.signum() < 0) {
            out[len - 1] = (byte) (out[len - 1] + 0x40);
        }
        return out;
    }

    static void put(byte[] data, int at, byte[] value) {
        System.arraycopy(value, 0, data, at, value.length);
    }
}
