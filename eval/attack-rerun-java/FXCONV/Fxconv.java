public class Fxconv {
    private String wsEof;
    private String[] wsRateCcy;
    private java.math.BigDecimal[] wsRate;
    private byte[] curFxId;
    private String curFxCcy;
    private java.math.BigDecimal curFxAmount;
    private byte[] curFoId;
    private String curFoCcy;
    private java.math.BigDecimal curWsConverted;
    private boolean curHasRate;
    private String curStatus;
    private java.io.ByteArrayOutputStream outBuf;

    private void p0000Main() throws Exception {
        wsRateCcy = new String[]{"USD", "EUR", "GBP", "JPY", "INR"};
        wsRate = new java.math.BigDecimal[]{
            new java.math.BigDecimal(java.math.BigInteger.valueOf(83125000L), 6),
            new java.math.BigDecimal(java.math.BigInteger.valueOf(90410000L), 6),
            new java.math.BigDecimal(java.math.BigInteger.valueOf(105333300L), 6),
            new java.math.BigDecimal(java.math.BigInteger.valueOf(555550L), 6),
            new java.math.BigDecimal(java.math.BigInteger.valueOf(998770L), 6)
        };
        wsEof = "N";
        outBuf = new java.io.ByteArrayOutputStream();
        String fxInPath = System.getenv("DD_FXIN");
        String fxOutPath = System.getenv("DD_FXOUT");
        byte[] allIn = new byte[0];
        if (fxInPath != null) {
            try {
                allIn = java.nio.file.Files.readAllBytes(java.nio.file.Path.of(fxInPath));
            } catch (java.nio.file.NoSuchFileException e) {
                allIn = new byte[0];
            }
        }
        int fxLen = 23;
        int nRec = 0;
        if (allIn.length >= fxLen) {
            nRec = allIn.length / fxLen;
        } else if (allIn.length == 0) {
            nRec = 0;
        } else {
            nRec = 0;
            wsEof = "Y";
        }
        int pos = 0;
        while (true) {
            if (pos >= nRec) {
                wsEof = "Y";
            } else {
                byte[] rec = new byte[fxLen];
                System.arraycopy(allIn, pos * fxLen, rec, 0, fxLen);
                curFxId = new byte[8];
                System.arraycopy(rec, 0, curFxId, 0, 8);
                curFxCcy = new String(rec, 3 + 8 - 8 + 5, 3, java.nio.charset.StandardCharsets.ISO_8859_1);
                curFxCcy = new String(rec, 8, 3, java.nio.charset.StandardCharsets.ISO_8859_1);
                byte[] amtBytes = new byte[12];
                System.arraycopy(rec, 11, amtBytes, 0, 12);
                curFxAmount = parseSignLeadingSeparate(amtBytes, 2);
                pos++;
                if (true) {
                    p1000Convert();
                }
                continue;
            }
            if (wsEof.equals("Y")) break;
        }
        if (fxOutPath != null) {
            java.nio.file.Files.write(java.nio.file.Path.of(fxOutPath), outBuf.toByteArray());
        }
    }

    private void p1000Convert() throws Exception {
        String collEnv = System.getenv("DIOCLE_COLLATION");
        boolean isEbcdic = "EBCDIC".equals(collEnv);
        curFoId = new byte[8];
        System.arraycopy(curFxId, 0, curFoId, 0, 8);
        curFoCcy = curFxCcy;
        boolean known;
        if (isEbcdic) {
            known = ebcdicEquals(curFxCcy, "USD") || ebcdicEquals(curFxCcy, "EUR") || ebcdicEquals(curFxCcy, "GBP") || ebcdicEquals(curFxCcy, "JPY") || ebcdicEquals(curFxCcy, "INR") || ebcdicEquals(curFxCcy, "CHF");
        } else {
            known = curFxCcy.equals("USD") || curFxCcy.equals("EUR") || curFxCcy.equals("GBP") || curFxCcy.equals("JPY") || curFxCcy.equals("INR") || curFxCcy.equals("CHF");
        }
        java.math.BigDecimal foValue;
        if (!known) {
            foValue = java.math.BigDecimal.ZERO.setScale(2);
            curStatus = "UC";
        } else {
            int found = -1;
            for (int i = 0; i < 5; i++) {
                boolean eq;
                if (isEbcdic) eq = ebcdicEquals(wsRateCcy[i], curFxCcy);
                else eq = wsRateCcy[i].equals(curFxCcy);
                if (eq) { found = i; break; }
            }
            if (found < 0) {
                foValue = java.math.BigDecimal.ZERO.setScale(2);
                curStatus = "NR";
            } else {
                java.math.BigDecimal prod = curFxAmount.multiply(wsRate[found]);
                java.math.BigDecimal rounded = prod.setScale(2, java.math.RoundingMode.HALF_UP);
                foValue = truncToS911V99(rounded);
                curStatus = "OK";
            }
        }
        byte[] foZzz = formatSignLeadingSeparate(foValue, 11, 2);
        byte[] foPrint = formatEdited(foValue);
        java.io.ByteArrayOutputStream r = new java.io.ByteArrayOutputStream();
        r.write(curFoId, 0, 8);
        r.write(curFoCcy.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1), 0, 3);
        r.write(foZzz, 0, foZzz.length);
        r.write(foPrint, 0, foPrint.length);
        r.write(curStatus.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1), 0, 2);
        outBuf.write(r.toByteArray(), 0, 46);
    }

    public static void main(String[] args) throws Exception {
        Fxconv p = new Fxconv();
        p.p0000Main();
    }

    static java.math.BigDecimal parseSignLeadingSeparate(byte[] b, int scale) {
        int n = b.length;
        boolean neg = false;
        int start = 0;
        if (n > 0 && (b[0] == (byte) '+' || b[0] == (byte) '-')) {
            neg = (b[0] == (byte) '-');
            start = 1;
        }
        StringBuilder sb = new StringBuilder();
        for (int i = start; i < n; i++) {
            byte c = b[i];
            if (c >= '0' && c <= '9') sb.append((char) c);
            else if (c == (byte) ' ') sb.append('0');
            else sb.append((char) c);
        }
        if (sb.length() == 0) sb.append('0');
        java.math.BigInteger unscaled = new java.math.BigInteger(sb.toString());
        if (neg) unscaled = unscaled.negate();
        return new java.math.BigDecimal(unscaled, scale);
    }

    static byte[] formatSignLeadingSeparate(java.math.BigDecimal v, int intDigits, int fracDigits) {
        int total = intDigits + fracDigits;
        java.math.BigDecimal sc = v.setScale(fracDigits, java.math.RoundingMode.UNNECESSARY);
        java.math.BigInteger un = sc.unscaledValue();
        boolean neg = un.signum() < 0;
        java.math.BigInteger abs = un.abs();
        String d = abs.toString();
        while (d.length() < total) d = "0" + d;
        if (d.length() > total) d = d.substring(d.length() - total);
        char s = neg ? '-' : '+';
        String out = s + d;
        return out.getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
    }

    static byte[] formatEdited(java.math.BigDecimal v) {
        boolean neg = v.signum() < 0;
        java.math.BigDecimal a = v.abs().setScale(2, java.math.RoundingMode.UNNECESSARY);
        java.math.BigInteger un = a.unscaledValue();
        java.math.BigInteger[] qr = un.divideAndRemainder(java.math.BigInteger.valueOf(100));
        String intPart = qr[0].toString();
        int fracInt = qr[1].intValue();
        String fracStr = (fracInt < 10 ? "0" : "") + Integer.toString(fracInt);
        String twelve = intPart;
        while (twelve.length() < 12) twelve = "0" + twelve;
        if (twelve.length() > 12) twelve = twelve.substring(twelve.length() - 12);
        int firstSig = -1;
        for (int i = 0; i < 12; i++) {
            if (twelve.charAt(i) != '0') { firstSig = i; break; }
        }
        char[] out = new char[19];
        out[0] = neg ? '-' : ' ';
        out[16] = '.';
        int[] dpos = {1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14, 15};
        for (int i = 0; i < 12; i++) out[dpos[i]] = twelve.charAt(i);
        out[17] = fracStr.charAt(0);
        out[18] = fracStr.charAt(1);
        if (firstSig == -1) {
            for (int i = 0; i < 11; i++) out[dpos[i]] = ' ';
            out[4] = ' ';
            out[8] = ' ';
            out[12] = ' ';
        } else {
            for (int i = 0; i < 11; i++) {
                if (i < firstSig) out[dpos[i]] = ' ';
            }
            out[4] = (firstSig <= 2) ? ',' : ' ';
            out[8] = (firstSig <= 5) ? ',' : ' ';
            out[12] = (firstSig <= 8) ? ',' : ' ';
        }
        return new String(out).getBytes(java.nio.charset.StandardCharsets.ISO_8859_1);
    }

    static java.math.BigDecimal truncToS911V99(java.math.BigDecimal v) {
        java.math.BigInteger un = v.unscaledValue();
        java.math.BigInteger limit = java.math.BigInteger.TEN.pow(13);
        java.math.BigInteger maxAbs = limit.subtract(java.math.BigInteger.ONE);
        if (un.abs().compareTo(maxAbs) > 0) {
            java.math.BigInteger abs = un.abs().remainder(limit);
            un = un.signum() < 0 ? abs.negate() : abs;
            return new java.math.BigDecimal(un, 2);
        }
        return v;
    }

    static boolean ebcdicEquals(String a, String b) {
        try {
            byte[] ba = a.getBytes("Cp037");
            byte[] bb = b.getBytes("Cp037");
            if (ba.length != bb.length) return false;
            for (int i = 0; i < ba.length; i++) if (ba[i] != bb[i]) return false;
            return true;
        } catch (Exception e) {
            return a.equals(b);
        }
    }
}
