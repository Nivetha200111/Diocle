import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class Chqclr {
    private static final int CQ_LEN = 40;
    private static final int CL_LEN = 35;
    private static final BigDecimal MOD_TOTAL = new BigDecimal("100000000000");
    private static final BigDecimal MOD_FEE = new BigDecimal("100000");
    private static final BigDecimal MOD_DEBIT = new BigDecimal("1000000000");

    private String wsEof = "N";
    private BigDecimal wsTotal = new BigDecimal("0.00");

    private final List<byte[]> inRecords = new ArrayList<>();
    private int inPos = 0;
    private byte[] cqRec = new byte[CQ_LEN];
    private java.io.OutputStream clOut;

    public static void main(String[] args) throws Exception {
        Chqclr p = new Chqclr();
        p.p0000Main();
    }

    private void p0000Main() throws Exception {
        String inStr = System.getenv("DD_CHQIN");
        String outStr = System.getenv("DD_CLROUT");
        if (inStr == null) {
            inStr = "CHQIN";
        }
        if (outStr == null) {
            outStr = "CLROUT";
        }
        Path inPath = Paths.get(inStr);
        Path outPath = Paths.get(outStr);
        byte[] all = Files.exists(inPath) ? Files.readAllBytes(inPath) : new byte[0];
        if (all.length % CQ_LEN == 0) {
            for (int i = 0; i < all.length; i += CQ_LEN) {
                byte[] r = new byte[CQ_LEN];
                System.arraycopy(all, i, r, 0, CQ_LEN);
                inRecords.add(r);
            }
        } else {
            String s = new String(all, StandardCharsets.ISO_8859_1);
            String[] parts = s.split("\n", -1);
            int n = parts.length;
            if (n > 0 && parts[n - 1].isEmpty() && s.endsWith("\n")) {
                n--;
            }
            for (int i = 0; i < n; i++) {
                String line = parts[i];
                if (line.endsWith("\r")) {
                    line = line.substring(0, line.length() - 1);
                }
                byte[] lb = line.getBytes(StandardCharsets.ISO_8859_1);
                byte[] r = new byte[CQ_LEN];
                Arrays.fill(r, (byte) 0x20);
                int cp = Math.min(lb.length, CQ_LEN);
                System.arraycopy(lb, 0, r, 0, cp);
                inRecords.add(r);
            }
        }
        if (outPath.getParent() != null) {
            Files.createDirectories(outPath.getParent());
        }
        clOut = Files.newOutputStream(outPath, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
        wsEof = "N";
        wsTotal = new BigDecimal("0.00");
        inPos = 0;
        while (!"Y".equals(wsEof)) {
            if (inPos >= inRecords.size()) {
                wsEof = "Y";
            } else {
                cqRec = inRecords.get(inPos++);
                p1000Item();
            }
        }
        clOut.close();
        String ed = formatTotalEd(wsTotal);
        String line = "CHQCLR NET=" + ed + "\n";
        System.out.write(line.getBytes(StandardCharsets.ISO_8859_1));
        System.out.flush();
    }

    private void p1000Item() throws Exception {
        byte[] newCl = new byte[CL_LEN];
        Arrays.fill(newCl, (byte) 0x20);
        setClFeeBytes(newCl, 28, new BigDecimal("0.00"));
        int cqType = cqRec[0] & 0xFF;
        BigDecimal clDebitVal;
        BigDecimal clFeeVal;
        if (cqType == (int) 'C') {
            System.arraycopy(cqRec, 1, newCl, 0, 10);
            System.arraycopy(cqRec, 11, newCl, 10, 8);
            BigDecimal cqAmt = parseSignedSeparate(cqRec, 19, 10);
            clDebitVal = BigDecimal.ZERO.subtract(cqAmt);
            clDebitVal = truncDebit(clDebitVal);
            setClDebitBytes(newCl, clDebitVal);
            clFeeVal = new BigDecimal("0.00");
            newCl[33] = (byte) 'C';
            newCl[34] = (byte) 'L';
        } else if (cqType == (int) 'R') {
            System.arraycopy(cqRec, 1, newCl, 0, 10);
            System.arraycopy(cqRec, 11, newCl, 10, 8);
            clDebitVal = new BigDecimal("0.00");
            setClDebitBytes(newCl, clDebitVal);
            BigDecimal rtFee = parseUnsigned(cqRec, 21, 5, 2);
            String reason = new String(cqRec, 19, 2, StandardCharsets.ISO_8859_1);
            BigDecimal fee;
            if ("NS".equals(reason)) {
                fee = rtFee.multiply(BigDecimal.valueOf(2));
                fee = truncFee(fee);
                clFeeVal = fee;
                setClFeeBytes(newCl, 28, clFeeVal);
            } else {
                // COBOL MOVE between identical DISPLAY numerics is a byte copy,
                // preserving non-digit bytes (e.g. letters) in CL-FEE.
                System.arraycopy(cqRec, 21, newCl, 28, 5);
                clFeeVal = parseUnsigned(newCl, 28, 5, 2);
            }
            newCl[33] = (byte) 'R';
            newCl[34] = (byte) 'T';
        } else {
            Arrays.fill(newCl, 0, 10, (byte) 0x20);
            Arrays.fill(newCl, 10, 18, (byte) '0');
            clDebitVal = new BigDecimal("0.00");
            setClDebitBytes(newCl, clDebitVal);
            clFeeVal = new BigDecimal("0.00");
            newCl[33] = (byte) 'R';
            newCl[34] = (byte) 'J';
        }
        BigDecimal storedDebit = parseStoredDebit(newCl);
        BigDecimal storedFee = parseStoredFee(newCl);
        wsTotal = truncTotal(wsTotal.add(storedDebit));
        wsTotal = truncTotal(wsTotal.subtract(storedFee));
        clOut.write(newCl);
    }

    private static BigDecimal parseSignedSeparate(byte[] rec, int off, int len) {
        int b0 = rec[off] & 0xFF;
        boolean neg = (b0 == (int) '-');
        long cents = 0L;
        // GnuCOBOL DISPLAY numerics use low nibble (byte & 0x0F) as digit value,
        // even when the byte is not '0'-'9' (e.g. letters, '.', '-').
        for (int i = off + 1; i < off + len; i++) {
            int nib = rec[i] & 0x0F;
            cents = cents * 10L + nib;
        }
        BigDecimal v = new BigDecimal(cents).movePointLeft(2);
        if (neg) {
            v = v.negate();
        }
        return v.setScale(2, RoundingMode.UNNECESSARY);
    }

    private static BigDecimal parseUnsigned(byte[] rec, int off, int len, int decimals) {
        long cents = 0L;
        // GnuCOBOL DISPLAY numerics use low nibble (byte & 0x0F) as digit value.
        for (int i = off; i < off + len; i++) {
            int nib = rec[i] & 0x0F;
            cents = cents * 10L + nib;
        }
        return new BigDecimal(cents).movePointLeft(decimals).setScale(decimals, RoundingMode.UNNECESSARY);
    }

    private static BigDecimal parseStoredDebit(byte[] cl) {
        return parseSignedSeparate(cl, 18, 10);
    }

    private static BigDecimal parseStoredFee(byte[] cl) {
        return parseUnsigned(cl, 28, 5, 2);
    }

    private static BigDecimal truncTotal(BigDecimal v) {
        BigDecimal scaled = v.movePointRight(2);
        BigDecimal r = scaled.remainder(MOD_TOTAL);
        return r.movePointLeft(2).setScale(2, RoundingMode.UNNECESSARY);
    }

    private static BigDecimal truncFee(BigDecimal v) {
        BigDecimal scaled = v.movePointRight(2);
        BigDecimal r = scaled.remainder(MOD_FEE);
        if (r.signum() < 0) {
            r = r.add(MOD_FEE);
        }
        return r.movePointLeft(2).setScale(2, RoundingMode.UNNECESSARY);
    }

    private static BigDecimal truncDebit(BigDecimal v) {
        BigDecimal scaled = v.movePointRight(2);
        BigDecimal r = scaled.remainder(MOD_DEBIT);
        return r.movePointLeft(2).setScale(2, RoundingMode.UNNECESSARY);
    }

    private static void setClDebitBytes(byte[] cl, int off, BigDecimal v) {
        setClDebitBytes(cl, v);
    }

    private static void setClDebitBytes(byte[] cl, BigDecimal v) {
        boolean neg = v.signum() < 0;
        BigDecimal a = v.abs();
        BigInteger cents = a.movePointRight(2).toBigIntegerExact();
        cents = cents.remainder(BigInteger.valueOf(1000000000L));
        String d = cents.toString();
        StringBuilder sb = new StringBuilder();
        for (int i = d.length(); i < 9; i++) {
            sb.append('0');
        }
        sb.append(d);
        cl[18] = (byte) (neg ? '-' : '+');
        byte[] db = sb.toString().getBytes(StandardCharsets.ISO_8859_1);
        System.arraycopy(db, 0, cl, 19, 9);
    }

    private static void setClFeeBytes(byte[] cl, int off, BigDecimal v) {
        boolean neg = v.signum() < 0;
        BigDecimal a = v.abs();
        BigInteger cents = a.movePointRight(2).toBigIntegerExact();
        cents = cents.remainder(BigInteger.valueOf(100000L));
        String d = cents.toString();
        StringBuilder sb = new StringBuilder();
        for (int i = d.length(); i < 5; i++) {
            sb.append('0');
        }
        sb.append(d);
        byte[] fb = sb.toString().getBytes(StandardCharsets.ISO_8859_1);
        System.arraycopy(fb, 0, cl, off, 5);
    }

    private static String formatTotalEd(BigDecimal total) {
        boolean neg = total.signum() < 0;
        BigDecimal a = total.abs();
        BigInteger cents = a.movePointRight(2).toBigIntegerExact();
        BigInteger[] dr = cents.divideAndRemainder(BigInteger.valueOf(100));
        String intStr = dr[0].toString();
        int frac = dr[1].intValue();
        String fracStr = frac < 10 ? "0" + frac : Integer.toString(frac);
        String intField;
        if (!neg) {
            int spaces = 10 - intStr.length();
            if (spaces < 0) {
                spaces = 0;
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < spaces; i++) {
                sb.append(' ');
            }
            sb.append(intStr);
            intField = sb.toString();
        } else {
            int spaces = 10 - intStr.length() - 1;
            if (spaces < 0) {
                spaces = 0;
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < spaces; i++) {
                sb.append(' ');
            }
            sb.append('-');
            sb.append(intStr);
            intField = sb.toString();
        }
        return intField + "." + fracStr;
    }
}
