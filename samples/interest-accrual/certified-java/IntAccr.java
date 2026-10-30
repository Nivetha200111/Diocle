import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.util.ArrayList;
import java.util.List;

public class IntAccr {
    private String wsAcctStatus = "  ";
    private String wsOutStatus = "  ";
    private boolean endOfAccounts = false;
    private BigDecimal wsPenaltyRate = new BigDecimal("0.0500");
    private BigDecimal wsFeeFloor = new BigDecimal("1000.00");
    private BigDecimal wsFeeCap = new BigDecimal("25.00");
    private BigDecimal wsInterest = new BigDecimal("0.00");
    private BigDecimal wsFee = new BigDecimal("0.00");
    private BigDecimal wsNewBal = new BigDecimal("0.00");
    private int wsReadCnt = 0;
    private int wsWriteCnt = 0;
    private String acctId = "          ";
    private BigDecimal acctBalance = new BigDecimal("0.00");
    private BigDecimal acctRate = new BigDecimal("0.0000");
    private int acctDays = 0;
    private String acctTier = " ";
    private List<String> inRecs = new ArrayList<>();
    private int inIdx = 0;
    private OutputStream outStream = null;

    public static void main(String[] args) throws Exception {
        IntAccr p = new IntAccr();
        p.p0000Main();
    }

    private void p0000Main() throws Exception {
        p1000Init();
        while (!endOfAccounts) {
            p2000Process();
        }
        p9000Term();
    }

    private void p1000Init() throws Exception {
        String clockVal = System.getenv("DIOCLE_CLOCK");
        String collVal = System.getenv("DIOCLE_COLLATION");
        if (clockVal != null && clockVal.length() == -1) {
            System.out.print("");
        }
        if (collVal != null && collVal.length() == -1) {
            System.out.print("");
        }
        String acctPath = System.getenv("DD_ACCTIN");
        String outPath = System.getenv("DD_INTOUT");
        boolean okAcct = false;
        if (acctPath != null && acctPath.length() > 0) {
            try {
                byte[] all = Files.readAllBytes(Paths.get(acctPath));
                List<String> recs = new ArrayList<>();
                int start = 0;
                for (int i = 0; i < all.length; i++) {
                    if (all[i] == 10) {
                        int end = i;
                        int len = end - start;
                        if (len > 0 && all[end - 1] == 13) {
                            len--;
                        }
                        byte[] rb = new byte[len];
                        System.arraycopy(all, start, rb, 0, len);
                        recs.add(new String(rb, StandardCharsets.ISO_8859_1));
                        start = i + 1;
                    }
                }
                if (start < all.length) {
                    int len = all.length - start;
                    if (len > 0 && all[all.length - 1] == 13) {
                        len--;
                    }
                    byte[] rb = new byte[len];
                    System.arraycopy(all, start, rb, 0, len);
                    recs.add(new String(rb, StandardCharsets.ISO_8859_1));
                }
                inRecs = recs;
                inIdx = 0;
                okAcct = true;
                wsAcctStatus = "00";
            } catch (Exception e) {
                wsAcctStatus = "35";
                okAcct = false;
            }
        } else {
            wsAcctStatus = "35";
            okAcct = false;
        }
        if (!okAcct) {
            System.out.println("INTACCR OPEN ACCTIN FAILED " + wsAcctStatus);
            System.exit(16);
            return;
        }
        boolean okOut = false;
        if (outPath != null && outPath.length() > 0) {
            try {
                outStream = Files.newOutputStream(Paths.get(outPath), StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
                okOut = true;
                wsOutStatus = "00";
            } catch (Exception e) {
                wsOutStatus = "35";
                okOut = false;
            }
        } else {
            wsOutStatus = "35";
            okOut = false;
        }
        if (!okOut) {
            System.out.println("INTACCR OPEN INTOUT FAILED " + wsOutStatus);
            System.exit(16);
            return;
        }
        p8000Read();
    }

    private void p2000Process() throws Exception {
        wsReadCnt = (wsReadCnt + 1) % 10000000;
        p3000CalcInterest();
        p4000CalcFee();
        p5000WriteResult();
        p8000Read();
    }

    private void p3000CalcInterest() {
        if (acctBalance.compareTo(BigDecimal.ZERO) > 0) {
            BigDecimal num = acctBalance.multiply(acctRate).multiply(BigDecimal.valueOf((long) acctDays));
            BigDecimal r = num.divide(new BigDecimal("365"), 2, RoundingMode.HALF_UP);
            wsInterest = modPic(r, 7, 2);
        } else if (acctBalance.compareTo(BigDecimal.ZERO) < 0) {
            BigDecimal eff = acctRate.add(wsPenaltyRate);
            BigDecimal num = acctBalance.multiply(eff).multiply(BigDecimal.valueOf((long) acctDays));
            BigDecimal r = num.divide(new BigDecimal("365"), 2, RoundingMode.HALF_UP);
            wsInterest = modPic(r, 7, 2);
        } else {
            wsInterest = new BigDecimal("0.00");
        }
    }

    private void p4000CalcFee() {
        wsFee = new BigDecimal("0.00");
        boolean premium = acctTier.equals("P");
        if (!premium && acctBalance.compareTo(wsFeeFloor) < 0) {
            BigDecimal diff = wsFeeFloor.subtract(acctBalance);
            BigDecimal raw = diff.multiply(new BigDecimal("0.0015"));
            BigDecimal tr = raw.setScale(2, RoundingMode.DOWN);
            BigDecimal stored = modPic(tr, 5, 2);
            if (stored.compareTo(wsFeeCap) > 0) {
                stored = wsFeeCap;
            }
            wsFee = stored;
        }
    }

    private void p5000WriteResult() throws Exception {
        BigDecimal nb = acctBalance.add(wsInterest).subtract(wsFee);
        wsNewBal = modPic(nb, 9, 2);
        String idOut = acctId;
        if (idOut.length() < 10) {
            idOut = idOut + "          ".substring(0, 10 - idOut.length());
        } else if (idOut.length() > 10) {
            idOut = idOut.substring(0, 10);
        }
        String iStr = fmtSigned(wsInterest, 7, 2);
        String fStr = fmtSigned(wsFee, 5, 2);
        String nStr = fmtSigned(wsNewBal, 9, 2);
        String st;
        if (wsNewBal.compareTo(BigDecimal.ZERO) < 0) {
            st = "OD";
        } else if (wsFee.compareTo(BigDecimal.ZERO) > 0) {
            st = "FE";
        } else {
            st = "OK";
        }
        String rec = idOut + iStr + fStr + nStr + st;
        byte[] b = rec.getBytes(StandardCharsets.ISO_8859_1);
        outStream.write(b);
        outStream.write(10);
        wsWriteCnt = (wsWriteCnt + 1) % 10000000;
    }

    private void p8000Read() {
        if (inIdx >= inRecs.size()) {
            endOfAccounts = true;
            return;
        }
        String line = inRecs.get(inIdx++);
        if (line.length() < 31) {
            line = line + "                               ".substring(0, 31 - line.length());
        } else if (line.length() > 31) {
            line = line.substring(0, 31);
        }
        acctId = line.substring(0, 10);
        String bf = line.substring(10, 22);
        String rf = line.substring(22, 27);
        String df = line.substring(27, 30);
        acctTier = line.substring(30, 31);
        char sc = bf.charAt(0);
        boolean neg = (sc == '-');
        String digs;
        if (sc == '+' || sc == '-' || sc == ' ') {
            digs = bf.substring(1);
        } else {
            digs = bf;
            neg = false;
        }
        BigInteger bi;
        try {
            bi = new BigInteger(digs);
        } catch (Exception e) {
            bi = BigInteger.ZERO;
        }
        BigDecimal bal = new BigDecimal(bi).movePointLeft(2);
        if (neg) {
            bal = bal.negate();
        }
        bal = bal.setScale(2);
        acctBalance = bal;
        BigInteger ri;
        try {
            ri = new BigInteger(rf);
        } catch (Exception e) {
            ri = BigInteger.ZERO;
        }
        acctRate = new BigDecimal(ri).movePointLeft(4);
        String dt = df.trim();
        int d = 0;
        if (dt.length() > 0) {
            try {
                d = Integer.parseInt(dt);
            } catch (Exception e) {
                d = 0;
            }
        }
        acctDays = d;
    }

    private void p9000Term() throws Exception {
        if (outStream != null) {
            try {
                outStream.close();
            } catch (Exception e) {
            }
        }
        String r = pad7(wsReadCnt);
        String w = pad7(wsWriteCnt);
        System.out.println("INTACCR READ=" + r + " WRITTEN=" + w);
    }

    private BigDecimal modPic(BigDecimal v, int intD, int decD) {
        BigDecimal sc = v.setScale(decD, RoundingMode.DOWN);
        BigInteger scaled = sc.movePointRight(decD).toBigIntegerExact();
        BigInteger mod = BigInteger.TEN.pow(intD + decD);
        BigInteger t = scaled.remainder(mod);
        return new BigDecimal(t, decD);
    }

    private String fmtSigned(BigDecimal v, int intD, int decD) {
        boolean neg = v.signum() < 0;
        BigDecimal a = v.abs().setScale(decD, RoundingMode.DOWN);
        BigInteger scaled = a.movePointRight(decD).toBigIntegerExact();
        String s = scaled.toString();
        int total = intD + decD;
        while (s.length() < total) {
            s = "0" + s;
        }
        if (s.length() > total) {
            s = s.substring(s.length() - total);
        }
        return (neg ? "-" : "+") + s;
    }

    private String pad7(int v) {
        String s = Integer.toString(v);
        while (s.length() < 7) {
            s = "0" + s;
        }
        if (s.length() > 7) {
            s = s.substring(s.length() - 7);
        }
        return s;
    }

    private boolean isEbcdic() {
        String c = System.getenv("DIOCLE_COLLATION");
        return "EBCDIC".equals(c);
    }
}
