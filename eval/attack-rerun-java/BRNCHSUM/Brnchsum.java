import java.io.OutputStream;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
public class Brnchsum {
    static byte[] wsPrev = new byte[]{32,32,32,32};
    static BigDecimal wsCount = BigDecimal.ZERO;
    static BigDecimal wsTotal = BigDecimal.ZERO;
    static BigDecimal wsOd = BigDecimal.ZERO;
    static BigDecimal wsAvg = BigDecimal.ZERO;
    static BigDecimal wsAllCount = BigDecimal.ZERO;
    static BigDecimal wsAllTotal = BigDecimal.ZERO;
    static BigDecimal wsAllOd = BigDecimal.ZERO;
    static byte[] curBranch = new byte[4];
    static BigDecimal curBalance = BigDecimal.ZERO;
    static OutputStream out;
    static boolean ebcdicMode = false;
    public static void main(String[] args) throws Exception {
        p0000Main();
    }
    private static void p0000Main() throws Exception {
        String brinPath = System.getenv("DD_BRIN");
        String broutPath = System.getenv("DD_BROUT");
        String coll = System.getenv("DIOCLE_COLLATION");
        String clk = System.getenv("DIOCLE_CLOCK");
        ebcdicMode = "EBCDIC".equals(coll);
        if (clk != null && clk.length() == 0) {
        }
        byte[] all = new byte[0];
        if (brinPath != null && Files.exists(Paths.get(brinPath))) {
            all = Files.readAllBytes(Paths.get(brinPath));
        }
        int recLen = 18;
        int n = all.length / recLen;
        out = Files.newOutputStream(Paths.get(broutPath));
        wsPrev[0]=32; wsPrev[1]=32; wsPrev[2]=32; wsPrev[3]=32;
        wsCount = BigDecimal.ZERO;
        wsTotal = BigDecimal.ZERO;
        wsOd = BigDecimal.ZERO;
        wsAvg = BigDecimal.ZERO;
        wsAllCount = BigDecimal.ZERO;
        wsAllTotal = BigDecimal.ZERO;
        wsAllOd = BigDecimal.ZERO;
        for (int i=0;i<n;i++) {
            int off=i*recLen;
            curBranch[0]=all[off];
            curBranch[1]=all[off+1];
            curBranch[2]=all[off+2];
            curBranch[3]=all[off+3];
            curBalance = decodeBalance(all, off+12);
            p1000Account();
        }
        if (wsCount.compareTo(BigDecimal.ZERO)>0) {
            p2000Break();
        }
        byte[] allBr = new byte[]{65,76,76,32};
        BigDecimal avg;
        if (wsAllCount.compareTo(BigDecimal.ZERO)>0) {
            BigDecimal q = wsAllTotal.divide(wsAllCount,2,RoundingMode.HALF_UP);
            avg = storeAvg(q);
            wsAvg = avg;
        } else {
            wsAvg = BigDecimal.ZERO;
            avg = wsAvg;
        }
        writeRecord(allBr, wsAllCount, wsAllTotal, avg, wsAllOd);
        out.close();
    }
    private static void p1000Account() throws Exception {
        boolean same = Arrays.equals(curBranch, wsPrev);
        if (!same && wsCount.compareTo(BigDecimal.ZERO)>0) {
            p2000Break();
        }
        System.arraycopy(curBranch,0,wsPrev,0,4);
        wsCount = storeCount(wsCount.add(BigDecimal.ONE));
        wsAllCount = storeCount(wsAllCount.add(BigDecimal.ONE));
        wsTotal = storeTotal(wsTotal.add(curBalance));
        wsAllTotal = storeTotal(wsAllTotal.add(curBalance));
        if (curBalance.compareTo(BigDecimal.ZERO)<0) {
            wsOd = storeOd(wsOd.add(BigDecimal.ONE));
            wsAllOd = storeOd(wsAllOd.add(BigDecimal.ONE));
        }
    }
    private static void p2000Break() throws Exception {
        BigDecimal q = wsTotal.divide(wsCount,2,RoundingMode.HALF_UP);
        wsAvg = storeAvg(q);
        byte[] b = Arrays.copyOf(wsPrev,4);
        writeRecord(b, wsCount, wsTotal, wsAvg, wsOd);
        wsCount = BigDecimal.ZERO;
        wsTotal = BigDecimal.ZERO;
        wsOd = BigDecimal.ZERO;
    }
    private static BigDecimal decodeBalance(byte[] d,int o) {
        BigDecimal v = BigDecimal.ZERO;
        for(int i=0;i<11;i++){
            int by = d[o+i/2] & 255;
            int nib = (i%2==0)?((by>>4)&15):(by&15);
            v = v.multiply(BigDecimal.TEN).add(BigDecimal.valueOf(nib));
        }
        int last = d[o+5] & 255;
        int sign = last & 15;
        if(sign==13){
            v=v.negate();
        }
        v=v.movePointLeft(2);
        return v;
    }
    private static BigDecimal storeCount(BigDecimal v){
        BigDecimal t=v.setScale(0,RoundingMode.DOWN);
        BigDecimal m=BigDecimal.valueOf(10000);
        return t.remainder(m);
    }
    private static BigDecimal storeOd(BigDecimal v){
        BigDecimal t=v.setScale(0,RoundingMode.DOWN);
        BigDecimal m=BigDecimal.valueOf(1000);
        return t.remainder(m);
    }
    private static BigDecimal storeTotal(BigDecimal v){
        BigDecimal t=v.setScale(2,RoundingMode.DOWN);
        BigDecimal m=BigDecimal.valueOf(100000000000L);
        BigDecimal a=t.abs().remainder(m);
        if(t.signum()<0 && a.signum()!=0){
            a=a.negate();
        }
        a=a.setScale(2,RoundingMode.UNNECESSARY);
        return a;
    }
    private static BigDecimal storeAvg(BigDecimal v){
        BigDecimal t=v.setScale(2,RoundingMode.DOWN);
        BigDecimal m=BigDecimal.valueOf(1000000000L);
        BigDecimal a=t.abs().remainder(m);
        if(t.signum()<0 && a.signum()!=0){
            a=a.negate();
        }
        a=a.setScale(2,RoundingMode.UNNECESSARY);
        return a;
    }
    private static String formatCountField(BigDecimal v,int w){
        String dig=v.abs().setScale(0,RoundingMode.UNNECESSARY).toPlainString();
        if(dig.length()>w){
            dig=dig.substring(dig.length()-w);
        }
        StringBuilder sb=new StringBuilder();
        for(int i=dig.length();i<w;i++) sb.append(' ');
        sb.append(dig);
        return sb.toString();
    }
    private static char digChar(int[] d,int k,int first){
        if(first==-1) return ' ';
        if(k<first) return ' ';
        return (char)('0'+d[k]);
    }
    private static String formatSignedField(BigDecimal v){
        boolean neg=v.signum()<0;
        BigDecimal a=v.abs();
        BigDecimal centsBD=a.movePointRight(2).setScale(0,RoundingMode.UNNECESSARY);
        long cents=centsBD.longValueExact();
        long intPart=cents/100L;
        int frac=(int)(cents%100L);
        int[] d=new int[9];
        long tmp=intPart;
        for(int i=8;i>=0;i--){d[i]=(int)(tmp%10L);tmp/=10L;}
        int first=-1;
        for(int i=0;i<9;i++){if(d[i]!=0){first=i;break;}}
        boolean c1=intPart>=1000000L;
        boolean c2=intPart>=1000L;
        if(first==-1){c1=false;c2=false;}
        StringBuilder sb=new StringBuilder(15);
        sb.append(neg?'-':' ');
        for(int k=0;k<3;k++) sb.append(digChar(d,k,first));
        sb.append(c1?',':' ');
        for(int k=3;k<6;k++) sb.append(digChar(d,k,first));
        sb.append(c2?',':' ');
        sb.append(digChar(d,6,first));
        sb.append(digChar(d,7,first));
        sb.append((char)('0'+d[8]));
        sb.append('.');
        sb.append((char)('0'+frac/10));
        sb.append((char)('0'+frac%10));
        return sb.toString();
    }
    private static void writeRecord(byte[] br,BigDecimal cnt,BigDecimal tot,BigDecimal avg,BigDecimal od) throws Exception {
        String sCnt=formatCountField(cnt,4);
        String sTot=formatSignedField(tot);
        String sAvg=formatSignedField(avg);
        String sOd=formatCountField(od,3);
        out.write(br,0,4);
        out.write(sCnt.getBytes(StandardCharsets.ISO_8859_1));
        out.write(sTot.getBytes(StandardCharsets.ISO_8859_1));
        out.write(sAvg.getBytes(StandardCharsets.ISO_8859_1));
        out.write(sOd.getBytes(StandardCharsets.ISO_8859_1));
    }
}
