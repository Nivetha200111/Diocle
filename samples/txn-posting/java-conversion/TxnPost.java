// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A typical naive line-by-line translation of src/TXNPOST.cbl, used to
// exercise Diocle's "bring your own conversion" verification mode.
// It intentionally uses double arithmetic and Math.round, the way many
// quick ports do. Diocle's verifier is expected to find where it diverges.
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class TxnPost {
    public static void main(String[] args) throws IOException {
        Path in = Path.of(System.getenv("DD_TXNIN"));
        Path out = Path.of(System.getenv("DD_POSTOUT"));
        int posted = 0;
        int rejected = 0;
        try (BufferedWriter w = Files.newBufferedWriter(out)) {
            for (String line : Files.readAllLines(in)) {
                line = String.format("%-37s", line);
                String id = line.substring(0, 9);
                char type = line.charAt(9);
                double amount = Double.parseDouble(line.substring(10, 20)) / 100.0;
                double balance = Double.parseDouble(line.substring(20, 32)) / 100.0;
                int odLimit = Integer.parseInt(line.substring(32, 37));

                double charge = 0;
                double newBalance = balance;
                String status;
                if (type == 'P') {
                    if (amount <= 0) {
                        status = "RJ";
                    } else {
                        charge = Math.round(amount * 0.0125 * 100) / 100.0;
                        if (charge > 15.00) {
                            charge = 15.00;
                        }
                        newBalance = balance - amount - charge;
                        if (newBalance <= -odLimit) {
                            newBalance = balance;
                            charge = 0;
                            status = "NS";
                        } else {
                            status = "OK";
                        }
                    }
                } else if (type == 'F') {
                    newBalance = balance - amount;
                    status = "FE";
                } else if (type == 'I') {
                    newBalance = balance + Math.round(amount / 12 * 100) / 100.0;
                    status = "IC";
                } else {
                    status = "RJ";
                }
                if (status.equals("RJ") || status.equals("NS")) {
                    rejected++;
                } else {
                    posted++;
                }
                w.write(id + signed(charge, 3) + signed(newBalance, 9) + status);
                w.newLine();
            }
        }
        System.out.printf("TXNPOST POSTED=%07d REJECTED=%07d%n", posted, rejected);
    }

    private static String signed(double value, int integerDigits) {
        long cents = Math.round(Math.abs(value) * 100);
        return (value < 0 ? "-" : "+") + String.format("%0" + (integerDigits + 2) + "d", cents);
    }
}
