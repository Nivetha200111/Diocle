import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

public class IntAccr {
  private static String wsAcctStatus = "  ";
  private static String wsOutStatus = "  ";
  private static boolean endOfAccounts = false;
  private static BigDecimal wsPenaltyRate = new BigDecimal("0.0500");
  private static BigDecimal wsFeeFloor = new BigDecimal("1000.00");
  private static BigDecimal wsFeeCap = new BigDecimal("25.00");
  private static BigDecimal wsInterest = new BigDecimal("0.00");
  private static BigDecimal wsFee = new BigDecimal("0.00");
  private static BigDecimal wsNewBal = new BigDecimal("0.00");
  private static long wsReadCnt = 0;
  private static long wsWriteCnt = 0;
  private static String acctId = "          ";
  private static BigDecimal acctBalance = new BigDecimal("0.00");
  private static BigDecimal acctRate = new BigDecimal("0.0000");
  private static int acctDays = 0;
  private static String acctTier = " ";
  private static BufferedReader acctReader = null;
  private static OutputStream outStream = null;

  public static void main(String[] args) throws Exception {
    String dioClock = System.getenv("DIOCLE_CLOCK");
    String dioColl = System.getenv("DIOCLE_COLLATION");
    if (dioClock != null && dioColl != null && dioClock.equals(dioColl)) {
    }
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
    String acctPathStr = System.getenv("DD_ACCTIN");
    String outPathStr = System.getenv("DD_INTOUT");
    if (acctPathStr == null || acctPathStr.isEmpty()) {
      wsAcctStatus = "35";
      System.out.println("INTACCR OPEN ACCTIN FAILED " + wsAcctStatus);
      System.exit(16);
      return;
    }
    try {
      Path p = Paths.get(acctPathStr);
      acctReader = new BufferedReader(new InputStreamReader(Files.newInputStream(p), StandardCharsets.ISO_8859_1));
      wsAcctStatus = "00";
    } catch (java.nio.file.NoSuchFileException e) {
      wsAcctStatus = "35";
      System.out.println("INTACCR OPEN ACCTIN FAILED " + wsAcctStatus);
      System.exit(16);
      return;
    } catch (java.nio.file.AccessDeniedException e) {
      wsAcctStatus = "37";
      System.out.println("INTACCR OPEN ACCTIN FAILED " + wsAcctStatus);
      System.exit(16);
      return;
    } catch (Exception e) {
      wsAcctStatus = "30";
      System.out.println("INTACCR OPEN ACCTIN FAILED " + wsAcctStatus);
      System.exit(16);
      return;
    }
    if (outPathStr == null || outPathStr.isEmpty()) {
      wsOutStatus = "35";
      System.out.println("INTACCR OPEN INTOUT FAILED " + wsOutStatus);
      System.exit(16);
      return;
    }
    try {
      Path p = Paths.get(outPathStr);
      Path parent = p.toAbsolutePath().getParent();
      if (parent != null) {
        try { Files.createDirectories(parent); } catch (Exception ignore) {}
      }
      outStream = Files.newOutputStream(p, StandardOpenOption.CREATE, StandardOpenOption.TRUNCATE_EXISTING, StandardOpenOption.WRITE);
      wsOutStatus = "00";
    } catch (java.nio.file.NoSuchFileException e) {
      wsOutStatus = "35";
      System.out.println("INTACCR OPEN INTOUT FAILED " + wsOutStatus);
      System.exit(16);
      return;
    } catch (java.nio.file.AccessDeniedException e) {
      wsOutStatus = "37";
      System.out.println("INTACCR OPEN INTOUT FAILED " + wsOutStatus);
      System.exit(16);
      return;
    } catch (Exception e) {
      wsOutStatus = "30";
      System.out.println("INTACCR OPEN INTOUT FAILED " + wsOutStatus);
      System.exit(16);
      return;
    }
    p8000Read();
  }

  private static void p2000Process() throws Exception {
    wsReadCnt = (wsReadCnt + 1) % 10000000L;
    p3000CalcInterest();
    p4000CalcFee();
    p5000WriteResult();
    p8000Read();
  }

  private static void p3000CalcInterest() {
    int cmp = acctBalance.compareTo(BigDecimal.ZERO);
    if (cmp > 0) {
      BigDecimal num = acctBalance.multiply(acctRate).multiply(BigDecimal.valueOf((long) acctDays));
      BigDecimal rounded = num.divide(new BigDecimal("365"), 2, RoundingMode.HALF_UP);
      wsInterest = fitPic(rounded, 7, 2);
    } else if (cmp < 0) {
      BigDecimal rate2 = acctRate.add(wsPenaltyRate);
      BigDecimal num = acctBalance.multiply(rate2).multiply(BigDecimal.valueOf((long) acctDays));
      BigDecimal rounded = num.divide(new BigDecimal("365"), 2, RoundingMode.HALF_UP);
      wsInterest = fitPic(rounded, 7, 2);
    } else {
      wsInterest = BigDecimal.ZERO.setScale(2);
    }
  }

  private static void p4000CalcFee() {
    wsFee = BigDecimal.ZERO.setScale(2);
    boolean isPremium = "P".equals(acctTier);
    if (!isPremium && acctBalance.compareTo(wsFeeFloor) < 0) {
      BigDecimal shortfall = wsFeeFloor.subtract(acctBalance);
      BigDecimal raw = shortfall.multiply(new BigDecimal("0.0015"));
      BigDecimal truncated = raw.setScale(2, RoundingMode.DOWN);
      BigDecimal fitted = fitPic(truncated, 5, 2);
      wsFee = fitted;
      if (wsFee.compareTo(wsFeeCap) > 0) {
        wsFee = wsFeeCap;
      }
    }
  }

  private static void p5000WriteResult() throws Exception {
    BigDecimal sum = acctBalance.add(wsInterest).subtract(wsFee);
    sum = sum.setScale(2, RoundingMode.DOWN);
    wsNewBal = fitPic(sum, 9, 2);
    String outInterestStr = formatSigned(wsInterest, 7, 2);
    String outFeeStr = formatSigned(wsFee, 5, 2);
    String outNewBalStr = formatSigned(wsNewBal, 9, 2);
    String status;
    if (wsNewBal.compareTo(BigDecimal.ZERO) < 0) {
      status = "OD";
    } else if (wsFee.compareTo(BigDecimal.ZERO) > 0) {
      status = "FE";
    } else {
      status = "OK";
    }
    String idField = acctId;
    if (idField.length() < 10) {
      idField = idField + "          ".substring(0, 10 - idField.length());
    } else if (idField.length() > 10) {
      idField = idField.substring(0, 10);
    }
    String outLine = idField + outInterestStr + outFeeStr + outNewBalStr + status;
    outStream.write((outLine + "\n").getBytes(StandardCharsets.ISO_8859_1));
    wsWriteCnt = (wsWriteCnt + 1) % 10000000L;
  }

  private static void p8000Read() throws Exception {
    String line = acctReader.readLine();
    if (line == null) {
      endOfAccounts = true;
      return;
    }
    if (line.length() < 31) {
      StringBuilder sb = new StringBuilder(line);
      while (sb.length() < 31) sb.append(' ');
      line = sb.toString();
    } else if (line.length() > 31) {
      line = line.substring(0, 31);
    }
    acctId = line.substring(0, 10);
    String balField = line.substring(10, 22);
    String rateField = line.substring(22, 27);
    String daysField = line.substring(27, 30);
    String tierField = line.substring(30, 31);
    acctBalance = parseSignedSeparate(balField, 11, 2);
    acctRate = parseUnsigned(rateField, 4);
    acctDays = parseUnsignedInt(daysField);
    acctTier = tierField;
  }

  private static void p9000Term() throws Exception {
    try { if (acctReader != null) acctReader.close(); } catch (Exception ignore) {}
    try { if (outStream != null) { outStream.flush(); outStream.close(); } } catch (Exception ignore) {}
    String r = String.format("%07d", Long.valueOf(wsReadCnt));
    String w = String.format("%07d", Long.valueOf(wsWriteCnt));
    System.out.println("INTACCR READ=" + r + " WRITTEN=" + w);
  }

  private static BigDecimal parseSignedSeparate(String f, int totalDigits, int scale) {
    if (f == null || f.length() == 0) return BigDecimal.ZERO.setScale(scale);
    char sc = f.charAt(0);
    String digs = f.substring(1);
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < digs.length(); i++) {
      char c = digs.charAt(i);
      if (c >= '0' && c <= '9') sb.append(c);
      else if (c == ' ') sb.append('0');
      else sb.append('0');
    }
    String num = sb.length() == 0 ? "0" : sb.toString();
    BigDecimal v;
    try {
      v = new BigDecimal(num).movePointLeft(scale);
    } catch (Exception e) {
      v = BigDecimal.ZERO.setScale(scale);
    }
    boolean neg = (sc == '-');
    if (neg) v = v.negate();
    v = v.setScale(scale, RoundingMode.DOWN);
    return v;
  }

  private static BigDecimal parseUnsigned(String f, int scale) {
    if (f == null || f.length() == 0) return BigDecimal.ZERO.setScale(scale);
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < f.length(); i++) {
      char c = f.charAt(i);
      if (c >= '0' && c <= '9') sb.append(c);
      else if (c == ' ') sb.append('0');
      else sb.append('0');
    }
    String num = sb.length() == 0 ? "0" : sb.toString();
    try {
      return new BigDecimal(num).movePointLeft(scale).setScale(scale, RoundingMode.DOWN);
    } catch (Exception e) {
      return BigDecimal.ZERO.setScale(scale);
    }
  }

  private static int parseUnsignedInt(String f) {
    if (f == null || f.length() == 0) return 0;
    StringBuilder sb = new StringBuilder();
    for (int i = 0; i < f.length(); i++) {
      char c = f.charAt(i);
      if (c >= '0' && c <= '9') sb.append(c);
      else if (c == ' ') sb.append('0');
      else sb.append('0');
    }
    try {
      return Integer.parseInt(sb.toString());
    } catch (Exception e) {
      return 0;
    }
  }

  private static BigDecimal fitPic(BigDecimal v, int intDigits, int fracDigits) {
    int total = intDigits + fracDigits;
    BigDecimal s;
    try {
      s = v.setScale(fracDigits, RoundingMode.DOWN);
    } catch (Exception e) {
      s = BigDecimal.ZERO.setScale(fracDigits);
    }
    BigInteger u = s.unscaledValue();
    BigInteger base = BigInteger.TEN.pow(total);
    boolean neg = u.signum() < 0;
    BigInteger abs = u.abs().mod(base);
    if (abs.equals(BigInteger.ZERO)) {
      return BigDecimal.ZERO.setScale(fracDigits);
    }
    BigInteger res = neg ? abs.negate() : abs;
    return new BigDecimal(res, fracDigits);
  }

  private static String formatSigned(BigDecimal v, int intDigits, int fracDigits) {
    int total = intDigits + fracDigits;
    BigDecimal s = v.setScale(fracDigits, RoundingMode.DOWN);
    BigInteger u = s.unscaledValue();
    boolean neg = u.signum() < 0;
    BigInteger abs = u.abs().remainder(BigInteger.TEN.pow(total));
    if (abs.equals(BigInteger.ZERO)) neg = false;
    String digs = abs.toString();
    if (digs.length() < total) {
      StringBuilder sb = new StringBuilder();
      for (int i = 0; i < total - digs.length(); i++) sb.append('0');
      sb.append(digs);
      digs = sb.toString();
    } else if (digs.length() > total) {
      digs = digs.substring(digs.length() - total);
    }
    return (neg ? "-" : "+") + digs;
  }
}
