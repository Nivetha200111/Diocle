import java.io.BufferedReader;
import java.io.ByteArrayInputStream;
import java.io.InputStreamReader;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class Chqclr {
    private BigDecimal wsTotal = BigDecimal.ZERO;
    private String clAcct = "          ";
    private String clNumberStr = "00000000";
    private BigDecimal clDebit = BigDecimal.ZERO;
    private BigDecimal clFee = BigDecimal.ZERO;
    private String clCode = "  ";

    private String curRaw = "";
    private char curType = ' ';
    private String curAcct = "";
    private String curNumberRaw = "";
    private String curAmountRaw = "";
    private String curReason = "";
    private String curFeeRaw = "";

    private List<String> inRecords = new ArrayList<>();
    private List<String> outRecords = new ArrayList<>();
    private boolean inHasNewline = false;

    public static void main(String[] args) throws Exception {
        new Chqclr().m0000Main();
    }

    private void m0000Main() throws Exception {
        String inPath = System.getenv("DD_CHQIN");
        String outPath = System.getenv("DD_CLROUT");
        String coll = System.getenv("DIOCLE_COLLATION");
        String clk = System.getenv("DIOCLE_CLOCK");
        if (coll == null) coll = "";
        if (clk == null) clk = "";
        inRecords = new ArrayList<>();
        outRecords = new ArrayList<>();
        wsTotal = BigDecimal.ZERO;
        inHasNewline = false;
        if (inPath != null && !inPath.isEmpty()) {
            Path p = Paths.get(inPath);
            if (Files.exists(p)) {
                byte[] all = Files.readAllBytes(p);
                for (byte b : all) {
                    if (b == (byte) '\n') { inHasNewline = true; break; }
                }
                if (inHasNewline) {
                    BufferedReader br = new BufferedReader(new InputStreamReader(new ByteArrayInputStream(all), StandardCharsets.ISO_8859_1));
                    String line;
                    while ((line = br.readLine()) != null) {
                        if (line.length() < 40) line = line + " ".repeat(40 - line.length());
                        else if (line.length() > 40) line = line.substring(0, 40);
                        inRecords.add(line);
                    }
                } else {
                    int n = all.length;
                    if (n == 0) { }
                    else {
                        for (int i = 0; i < n; i += 40) {
                            int len = Math.min(40, n - i);
                            String chunk = new String(all, i, len, StandardCharsets.ISO_8859_1);
                            if (chunk.length() < 40) chunk = chunk + " ".repeat(40 - chunk.length());
                            inRecords.add(chunk);
                        }
                    }
                }
            }
        }
        for (String rec : inRecords) {
            curRaw = rec;
            curType = rec.charAt(0);
            curAcct = rec.substring(1, 11);
            curNumberRaw = rec.substring(11, 19);
            curAmountRaw = rec.substring(19, 29);
            curReason = rec.substring(19, 21);
            curFeeRaw = rec.substring(21, 26);
            m1000Item();
        }
        if (outPath != null && !outPath.isEmpty()) {
            Path op = Paths.get(outPath);
            Path parent = op.getParent();
            if (parent != null) Files.createDirectories(parent);
            StringBuilder sb = new StringBuilder();
            if (inHasNewline) {
                for (String r : outRecords) sb.append(r).append('\n');
            } else {
                for (String r : outRecords) sb.append(r);
            }
            Files.write(op, sb.toString().getBytes(StandardCharsets.ISO_8859_1));
        }
        String edited = formatFloatingMinus(wsTotal, 10, 2);
        System.out.print("CHQCLR NET=" + edited + "\n");
        System.out.flush();
    }

    private void m1000Item() {
        clFee = BigDecimal.ZERO;
        boolean isCheque = (curType == 'C');
        boolean isReturn = (curType == 'R');
        if (isCheque) {
            clAcct = curAcct;
            clNumberStr = curNumberRaw;
            BigDecimal cqAmount = parseSignedSeparate(curAmountRaw);
            BigDecimal v = BigDecimal.ZERO.subtract(cqAmount);
            clDebit = truncSigned(v, 7, 2);
            clCode = "CL";
        } else if (isReturn) {
            clAcct = curAcct;
            clNumberStr = curNumberRaw;
            clDebit = BigDecimal.ZERO;
            BigDecimal rtFee = parseUnsigned(curFeeRaw, 2);
            boolean isNsf = curReason.equals("NS");
            if (isNsf) {
                BigDecimal doubled = rtFee.multiply(new BigDecimal(2));
                clFee = truncUnsigned(doubled, 3, 2);
            } else {
                clFee = truncUnsigned(rtFee, 3, 2);
            }
            clCode = "RT";
        } else {
            clAcct = "          ";
            clNumberStr = "00000000";
            clDebit = BigDecimal.ZERO;
            clCode = "RJ";
        }
        wsTotal = truncSigned(wsTotal.add(clDebit), 9, 2);
        wsTotal = truncSigned(wsTotal.subtract(clFee), 9, 2);
        String debitStr = formatSignedSeparate(clDebit, 7, 2);
        String feeStr = formatUnsigned(clFee, 3, 2);
        String rec = clAcct + clNumberStr + debitStr + feeStr + clCode;
        outRecords.add(rec);
    }

    private static BigDecimal parseSignedSeparate(String s) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO;
        boolean neg = s.charAt(0) == '-';
        String d = s.length() > 1 ? s.substring(1) : "0";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < d.length(); i++) {
            char c = d.charAt(i);
            if (c >= '0' && c <= '9') sb.append(c);
            else sb.append('0');
        }
        if (sb.length() == 0) sb.append('0');
        BigDecimal cents = new BigDecimal(sb.toString());
        BigDecimal v = cents.movePointLeft(2);
        return neg ? v.negate() : v;
    }

    private static BigDecimal parseUnsigned(String s, int frac) {
        if (s == null || s.isEmpty()) return BigDecimal.ZERO;
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c >= '0' && c <= '9') sb.append(c);
            else if (c == ' ' || c == '+') continue;
            else if (c == '-') continue;
            else sb.append('0');
        }
        String t = sb.toString().trim();
        if (t.isEmpty()) t = "0";
        BigDecimal cents = new BigDecimal(t);
        return cents.movePointLeft(frac);
    }

    private static BigDecimal truncSigned(BigDecimal v, int intD, int fracD) {
        int total = intD + fracD;
        BigDecimal centsBD = v.movePointRight(fracD).setScale(0, RoundingMode.DOWN);
        BigInteger cents = centsBD.toBigInteger();
        BigInteger mod = BigInteger.TEN.pow(total);
        boolean neg = cents.signum() < 0;
        BigInteger absMod = cents.abs().mod(mod);
        if (absMod.equals(BigInteger.ZERO)) return BigDecimal.ZERO.movePointLeft(fracD).setScale(fracD);
        BigInteger nc = neg ? absMod.negate() : absMod;
        return new BigDecimal(nc).movePointLeft(fracD);
    }

    private static BigDecimal truncUnsigned(BigDecimal v, int intD, int fracD) {
        int total = intD + fracD;
        BigDecimal centsBD = v.movePointRight(fracD).setScale(0, RoundingMode.DOWN);
        BigInteger cents = centsBD.toBigInteger();
        BigInteger mod = BigInteger.TEN.pow(total);
        BigInteger t = cents.mod(mod);
        return new BigDecimal(t).movePointLeft(fracD);
    }

    private static String formatSignedSeparate(BigDecimal v, int intD, int fracD) {
        int total = intD + fracD;
        BigDecimal centsBD = v.movePointRight(fracD).setScale(0, RoundingMode.DOWN);
        BigInteger cents = centsBD.toBigInteger();
        BigInteger mod = BigInteger.TEN.pow(total);
        boolean neg = cents.signum() < 0;
        BigInteger abs = cents.abs().mod(mod);
        if (abs.equals(BigInteger.ZERO)) neg = false;
        String digits = abs.toString();
        while (digits.length() < total) digits = "0" + digits;
        return (neg ? "-" : "+") + digits;
    }

    private static String formatUnsigned(BigDecimal v, int intD, int fracD) {
        int total = intD + fracD;
        BigDecimal centsBD = v.movePointRight(fracD).setScale(0, RoundingMode.DOWN);
        BigInteger cents = centsBD.toBigInteger();
        BigInteger mod = BigInteger.TEN.pow(total);
        BigInteger t = cents.mod(mod);
        String digits = t.toString();
        while (digits.length() < total) digits = "0" + digits;
        return digits;
    }

    private static String formatFloatingMinus(BigDecimal v, int intD, int fracD) {
        boolean neg = v.signum() < 0;
        BigDecimal abs = v.abs();
        BigDecimal centsBD = abs.movePointRight(fracD).setScale(0, RoundingMode.DOWN);
        BigInteger cents = centsBD.toBigInteger();
        BigInteger modAll = BigInteger.TEN.pow(intD + fracD);
        cents = cents.mod(modAll);
        String all = cents.toString();
        while (all.length() < intD + fracD) all = "0" + all;
        String intPart = all.substring(0, intD);
        String fracPart = all.substring(intD);
        char[] out = new char[intD];
        int first = -1;
        for (int i = 0; i < intD; i++) {
            if (intPart.charAt(i) != '0') { first = i; break; }
        }
        if (first == -1) {
            for (int i = 0; i < intD - 1; i++) out[i] = ' ';
            out[intD - 1] = '0';
            if (neg) {
                boolean nonZeroFrac = false;
                for (int i = 0; i < fracPart.length(); i++) if (fracPart.charAt(i) != '0') nonZeroFrac = true;
                if (nonZeroFrac) out[intD - 2] = '-';
                else {
                    boolean isZero = cents.equals(BigInteger.ZERO);
                    if (!isZero) out[intD - 2] = '-';
                }
            }
        } else {
            for (int i = 0; i < first; i++) out[i] = ' ';
            for (int i = first; i < intD; i++) out[i] = intPart.charAt(i);
            if (neg) {
                if (first > 0) out[first - 1] = '-';
            }
        }
        return new String(out) + "." + fracPart;
    }
}
