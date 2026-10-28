// SYNTHETIC SAMPLE - written for the Diocle hackathon project. Fictional company; not derived from any real system.
// HAND-WRITTEN TEST FIXTURE, NOT MODEL OUTPUT.
// A typical naive port of src/PKDPOST.cbl with the packed-data mistakes migrations really make:
// the packed decoder drops the sign nibble, COMP is read little-endian (as if COMP-5), the overpunch
// table is the EBCDIC one, the P-scaled limit misses its x100, and arithmetic uses double + Math.round.
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class PkdPost {
    public static void main(String[] args) throws Exception {
        byte[] in = Files.readAllBytes(Path.of(System.getenv("DD_PKIN")));
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        int read = 0;
        for (int off = 0; off + 33 <= in.length; off += 33) {
            read++;
            double bal = unpack(in, off + 10, 6) / 100.0;
            double rate = unpack(in, off + 16, 3) / 10000.0;
            int days = (in[off + 19] & 0xFF) | (in[off + 20] << 8);
            double adj = overpunch(new String(in, off + 21, 7, StandardCharsets.ISO_8859_1)) / 100.0;
            double limit = Integer.parseInt(new String(in, off + 28, 3, StandardCharsets.ISO_8859_1));
            int items = (in[off + 31] & 0xFF) | (in[off + 32] << 8);

            double interest = Math.round(bal * rate * days / 365 * 100) / 100.0;
            double newBal = bal + interest + adj;
            out.write(in, off, 10);
            out.write(pack(Math.round(interest * 100), 5));
            out.write(pack(Math.round(newBal * 100), 6));
            long head = Math.round((limit - newBal) * 100);
            out.write((String.format("%09d", Math.abs(head)) + (head < 0 ? "-" : "+")).getBytes(StandardCharsets.ISO_8859_1));
            int units = items * 1000;
            out.write(new byte[] {(byte) (units >> 24), (byte) (units >> 16), (byte) (units >> 8), (byte) units});
            long rev = Math.round(-adj * 100);
            String s = String.format("%07d", Math.abs(rev));
            out.write((s.substring(0, 6) + (rev < 0 ? "}JKLMNOPQR".charAt(s.charAt(6) - '0') : s.charAt(6)))
                    .getBytes(StandardCharsets.ISO_8859_1));
        }
        Files.write(Path.of(System.getenv("DD_PKOUT")), out.toByteArray());
        System.out.println("PKDPOST READ=" + String.format("%07d", read));
    }

    static long unpack(byte[] b, int off, int len) {
        long v = 0;
        for (int i = 0; i < len; i++) {
            v = v * 10 + ((b[off + i] & 0xFF) >> 4);
            if (i < len - 1) v = v * 10 + (b[off + i] & 0x0F);
        }
        return v;  // sign nibble ignored
    }

    static byte[] pack(long cents, int len) {
        String d = String.format("%0" + (len * 2 - 1) + "d", Math.abs(cents));
        byte[] out = new byte[len];
        for (int i = 0; i < len; i++) {
            int hi = d.charAt(2 * i) - '0';
            int lo = 2 * i + 1 < d.length() ? d.charAt(2 * i + 1) - '0' : (cents < 0 ? 0xD : 0xC);
            out[i] = (byte) ((hi << 4) | lo);
        }
        return out;
    }

    static long overpunch(String s) {
        char last = s.charAt(s.length() - 1);
        int neg = "}JKLMNOPQR".indexOf(last);
        if (neg >= 0) return -Long.parseLong(s.substring(0, s.length() - 1) + neg);
        int pos = "{ABCDEFGHI".indexOf(last);
        if (pos >= 0) return Long.parseLong(s.substring(0, s.length() - 1) + pos);
        return Long.parseLong(s.replaceAll("[^0-9]", "0"));
    }
}
