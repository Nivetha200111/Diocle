// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A behaviour-faithful translation of samples/interest-accrual/src/INTACCR.cbl,
// used only to test that the verifier reports a pass when outputs truly match.
import java.io.BufferedWriter;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.file.Files;
import java.nio.file.Path;

public class IntAccr {
    private static final BigDecimal PENALTY_RATE = new BigDecimal("0.0500");
    private static final BigDecimal FEE_FLOOR = new BigDecimal("1000.00");
    private static final BigDecimal FEE_CAP = new BigDecimal("25.00");
    private static final BigDecimal FEE_RATE = new BigDecimal("0.0015");
    private static final BigDecimal DAYS_IN_YEAR = BigDecimal.valueOf(365);

    public static void main(String[] args) throws IOException {
        Path in = Path.of(System.getenv("DD_ACCTIN"));
        Path out = Path.of(System.getenv("DD_INTOUT"));
        long read = 0;
        long written = 0;
        try (BufferedWriter w = Files.newBufferedWriter(out)) {
            for (String line : Files.readAllLines(in)) {
                line = String.format("%-31s", line);
                String id = line.substring(0, 10);
                BigDecimal balance = new BigDecimal(line.substring(10, 22)).movePointLeft(2);
                BigDecimal rate = new BigDecimal(line.substring(22, 27)).movePointLeft(4);
                BigDecimal days = new BigDecimal(line.substring(27, 30));
                boolean premium = line.charAt(30) == 'P';
                read++;

                // 3000-CALC-INTEREST: COMPUTE ROUNDED = half away from zero; no SIZE ERROR = drop high-order digits.
                BigDecimal interest = BigDecimal.ZERO.setScale(2);
                if (balance.signum() > 0) {
                    interest = store(balance.multiply(rate).multiply(days), RoundingMode.HALF_UP, 7);
                } else if (balance.signum() < 0) {
                    interest = store(balance.multiply(rate.add(PENALTY_RATE)).multiply(days), RoundingMode.HALF_UP, 7);
                }

                // 4000-CALC-FEE: COMPUTE without ROUNDED truncates; overflow truncates before the cap check.
                BigDecimal fee = BigDecimal.ZERO.setScale(2);
                if (!premium && balance.compareTo(FEE_FLOOR) < 0) {
                    fee = truncateHigh(FEE_FLOOR.subtract(balance).multiply(FEE_RATE).setScale(2, RoundingMode.DOWN), 5);
                    if (fee.compareTo(FEE_CAP) > 0) {
                        fee = FEE_CAP;
                    }
                }

                // 5000-WRITE-RESULT
                BigDecimal newBalance = truncateHigh(balance.add(interest).subtract(fee), 9);
                String status = newBalance.signum() < 0 ? "OD" : fee.signum() > 0 ? "FE" : "OK";
                w.write(id + signed(interest, 7) + signed(fee, 5) + signed(newBalance, 9) + status);
                w.newLine();
                written++;
            }
        }
        // PIC 9(7) COMP is a 4-byte binary item; GnuCOBOL -std=ibm DISPLAYs it with 10 digits.
        System.out.printf("INTACCR READ=%010d WRITTEN=%010d%n", read, written);
    }

    private static BigDecimal store(BigDecimal numerator, RoundingMode mode, int integerDigits) {
        return truncateHigh(numerator.divide(DAYS_IN_YEAR, 2, mode), integerDigits);
    }

    private static BigDecimal truncateHigh(BigDecimal value, int integerDigits) {
        BigInteger modulus = BigInteger.TEN.pow(integerDigits + 2);
        BigInteger unscaled = value.setScale(2, RoundingMode.DOWN).unscaledValue();
        BigInteger kept = unscaled.abs().mod(modulus);
        return new BigDecimal(unscaled.signum() < 0 ? kept.negate() : kept, 2);
    }

    private static String signed(BigDecimal value, int integerDigits) {
        String digits = value.abs().unscaledValue().toString();
        return (value.signum() < 0 ? "-" : "+") + "0".repeat(integerDigits + 2 - digits.length()) + digits;
    }
}
