import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

public class Loanamrt {
  private byte[] loanBytes;
  private int loanPos;
  private OutputStream amOut;
  private boolean ebcdic;
  private String lnId;
  private BigDecimal lnPrincipal;
  private BigDecimal lnRate;
  private int lnTerm;
  private String lnStart;
  private String amId;
  private int amPeriod;
  private int amYyyymm;
  private BigDecimal amPayment;
  private BigDecimal amInterest;
  private BigDecimal amBalance;
  private boolean wsEof;
  private BigDecimal wsBal;
  private BigDecimal wsPrinPart;
  private BigDecimal wsInt;
  private int wsYear;
  private int wsMonth;
  private int wsPeriods;
  private int wsP;
  private int wsLoans;
  private int wsRejects;
  private int wsLines;

  public static void main(String[] args) throws Exception {
    Loanamrt prog = new Loanamrt();
    prog.p0000Main();
  }

  private void p0000Main() throws Exception {
    String loanPath = System.getenv("DD_LOANIN");
    String amPath = System.getenv("DD_AMRTOUT");
    if (loanPath == null) {
      loanPath = "LOANIN";
    }
    if (amPath == null) {
      amPath = "AMRTOUT";
    }
    String coll = System.getenv("DIOCLE_COLLATION");
    ebcdic = "EBCDIC".equals(coll);
    try {
      loanBytes = Files.readAllBytes(Paths.get(loanPath));
    } catch (Exception e) {
      loanBytes = new byte[0];
    }
    loanPos = 0;
    amOut = Files.newOutputStream(Paths.get(amPath), StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
    wsEof = false;
    wsLoans = 0;
    wsRejects = 0;
    wsLines = 0;
    wsBal = new BigDecimal(BigInteger.ZERO, 2);
    wsPrinPart = new BigDecimal(BigInteger.ZERO, 2);
    wsInt = new BigDecimal(BigInteger.ZERO, 2);
    wsYear = 0;
    wsMonth = 0;
    wsPeriods = 0;
    wsP = 0;
    while (!wsEof) {
      if (loanPos + 26 > loanBytes.length) {
        wsEof = true;
      } else {
        readLoan();
        p1000Loan();
      }
    }
    amOut.close();
    String line = "LOANAMRT LOANS=" + countText(wsLoans, 5) + " REJECTS=" + countText(wsRejects, 5) + " LINES=" + countText(wsLines, 7);
    System.out.println(line);
  }

  private void readLoan() {
    lnId = new String(loanBytes, loanPos, 8, StandardCharsets.ISO_8859_1);
    lnPrincipal = unpack(loanBytes, loanPos + 8, 6, 2, true);
    lnRate = unpack(loanBytes, loanPos + 14, 4, 5, false);
    int raw = ((loanBytes[loanPos + 18] & 255) << 8) | (loanBytes[loanPos + 19] & 255);
    lnTerm = raw % 1000;
    lnStart = new String(loanBytes, loanPos + 20, 6, StandardCharsets.ISO_8859_1);
    loanPos += 26;
  }

  private void p1000Loan() throws Exception {
    String mm = lnStart.substring(4, 6);
    boolean badMonth = cmpAlpha(mm, "01") < 0 || cmpAlpha(mm, "12") > 0;
    if (lnTerm == 0 || lnPrincipal.compareTo(BigDecimal.ZERO) <= 0 || badMonth) {
      wsRejects = (wsRejects + 1) % 100000;
    } else {
      wsLoans = (wsLoans + 1) % 100000;
      wsBal = fit(lnPrincipal, 11, 2);
      wsPrinPart = prinPart(lnPrincipal, lnTerm);
      wsYear = parseNum(lnStart.substring(0, 4));
      wsMonth = parseNum(mm);
      wsPeriods = lnTerm;
      if (wsPeriods > 12) {
        wsPeriods = 12;
      }
      for (wsP = 1; wsP <= wsPeriods; wsP++) {
        p2000Period();
      }
    }
  }

  private void p2000Period() throws Exception {
    wsInt = intPart(wsBal, lnRate);
    if (wsP == lnTerm) {
      wsPrinPart = fit(wsBal, 9, 2);
    }
    wsBal = fit(wsBal.subtract(wsPrinPart), 11, 2);
    amId = lnId;
    amPeriod = wsP;
    int y = wsYear % 10000;
    if (y < 0) {
      y += 10000;
    }
    int m = wsMonth;
    amYyyymm = (y * 100 + m) % 1000000;
    amPayment = fit(wsPrinPart.add(wsInt), 9, 2);
    amInterest = fit(wsInt, 9, 2);
    amBalance = fit(wsBal, 11, 2);
    writeAm();
    wsLines = (wsLines + 1) % 10000000;
    wsMonth = wsMonth + 1;
    if (wsMonth > 12) {
      wsMonth = 1;
      wsYear = (wsYear + 1) % 10000;
    }
  }

  private void writeAm() throws Exception {
    byte[] rec = new byte[33];
    byte[] idB = amId.getBytes(StandardCharsets.ISO_8859_1);
    for (int i = 0; i < 8; i++) {
      byte b = 32;
      if (i < idB.length) {
        b = idB[i];
      }
      rec[i] = b;
    }
    int p = amPeriod % 1000;
    if (p < 0) {
      p += 1000;
    }
    rec[8] = (byte) (48 + p / 100);
    rec[9] = (byte) (48 + (p / 10) % 10);
    rec[10] = (byte) (48 + p % 10);
    int v = amYyyymm % 1000000;
    if (v < 0) {
      v += 1000000;
    }
    rec[11] = (byte) (48 + v / 100000);
    rec[12] = (byte) (48 + (v / 10000) % 10);
    rec[13] = (byte) (48 + (v / 1000) % 10);
    rec[14] = (byte) (48 + (v / 100) % 10);
    rec[15] = (byte) (48 + (v / 10) % 10);
    rec[16] = (byte) (48 + v % 10);
    pack(amPayment, 9, 5, 2, true, rec, 17);
    pack(amInterest, 9, 5, 2, true, rec, 22);
    pack(amBalance, 11, 6, 2, true, rec, 27);
    amOut.write(rec);
  }

  private int cmpAlpha(String a, String b) {
    if (!ebcdic) {
      return a.compareTo(b);
    }
    try {
      Charset eb = Charset.forName("Cp037");
      byte[] ab = a.getBytes(eb);
      byte[] bb = b.getBytes(eb);
      int n = ab.length;
      if (bb.length < n) {
        n = bb.length;
      }
      for (int i = 0; i < n; i++) {
        int av = ab[i] & 255;
        int bv = bb[i] & 255;
        if (av != bv) {
          return av - bv;
        }
      }
      if (ab.length == bb.length) {
        return 0;
      }
      if (ab.length < bb.length) {
        return -1;
      }
      return 1;
    } catch (Exception e) {
      return a.compareTo(b);
    }
  }

  private static int parseNum(String s) {
    int v = 0;
    for (int i = 0; i < s.length(); i++) {
      char ch = s.charAt(i);
      if (ch >= 48 && ch <= 57) {
        v = v * 10 + (ch - 48);
      } else {
        v = v * 10;
      }
    }
    return v;
  }

  private static String countText(int v, int w) {
    int mod = 1;
    for (int i = 0; i < w; i++) {
      mod = mod * 10;
    }
    int t = v % mod;
    if (t < 0) {
      t += mod;
    }
    char[] c = new char[w];
    for (int i = w - 1; i >= 0; i--) {
      c[i] = (char) (48 + t % 10);
      t = t / 10;
    }
    return new String(c);
  }

  private static BigDecimal unpack(byte[] d, int off, int len, int scale, boolean signed) {
    BigInteger mag = BigInteger.ZERO;
    int nibs = len * 2 - 1;
    for (int i = 0; i < nibs; i++) {
      int by = d[off + i / 2] & 255;
      int nib;
      if ((i & 1) == 0) {
        nib = (by >> 4) & 15;
      } else {
        nib = by & 15;
      }
      int dig = nib;
      if (dig > 9) {
        dig = 0;
      }
      mag = mag.multiply(BigInteger.TEN).add(BigInteger.valueOf(dig));
    }
    int sign = d[off + len - 1] & 15;
    boolean neg = (sign == 13);
    BigDecimal v = new BigDecimal(mag, scale);
    if (neg && mag.signum() != 0) {
      v = v.negate();
    }
    return v;
  }

  private static void pack(BigDecimal v, int totalDigits, int len, int scale, boolean signed, byte[] out, int off) {
    BigDecimal t = v.setScale(scale, RoundingMode.DOWN);
    BigInteger u = t.unscaledValue();
    boolean neg = u.signum() < 0;
    BigInteger mag = u.abs();
    BigInteger base = BigInteger.TEN.pow(totalDigits);
    mag = mag.mod(base);
    String s = mag.toString();
    int cap = len * 2 - 1;
    if (s.length() > cap) {
      s = s.substring(s.length() - cap);
    }
    int pad = cap - s.length();
    for (int i = 0; i < len - 1; i++) {
      int hiIdx = i * 2;
      int loIdx = i * 2 + 1;
      int hi = (hiIdx < pad) ? 0 : (s.charAt(hiIdx - pad) - 48);
      int lo = (loIdx < pad) ? 0 : (s.charAt(loIdx - pad) - 48);
      out[off + i] = (byte) ((hi << 4) | lo);
    }
    int lastIdx = cap - 1;
    int hi = (lastIdx < pad) ? 0 : (s.charAt(lastIdx - pad) - 48);
    int sign;
    if (!signed) {
      sign = 15;
    } else if (neg && mag.signum() != 0) {
      sign = 13;
    } else {
      sign = 12;
    }
    out[off + len - 1] = (byte) ((hi << 4) | sign);
  }

  private static BigDecimal fit(BigDecimal v, int totalDigits, int scale) {
    BigDecimal t = v.setScale(scale, RoundingMode.DOWN);
    BigInteger base = BigInteger.TEN.pow(totalDigits);
    BigInteger u = t.unscaledValue();
    if (u.signum() == 0) {
      return new BigDecimal(BigInteger.ZERO, scale);
    }
    BigInteger mag = u.abs().mod(base);
    if (mag.signum() == 0) {
      return new BigDecimal(BigInteger.ZERO, scale);
    }
    if (u.signum() < 0) {
      return new BigDecimal(mag.negate(), scale);
    }
    return new BigDecimal(mag, scale);
  }

  private static BigInteger roundQuotient(BigInteger num, BigInteger den) {
    BigInteger[] qr = num.divideAndRemainder(den);
    BigInteger q = qr[0];
    BigInteger rem = qr[1];
    if (rem.signum() == 0) {
      return q;
    }
    BigInteger twice = rem.abs().multiply(BigInteger.valueOf(2));
    if (twice.compareTo(den) >= 0) {
      if (num.signum() >= 0) {
        return q.add(BigInteger.ONE);
      } else {
        return q.subtract(BigInteger.ONE);
      }
    }
    return q;
  }

  private static BigDecimal prinPart(BigDecimal principal, int term) {
    BigDecimal p2 = principal.setScale(2, RoundingMode.DOWN);
    BigInteger n = p2.unscaledValue();
    BigInteger d = BigInteger.valueOf(term);
    BigInteger m = roundQuotient(n, d);
    BigDecimal r = new BigDecimal(m, 2);
    return fit(r, 9, 2);
  }

  private static BigDecimal intPart(BigDecimal bal, BigDecimal rate) {
    BigDecimal b2 = bal.setScale(2, RoundingMode.DOWN);
    BigDecimal r5 = rate.setScale(5, RoundingMode.DOWN);
    BigInteger b = b2.unscaledValue();
    BigInteger r = r5.unscaledValue();
    BigInteger num = b.multiply(r);
    BigInteger den = BigInteger.valueOf(1200000);
    BigInteger q = roundQuotient(num, den);
    BigDecimal res = new BigDecimal(q, 2);
    return fit(res, 9, 2);
  }
}
