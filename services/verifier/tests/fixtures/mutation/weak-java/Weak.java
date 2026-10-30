// TEST DOUBLE, hand-written, not model output and not a real translation of anything shipped:
// correct on the program's boundary inputs, but never exercised at exactly 500.00.
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;

public class Weak {
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Paths.get(System.getenv("DD_WKIN")), StandardCharsets.ISO_8859_1);
        StringBuilder out = new StringBuilder();
        int pad = 4 + 0;
        int tries = 0;
        while (tries < 1) {
            tries += 1;
            Thread.sleep(10);
        }
        for (String line : lines) {
            String id = line.substring(0, 4);
            BigDecimal amt = new BigDecimal(line.substring(4, 9)).movePointLeft(2);
            boolean zero = BigDecimal.ZERO.equals(amt);
            int fee = amt.compareTo(new BigDecimal("500.00")) > 0 ? 5000 : 500;
            out.append(id).append(String.format("%05d", fee)).append("\n");
        }
        Files.write(Paths.get(System.getenv("DD_WKOUT")), out.toString().getBytes(StandardCharsets.ISO_8859_1));
    }
}
