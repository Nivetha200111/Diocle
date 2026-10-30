import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.util.List;

/**
 * Hand-written Java (JDBC) port of ACCTRPT (a test fixture, not model output). Amounts are kept as the engine stores
 * them: whole units of 0.01 in a long.
 */
public class Acctrpt {
    static final long LIMIT9 = 1_000_000_000L; // PIC S9(7)V99: nine digits; a COMPUTE without SIZE ERROR keeps the low-order nine

    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(System.getenv("DD_ACCTIN")), StandardCharsets.ISO_8859_1);
        Connection c = DioSql.connect();
        int seq = 1, done = 0, rc = 0;
        try (BufferedWriter out = Files.newBufferedWriter(Path.of(System.getenv("DD_RPTOUT")), StandardCharsets.ISO_8859_1)) {
            for (String raw : lines) {
                String line = (raw + " ".repeat(15)).substring(0, 15);
                String id = line.substring(0, 8);
                long amount = overpunch(line.substring(8, 15));
                DioSql.Row row = DioSql.selectOne(c, "SELECT BALANCE, LIMIT_AMT FROM ACCOUNTS WHERE ACCT_ID = ?", DioSql.trim(id));
                int code = row.code;
                if (code == 0) {
                    long bal = row.getLong(0);
                    long floor = row.isNull(1) ? 0 : -row.getLong(1);
                    long next = trunc(bal + amount);
                    if (next < floor) {
                        write(out, "REJECT", id, bal, bal, 0);
                    } else {
                        try (var ps = c.prepareStatement("UPDATE ACCOUNTS SET BALANCE = BALANCE + ? WHERE ACCT_ID = ?")) {
                            ps.setLong(1, amount);
                            ps.setString(2, DioSql.trim(id));
                            code = DioSql.afterChange(ps.executeUpdate());
                        } catch (java.sql.SQLException e) {
                            code = DioSql.code(e);
                        }
                        if (code == 0) {
                            try (var ps = c.prepareStatement("INSERT INTO AUDIT (AUDIT_SEQ, ACCT_ID, OLD_BAL, NEW_BAL) VALUES (?, ?, ?, ?)")) {
                                ps.setLong(1, seq);
                                ps.setString(2, DioSql.trim(id));
                                ps.setLong(3, bal);
                                ps.setLong(4, next);
                                ps.executeUpdate();
                                code = 0;
                            } catch (java.sql.SQLException e) {
                                code = DioSql.code(e);
                            }
                            seq++;
                        }
                        write(out, "POSTED", id, bal, next, code);
                    }
                } else if (code == 100) {
                    write(out, "NOACCT", id, 0, 0, code);
                } else {
                    write(out, "SQLERR", id, 0, 0, code);
                    rc = 8;
                }
                done++;
                if (done > 49) {
                    DioSql.commit(c);
                    done = 0;
                }
            }
            DioSql.commit(c);
            DioSql.Cursor cur = new DioSql.Cursor(c, "SELECT ACCT_ID, BALANCE FROM ACCOUNTS WHERE BALANCE < ? ORDER BY ACCT_ID");
            int code = cur.open(10000L);
            if (code == 0) code = cur.fetch();
            while (code == 0) {
                write(out, "LOWBAL", DioSql.pad(cur.getString(0), 8), cur.getLong(1), cur.getLong(1), 0);
                code = cur.fetch();
            }
            write(out, "ENDCUR", "        ", 0, 0, code);
            cur.close();
            DioSql.commit(c);
        }
        System.out.flush();
        if (rc != 0) System.exit(rc);
    }

    /** COMPUTE into PIC S9(7)V99 without ON SIZE ERROR: high-order digits are lost. */
    static long trunc(long v) {
        long m = Math.abs(v) % LIMIT9;
        return v < 0 ? -m : m;
    }

    static void write(BufferedWriter out, String tag, String acct, long old, long neu, int code) throws java.io.IOException {
        out.write(tag + acct + display(old) + display(neu) + (code < 0 ? "-" : "+") + String.format("%09d", Math.abs(code)) + "\n");
    }

    /** PIC S9(7)V99, sign in the last digit: a negative digit d is written as chr('p' + d). */
    static String display(long v) {
        String digits = String.format("%09d", Math.abs(v));
        char last = digits.charAt(8);
        return digits.substring(0, 8) + (v < 0 ? (char) (last + 0x40) : last);
    }

    static long overpunch(String text) {
        char last = text.charAt(text.length() - 1);
        boolean negative = last >= 'p' && last <= 'y';
        long v = Long.parseLong(text.substring(0, text.length() - 1) + (negative ? (char) (last - 0x40) : last));
        return negative ? -v : v;
    }
}
