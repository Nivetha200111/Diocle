import java.math.BigDecimal;
import java.math.RoundingMode;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;

/**
 * Diocle support for converted EXEC SQL programs. The verifier compiles ITS OWN copy of this file over any file of the
 * same name in the converted sources, so it cannot be changed by the conversion.
 *
 * Stand-in engine: SQLite, NOT DB2 (the COBOL side runs on the same engine through a C shim). Storage convention,
 * identical on both sides: DECIMAL(p,s), SMALLINT, INTEGER and BIGINT are INTEGER columns holding value * 10^s
 * (bind and read them with long; use scaled() and dec() to convert), CHAR/VARCHAR are TEXT without trailing blanks
 * (bind trim(value); read with pad(value, n)).
 *
 * SQLCODE values: 0, +100 no row / past the last row / UPDATE or DELETE that changed no row, -803 duplicate key,
 * -811 SELECT INTO found more than one row, -407 NULL into NOT NULL, -404 string too long, -413 numeric overflow,
 * -305 NULL read without an indicator (your code decides this), -501 cursor not open, -502 cursor already open,
 * -901 any other engine error.
 *
 * Transactions: autocommit is off. COMMIT and ROLLBACK (use commit()/rollback() below) close every open cursor.
 * Work still uncommitted when the program ends normally is committed, as DB2 does at normal termination.
 */
public final class DioSql {
    private DioSql() {}

    private static final List<Cursor> OPEN = new ArrayList<>();

    /** The program's database (path in DIOCLE_DB), autocommit off. Call once. */
    public static Connection connect() throws SQLException {
        String path = System.getenv("DIOCLE_DB");
        if (path == null || path.isEmpty()) throw new SQLException("DIOCLE_DB is not set");
        final Connection c = DriverManager.getConnection("jdbc:sqlite:" + path);
        c.setAutoCommit(false);
        try (java.sql.Statement st = c.createStatement()) { st.execute("PRAGMA max_page_count=8192"); }
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try { if (!c.isClosed()) c.commit(); } catch (SQLException e) { /* nothing more to do at exit */ }
        }));
        return c;
    }

    /** SQLCODE for an engine error (the documented small set). */
    public static int code(SQLException e) {
        String m = String.valueOf(e.getMessage());
        if (m.contains("UNIQUE constraint failed") || m.contains("PRIMARY KEY")) return -803;
        if (m.contains("NOT NULL constraint failed")) return -407;
        if (m.contains("dio_len")) return -404;
        if (m.contains("dio_prec")) return -413;
        return -901;
    }

    /** SQLCODE after an UPDATE or DELETE that changed n rows. */
    public static int afterChange(int n) { return n == 0 ? 100 : 0; }

    /** value * 10^scale as the engine stores it, truncating extra decimals toward zero (a COBOL MOVE does the same). */
    public static long scaled(BigDecimal v, int scale) {
        return v.setScale(scale, RoundingMode.DOWN).movePointRight(scale).longValueExact();
    }

    public static BigDecimal dec(long stored, int scale) { return BigDecimal.valueOf(stored, scale); }

    /** CHAR semantics: trailing blanks are not data. */
    public static String trim(String s) {
        int n = s.length();
        while (n > 0 && s.charAt(n - 1) == ' ') n--;
        return s.substring(0, n);
    }

    /** MOVE to PIC X(n): blank-padded or truncated to n characters. */
    public static String pad(String s, int n) {
        if (s == null) s = "";
        if (s.length() >= n) return s.substring(0, n);
        return s + " ".repeat(n - s.length());
    }

    static void bind(PreparedStatement ps, Object[] binds) throws SQLException {
        for (int i = 0; i < binds.length; i++) {
            Object b = binds[i];
            if (b == null) ps.setNull(i + 1, java.sql.Types.NULL);
            else if (b instanceof Long || b instanceof Integer) ps.setLong(i + 1, ((Number) b).longValue());
            else if (b instanceof String) ps.setString(i + 1, (String) b);
            else throw new SQLException("bind long, int, String or null only, not " + b.getClass().getName());
        }
    }

    public static void commit(Connection c) throws SQLException { closeAll(); c.commit(); }

    public static void rollback(Connection c) throws SQLException { closeAll(); c.rollback(); }

    private static void closeAll() {
        for (Cursor cur : new ArrayList<>(OPEN)) cur.closeQuietly();
        OPEN.clear();
    }

    /** One row read by SELECT INTO: code is the SQLCODE; the values are valid only when code is 0. */
    public static final class Row {
        public final int code;
        private final Object[] values;
        Row(int code, Object[] values) { this.code = code; this.values = values; }
        public boolean isNull(int i) { return values[i] == null; }
        public long getLong(int i) { return (Long) values[i]; }
        public String getString(int i) { return (String) values[i]; }
    }

    /** SELECT INTO: no row gives code 100, more than one gives -811 (nothing is returned in either case). */
    public static Row selectOne(Connection c, String sql, Object... binds) {
        try (PreparedStatement ps = c.prepareStatement(sql)) {
            bind(ps, binds);
            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) return new Row(100, null);
                int n = rs.getMetaData().getColumnCount();
                Object[] v = new Object[n];
                for (int i = 0; i < n; i++) v[i] = rs.getObject(i + 1);
                for (int i = 0; i < n; i++) if (v[i] instanceof Number) v[i] = ((Number) v[i]).longValue();
                if (rs.next()) return new Row(-811, null);
                return new Row(0, v);
            }
        } catch (SQLException e) {
            return new Row(code(e), null);
        }
    }

    /** A cursor: open(binds) evaluates the host variables once, fetch() moves to the next row. */
    public static final class Cursor {
        private final Connection conn;
        private final String sql;
        private PreparedStatement ps;
        private ResultSet rs;

        public Cursor(Connection conn, String sql) { this.conn = conn; this.sql = sql; }

        /** @return SQLCODE: 0, or -502 when already open. */
        public int open(Object... binds) {
            if (rs != null) return -502;
            try {
                ps = conn.prepareStatement(sql);
                bind(ps, binds);
                rs = ps.executeQuery();
                OPEN.add(this);
                return 0;
            } catch (SQLException e) {
                closeQuietly();
                return code(e);
            }
        }

        /** @return SQLCODE: 0 (a row is available through getLong/getString/isNull), 100 past the last row, -501 not open. */
        public int fetch() {
            if (rs == null) return -501;
            try { return rs.next() ? 0 : 100; } catch (SQLException e) { return code(e); }
        }

        public boolean isNull(int i) throws SQLException { rs.getObject(i + 1); return rs.wasNull(); }
        public long getLong(int i) throws SQLException { return rs.getLong(i + 1); }
        public String getString(int i) throws SQLException { return rs.getString(i + 1); }

        /** @return SQLCODE: 0, or -501 when not open. */
        public int close() {
            if (rs == null) return -501;
            closeQuietly();
            OPEN.remove(this);
            return 0;
        }

        void closeQuietly() {
            try { if (rs != null) rs.close(); } catch (SQLException e) { /* closing */ }
            try { if (ps != null) ps.close(); } catch (SQLException e) { /* closing */ }
            rs = null; ps = null;
        }
    }
}
