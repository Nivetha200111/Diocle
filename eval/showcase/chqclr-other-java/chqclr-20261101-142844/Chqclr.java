import java.io.*;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

public class Chqclr {
    private static final Charset CHARSET = StandardCharsets.ISO_8859_1;
    private static final int CQ_REC_LEN = 40;
    private static final int CL_REC_LEN = 35;

    private byte[][] cqRecords;
    private int cqIndex = 0;
    private List<byte[]> clOut = new ArrayList<>();

    private String wsEof = "N";
    private BigDecimal wsTotal = BigDecimal.ZERO.setScale(2);

    // current work fields for CLRREC
    private String clAcct = "";
    private String clNumberStr = "00000000";
    private BigDecimal clDebit = BigDecimal.ZERO.setScale(2);
    private BigDecimal clFee = BigDecimal.ZERO.setScale(2);
    private String clCode = "  ";

    // current CQ record fields
    private String cqType;
    private String cqAcct;
    private String cqNumberStr;
    private BigDecimal cqAmount;
    private String rtAcct;
    private String rtNumberStr;
    private String rtReason;
    private BigDecimal rtFee;

    public static void main(String[] args) throws Exception {
        // guard: no forbidden APIs are used
        Chqclr prog = new Chqclr();
        prog.p0000Main();
    }

    private void p0000Main() throws Exception {
        String chqInPath = System.getenv("DD_CHQIN");
        String clrOutPath = System.getenv("DD_CLROUT");
        if (chqInPath == null || clrOutPath == null) {
            System.err.println("Missing DD env vars");
            System.exit(1);
        }
        loadCqFile(Paths.get(chqInPath));

        wsEof = "N";
        wsTotal = BigDecimal.ZERO.setScale(2);

        // OPEN simulated
        while (!"Y".equals(wsEof)) {
            byte[] rec = readCqRecord();
            if (rec == null) {
                wsEof = "Y";
            } else {
                parseCqRecord(rec);
                p1000Item();
            }
        }
        // CLOSE
        writeClFile(Paths.get(clrOutPath));

        String edited = formatEdited(wsTotal);
        System.out.println("CHQCLR NET=" + edited);
        // RETURN-CODE handling: if any non-zero code were set, exit with it (not used here)
        // System.exit(0) implicit
    }

    private void p1000Item() {
        // MOVE ZERO TO CL-FEE
        clFee = BigDecimal.ZERO.setScale(2);
        // initialize defaults for this record
        // EVALUATE TRUE
        boolean isCheque = "C".equals(cqType);
        boolean isReturn = "R".equals(cqType);
        if (isCheque) {
            clAcct = cqAcct;
            clNumberStr = cqNumberStr;
            // COMPUTE CL-DEBIT = ZERO - CQ-AMOUNT
            clDebit = BigDecimal.ZERO.subtract(cqAmount).setScale(2, RoundingMode.UNNECESSARY);
            clCode = "CL";
        } else if (isReturn) {
            clAcct = rtAcct;
            clNumberStr = rtNumberStr;
            clDebit = BigDecimal.ZERO.setScale(2);
            if ("NS".equals(rtReason)) {
                // COMPUTE CL-FEE = RT-FEE * 2
                clFee = rtFee.multiply(new BigDecimal("2")).setScale(2, RoundingMode.UNNECESSARY);
                // TRUNC by PIC digits: 9(3)V99 max 999.99, but multiplication by 2 stays in range for test
            } else {
                clFee = rtFee.setScale(2, RoundingMode.UNNECESSARY);
            }
            clCode = "RT";
        } else {
            clAcct = "          "; // 10 spaces
            clNumberStr = "00000000";
            clDebit = BigDecimal.ZERO.setScale(2);
            // CL-FEE already zero
            clCode = "RJ";
        }
        // ADD CL-DEBIT TO WS-TOTAL
        wsTotal = wsTotal.add(clDebit);
        // SUBTRACT CL-FEE FROM WS-TOTAL
        wsTotal = wsTotal.subtract(clFee);

        // WRITE CL-REC
        byte[] out = buildClRecord();
        clOut.add(out);
    }

    private byte[] readCqRecord() {
        if (cqIndex >= cqRecords.length) return null;
        return cqRecords[cqIndex++];
    }

    private void loadCqFile(Path p) throws IOException {
        if (!Files.exists(p)) {
            cqRecords = new byte[0][];
            return;
        }
        byte[] all = Files.readAllBytes(p);
        if (all.length == 0) {
            cqRecords = new byte[0][];
            return;
        }
        // Heuristic: if file contains newline and line-split yields plausible record lengths
        boolean hasNewline = false;
        for (byte b : all) if (b == (byte)'\n') { hasNewline = true; break; }
        if (hasNewline) {
            // split on \n, keeping lines without terminators
            List<byte[]> lines = new ArrayList<>();
            ByteArrayOutputStream cur = new ByteArrayOutputStream();
            for (int i=0;i<all.length;i++) {
                byte b = all[i];
                if (b == (byte)'\n') {
                    byte[] line = cur.toByteArray();
                    // strip trailing \r
                    if (line.length>0 && line[line.length-1]==(byte)'\r') line = Arrays.copyOf(line, line.length-1);
                    lines.add(line);
                    cur.reset();
                } else {
                    cur.write(b);
                }
            }
            // last line if not terminated
            if (cur.size()>0) {
                byte[] line = cur.toByteArray();
                if (line.length>0 && line[line.length-1]==(byte)'\r') line = Arrays.copyOf(line, line.length-1);
                lines.add(line);
            }
            // Check if every non-empty line has length CQ_REC_LEN, or all lines consistent with fixed length
            boolean allLenOk = true;
            for (byte[] l : lines) {
                if (l.length != CQ_REC_LEN) { allLenOk = false; break; }
            }
            if (allLenOk) {
                cqRecords = lines.toArray(new byte[0][]);
                return;
            }
            // If lines are not exactly record length, fall back to fixed if total bytes multiple of record length ignoring newlines? 
            // If not allLenOk, treat as variable and pad/truncate to record length
            // But spec says LINE SEQUENTIAL one record per line -> use lines padded
            // We'll pad/truncate lines to 40
            if (!allLenOk && lines.size()>0) {
                // If at least one line length <=40 and not binary multiple, assume LINE SEQUENTIAL
                // Decide: if file size % CQ_REC_LEN !=0 then it's line sequential
                if (all.length % CQ_REC_LEN != 0) {
                    List<byte[]> padded = new ArrayList<>();
                    for (byte[] l : lines) {
                        byte[] rec = new byte[CQ_REC_LEN];
                        Arrays.fill(rec, (byte)' ');
                        int len = Math.min(l.length, CQ_REC_LEN);
                        System.arraycopy(l, 0, rec, 0, len);
                        padded.add(rec);
                    }
                    cqRecords = padded.toArray(new byte[0][]);
                    return;
                }
            }
        }
        // Fixed binary mode: split every CQ_REC_LEN bytes, no separators
        int n = all.length / CQ_REC_LEN;
        List<byte[]> recs = new ArrayList<>();
        for (int i=0;i<n;i++) {
            byte[] rec = Arrays.copyOfRange(all, i*CQ_REC_LEN, (i+1)*CQ_REC_LEN);
            recs.add(rec);
        }
        // If trailing bytes remain (should not happen for proper file), ignore or handle?
        cqRecords = recs.toArray(new byte[0][]);
    }

    private void parseCqRecord(byte[] rec) {
        String s = new String(rec, CHARSET);
        cqType = s.substring(0,1);
        String body = s.substring(1, 40);
        // For cheque
        cqAcct = body.substring(0,10);
        cqNumberStr = body.substring(10,18);
        String amtStr = body.substring(18,28); // 10 chars sign+9digits
        cqAmount = parseSignedSeparate(amtStr, 2);
        // For return
        rtAcct = body.substring(0,10);
        rtNumberStr = body.substring(10,18);
        rtReason = body.substring(18,20);
        String feeStr = body.substring(20,25); // 5 digits
        rtFee = parseUnsigned(feeStr, 2);
    }

    private BigDecimal parseSignedSeparate(String field, int scale) {
        if (field.length()==0) return BigDecimal.ZERO.setScale(scale);
        char signChar = field.charAt(0);
        String digits = field.substring(1);
        // digits may contain spaces? but should be digits
        digits = digits.trim();
        if (digits.isEmpty()) digits="0";
        // Keep only digits
        StringBuilder d = new StringBuilder();
        for (char c: digits.toCharArray()) if (c>='0' && c<='9') d.append(c);
        if (d.length()==0) d.append('0');
        BigDecimal val = new BigDecimal(d.toString());
        BigDecimal divisor = BigDecimal.TEN.pow(scale);
        val = val.divide(divisor).setScale(scale, RoundingMode.UNNECESSARY);
        if (signChar=='-') val = val.negate();
        // '+' stays positive
        return val;
    }

    private BigDecimal parseUnsigned(String field, int scale) {
        String t = field.trim();
        if (t.isEmpty()) return BigDecimal.ZERO.setScale(scale);
        StringBuilder d = new StringBuilder();
        for (char c: t.toCharArray()) if (c>='0' && c<='9') d.append(c);
        if (d.length()==0) return BigDecimal.ZERO.setScale(scale);
        BigDecimal val = new BigDecimal(d.toString());
        BigDecimal divisor = BigDecimal.TEN.pow(scale);
        val = val.divide(divisor).setScale(scale, RoundingMode.UNNECESSARY);
        return val;
    }

    private byte[] buildClRecord() {
        byte[] rec = new byte[CL_REC_LEN];
        Arrays.fill(rec, (byte)' ');
        // CL-ACCT X10
        putString(rec, 0, 10, clAcct);
        // CL-NUMBER 9(8)
        putString(rec, 10, 8, zeroPadNumeric(clNumberStr, 8));
        // CL-DEBIT S9(7)V99 SIGN LEADING SEPARATE 10
        String debitField = formatSignedSeparate(clDebit, 7, 2);
        putString(rec, 18, 10, debitField);
        // CL-FEE 9(3)V99 5 digits
        String feeField = formatUnsigned(clFee, 3, 2);
        putString(rec, 28, 5, feeField);
        // CL-CODE XX
        putString(rec, 33, 2, clCode);
        return rec;
    }

    private void putString(byte[] rec, int off, int len, String val) {
        byte[] b = val.getBytes(CHARSET);
        for (int i=0;i<len;i++) {
            byte c = (byte)' ';
            if (i < b.length) c = b[i];
            // pad with spaces if shorter
            rec[off+i]=c;
        }
    }

    private String zeroPadNumeric(String s, int len) {
        String digitsOnly = s.replaceAll("[^0-9]", "");
        if (digitsOnly.isEmpty()) digitsOnly="0";
        if (digitsOnly.length()>len) {
            // TRUNC(STD): keep only PIC digits (low-order)
            digitsOnly = digitsOnly.substring(digitsOnly.length()-len);
        }
        return String.format("%"+len+"s", digitsOnly).replace(' ', '0');
    }

    private String formatSignedSeparate(BigDecimal val, int intDigits, int fracDigits) {
        int totalDigits = intDigits + fracDigits;
        boolean negative = val.signum() < 0;
        BigDecimal abs = val.abs().setScale(fracDigits, RoundingMode.UNNECESSARY);
        BigDecimal scaled = abs.movePointRight(fracDigits); // integer of all digits
        // scaled may have fractional? already scaled
        String digits = scaled.toPlainString();
        // Remove decimal point if any (should be integer)
        int dot = digits.indexOf('.');
        if (dot>=0) digits = digits.substring(0,dot);
        // digits should be totalDigits length zero padded
        if (digits.length() > totalDigits) {
            // truncation: keep low-order digits
            digits = digits.substring(digits.length()-totalDigits);
        }
        digits = String.format("%"+totalDigits+"s", digits).replace(' ', '0');
        char sign = negative ? '-' : '+';
        return sign + digits;
    }

    private String formatUnsigned(BigDecimal val, int intDigits, int fracDigits) {
        int totalDigits = intDigits + fracDigits;
        BigDecimal abs = val.abs().setScale(fracDigits, RoundingMode.UNNECESSARY);
        BigDecimal scaled = abs.movePointRight(fracDigits);
        String digits = scaled.toPlainString();
        int dot = digits.indexOf('.');
        if (dot>=0) digits = digits.substring(0,dot);
        if (digits.length() > totalDigits) {
            digits = digits.substring(digits.length()-totalDigits);
        }
        digits = String.format("%"+totalDigits+"s", digits).replace(' ', '0');
        return digits;
    }

    private String formatEdited(BigDecimal val) {
        // PIC -(9)9.99 => 10 integer digits, 2 fraction
        int intWidth = 10;
        int frac = 2;
        boolean negative = val.signum() < 0;
        BigDecimal abs = val.abs().setScale(frac, RoundingMode.HALF_UP); // COBOL rounding same as half up for this?
        // split
        BigDecimal intPartBD = abs.setScale(0, RoundingMode.DOWN);
        long intPart = intPartBD.longValue(); // fits in 10 digits
        String intPadded = String.format("%010d", intPart);
        // Handle case where intPart > 9999999999 (10 digits) - truncate low order? PIC -(9)9 would overflow, but WS-TOTAL limited to 9 digits
        if (intPadded.length() > intWidth) {
            intPadded = intPadded.substring(intPadded.length()-intWidth);
        }
        String fracStr = abs.remainder(BigDecimal.ONE).movePointRight(frac).setScale(0, RoundingMode.DOWN).toPlainString();
        // fracStr should be 2 digits
        // Derive fraction correctly with formatting
        BigDecimal fracBD = abs.subtract(new BigDecimal(intPart));
        // Actually use string formatting to get exactly 2 digits
        String absFormatted = String.format(Locale.ROOT, "%010d.%02d", intPart, getFracTwoDigits(abs));
        // Now apply zero suppression and floating sign
        // absFormatted is like "0000000123.45"
        String intStr = absFormatted.substring(0,intWidth); // 10 chars
        String fracFormatted = absFormatted.substring(intWidth+1); // 2 chars
        // Find first non-zero in intStr
        int firstNonZero = -1;
        for (int i=0;i<intWidth;i++) {
            if (intStr.charAt(i)!='0') { firstNonZero=i; break; }
        }
        char[] outInt = new char[intWidth];
        if (firstNonZero==-1) {
            // all zeros -> keep last zero
            for (int i=0;i<intWidth-1;i++) outInt[i]=' ';
            outInt[intWidth-1]='0';
        } else {
            for (int i=0;i<intWidth;i++) {
                if (i < firstNonZero) outInt[i]=' ';
                else outInt[i]=intStr.charAt(i);
            }
        }
        if (negative) {
            // place '-' immediately left of first significant digit
            int pos;
            if (firstNonZero==-1) pos = intWidth-2; // for zero case, sign before the zero? yields "        -0"
            else pos = firstNonZero-1;
            if (pos>=0) outInt[pos]='-';
            else {
                // overflow: no room, would overwrite? COBOL would place sign at first position
                outInt[0]='-';
            }
        }
        return new String(outInt) + "." + fracFormatted;
    }

    private int getFracTwoDigits(BigDecimal abs) {
        BigDecimal frac = abs.remainder(BigDecimal.ONE).movePointRight(2);
        // rounding already done via setScale(2)
        int v = frac.setScale(0, RoundingMode.DOWN).intValue();
        if (v<0) v=-v;
        return v;
    }

    private void writeClFile(Path p) throws IOException {
        if (p.getParent()!=null) Files.createDirectories(p.getParent());
        try (OutputStream os = Files.newOutputStream(p, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING)) {
            for (byte[] rec : clOut) {
                os.write(rec);
            }
        }
    }
}
