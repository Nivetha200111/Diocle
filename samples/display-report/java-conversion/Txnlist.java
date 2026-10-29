import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Hand-written Java port of TXNLIST (a test fixture, not model output): no output file, only DISPLAY lines
 * on stdout and the RETURN-CODE.
 */
public class Txnlist {
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(System.getenv("DD_TXNIN")));
        StringBuilder out = new StringBuilder("TXNLIST DAILY LISTING\n");
        BigDecimal credits = BigDecimal.ZERO, debits = BigDecimal.ZERO;
        int listed = 0, rejected = 0;
        for (String raw : lines) {
            String line = (raw + " ".repeat(15)).substring(0, 15);
            String id = line.substring(0, 6);
            char type = line.charAt(6);
            BigDecimal amount = new BigDecimal(line.substring(8)).movePointLeft(2);
            if (line.charAt(7) == '-') {
                amount = amount.negate();
            }
            listed++;
            String edited = edit(amount, 5);
            if (type == 'C') {
                credits = credits.add(amount);
                out.append(id).append(" CR ").append(edited).append('\n');
            } else if (type == 'D') {
                debits = debits.add(amount);
                out.append(id).append(" DB ").append(edited).append('\n');
            } else {
                rejected++;
                out.append(id).append(" ?? ").append(edited).append(" REJECTED\n");
            }
        }
        out.append("CREDITS ").append(edit(credits, 9)).append('\n');
        out.append("DEBITS  ").append(edit(debits, 9)).append('\n');
        out.append(String.format("LISTED %07d REJECTED %07d%n", listed, rejected));
        System.out.print(out);
        System.out.flush();
        if (rejected > 0) {
            System.exit(4);
        }
    }

    /** PIC -(n)9.99: a floating minus sign, n-1 digit positions before the 9, right-justified in n+4 characters. */
    static String edit(BigDecimal v, int n) {
        String digits = v.abs().setScale(2).toPlainString();
        String text = (v.signum() < 0 ? "-" : "") + digits;
        return " ".repeat(Math.max(0, n + 4 - text.length())) + text;
    }
}
