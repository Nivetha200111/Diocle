import java.io.BufferedWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

/**
 * Hand-written Java port of CUSTUPD (a test fixture, not model output) on DioKsds, the verifier's keyed-file support
 * class. Amounts are kept as whole units of 0.01 in a long; the record is the 38-byte CUST-REC as a latin-1 String.
 */
public class Custupd {
    static final long LIMIT9 = 1_000_000_000L;      // PIC S9(7)V99: nine digits
    static final long LIMIT11 = 100_000_000_000L;   // PIC S9(9)V99: eleven digits

    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(System.getenv("DD_TRANIN")), StandardCharsets.ISO_8859_1);
        DioKsds cust = DioKsds.select("CUSTMAST", 38, 2, 6, "DYNAMIC");
        cust.open("I-O");
        if (!cust.status().equals("00")) {
            System.out.println("CUSTMAST OPEN FAILED " + cust.status());
            System.out.flush();
            System.exit(12);
        }
        try (BufferedWriter rej = Files.newBufferedWriter(Path.of(System.getenv("DD_REJOUT")), StandardCharsets.ISO_8859_1)) {
            for (String raw : lines) {
                String line = (raw + " ".repeat(36)).substring(0, 36);
                char code = line.charAt(0);
                String id = line.substring(1, 7), name = line.substring(7, 27);
                long amount = overpunch(line.substring(27, 36));
                if (code == 'A') {
                    cust.write("AA" + id + name + display(amount) + "N");
                    if (cust.status().equals("22")) reject(rej, id, code, "DUPLICATE   ", cust.status());
                    else if (!cust.status().equals("00")) reject(rej, id, code, "WRITE ERROR ", cust.status());
                } else if (code == 'C') {
                    cust.read(id);
                    if (cust.status().equals("23")) {
                        reject(rej, id, code, "NOT FOUND   ", cust.status());
                    } else if (!cust.status().equals("00")) {
                        reject(rej, id, code, "READ ERROR  ", cust.status());
                    } else {
                        String r = cust.record();
                        long balance = trunc(overpunch(r.substring(28, 37)) + amount, LIMIT9);
                        cust.rewrite(r.substring(0, 8) + name + display(balance) + "C");
                        if (!cust.status().equals("00")) reject(rej, id, code, "REWRITE ERR ", cust.status());
                    }
                } else if (code == 'D') {
                    cust.delete(id);
                    if (cust.status().equals("23")) reject(rej, id, code, "NOT FOUND   ", cust.status());
                    else if (!cust.status().equals("00")) reject(rej, id, code, "DELETE ERROR", cust.status());
                } else {
                    reject(rej, id, code, "BAD CODE    ", cust.status());
                }
            }
            cust.start(">=", "999999");
            if (cust.status().equals("23")) {
                rej.write("SUMARY" + " ".repeat(6) + " " + "NO RECORDS  " + cust.status() + "\n");
            }
            if (cust.status().equals("00")) {
                long count = 0, total = 0;
                do {
                    cust.readNext();
                    if (cust.status().equals("00")) {
                        count++;
                        total = trunc(total + overpunch(cust.record().substring(28, 37)), LIMIT11);
                    }
                } while (cust.status().equals("00"));
                String edited = (total < 0 ? "-" : " ") + String.format("%09d", Math.abs(total) / 100) + "." + String.format("%02d", Math.abs(total) % 100);
                rej.write("SUMARY" + String.format("%05d", count % 100000) + " " + " " + edited.substring(0, 12) + cust.status() + "\n");
            }
        }
        cust.close();
    }

    static void reject(BufferedWriter out, String id, char code, String reason, String status) throws java.io.IOException {
        out.write("REJECT" + id + code + reason + status + "\n");
    }

    /** ADD / COMPUTE without ON SIZE ERROR: the high-order digits are lost, the sign stays. */
    static long trunc(long v, long limit) {
        long m = Math.abs(v) % limit;
        return v < 0 ? -m : m;
    }

    /** PIC S9(7)V99, sign in the last digit: a negative digit d is written as chr('p' + d). */
    static String display(long v) {
        String digits = String.format("%09d", Math.abs(v));
        char last = digits.charAt(8);
        return digits.substring(0, 8) + (v < 0 ? (char) (last + 0x40) : last);
    }

    static long overpunch(String text) {
        char last = text.charAt(text.length() - 1);
        boolean negative = last >= 'p' && last <= 'y';
        long v = Long.parseLong(text.substring(0, text.length() - 1) + (negative ? (char) (last - 0x40) : last));
        return negative ? -v : v;
    }
}
