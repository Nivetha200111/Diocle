// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A typical naive line-by-line translation of src/DAYCTRL.cbl, used to
// exercise Diocle's "bring your own conversion" verification mode.
// It intentionally uses double arithmetic and Math.round, the way many
// quick ports do. Diocle's verifier is expected to find where it diverges.
import java.io.BufferedWriter;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

public class DayCtrl {
    public static void main(String[] args) throws IOException {
        Path in = Path.of(System.getenv("DD_DAYIN"));
        Path out = Path.of(System.getenv("DD_CTLOUT"));
        int read = 0;
        int lost = 0;
        double controlTotal = 0;
        try (BufferedWriter w = Files.newBufferedWriter(out)) {
            for (String line : Files.readAllLines(in)) {
                line = String.format("%-30s", line);
                String id = line.substring(0, 10);
                double principal = Double.parseDouble(line.substring(10, 22)) / 100.0;
                double rate = Integer.parseInt(line.substring(22, 27)) / 10000.0;
                int days = Integer.parseInt(line.substring(27, 30));
                read++;

                double exact = principal * rate * days / 365;
                double interest = Math.round(exact * 100) / 100.0;
                controlTotal += exact;
                char flag = '-';
                if (interest == 0 && principal != 0 && rate != 0 && days != 0) {
                    flag = 'Z';
                    lost++;
                }
                w.write(id + signed(interest, 7) + signed(controlTotal, 11) + flag);
                w.newLine();
            }
        }
        System.out.printf("DAYCTRL ACCOUNTS=%07d LOST=%07d CONTROL=%.2f%n", read, lost, controlTotal);
    }

    private static String signed(double value, int integerDigits) {
        long cents = Math.round(Math.abs(value) * 100);
        return (value < 0 ? "-" : "+") + String.format("%0" + (integerDigits + 2) + "d", cents);
    }
}
