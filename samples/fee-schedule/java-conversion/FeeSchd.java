// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A typical naive line-by-line translation of src/FEESCHD.cbl, used to
// exercise Diocle's "bring your own conversion" verification mode.
// It intentionally uses double arithmetic and Math.round, the way many
// quick ports do. Diocle's verifier is expected to find where it diverges.
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class FeeSchd {
    public static void main(String[] args) throws IOException {
        Path in = Path.of(System.getenv("DD_FEEIN"));
        Path out = Path.of(System.getenv("DD_CHGOUT"));
        int read = 0;
        int capped = 0;
        try (BufferedWriter w = Files.newBufferedWriter(out)) {
            for (String line : Files.readAllLines(in)) {
                line = String.format("%-29s", line);
                String id = line.substring(0, 10);
                char product = line.charAt(10);
                double avgBalance = Double.parseDouble(line.substring(11, 23)) / 100.0;
                int txnCount = Integer.parseInt(line.substring(23, 27));
                int monthDays = Integer.parseInt(line.substring(27, 29));
                read++;
                String code = "OK";

                double base;
                int freeTxns;
                if (product == 'A') {
                    base = 6.00;
                    freeTxns = 10;
                } else if (product == 'B') {
                    base = 3.50;
                    freeTxns = 25;
                } else {
                    base = 0;
                    freeTxns = 9999;
                }
                if (avgBalance > 5000.00 && base > 0) {
                    base = 0;
                    code = "WV";
                }

                int excess = txnCount - freeTxns;
                double txnFee = excess > 0 ? excess * 0.35 : 0;

                double odInterest = 0;
                if (avgBalance < 0) {
                    odInterest = Math.round(-avgBalance * 0.1899 * monthDays / 365 * 100) / 100.0;
                }

                double total = base + txnFee + odInterest;
                if (product != 'C' && total > 40.00) {
                    total = 40.00;
                    code = "CP";
                    capped++;
                }
                w.write(id + signed(base, 3) + signed(txnFee, 3) + signed(odInterest, 5) + signed(total, 3) + code);
                w.newLine();
            }
        }
        System.out.printf("FEESCHD ACCOUNTS=%07d CAPPED=%07d%n", read, capped);
    }

    private static String signed(double value, int integerDigits) {
        long cents = Math.round(Math.abs(value) * 100);
        return (value < 0 ? "-" : "+") + String.format("%0" + (integerDigits + 2) + "d", cents);
    }
}
