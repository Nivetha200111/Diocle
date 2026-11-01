import java.io.FileOutputStream;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

public class Acctrpt {
    static Connection c;
    static int sqlcode = 0;
    static int returnCode = 0;
    static boolean endOfAccts = false;
    static BigDecimal wsBal = new BigDecimal("0.00");
    static BigDecimal wsLimit = new BigDecimal("0.00");
    static int wsLimitInd = 0;
    static BigDecimal wsNew = new BigDecimal("0.00");
    static BigDecimal wsFloor = new BigDecimal("0.00");
    static BigDecimal wsLow = new BigDecimal("100.00");
    static long wsSeq = 1;
    static int wsDone = 0;
    static String wsLowId = "        ";
    static BigDecimal wsLowBal = new BigDecimal("0.00");
    static String aiAcctId = "        ";
    static BigDecimal aiAmount = new BigDecimal("0.00");
    static String rptTag = "      ";
    static String rptAcct = "        ";
    static BigDecimal rptOld = new BigDecimal("0.00");
    static BigDecimal rptNew = new BigDecimal("0.00");
    static int rptCode = 0;
    static List<String> inRecs = new ArrayList<>();
    static int inPos = 0;
    static OutputStream out = null;

    public static void main(String[] args) throws Exception {
        Connection c = DioSql.connect();
        Acctrpt.c = c;
        m0000Main();
        if (out != null) {
            try { out.close(); } catch (Exception e) {}
            out = null;
        }
        if (returnCode != 0) System.exit(returnCode);
    }

    private static void m0000Main() throws Exception {
        byte[] all = Files.readAllBytes(Paths.get(System.getenv("DD_ACCTIN")));
        List<String> recs = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < all.length; i++) {
            if (all[i] == (byte) 10) {
                int end = i;
                if (end > start && all[end - 1] == (byte) 13) end--;
                int len = end - start;
                byte[] rb = new byte[len];
                for (int k = 0; k < len; k++) rb[k] = all[start + k];
                recs.add(new String(rb, StandardCharsets.ISO_8859_1));
                start = i + 1;
            }
        }
        if (start < all.length) {
            int end = all.length;
            if (end > start && all[end - 1] == (byte) 13) end--;
            int len = end - start;
            byte[] rb = new byte[len];
            for (int k = 0; k < len; k++) rb[k] = all[start + k];
            recs.add(new String(rb, StandardCharsets.ISO_8859_1));
        }
        inRecs = recs;
        inPos = 0;
        out = new FileOutputStream(System.getenv("DD_RPTOUT"));
        endOfAccts = false;
        m8000Read();
        while (!endOfAccts) {
            m1000Post();
        }
        try {
            DioSql.commit(Acctrpt.c);
            sqlcode = 0;
        } catch (SQLException e) {
            sqlcode = DioSql.code(e);
        }
        m3000LowBalances();
        try { out.close(); } catch (Exception e) {}
        out = null;
    }

    private static void m1000Post() throws Exception {
        rptTag = "      ";
        rptAcct = "        ";
        rptAcct = aiAcctId;
        DioSql.Row row = DioSql.selectOne(Acctrpt.c, "SELECT BALANCE, LIMIT_AMT FROM ACCOUNTS WHERE ACCT_ID = ?", DioSql.trim(aiAcctId));
        if (row.code == 0) {
            long sBal = row.getLong(0);
            wsBal = truncateToPic(DioSql.dec(sBal, 2), 9, 2);
            if (row.isNull(1)) {
                wsLimitInd = -1;
            } else {
                long sLim = row.getLong(1);
                wsLimit = truncateToPic(DioSql.dec(sLim, 2), 9, 2);
                wsLimitInd = 0;
            }
            sqlcode = 0;
            m2000Apply();
        } else if (row.code == 100) {
            sqlcode = 100;
            rptTag = "NOACCT";
            rptOld = new BigDecimal("0.00");
            rptNew = new BigDecimal("0.00");
            rptCode = sqlcode;
            writeRptRec();
        } else {
            sqlcode = row.code;
            rptTag = "SQLERR";
            rptOld = new BigDecimal("0.00");
            rptNew = new BigDecimal("0.00");
            rptCode = sqlcode;
            writeRptRec();
            returnCode = 8;
        }
        wsDone = truncateInt(wsDone + 1, 5);
        if (wsDone > 49) {
            try {
                DioSql.commit(Acctrpt.c);
                sqlcode = 0;
            } catch (SQLException e) {
                sqlcode = DioSql.code(e);
            }
            wsDone = 0;
        }
        m8000Read();
    }

    private static void m2000Apply() throws Exception {
        wsNew = truncateToPic(wsBal.add(aiAmount), 9, 2);
        wsFloor = new BigDecimal("0.00");
        if (wsLimitInd >= 0) {
            wsFloor = truncateToPic(BigDecimal.ZERO.subtract(wsLimit), 9, 2);
        }
        rptOld = wsBal;
        if (wsNew.compareTo(wsFloor) < 0) {
            rptTag = "REJECT";
            rptNew = wsBal;
            rptCode = 0;
            writeRptRec();
        } else {
            try (PreparedStatement ps = Acctrpt.c.prepareStatement("UPDATE ACCOUNTS SET BALANCE = BALANCE + ? WHERE ACCT_ID = ?")) {
                ps.setLong(1, DioSql.scaled(aiAmount, 2));
                ps.setString(2, DioSql.trim(aiAcctId));
                int n = ps.executeUpdate();
                sqlcode = DioSql.afterChange(n);
            } catch (SQLException e) {
                sqlcode = DioSql.code(e);
            }
            if (sqlcode == 0) {
                try (PreparedStatement ps2 = Acctrpt.c.prepareStatement("INSERT INTO AUDIT (AUDIT_SEQ, ACCT_ID, OLD_BAL, NEW_BAL) VALUES (?,?,?,?)")) {
                    ps2.setLong(1, wsSeq);
                    ps2.setString(2, DioSql.trim(aiAcctId));
                    ps2.setLong(3, DioSql.scaled(wsBal, 2));
                    ps2.setLong(4, DioSql.scaled(wsNew, 2));
                    ps2.executeUpdate();
                    sqlcode = 0;
                } catch (SQLException e) {
                    sqlcode = DioSql.code(e);
                }
                wsSeq = truncateLong(wsSeq + 1, 9);
            }
            rptTag = "POSTED";
            rptNew = wsNew;
            rptCode = sqlcode;
            writeRptRec();
        }
    }

    private static void m3000LowBalances() throws Exception {
        DioSql.Cursor lowcur = new DioSql.Cursor(Acctrpt.c, "SELECT ACCT_ID, BALANCE FROM ACCOUNTS WHERE BALANCE < ? ORDER BY ACCT_ID");
        sqlcode = lowcur.open(DioSql.scaled(wsLow, 2));
        sqlcode = fetchLow(lowcur);
        while (sqlcode == 0) {
            rptTag = "LOWBAL";
            rptAcct = wsLowId;
            rptOld = wsLowBal;
            rptNew = wsLowBal;
            rptCode = sqlcode;
            writeRptRec();
            sqlcode = fetchLow(lowcur);
        }
        rptTag = "ENDCUR";
        rptAcct = "        ";
        rptOld = new BigDecimal("0.00");
        rptNew = new BigDecimal("0.00");
        rptCode = sqlcode;
        writeRptRec();
        sqlcode = lowcur.close();
        try {
            DioSql.commit(Acctrpt.c);
            sqlcode = 0;
        } catch (SQLException e) {
            sqlcode = DioSql.code(e);
        }
    }

    private static void m8000Read() {
        if (inPos >= inRecs.size()) {
            endOfAccts = true;
        } else {
            String line = inRecs.get(inPos);
            inPos++;
            if (line.length() < 15) {
                StringBuilder sb = new StringBuilder(line);
                while (sb.length() < 15) sb.append(' ');
                line = sb.toString();
            } else if (line.length() > 15) {
                line = line.substring(0, 15);
            }
            aiAcctId = line.substring(0, 8);
            String amtRaw = line.substring(8, 15);
            BigDecimal dec = decodeSignedDisplay(amtRaw, 5, 2);
            aiAmount = truncateToPic(dec, 7, 2);
        }
    }

    private static int fetchLow(DioSql.Cursor cur) {
        int rc = cur.fetch();
        if (rc != 0) return rc;
        try {
            if (cur.isNull(0) || cur.isNull(1)) return -305;
            String id = cur.getString(0);
            if (id == null) id = "";
            long bal = cur.getLong(1);
            wsLowId = DioSql.pad(id, 8);
            wsLowBal = truncateToPic(DioSql.dec(bal, 2), 9, 2);
            return 0;
        } catch (SQLException e) {
            return DioSql.code(e);
        }
    }

    private static void writeRptRec() throws Exception {
        byte[] tagB = toBytesFixed(rptTag, 6);
        byte[] acctB = toBytesFixed(rptAcct, 8);
        byte[] oldB = encodeSignedDisplay(rptOld, 7, 2);
        byte[] newB = encodeSignedDisplay(rptNew, 7, 2);
        byte[] codeB = encodeLeadingSeparate(rptCode, 9);
        byte[] rec = new byte[6 + 8 + 9 + 9 + 10];
        int p = 0;
        for (byte b : tagB) rec[p++] = b;
        for (byte b : acctB) rec[p++] = b;
        for (byte b : oldB) rec[p++] = b;
        for (byte b : newB) rec[p++] = b;
        for (byte b : codeB) rec[p++] = b;
        out.write(rec);
        out.write(10);
    }

    private static byte[] toBytesFixed(String s, int n) {
        if (s == null) s = "";
        byte[] b = new byte[n];
        for (int i = 0; i < n; i++) {
            char ch = i < s.length() ? s.charAt(i) : ' ';
            b[i] = (byte) (ch & 255);
        }
        return b;
    }

    private static BigDecimal truncateToPic(BigDecimal v, int totalDigits, int scale) {
        BigDecimal t = v.setScale(scale, RoundingMode.DOWN);
        BigDecimal mod = BigDecimal.TEN.pow(totalDigits);
        BigDecimal scaled = t.movePointRight(scale);
        BigDecimal r = scaled.remainder(mod);
        return r.movePointLeft(scale).setScale(scale, RoundingMode.UNNECESSARY);
    }

    private static int truncateInt(int v, int digits) {
        int p = 1;
        for (int i = 0; i < digits; i++) p *= 10;
        return v % p;
    }

    private static long truncateLong(long v, int digits) {
        long p = 1;
        for (int i = 0; i < digits; i++) p *= 10;
        return v % p;
    }

    private static BigDecimal decodeSignedDisplay(String raw, int intDigits, int scale) {
        int total = intDigits + scale;
        StringBuilder digits = new StringBuilder();
        boolean neg = false;
        for (int i = 0; i < total; i++) {
            char ch = i < raw.length() ? raw.charAt(i) : ' ';
            if (i == total - 1) {
                if (ch >= '0' && ch <= '9') {
                    digits.append(ch);
                    neg = false;
                } else if (ch >= '@' && ch <= 'I') {
                    digits.append((char) ('0' + (ch - '@')));
                    neg = true;
                } else if (ch >= 'p' && ch <= 'y') {
                    digits.append((char) ('0' + (ch - 'p')));
                    neg = true;
                } else if (ch == ' ') {
                    digits.append('0');
                    neg = false;
                } else {
                    digits.append('0');
                    neg = false;
                }
            } else {
                if (ch >= '0' && ch <= '9') digits.append(ch);
                else if (ch == ' ') digits.append('0');
                else if (ch >= '@' && ch <= 'I') digits.append((char) ('0' + (ch - '@')));
                else digits.append('0');
            }
        }
        BigDecimal scaled = new BigDecimal(digits.toString());
        BigDecimal v = scaled.movePointLeft(scale);
        if (neg) v = v.negate();
        return v.setScale(scale, RoundingMode.UNNECESSARY);
    }

    private static byte[] encodeSignedDisplay(BigDecimal v, int intDigits, int scale) {
        int total = intDigits + scale;
        BigDecimal t = truncateToPic(v, total, scale);
        BigDecimal scaled = t.movePointRight(scale);
        boolean neg = scaled.signum() < 0;
        long abs = scaled.abs().longValueExact();
        String fmt = "%0" + total + "d";
        String s = String.format(java.util.Locale.US, fmt, abs);
        byte[] b = new byte[total];
        for (int i = 0; i < total - 1; i++) b[i] = (byte) s.charAt(i);
        int d = s.charAt(total - 1) - '0';
        if (neg) b[total - 1] = (byte) (d + 64);
        else b[total - 1] = (byte) s.charAt(total - 1);
        return b;
    }

    private static byte[] encodeLeadingSeparate(long val, int digits) {
        long p = 1;
        for (int i = 0; i < digits; i++) p *= 10;
        long r = val % p;
        boolean neg = r < 0;
        long abs = r < 0 ? -r : r;
        String fmt = "%0" + digits + "d";
        String s = String.format(java.util.Locale.US, fmt, abs);
        byte[] b = new byte[digits + 1];
        b[0] = (byte) (neg ? '-' : '+');
        for (int i = 0; i < digits; i++) b[i + 1] = (byte) s.charAt(i);
        return b;
    }
}
