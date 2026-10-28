// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// Faithful Java port of samples/account-match/src/ACCTMTCH.cbl, used to prove multi-file verification.
import java.math.BigDecimal;
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class Acctmtch {
    static final boolean EBCDIC = "EBCDIC".equals(System.getenv("DIOCLE_COLLATION"));
    static final Charset CP037 = Charset.forName("Cp037");

    String mstKey, txnKey;  // null = HIGH-VALUES
    String mst, txn;
    BigDecimal balance = BigDecimal.ZERO;
    int count;
    long newCount, excCount;
    Iterator<String> masters, txns;
    final List<String> newMaster = new ArrayList<>(), exceptions = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        Acctmtch p = new Acctmtch();
        p.masters = read("DD_MSTIN", 24).iterator();
        p.txns = read("DD_TXNIN", 19).iterator();
        p.readMst();
        p.readTxn();
        while (!(p.mstKey == null && p.txnKey == null)) p.match();
        Files.write(Path.of(System.getenv("DD_NEWMST")), p.newMaster);
        Files.write(Path.of(System.getenv("DD_EXCOUT")), p.exceptions);
        System.out.println("ACCTMTCH NEW=" + String.format("%07d", p.newCount) + " EXC=" + String.format("%07d", p.excCount));
        System.exit(p.excCount > 0 ? 4 : 0);
    }

    static List<String> read(String dd, int length) throws Exception {
        List<String> out = new ArrayList<>();
        for (String l : Files.readAllLines(Path.of(System.getenv(dd)), Charset.forName("ISO-8859-1")))
            out.add(String.format("%-" + length + "s", l).substring(0, length));
        return out;
    }

    static int compare(String a, String b) {  // null is HIGH-VALUES
        if (a == null || b == null) return a == null ? (b == null ? 0 : 1) : -1;
        if (!EBCDIC) return a.compareTo(b);
        byte[] x = a.getBytes(CP037), y = b.getBytes(CP037);
        for (int i = 0; i < Math.min(x.length, y.length); i++)
            if (x[i] != y[i]) return (x[i] & 0xFF) - (y[i] & 0xFF);
        return x.length - y.length;
    }

    void match() {
        int c = compare(txnKey, mstKey);
        if (c < 0) {
            exception("NO ACCOUNT");
            readTxn();
        } else if (c == 0) {
            apply();
            readTxn();
        } else {
            writeMaster();
            readMst();
        }
    }

    void apply() {
        if (mst.substring(20, 24).equals("FRZN")) {
            exception("FROZEN");
            return;
        }
        BigDecimal amount = signed(txn.substring(8, 18), 2);
        switch (txn.charAt(18)) {
            case 'C' -> { balance = wrap(balance.add(amount)); count = (count + 1) % 10000; }
            case 'D' -> { balance = wrap(balance.subtract(amount)); count = (count + 1) % 10000; }
            default -> exception("BAD TYPE");
        }
    }

    static BigDecimal wrap(BigDecimal v) {  // S9(9)V99 keeps the low-order digits
        BigDecimal r = v.abs().remainder(BigDecimal.TEN.pow(9));
        return v.signum() < 0 ? r.negate() : r;
    }

    static BigDecimal signed(String s, int scale) {
        BigDecimal v = new BigDecimal(s.substring(1)).movePointLeft(scale);
        return s.charAt(0) == '-' ? v.negate() : v;
    }

    static String leadingSeparate(BigDecimal v, int digits) {
        String d = v.abs().movePointRight(2).toBigInteger().toString();
        return (v.signum() < 0 ? "-" : "+") + "0".repeat(digits - d.length()) + d;
    }

    void writeMaster() {
        newMaster.add(mst.substring(0, 8) + leadingSeparate(balance, 11) + mst.substring(20, 24) + String.format("%04d", count));
        newCount++;
    }

    void exception(String reason) {
        String line = txn.substring(0, 8) + leadingSeparate(signed(txn.substring(8, 18), 2), 9) + String.format("%-12s", reason);
        exceptions.add(line.stripTrailing());
        excCount++;
    }

    void readMst() {
        if (masters.hasNext()) {
            mst = masters.next();
            mstKey = mst.substring(0, 8);
            balance = signed(mst.substring(8, 20), 2);
            count = 0;
        } else {
            mstKey = null;
        }
    }

    void readTxn() {
        if (txns.hasNext()) {
            txn = txns.next();
            txnKey = txn.substring(0, 8);
        } else {
            txnKey = null;
        }
    }
}
