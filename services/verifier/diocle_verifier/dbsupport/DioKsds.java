import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/**
 * Diocle support for converted programs that use KEYED (INDEXED / VSAM KSDS-style) files. The verifier compiles ITS OWN
 * copy of this file over any file of the same name in the converted sources, so it cannot be changed by the conversion.
 *
 * Stand-in: this class reproduces the observable behaviour of GnuCOBOL's INDEXED file handler (Berkeley DB) for the
 * verified subset: one RECORD KEY (no alternate keys, no DUPLICATES), ACCESS SEQUENTIAL / RANDOM / DYNAMIC, OPEN
 * INPUT / OUTPUT / I-O, READ, READ NEXT, WRITE, REWRITE, DELETE, START (=, >=, >), CLOSE. It is NOT IBM VSAM. OPEN EXTEND on a
 * keyed file is not supported (it throws). The original COBOL runs on the real GnuCOBOL handler; the verifier checks
 * this class against that handler with randomised operation sequences, and compares the final file contents.
 *
 * Records and keys are Strings with one char per byte (latin-1). Keys order byte-wise, unsigned, whatever the program's
 * collating sequence (GnuCOBOL's handler does the same). Every method returns the two-character FILE STATUS the COBOL
 * statement would set: "00" ok, "10" end of file, "21" sequence error, "22" duplicate key, "23" record not found,
 * "35" file not found, "41" already open, "42" not open, "43" no current record, "46" read after end of file,
 * "47" not open for input, "48" not open for output, "49" not open for I-O. After a status other than "00" the
 * record returned by record() is undefined: do not use it. File contents are saved when the file is closed and when
 * the program ends (the implicit close at STOP RUN).
 */
public final class DioKsds {
    public static final int MAX_RECORDS = 20000;
    private static final long MAX_BYTES = 8L << 20;

    private final String dd;
    private final int recLen, keyOff, keyLen;
    private final char access;  // 'S' sequential, 'R' random, 'D' dynamic
    private final TreeMap<String, String> map = new TreeMap<>();
    private String mode = null;          // null = closed; "INPUT", "OUTPUT", "I-O"
    private String last = "00";
    private String cur = "";             // the record area of the last successful read
    // position for READ NEXT: next record is the first key > pos (or >= pos when inclusive); atEnd = end of file already reported
    private String pos = null;
    private boolean inclusive = false, atEnd = false;
    private String lastRead = null;      // key of the current record (sequential REWRITE/DELETE), null = none
    private String lastWritten = null;   // key of the last record written (sequential access ordering)
    private boolean saved = true;
    private static final List<DioKsds> ALL = new ArrayList<>();

    private DioKsds(String dd, int recLen, int keyOff, int keyLen, char access) {
        this.dd = dd; this.recLen = recLen; this.keyOff = keyOff; this.keyLen = keyLen; this.access = access;
    }

    /** SELECT name ASSIGN TO dd ... ACCESS MODE accessMode, with the record layout: RECORD KEY at byte keyOffset (0-based). */
    public static synchronized DioKsds select(String dd, int recordLength, int keyOffset, int keyLength, String accessMode) {
        char a = accessMode.toUpperCase().charAt(0);
        if ("SRD".indexOf(a) < 0 || recordLength <= 0 || keyLength <= 0 || keyOffset < 0 || keyOffset + keyLength > recordLength)
            throw new IllegalArgumentException("DioKsds.select: bad record or key description");
        if (ALL.isEmpty()) {
            Runtime.getRuntime().addShutdownHook(new Thread(() -> { for (DioKsds f : ALL) f.flush(); }));
        }
        DioKsds f = new DioKsds(dd, recordLength, keyOffset, keyLength, a);
        ALL.add(f);
        return f;
    }

    public String status() { return last; }
    public String record() { return cur; }

    private String key(String record) {
        if (record.length() != recLen) throw new IllegalArgumentException("DioKsds: record must be " + recLen + " bytes, got " + record.length());
        return record.substring(keyOff, keyOff + keyLen);
    }
    private String fkey(String key) {
        if (key.length() != keyLen) throw new IllegalArgumentException("DioKsds: key must be " + keyLen + " bytes, got " + key.length());
        return key;
    }
    private String done(String s) { last = s; return s; }
    private String current() { String c = lastRead; lastRead = null; return c; }

    private Path path() {
        String p = System.getenv("DD_" + dd);
        if (p == null || p.isEmpty()) throw new IllegalStateException("DioKsds: DD_" + dd + " is not set");
        return Paths.get(p);
    }

    public String open(String openMode) {
        if (mode != null) return done("41");
        String m = openMode.toUpperCase();
        if (m.equals("EXTEND")) throw new IllegalStateException("OPEN EXTEND on a keyed file is not in the verified subset");
        if (!m.equals("INPUT") && !m.equals("OUTPUT") && !m.equals("I-O")) throw new IllegalArgumentException("open mode " + openMode);
        map.clear();
        if (!m.equals("OUTPUT")) {
            Path p = path();
            if (!Files.isRegularFile(p)) return done("35");
            try {
                if (Files.size(p) > MAX_BYTES) throw new IllegalStateException("DioKsds: keyed file over the size cap");
                String data = new String(Files.readAllBytes(p), StandardCharsets.ISO_8859_1);
                if (data.length() % recLen != 0) throw new IllegalStateException("DioKsds: " + dd + " is not a whole number of records");
                for (int i = 0; i < data.length(); i += recLen) { String r = data.substring(i, i + recLen); map.put(key(r), r); }
            } catch (IOException e) { throw new IllegalStateException("DioKsds: cannot read " + dd, e); }
        } else {
            saved = false;
        }
        mode = m; pos = map.isEmpty() ? null : map.firstKey(); inclusive = true;  // GnuCOBOL: the first READ NEXT returns the record that was first when the file was opened
         atEnd = false; lastRead = null; lastWritten = null;
        return done("00");
    }

    public String close() {
        if (mode == null) return done("42");
        flush();
        mode = null;
        return done("00");
    }

    private synchronized void flush() {
        if (mode == null || mode.equals("INPUT") || saved) return;
        StringBuilder sb = new StringBuilder();
        for (String r : map.values()) sb.append(r);
        try { Files.write(path(), sb.toString().getBytes(StandardCharsets.ISO_8859_1)); saved = true; }
        catch (IOException e) { throw new IllegalStateException("DioKsds: cannot write " + dd, e); }
    }

    public String write(String record) {
        lastRead = null;
        if (mode == null || mode.equals("INPUT") || (access == 'S' && mode.equals("I-O"))) return done("48");
        String k = key(record);
        if (access == 'S' && lastWritten != null && k.compareTo(lastWritten) <= 0) return done("21");
        if (map.containsKey(k)) return done("22");
        if (map.size() >= MAX_RECORDS) throw new IllegalStateException("DioKsds: more than " + MAX_RECORDS + " records");
        map.put(k, record); saved = false; lastWritten = k;
        return done("00");
    }

    public String rewrite(String record) {
        if (mode == null || !mode.equals("I-O")) return done("49");
        String k = key(record);
        if (access == 'S') {
            String c = current();
            if (c == null) return done("43");
            if (!k.equals(c)) throw new IllegalStateException("REWRITE changes the record key: not in the verified subset");
        } else if (!map.containsKey(k)) {
            return done("21");
        }
        map.put(k, record); saved = false;
        return done("00");
    }

    /** DELETE: sequential access deletes the record last read; random and dynamic delete the record whose key is given. */
    public String delete(String key) {
        if (mode == null || !mode.equals("I-O")) return done("49");
        String k;
        if (access == 'S') { k = current(); if (k == null) return done("43"); }
        else { k = fkey(key); if (!map.containsKey(k)) return done("23"); }
        map.remove(k); saved = false; lastRead = null;
        return done("00");
    }

    /** READ ... (by RECORD KEY): random and dynamic access. */
    public String read(String key) {
        if (access == 'S') throw new IllegalStateException("READ by key needs ACCESS RANDOM or DYNAMIC");
        lastRead = null;
        if (mode == null || mode.equals("OUTPUT")) return done("47");
        String k = fkey(key);
        String r = map.get(k);
        if (r == null) return done("23");
        cur = r; lastRead = k; pos = k; inclusive = false; atEnd = false;
        return done("00");
    }

    /** READ NEXT (or plain READ in sequential access). */
    public String readNext() {
        if (access == 'R') throw new IllegalStateException("READ NEXT needs ACCESS SEQUENTIAL or DYNAMIC");
        lastRead = null;
        if (mode == null || mode.equals("OUTPUT")) return done("47");
        if (atEnd) return done("46");
        Map.Entry<String, String> e = pos == null ? (map.isEmpty() ? null : map.firstEntry())
                : inclusive ? map.ceilingEntry(pos) : map.higherEntry(pos);
        if (e == null) { atEnd = true; lastRead = null; return done("10"); }
        cur = e.getValue(); lastRead = e.getKey(); pos = e.getKey(); inclusive = false;
        return done("00");
    }

    /** START KEY relation key; relation is "=", ">=" or ">". Sequential and dynamic access. */
    public String start(String relation, String key) {
        if (access == 'R') throw new IllegalStateException("START needs ACCESS SEQUENTIAL or DYNAMIC");
        lastRead = null;
        if (mode == null || mode.equals("OUTPUT")) return done("47");
        String k = fkey(key);
        Map.Entry<String, String> e = relation.equals(">") ? map.higherEntry(k) : map.ceilingEntry(k);
        if (e != null && relation.equals("=") && !e.getKey().equals(k)) e = null;
        if (!relation.equals("=") && !relation.equals(">=") && !relation.equals(">")) throw new IllegalArgumentException("START relation " + relation);
        lastRead = null;
        if (e == null) { atEnd = true; return done("23"); }
        pos = e.getKey(); inclusive = true; atEnd = false; lastRead = null;
        return done("00");
    }
}
