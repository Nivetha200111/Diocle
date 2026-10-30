import java.nio.file.*;
import java.util.*;

/** Test driver: the same operation lines as probe.cob.tmpl, run on DioKsds (conformance against the real GnuCOBOL handler). */
public class KsdsProbe {
    public static void main(String[] a) throws Exception {
        DioKsds f = DioKsds.select("KFILE", 12, 2, 4, a[0]);
        StringBuilder out = new StringBuilder();
        for (String l : Files.readAllLines(Paths.get(a[1]), java.nio.charset.StandardCharsets.ISO_8859_1)) {
            l = String.format("%-14s", l).substring(0, 14) + String.format("%-6s", l.length() > 14 ? l.substring(14) : "");
            String op = l.substring(0, 2), mode = l.substring(2, 4), key = l.substring(4, 8), data = l.substring(8, 14);
            String rec = "XX" + key + data;
            switch (op) {
                case "OP": { String m = mode.equals("IN") ? "INPUT" : mode.equals("OU") ? "OUTPUT" : "I-O"; f.open(m); out.append(op + mode + " " + f.status()); break; }
                case "CL": f.close(); out.append(op + " " + f.status()); break;
                case "WR": f.write(rec); out.append(op + " " + f.status()); break;
                case "RW": try { f.rewrite(rec); } catch (IllegalStateException e) { System.out.print(out); System.out.println("KEYCHANGE"); return; } out.append(op + " " + f.status()); break;
                case "DL": f.delete(key); out.append(op + " " + f.status()); break;
                case "RK": if (a[0].equals("SEQUENTIAL")) f.readNext(); else f.read(key); out.append(op + " " + f.status() + (f.status().equals("00") ? " " + f.record() : "")); break;
                case "RN": f.readNext(); out.append(op + " " + f.status() + (f.status().equals("00") ? " " + f.record() : "")); break;
                case "S1": f.start("=", key); out.append(op + " " + f.status()); break;
                case "S2": f.start(">=", key); out.append(op + " " + f.status()); break;
                case "S3": f.start(">", key); out.append(op + " " + f.status()); break;
            }
            out.append('\n');
        }
        System.out.print(out);
    }
}
