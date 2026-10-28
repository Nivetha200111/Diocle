// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A plausible port of src/LOYWAIVE.cbl with one narrow defect: "NOT < 5000.00" became "> 5000.00", so an
// account with exactly 5000.00 is charged. Generated test inputs almost never hit that exact value.
import java.math.BigDecimal;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public class Loywaive {
    public static void main(String[] args) throws Exception {
        List<String> out = new ArrayList<>();
        for (String line : Files.readAllLines(Path.of(System.getenv("DD_LOYIN")))) {
            line = String.format("%-21s", line);
            String acct = line.substring(0, 8);
            BigDecimal balance = new BigDecimal(line.substring(9, 18)).movePointLeft(2);
            if (line.charAt(8) == '-') balance = balance.negate();
            int tenure = Integer.parseInt(line.substring(18, 21));
            boolean waived = balance.compareTo(new BigDecimal("5000.00")) > 0 || tenure >= 120;
            out.add(acct + (waived ? "0000WV" : "0450CH"));
        }
        Files.write(Path.of(System.getenv("DD_LOYOUT")), out);
    }
}
