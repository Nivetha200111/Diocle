import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * Hand-written Java port of FEEPOST and its CALLed module FEECALC (a test fixture, not model output).
 * The COBOL calls the module through WS-FEE-PGM, which only ever holds 'FEECALC'.
 */
public class FeePost {
    public static void main(String[] args) throws Exception {
        List<String> out = new ArrayList<>();
        for (String raw : Files.readAllLines(Path.of(System.getenv("DD_PAYIN")))) {
            String line = (raw + " ".repeat(14)).substring(0, 14);
            BigDecimal amount = new BigDecimal(line.substring(7)).movePointLeft(2);
            if (line.charAt(6) == '-') {
                amount = amount.negate();
            }
            BigDecimal fee = feecalc(amount);
            out.add(line.substring(0, 6) + signed(amount) + signed(fee));
        }
        Files.write(Path.of(System.getenv("DD_POSTOUT")), out);
    }

    /** FEECALC: 1.5 percent of a positive payment, rounded, minimum 1.00; nothing for a refund. */
    static BigDecimal feecalc(BigDecimal amount) {
        if (amount.signum() > 0) {
            BigDecimal fee = amount.multiply(new BigDecimal("0.015")).setScale(2, RoundingMode.HALF_UP);
            return fee.compareTo(new BigDecimal("1.00")) < 0 ? new BigDecimal("1.00") : fee;
        }
        return new BigDecimal("0.00");
    }

    /** PIC S9(5)V99 SIGN LEADING SEPARATE. */
    static String signed(BigDecimal v) {
        return (v.signum() < 0 ? "-" : "+") + String.format("%07d", v.abs().movePointRight(2).toBigIntegerExact());
    }
}
