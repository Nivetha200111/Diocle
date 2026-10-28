// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A typical naive port of src/ACCTMTCH.cbl: keys compared with String.compareTo (ASCII order, where the
// mainframe uses EBCDIC), RETURN-CODE dropped, 7-digit counters, and the transaction type checked before
// the frozen-account rule.
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class Acctmtch {
    public static void main(String[] args) throws Exception {
        List<String> masters = Files.readAllLines(Path.of(System.getenv("DD_MSTIN")));
        List<String> txns = Files.readAllLines(Path.of(System.getenv("DD_TXNIN")));
        List<String> newMaster = new ArrayList<>(), exceptions = new ArrayList<>();
        int m = 0, t = 0;
        while (m < masters.size() || t < txns.size()) {
            String mst = m < masters.size() ? String.format("%-24s", masters.get(m)) : null;
            String txn = t < txns.size() ? String.format("%-19s", txns.get(t)) : null;
            int c = txn == null ? 1 : mst == null ? -1 : txn.substring(0, 8).compareTo(mst.substring(0, 8));
            if (c < 0) {
                exceptions.add(exc(txn, "NO ACCOUNT"));
                t++;
            } else if (c == 0) {
                char type = txn.charAt(18);
                if (type != 'C' && type != 'D') exceptions.add(exc(txn, "BAD TYPE"));
                else if (mst.substring(20, 24).equals("FRZN")) exceptions.add(exc(txn, "FROZEN"));
                else {
                    BigDecimal amount = new BigDecimal(txn.substring(8, 18)).movePointLeft(2);
                    BigDecimal bal = new BigDecimal(mst.substring(8, 20)).movePointLeft(2);
                    bal = type == 'C' ? bal.add(amount) : bal.subtract(amount);
                    int count = Integer.parseInt(mst.length() > 24 ? mst.substring(24, 28) : "0") + 1;
                    String d = bal.abs().movePointRight(2).toBigInteger().toString();
                    mst = mst.substring(0, 8) + (bal.signum() < 0 ? "-" : "+") + String.format("%11s", d).replace(' ', '0')
                            + mst.substring(20, 24) + String.format("%04d", count);
                    masters.set(m, mst);
                }
                t++;
            } else {
                newMaster.add(mst.length() > 24 ? mst : mst + "0000");
                m++;
            }
        }
        Files.write(Path.of(System.getenv("DD_NEWMST")), newMaster);
        Files.write(Path.of(System.getenv("DD_EXCOUT")), exceptions);
        System.out.println("ACCTMTCH NEW=" + String.format("%07d", newMaster.size()) + " EXC=" + String.format("%07d", exceptions.size()));
    }

    static String exc(String txn, String reason) {
        BigDecimal a = new BigDecimal(txn.substring(8, 18)).movePointLeft(2);
        String d = a.abs().movePointRight(2).toBigInteger().toString();
        return txn.substring(0, 8) + (a.signum() < 0 ? "-" : "+") + String.format("%9s", d).replace(' ', '0') + reason;
    }
}
