import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

public class DayCtrl {
    private static BufferedReader dayReader;
    private static BufferedWriter ctlWriter;
    private static String wsDayStatus = "00";
    private static String wsCtlStatus = "00";
    private static boolean endOfAccounts = false;
    private static BigDecimal wsInterest = new BigDecimal("0.00");
    private static BigDecimal wsCtlTotal = new BigDecimal("0.00");
    private static int wsReadCnt = 0;
    private static int wsLostCnt = 0;
    private static String dayAcctId = "          ";
    private static BigDecimal dayPrincipal = new BigDecimal("0.00");
    private static BigDecimal dayRate = new BigDecimal("0.0000");
    private static int dayDays = 0;
    private static String ctlAcctId = "          ";
    private static char ctlFlag = '-';

    public static void main(String[] args) throws Exception {
        p0000Main();
    }

    private static void p0000Main() throws Exception {
        p1000Init();
        while (!endOfAccounts) {
            p2000Process();
        }
        p9000Term();
    }

    private static void p1000Init() throws Exception {
        String dayPath = System.getenv("DD_DAYIN");
        String ctlPath = System.getenv("DD_CTLOUT");
        try {
            if (dayPath == null) {
                throw new java.io.IOException("missing");
            }
            dayReader = Files.newBufferedReader(Paths.get(dayPath), StandardCharsets.ISO_8859_1);
            wsDayStatus = "00";
        } catch (Exception e) {
            wsDayStatus = "35";
            System.out.println("DAYCTRL OPEN DAYIN FAILED " + wsDayStatus);
            System.exit(16);
            return;
        }
        try {
            if (ctlPath == null) {
                throw new java.io.IOException("missing");
            }
            ctlWriter = Files.newBufferedWriter(Paths.get(ctlPath), StandardCharsets.ISO_8859_1,
                    StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
            wsCtlStatus = "00";
        } catch (Exception e) {
            wsCtlStatus = "35";
            try {
                dayReader.close();
            } catch (Exception ex) {
            }
            System.out.println("DAYCTRL OPEN CTLOUT FAILED " + wsCtlStatus);
            System.exit(16);
            return;
        }
        p8000Read();
    }

    private static void p2000Process() throws Exception {
        wsReadCnt = (wsReadCnt + 1) % 10000000;
        p3000Accrue();
        p5000WriteResult();
        p8000Read();
    }

    private static void p3000Accrue() {
        BigDecimal daysDec = BigDecimal.valueOf((long) dayDays);
        BigDecimal numer = dayPrincipal.multiply(dayRate).multiply(daysDec);
        BigDecimal rounded = numer.divide(BigDecimal.valueOf(365L), 2, RoundingMode.HALF_UP);
        wsInterest = truncatePic(rounded, 9);
        wsCtlTotal = truncatePic(wsCtlTotal.add(wsInterest), 13);
        boolean interestZero = wsInterest.compareTo(BigDecimal.ZERO) == 0;
        boolean princZero = dayPrincipal.compareTo(BigDecimal.ZERO) == 0;
        boolean rateZero = dayRate.compareTo(BigDecimal.ZERO) == 0;
        boolean daysZero = dayDays == 0;
        if (interestZero && !princZero && !rateZero && !daysZero) {
            ctlFlag = 'Z';
            wsLostCnt = (wsLostCnt + 1) % 10000000;
        } else {
            ctlFlag = '-';
        }
    }

    private static void p5000WriteResult() throws Exception {
        ctlAcctId = dayAcctId;
        String interestStr = formatLeadingSeparate(wsInterest, 7);
        String totalStr = formatLeadingSeparate(wsCtlTotal, 11);
        String rec = ctlAcctId + interestStr + totalStr + ctlFlag;
        ctlWriter.write(rec);
        ctlWriter.write("\n");
    }

    private static void p8000Read() throws Exception {
        String line = dayReader.readLine();
        if (line == null) {
            endOfAccounts = true;
            return;
        }
        if (line.length() < 30) {
            StringBuilder sb = new StringBuilder(line);
            while (sb.length() < 30) {
                sb.append(' ');
            }
            line = sb.toString();
        } else if (line.length() > 30) {
            line = line.substring(0, 30);
        }
        dayAcctId = line.substring(0, 10);
        String princStr = line.substring(10, 22);
        String rateStr = line.substring(22, 27);
        String daysStr = line.substring(27, 30);
        dayPrincipal = parsePrincipal(princStr);
        dayRate = parseRate(rateStr);
        dayDays = parseDays(daysStr);
    }

    private static void p9000Term() throws Exception {
        try {
            dayReader.close();
        } catch (Exception e) {
        }
        try {
            ctlWriter.close();
        } catch (Exception e) {
        }
        String readDisp = zeroPad7(wsReadCnt);
        String lostDisp = zeroPad7(wsLostCnt);
        String edited = formatEdited(wsCtlTotal);
        System.out.println("DAYCTRL ACCOUNTS=" + readDisp + " LOST=" + lostDisp + " CONTROL=" + edited);
    }

    private static BigDecimal parsePrincipal(String s) {
        int sign = 1;
        char c0 = s.charAt(0);
        if (c0 == '-') {
            sign = -1;
        }
        BigInteger mag = BigInteger.ZERO;
        for (int i = 1; i < 12; i++) {
            char c = s.charAt(i);
            int d = 0;
            if (c >= '0' && c <= '9') {
                d = c - '0';
            } else {
                d = 0;
            }
            mag = mag.multiply(BigInteger.TEN).add(BigInteger.valueOf((long) d));
        }
        if (sign < 0) {
            mag = mag.negate();
        }
        return new BigDecimal(mag, 2);
    }

    private static BigDecimal parseRate(String s) {
        BigInteger mag = BigInteger.ZERO;
        for (int i = 0; i < 5; i++) {
            char c = s.charAt(i);
            int d = 0;
            if (c >= '0' && c <= '9') {
                d = c - '0';
            } else {
                d = 0;
            }
            mag = mag.multiply(BigInteger.TEN).add(BigInteger.valueOf((long) d));
        }
        return new BigDecimal(mag, 4);
    }

    private static int parseDays(String s) {
        int v = 0;
        for (int i = 0; i < 3; i++) {
            char c = s.charAt(i);
            int d = 0;
            if (c >= '0' && c <= '9') {
                d = c - '0';
            } else {
                d = 0;
            }
            v = v * 10 + d;
        }
        return v;
    }

    private static BigDecimal truncatePic(BigDecimal v, int totalDigits) {
        BigDecimal s2 = v.setScale(2, RoundingMode.UNNECESSARY);
        BigInteger unscaled = s2.movePointRight(2).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(totalDigits);
        BigInteger r = unscaled.remainder(mod);
        return new BigDecimal(r, 2);
    }

    private static String formatLeadingSeparate(BigDecimal v, int intDigits) {
        char signChar = v.signum() < 0 ? '-' : '+';
        BigDecimal abs = v.abs();
        BigInteger cents = abs.movePointRight(2).toBigIntegerExact();
        BigInteger[] dr = cents.divideAndRemainder(BigInteger.valueOf(100L));
        String intStr = dr[0].toString();
        int frac = dr[1].intValue();
        StringBuilder ib = new StringBuilder();
        for (int i = 0; i < intDigits - intStr.length(); i++) {
            ib.append('0');
        }
        ib.append(intStr);
        String intPadded = ib.toString();
        if (intPadded.length() > intDigits) {
            intPadded = intPadded.substring(intPadded.length() - intDigits);
        }
        String fracStr = frac < 10 ? ("0" + frac) : Integer.toString(frac);
        return signChar + intPadded + fracStr;
    }

    private static String formatEdited(BigDecimal v) {
        boolean neg = v.signum() < 0;
        BigDecimal abs = v.abs();
        BigInteger cents = abs.movePointRight(2).toBigIntegerExact();
        BigInteger intPart = cents.divide(BigInteger.valueOf(100L));
        int frac = cents.remainder(BigInteger.valueOf(100L)).intValue();
        String digits = intPart.toString();
        int width = 12;
        String intField;
        if (!neg) {
            int spaces = width - digits.length();
            if (spaces < 0) {
                spaces = 0;
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < spaces; i++) {
                sb.append(' ');
            }
            sb.append(digits);
            intField = sb.toString();
        } else {
            int spaces = width - digits.length() - 1;
            if (spaces < 0) {
                spaces = 0;
            }
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < spaces; i++) {
                sb.append(' ');
            }
            sb.append('-');
            sb.append(digits);
            intField = sb.toString();
        }
        String fracStr = frac < 10 ? ("0" + frac) : Integer.toString(frac);
        return intField + "." + fracStr;
    }

    private static String zeroPad7(int v) {
        int a = v % 10000000;
        if (a < 0) {
            a += 10000000;
        }
        String s = Integer.toString(a);
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 7 - s.length(); i++) {
            sb.append('0');
        }
        sb.append(s);
        return sb.toString();
    }
}
