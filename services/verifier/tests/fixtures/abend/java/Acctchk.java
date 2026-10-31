// SYNTHETIC test fixture for Diocle's CEE3ABD stand-in: a hand-written port of ACCTCHK.cbl, not model output.
// CALL 'CEE3ABD' is translated as the stand-in behaves: flush stdout, close open files (records written so far stay),
// "CEE3ABD abend code <n>" on stderr, exit code 16.
import java.io.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class Acctchk {
    private static BufferedReader in;
    private static Writer out;
    private static int count;

    public static void main(String[] args) throws IOException {
        main0000();
    }

    private static void main0000() throws IOException {
        Path inPath = Path.of(System.getenv("DD_ACCTIN"));
        if (!Files.isRegularFile(inPath)) {
            System.out.println("ACCTIN OPEN FAILED 35");
            abend9999(101);
        }
        in = Files.newBufferedReader(inPath, StandardCharsets.ISO_8859_1);
        out = Files.newBufferedWriter(Path.of(System.getenv("DD_ACCTOUT")), StandardCharsets.ISO_8859_1);
        String line;
        while ((line = in.readLine()) != null) {
            check1000(line);
        }
        System.out.println("ACCOUNTS CHECKED " + String.format("%05d", count));
        in.close();
        out.close();
    }

    private static void check1000(String line) throws IOException {
        String rec = (line + " ".repeat(17)).substring(0, 17);
        String id = rec.substring(0, 6);
        if (id.isBlank()) {
            System.out.println("BLANK ACCOUNT ID AFTER " + String.format("%05d", count));
            abend9999(999);
        }
        count = (count + 1) % 100000;
        BigDecimal bal = new BigDecimal(rec.substring(8, 17)).movePointLeft(2);
        if (rec.charAt(7) == '-') bal = bal.negate();
        String flag = bal.signum() < 0 ? "N" : rec.charAt(6) == 'S' ? "S" : "Y";
        String digits = bal.abs().movePointRight(2).toBigInteger().toString();
        out.write(id + flag + (bal.signum() < 0 ? "-" : "+") + "0".repeat(9 - digits.length()) + digits + "\n");
    }

    private static void abend9999(int code) throws IOException {
        System.out.println("ABENDING PROGRAM");
        cee3abd(code);
    }

    private static void cee3abd(int code) throws IOException {
        System.out.flush();
        if (in != null) in.close();
        if (out != null) out.close();
        System.err.println("CEE3ABD abend code " + code);
        System.exit(16);
    }
}
