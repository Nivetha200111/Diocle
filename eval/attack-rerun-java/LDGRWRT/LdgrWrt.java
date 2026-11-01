import java.math.BigDecimal;
import java.math.RoundingMode;
public class LdgrWrt {
    public static void main(String[] args) throws Exception {
        LdgrWrt p = new LdgrWrt();
        p.p0000Main();
    }
    private String wsMstStatus = "00";
    private boolean endOfMaster = false;
    private long wsInterestCents = 0L;
    private long wsReadCnt = 0L;
    private long wsUpdatedCnt = 0L;
    private long wsOverdrawnCnt = 0L;
    private byte[] curAcctId = new byte[8];
    private int curStatusByte = 32;
    private long curBalanceCents = 0L;
    private int curRateInt = 0;
    private int curFeeCnt = 0;
    private java.util.List<byte[]> recList = new java.util.ArrayList<>();
    private byte[] trailingBytes = new byte[0];
    private int nextIdx = 0;
    private int lastIdx = -1;
    private void p0000Main() throws Exception {
        String p = System.getenv("DD_ACCTMST");
        if (p == null || p.length() == 0) {
            wsMstStatus = "35";
            System.out.println("LDGRWRT OPEN ACCTMST FAILED " + wsMstStatus);
            System.exit(16);
            return;
        }
        byte[] all;
        try {
            all = java.nio.file.Files.readAllBytes(java.nio.file.Paths.get(p));
        } catch (Exception e) {
            wsMstStatus = "35";
            System.out.println("LDGRWRT OPEN ACCTMST FAILED " + wsMstStatus);
            System.exit(16);
            return;
        }
        wsMstStatus = "00";
        int n = all.length / 26;
        int rem = all.length % 26;
        recList.clear();
        for (int i = 0; i < n; i++) {
            byte[] r = new byte[26];
            System.arraycopy(all, i * 26, r, 0, 26);
            recList.add(r);
        }
        if (rem > 0) {
            trailingBytes = new byte[rem];
            System.arraycopy(all, n * 26, trailingBytes, 0, rem);
        } else {
            trailingBytes = new byte[0];
        }
        nextIdx = 0;
        lastIdx = -1;
        endOfMaster = false;
        p8000Read();
        while (!endOfMaster) {
            p2000Process();
        }
        int total = recList.size() * 26 + trailingBytes.length;
        byte[] out = new byte[total];
        for (int i = 0; i < recList.size(); i++) {
            System.arraycopy(recList.get(i), 0, out, i * 26, 26);
        }
        if (trailingBytes.length > 0) {
            System.arraycopy(trailingBytes, 0, out, recList.size() * 26, trailingBytes.length);
        }
        try {
            java.nio.file.Files.write(java.nio.file.Paths.get(p), out);
        } catch (Exception e) {
        }
        String line = "LDGRWRT READ " + fmt7(wsReadCnt) + " UPDATED " + fmt7(wsUpdatedCnt) + " OVERDRAWN " + fmt7(wsOverdrawnCnt);
        System.out.println(line);
        if (wsOverdrawnCnt > 0L) {
            System.exit(4);
        }
    }
    private void p2000Process() {
        wsReadCnt++;
        if (wsReadCnt == 10000000L) wsReadCnt = 0L;
        if (curStatusByte != 67) {
            p3000Post();
            byte[] nr = encodeCur();
            recList.set(lastIdx, nr);
            wsUpdatedCnt++;
            if (wsUpdatedCnt == 10000000L) wsUpdatedCnt = 0L;
        }
        p8000Read();
    }
    private void p3000Post() {
        BigDecimal numer = BigDecimal.valueOf(curBalanceCents).multiply(BigDecimal.valueOf((long) curRateInt));
        BigDecimal ic = numer.divide(BigDecimal.valueOf(120000L), 0, RoundingMode.HALF_UP);
        long interestCents = ic.longValueExact();
        interestCents = trunc9(interestCents);
        wsInterestCents = interestCents;
        BigDecimal balBD = BigDecimal.valueOf(curBalanceCents, 2);
        BigDecimal intBD = BigDecimal.valueOf(interestCents, 2);
        BigDecimal sumBD = balBD.add(intBD);
        long sumCents = toCentsTrunc(sumBD);
        sumCents = trunc9(sumCents);
        curBalanceCents = sumCents;
        BigDecimal curBD = BigDecimal.valueOf(curBalanceCents, 2);
        if (curBD.compareTo(BigDecimal.ZERO) >= 0 && curBD.compareTo(new BigDecimal("100.00")) < 0) {
            BigDecimal feeBD = new BigDecimal("2.50");
            BigDecimal afterBD = curBD.subtract(feeBD);
            long afterCents = toCentsTrunc(afterBD);
            afterCents = trunc9(afterCents);
            curBalanceCents = afterCents;
            curFeeCnt = (curFeeCnt + 1) % 1000;
        }
        BigDecimal finalBD = BigDecimal.valueOf(curBalanceCents, 2);
        if (finalBD.compareTo(BigDecimal.ZERO) < 0) {
            curStatusByte = 79;
            wsOverdrawnCnt++;
            if (wsOverdrawnCnt == 10000000L) wsOverdrawnCnt = 0L;
        }
    }
    private void p8000Read() {
        if (nextIdx >= recList.size()) {
            endOfMaster = true;
        } else {
            byte[] r = recList.get(nextIdx);
            decodeCur(r);
            lastIdx = nextIdx;
            nextIdx++;
        }
    }
    private void decodeCur(byte[] r) {
        System.arraycopy(r, 0, curAcctId, 0, 8);
        curStatusByte = r[8] & 255;
        long mag = 0L;
        for (int i = 0; i < 8; i++) {
            int b = r[9 + i] & 255;
            int d = b - 48;
            if (d < 0 || d > 9) d = 0;
            mag = mag * 10L + (long) d;
        }
        int lb = r[18] & 255;
        int lastD;
        boolean neg = false;
        if (lb >= 48 && lb <= 57) {
            lastD = lb - 48;
        } else if (lb >= 112 && lb <= 121) {
            lastD = lb - 112;
            neg = true;
        } else if (lb >= 80 && lb <= 89) {
            lastD = lb - 80;
            neg = true;
        } else {
            lastD = 0;
        }
        mag = mag * 10L + (long) lastD;
        curBalanceCents = neg ? -mag : mag;
        int rate = 0;
        for (int i = 0; i < 5; i++) {
            int b = r[18 + i] & 255;
            int d = b - 48;
            if (d < 0 || d > 9) d = 0;
            rate = rate * 10 + d;
        }
        curRateInt = rate;
        int fee = 0;
        for (int i = 0; i < 3; i++) {
            int b = r[23 + i] & 255;
            int d = b - 48;
            if (d < 0 || d > 9) d = 0;
            fee = fee * 10 + d;
        }
        curFeeCnt = fee;
    }
    private byte[] encodeCur() {
        byte[] r = new byte[26];
        System.arraycopy(curAcctId, 0, r, 0, 8);
        r[8] = (byte) curStatusByte;
        long v = curBalanceCents;
        boolean neg = v < 0L;
        long mag = neg ? -v : v;
        String s = String.format("%09d", Long.valueOf(mag));
        for (int i = 0; i < 8; i++) r[9 + i] = (byte) s.charAt(i);
        int lastD = s.charAt(8) - 48;
        if (!neg) r[18] = (byte) (48 + lastD);
        else r[18] = (byte) (112 + lastD);
        String rs = String.format("%05d", Integer.valueOf(curRateInt));
        for (int i = 0; i < 5; i++) r[18 + i] = (byte) rs.charAt(i);
        String fs = String.format("%03d", Integer.valueOf(curFeeCnt));
        for (int i = 0; i < 3; i++) r[23 + i] = (byte) fs.charAt(i);
        return r;
    }
    private static long trunc9(long v) {
        if (v > 999999999L || v < -999999999L) return v % 1000000000L;
        return v;
    }
    private static long toCentsTrunc(BigDecimal v) {
        BigDecimal t = v.setScale(2, RoundingMode.DOWN);
        return t.movePointRight(2).longValueExact();
    }
    private static String fmt7(long v) {
        long w = v % 10000000L;
        if (w < 0L) w = -w;
        return String.format("%07d", Long.valueOf(w));
    }
}
