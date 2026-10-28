// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A typical naive line-by-line translation of src/INTACCR.cbl, used to
// exercise Diocle's "bring your own conversion" verification mode.
// It intentionally uses double arithmetic and Math.round, the way many
// quick ports do. Diocle's verifier is expected to find where it diverges.
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class IntAccr {
    public static void main(String[] args) throws IOException {
        Path in = Path.of(System.getenv("DD_ACCTIN"));
        Path out = Path.of(System.getenv("DD_INTOUT"));
        int read = 0;
        int written = 0;
        try (BufferedWriter w = Files.newBufferedWriter(out)) {
            for (String line : Files.readAllLines(in)) {
                line = String.format("%-31s", line);
                String id = line.substring(0, 10);
                double balance = Double.parseDouble(line.substring(10, 22)) / 100.0;
                double rate = Integer.parseInt(line.substring(22, 27)) / 10000.0;
                int days = Integer.parseInt(line.substring(27, 30));
                boolean premium = line.charAt(30) == 'P';
                read++;

                double interest = 0;
                if (balance > 0) {
                    interest = Math.round(balance * rate * days / 365 * 100) / 100.0;
                } else if (balance < 0) {
                    interest = Math.round(balance * (rate + 0.05) * days / 365 * 100) / 100.0;
                }

                double fee = 0;
                if (!premium && balance < 1000.00) {
                    fee = Math.round((1000.00 - balance) * 0.0015 * 100) / 100.0;
                    if (fee > 25.00) {
                        fee = 25.00;
                    }
                }

                double newBalance = balance + interest - fee;
                String status = newBalance < 0 ? "OD" : fee > 0 ? "FE" : "OK";
                w.write(id + signed(interest, 7) + signed(fee, 5) + signed(newBalance, 9) + status);
                w.newLine();
                written++;
            }
        }
        System.out.printf("INTACCR READ=%07d WRITTEN=%07d%n", read, written);
    }

    private static String signed(double value, int integerDigits) {
        long cents = Math.round(Math.abs(value) * 100);
        return (value < 0 ? "-" : "+") + String.format("%0" + (integerDigits + 2) + "d", cents);
    }
}
