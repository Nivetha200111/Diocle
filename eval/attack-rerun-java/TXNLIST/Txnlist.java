import java.io.IOException;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;

public class Txnlist {
    private static String wsTxnStatus = "00";
    private static boolean endOfTxns = false;
    private static String txnId = "      ";
    private static char txnType = ' ';
    private static BigDecimal txnAmount = new BigDecimal(BigInteger.ZERO, 2);
    private static BigDecimal wsCredits = new BigDecimal(BigInteger.ZERO, 2);
    private static BigDecimal wsDebits = new BigDecimal(BigInteger.ZERO, 2);
    private static long wsListedCnt = 0;
    private static long wsRejectedCnt = 0;
    private static List<String> txnLines = new ArrayList<>();
    private static int txnIndex = 0;
    private static int returnCode = 0;

    public static void main(String[] args) throws Exception {
        paragraph0000Main();
    }

    private static void paragraph0000Main() throws Exception {
        String txnPath = System.getenv("DD_TXNIN");
        if (txnPath == null || txnPath.isEmpty()) {
            wsTxnStatus = "35";
            cobDisplay("TXNLIST OPEN TXNIN FAILED " + wsTxnStatus);
            returnCode = 16;
            System.exit(returnCode);
            return;
        }
        byte[] all;
        try {
            all = Files.readAllBytes(Paths.get(txnPath));
        } catch (IOException e) {
            wsTxnStatus = "35";
            cobDisplay("TXNLIST OPEN TXNIN FAILED " + wsTxnStatus);
            returnCode = 16;
            System.exit(returnCode);
            return;
        }
        wsTxnStatus = "00";
        txnLines = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < all.length; i++) {
            if (all[i] == (byte) '\n') {
                int end = i;
                if (end > start && all[end - 1] == (byte) '\r') {
                    end--;
                }
                String line = new String(all, start, end - start, StandardCharsets.ISO_8859_1);
                txnLines.add(line);
                start = i + 1;
            }
        }
        if (start < all.length) {
            int end = all.length;
            if (all[end - 1] == (byte) '\r') {
                end--;
            }
            String line = new String(all, start, end - start, StandardCharsets.ISO_8859_1);
            txnLines.add(line);
        }
        txnIndex = 0;
        endOfTxns = false;
        cobDisplay("TXNLIST DAILY LISTING");
        paragraph8000Read();
        while (!endOfTxns) {
            paragraph2000List();
        }
        paragraph9000Summary();
        if (returnCode != 0) {
            System.exit(returnCode);
        }
    }

    private static void paragraph2000List() throws Exception {
        wsListedCnt = (wsListedCnt + 1) % 10000000L;
        String amtEdit = formatFloating(txnAmount, 6);
        if (typeMatches(txnType, 'C')) {
            wsCredits = addCapped(wsCredits, txnAmount);
            cobDisplay(txnId + " CR " + amtEdit);
        } else if (typeMatches(txnType, 'D')) {
            wsDebits = addCapped(wsDebits, txnAmount);
            cobDisplay(txnId + " DB " + amtEdit);
        } else {
            wsRejectedCnt = (wsRejectedCnt + 1) % 10000000L;
            cobDisplay(txnId + " ?? " + amtEdit + " REJECTED");
        }
        paragraph8000Read();
    }

    private static void paragraph9000Summary() throws Exception {
        String totEdit = formatFloating(wsCredits, 10);
        cobDisplay("CREDITS " + totEdit);
        totEdit = formatFloating(wsDebits, 10);
        cobDisplay("DEBITS  " + totEdit);
        String listedStr = padLeft7(wsListedCnt);
        String rejectedStr = padLeft7(wsRejectedCnt);
        cobDisplay("LISTED " + listedStr + " REJECTED " + rejectedStr);
        if (wsRejectedCnt > 0) {
            returnCode = 4;
        }
    }

    private static void paragraph8000Read() {
        if (txnIndex < txnLines.size()) {
            String line = txnLines.get(txnIndex++);
            String rec;
            if (line.length() >= 15) {
                rec = line.substring(0, 15);
            } else {
                StringBuilder sb = new StringBuilder(line);
                while (sb.length() < 15) {
                    sb.append(' ');
                }
                rec = sb.toString();
            }
            txnId = rec.substring(0, 6);
            txnType = rec.charAt(6);
            String amtField = rec.substring(7, 15);
            txnAmount = parseAmount(amtField);
            wsTxnStatus = "00";
        } else {
            endOfTxns = true;
            wsTxnStatus = "10";
        }
    }

    private static BigDecimal parseAmount(String f) {
        char s = f.charAt(0);
        boolean neg = (s == '-');
        StringBuilder dig = new StringBuilder(7);
        for (int i = 1; i < 8; i++) {
            char c = f.charAt(i);
            if (c >= '0' && c <= '9') {
                dig.append(c);
            } else {
                dig.append('0');
            }
        }
        String d = dig.toString();
        String combo = d.substring(0, 5) + d.substring(5, 7);
        BigInteger unscaled = new BigInteger(combo);
        if (neg) {
            unscaled = unscaled.negate();
        }
        return new BigDecimal(unscaled, 2);
    }

    private static BigDecimal addCapped(BigDecimal base, BigDecimal delta) {
        BigDecimal sum = base.add(delta);
        BigInteger scaled = sum.movePointRight(2).toBigInteger();
        BigInteger limit = BigInteger.valueOf(100000000000L);
        if (scaled.abs().compareTo(limit) >= 0) {
            BigInteger r = scaled.abs().remainder(limit);
            if (scaled.signum() < 0) {
                r = r.negate();
            }
            return new BigDecimal(r, 2);
        }
        return new BigDecimal(scaled, 2);
    }

    private static String formatFloating(BigDecimal v, int intDigits) {
        boolean neg = v.signum() < 0;
        if (v.signum() == 0) {
            neg = false;
        }
        BigInteger scaled = v.abs().movePointRight(2).toBigInteger();
        BigInteger[] dr = scaled.divideAndRemainder(BigInteger.valueOf(100));
        BigInteger intPart = dr[0];
        int frac = dr[1].intValue();
        String intStr = intPart.toString();
        String fracStr = frac < 10 ? "0" + frac : "" + frac;
        if (intStr.length() > intDigits) {
            String head = (neg ? "-" : "") + intStr;
            return head + "." + fracStr;
        }
        StringBuilder pad = new StringBuilder();
        for (int i = 0; i < intDigits - intStr.length(); i++) {
            pad.append('0');
        }
        pad.append(intStr);
        char[] ch = new char[intDigits];
        for (int i = 0; i < intDigits; i++) {
            ch[i] = pad.charAt(i);
        }
        if (!neg) {
            int first = -1;
            for (int i = 0; i < intDigits; i++) {
                if (ch[i] != '0') {
                    first = i;
                    break;
                }
            }
            if (first == -1) {
                for (int i = 0; i < intDigits - 1; i++) {
                    ch[i] = ' ';
                }
            } else {
                for (int i = 0; i < first && i < intDigits - 1; i++) {
                    ch[i] = ' ';
                }
            }
        } else {
            int first = -1;
            for (int i = 0; i < intDigits; i++) {
                if (ch[i] != '0') {
                    first = i;
                    break;
                }
            }
            if (first == -1) {
                for (int i = 0; i < intDigits - 1; i++) {
                    ch[i] = ' ';
                }
                ch[intDigits - 2] = '-';
            } else if (first == 0) {
                return "-" + new String(ch) + "." + fracStr;
            } else {
                for (int i = 0; i < first - 1; i++) {
                    ch[i] = ' ';
                }
                ch[first - 1] = '-';
            }
        }
        return new String(ch) + "." + fracStr;
    }

    private static String padLeft7(long val) {
        String s = Long.toString(val);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 7 - s.length(); i++) {
            sb.append('0');
        }
        sb.append(s);
        return sb.toString();
    }

    private static void cobDisplay(String s) throws IOException {
        byte[] b = s.getBytes(StandardCharsets.ISO_8859_1);
        System.out.write(b);
        System.out.write('\n');
    }

    private static boolean typeMatches(char t, char e) {
        String col = System.getenv("DIOCLE_COLLATION");
        if ("EBCDIC".equals(col)) {
            try {
                byte tb = String.valueOf(t).getBytes("Cp037")[0];
                byte eb = String.valueOf(e).getBytes("Cp037")[0];
                return tb == eb;
            } catch (Exception ex) {
                return t == e;
            }
        }
        return t == e;
    }
}
