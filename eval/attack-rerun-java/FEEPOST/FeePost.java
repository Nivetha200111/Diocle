public class FeePost {
  private static final java.math.BigDecimal RATE = new java.math.BigDecimal("0.015");
  private static final java.math.BigDecimal ONE = new java.math.BigDecimal("1.00");

  private String payId = "      ";
  private java.math.BigDecimal payAmount = java.math.BigDecimal.ZERO.setScale(2);
  private String postId = "      ";
  private java.math.BigDecimal postAmount = java.math.BigDecimal.ZERO.setScale(2);
  private java.math.BigDecimal postFee = java.math.BigDecimal.ZERO.setScale(2);
  private String wsFeePgm = "FEECALC ";
  private java.math.BigDecimal wsFee = java.math.BigDecimal.ZERO.setScale(2);
  private boolean endOfPayments = false;

  private java.math.BigDecimal lAmount = java.math.BigDecimal.ZERO.setScale(2);
  private java.math.BigDecimal lFee = java.math.BigDecimal.ZERO.setScale(2);

  private java.io.BufferedReader payReader;
  private java.io.BufferedWriter postWriter;

  public static void main(String[] args) throws Exception {
    FeePost prog = new FeePost();
    prog.p0000Main();
  }

  // 0000-MAIN (FEEPOST)
  private void p0000Main() throws Exception {
    String payinPath = System.getenv("DD_PAYIN");
    String postoutPath = System.getenv("DD_POSTOUT");
    payReader = java.nio.file.Files.newBufferedReader(java.nio.file.Paths.get(payinPath), java.nio.charset.StandardCharsets.ISO_8859_1);
    postWriter = java.nio.file.Files.newBufferedWriter(java.nio.file.Paths.get(postoutPath), java.nio.charset.StandardCharsets.ISO_8859_1);
    wsFeePgm = "FEECALC ";
    p8000Read();
    while (!endOfPayments) {
      p2000Post();
    }
    payReader.close();
    postWriter.close();
  }

  // 2000-POST
  private void p2000Post() throws Exception {
    lAmount = payAmount;
    lFee = wsFee;
    feeCalc0000Main();
    wsFee = lFee;
    postId = payId;
    postAmount = payAmount;
    postFee = wsFee;
    String outLine = postId + formatSignLeadingSeparate(postAmount) + formatSignLeadingSeparate(postFee);
    postWriter.write(outLine);
    postWriter.write("\n");
    p8000Read();
  }

  // 8000-READ
  private void p8000Read() throws Exception {
    String line = payReader.readLine();
    if (line == null) {
      endOfPayments = true;
    } else {
      if (line.length() > 14) {
        line = line.substring(0, 14);
      } else if (line.length() < 14) {
        StringBuilder sb = new StringBuilder(line);
        while (sb.length() < 14) sb.append(' ');
        line = sb.toString();
      }
      payId = line.substring(0, 6);
      String amtField = line.substring(6, 14);
      payAmount = parseSignLeadingSeparate(amtField);
    }
  }

  // 0000-MAIN (FEECALC) - CALL target of WS-FEE-PGM ('FEECALC')
  private void feeCalc0000Main() {
    if (lAmount.compareTo(java.math.BigDecimal.ZERO) > 0) {
      java.math.BigDecimal raw = lAmount.multiply(RATE);
      java.math.BigDecimal rounded = raw.setScale(2, java.math.RoundingMode.HALF_UP);
      rounded = truncToS9_5V99(rounded);
      lFee = rounded;
      if (lFee.compareTo(ONE) < 0) {
        lFee = new java.math.BigDecimal("1.00");
      }
    } else {
      lFee = java.math.BigDecimal.ZERO.setScale(2);
    }
  }

  private static java.math.BigDecimal parseSignLeadingSeparate(String field) {
    char s = field.charAt(0);
    boolean negative = (s == '-');
    long v = 0;
    for (int i = 1; i < 8; i++) {
      char c = field.charAt(i);
      int d;
      if (c >= '0' && c <= '9') d = c - '0';
      else if (c == ' ') d = 0;
      else d = 0;
      v = v * 10 + d;
    }
    if (negative) v = -v;
    return java.math.BigDecimal.valueOf(v, 2);
  }

  private static String formatSignLeadingSeparate(java.math.BigDecimal val) {
    if (val.compareTo(java.math.BigDecimal.ZERO) == 0) {
      return "+0000000";
    }
    char sign = val.signum() < 0 ? '-' : '+';
    java.math.BigDecimal abs = val.abs().setScale(2, java.math.RoundingMode.DOWN);
    long unscaled = abs.movePointRight(2).toBigIntegerExact().longValueExact();
    long mod = unscaled % 10000000L;
    if (mod < 0) mod = -mod;
    String digits = String.format(java.util.Locale.ROOT, "%07d", mod);
    return sign + digits;
  }

  private static java.math.BigDecimal truncToS9_5V99(java.math.BigDecimal val) {
    if (val.compareTo(java.math.BigDecimal.ZERO) == 0) return java.math.BigDecimal.ZERO.setScale(2);
    boolean neg = val.signum() < 0;
    java.math.BigDecimal abs = val.abs().setScale(2, java.math.RoundingMode.DOWN);
    long unscaled = abs.movePointRight(2).toBigIntegerExact().longValueExact();
    long mod = unscaled % 10000000L;
    java.math.BigDecimal r = java.math.BigDecimal.valueOf(mod, 2);
    return neg ? r.negate() : r;
  }
}
