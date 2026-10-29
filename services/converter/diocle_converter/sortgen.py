"""Deterministic DFSORT/SYNCSORT SORT-step emulation: no model calls, pure Python (same spirit as schema.py).

generate_sort_class() turns one analyzer SortSpec dict (services/analyzer/diocle_analyzer/jcl.py's
SortSpec.fields: list of (start, length, format, "A"|"D") 1-based tuples, plus option_equals) into a
standalone Java class. It is one step of a JCL job pipeline (see pipeline.py): it reads its input DD's
fixed-length records, sorts them major key first, minor key(s) after (COBOL/DFSORT SORT FIELDS=(...) lists
keys in that order already, so composing java.util.Comparator in field order via .thenComparing(...) gives
the right precedence with no extra work), and writes the sorted records to its output DD.

Key comparison by format:
- CH: raw byte compare over the key's byte range, in the job's collation. This mirrors
  services/verifier/diocle_verifier/multi.py's own _sort_key() convention exactly, which the rest of this
  codebase already uses to decide sort order when generating verification inputs: EBCDIC bytes are compared
  unsigned (Java's `String.getBytes("Cp037")` then an unsigned byte-array compare), ASCII/Latin-1 bytes are
  compared unsigned too. "Collation" here is a byte encoding choice, not a locale: CH keys are compared on
  the encoded bytes, never on Java's default (UTF-16 code point) String.compareTo, which would silently
  reorder records whenever two collations disagree (exactly the EBCDIC-vs-ASCII trap this fixture's hand
  written Acctmtch.java was deliberately left with, see samples/account-match/java-conversion/Acctmtch.java).
- ZD/PD/BI: numeric formats are out of this v1's scope beyond what the analyzer already recognizes; those
  keys could only reach here if the analyzer had treated them as parseable, so generate_sort_class() parses
  the raw characters of the key range as an unsigned decimal integer wide enough for the field (sufficient for
  ZD-with-no-sign-nibble and the fixed-width BI/PD v1 needs); a real PD/BI/signed-ZD decoder is future work and
  is flagged in a comment in the generated source, not silently guessed at, since the actual fixture this
  pass ships against (QMKD010/SORTTXN) only uses CH keys.
- "A"/"D": ascending or descending comparator direction per key, via Comparator.reversed() on a descending key.

Stability (OPTION EQUALS, and the default when it is absent): the generated code always uses
Collections.sort(List, Comparator), which the JDK guarantees is a stable sort (implemented as a stable
merge sort; see java.util.Collections#sort javadoc). When optionEquals is true this gives exactly DFSORT's
OPTION EQUALS semantics (ties keep their relative input order) for free. When optionEquals is false, real
DFSORT/SYNCSORT tie order on a key collision is implementation- and installation-defined (not guaranteed by
the product itself), so using a stable sort regardless is a deliberate, documented default: it can only be
*more* deterministic than the mainframe tool it emulates, never less, and it never needs to re-derive
"whatever DFSORT's internal tie-break happens to be" to match byte for byte. See the module's test for
whether the shipped fixture actually exercises a tie (it currently does not: SORTIN.txt's three records all
have distinct 8-byte keys), noted there for the verifier-agent to consider adding a tie case.

Record format: one record per line, newline-terminated (the same "line" format
services/verifier/diocle_verifier/runners.py's read_records()/write_records() use for fixed-width COBOL
records in this codebase -- see samples/account-match/jcl/SORTIN.txt, which is 19-byte records separated by
"\\n", not a true fixed-length byte stream with no separators). record_length is still required and checked,
so a malformed input file (wrong LRECL) fails loudly instead of silently misreading keys.

On-disk byte encoding is always ISO-8859-1 / latin-1 (one Java char == one stored byte), matching
runners.py's read_records()/write_records() convention exactly: "collation" is never a different file
encoding, it is which charset the CH key's bytes get *re-encoded into before comparing* (see multi.py's
_sort_key(): it takes a latin-1 Python string and does value.encode("cp037" if ebcdic else "latin-1")).
The generated Java mirrors that precisely: read/write the whole record as ISO-8859-1, but for a CH key
comparison, first re-encode just that key's substring from ISO-8859-1 into the collation's charset (Cp037
for ebcdic, i.e. a no-op re-encode for ascii) and compare those bytes unsigned.
"""

from __future__ import annotations

_CHARSET = {"ebcdic": "Cp037", "ascii": "ISO-8859-1"}
_FILE_CHARSET = "ISO-8859-1"  # always: see module docstring


def _key_comparator(start: int, length: int, fmt: str, order: str) -> str:
    """One Comparator<byte[]> expression (over whole records, as raw ISO-8859-1 bytes) for one sort key."""
    lo, hi = start - 1, start - 1 + length  # SortSpec.fields is 1-based start; Java slicing is 0-based
    if fmt == "CH":
        expr = f"DiocleSort.compareKeyBytes(a, {lo}, {hi}, b, {lo}, {hi}, CHARSET)"
    else:  # ZD/PD/BI: see module docstring -- unsigned decimal digits read from the key's byte range
        expr = f"DiocleSort.compareUnsignedDigits(a, {lo}, {hi}, b, {lo}, {hi})"
    if order == "D":
        return f"(a, b) -> -({expr})"
    return f"(a, b) -> {expr}"


def generate_sort_class(spec: dict, class_name: str, record_length: int, collation: str) -> str:
    """Java source for a standalone SORT-step class. spec is a SortSpec-shaped dict:
    {"fields": [[start, length, format, "A"|"D"], ...], "optionEquals": bool, "unsupported": str|None}.

    Reads DD_<class_name's step input> is not assumed here: the DD env var names are the pipeline's
    job (see pipeline.py), which passes them as args[0] (input DD env var name) and args[1] (output DD env
    var name) so one generated class can be reused for any step without baking DD names into the class.
    """
    if spec.get("unsupported"):
        raise ValueError(f"cannot generate a SORT class for an unsupported spec: {spec['unsupported']}")
    fields = spec.get("fields") or []
    if not fields:
        raise ValueError("SortSpec has no fields to sort by")
    if record_length <= 0:
        raise ValueError(f"record_length must be positive, got {record_length}")
    for start, length, fmt, order in fields:
        if start < 1 or length < 1 or start - 1 + length > record_length:
            raise ValueError(f"key (start={start}, length={length}) does not fit in a {record_length}-byte record")
    if collation not in _CHARSET:
        raise ValueError(f"unsupported collation {collation!r}; expected one of {sorted(_CHARSET)}")
    charset = _CHARSET[collation]

    comparators = [_key_comparator(start, length, fmt, order) for start, length, fmt, order in fields]
    chain = comparators[0]
    for extra in comparators[1:]:
        chain += f"\n            .thenComparing({extra})"

    key_summary = ", ".join(f"({s},{l},{f},{o})" for s, l, f, o in fields)
    return f'''// GENERATED by diocle_converter.sortgen -- deterministic, no model call. Do not hand-edit.
// SORT FIELDS=({key_summary}) OPTION {"EQUALS" if spec.get("optionEquals") else "(absent; stable sort used anyway, see sortgen.py)"}
// Record length: {record_length} bytes, one record per newline-terminated line.
// On-disk bytes: ISO-8859-1 (one char per byte), matching diocle_verifier.runners' convention.
// Collation: {collation} -- CH keys are re-encoded into {charset} before comparing (see sortgen.py docstring).
import java.nio.charset.Charset;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class {class_name} {{
    static final int RECORD_LENGTH = {record_length};
    static final Charset FILE_CHARSET = Charset.forName("{_FILE_CHARSET}");
    static final Charset CHARSET = Charset.forName("{charset}");  // used only to re-encode CH keys, never for file I/O

    public static void main(String[] args) throws Exception {{
        String inputDd = args.length > 0 ? args[0] : "SORTIN";
        String outputDd = args.length > 1 ? args[1] : "SORTOUT";
        Path inPath = Path.of(System.getenv("DD_" + inputDd));
        Path outPath = Path.of(System.getenv("DD_" + outputDd));
        List<byte[]> records = new ArrayList<>();
        for (String line : Files.readAllLines(inPath, FILE_CHARSET)) {{
            byte[] record = line.getBytes(FILE_CHARSET);
            if (record.length != RECORD_LENGTH) {{
                throw new IllegalStateException("record length " + record.length + " != " + RECORD_LENGTH
                        + " (LRECL mismatch): " + line);
            }}
            records.add(record);
        }}
        Comparator<byte[]> comparator = {chain};
        Collections.sort(records, comparator);  // stable: ties keep input order (see sortgen.py docstring)
        List<String> out = new ArrayList<>();
        for (byte[] record : records) out.add(new String(record, FILE_CHARSET));
        Files.write(outPath, out, FILE_CHARSET);
    }}
}}

final class DiocleSort {{
    private DiocleSort() {{}}

    /** CH key comparison: a[aLo,aHi) / b[bLo,bHi) are ISO-8859-1 bytes straight from the record (see
     * sortgen.py docstring); re-encode each key's characters into `charset` (the job's collation: Cp037
     * for EBCDIC, a no-op for ASCII/ISO-8859-1) and compare those bytes unsigned -- never Java's default
     * (signed, UTF-16) String.compareTo, which would silently use the wrong order whenever the collation
     * is not plain ASCII. */
    static int compareKeyBytes(byte[] a, int aLo, int aHi, byte[] b, int bLo, int bHi, Charset charset) {{
        byte[] ak = recode(a, aLo, aHi, charset), bk = recode(b, bLo, bHi, charset);
        int n = Math.min(ak.length, bk.length);
        for (int i = 0; i < n; i++) {{
            int av = ak[i] & 0xFF, bv = bk[i] & 0xFF;
            if (av != bv) return Integer.compare(av, bv);
        }}
        return Integer.compare(ak.length, bk.length);
    }}

    private static byte[] recode(byte[] record, int lo, int hi, Charset charset) {{
        String key = new String(record, lo, hi - lo, Charset.forName("{_FILE_CHARSET}"));
        return key.getBytes(charset);
    }}

    /** ZD/PD/BI keys (v1 scope, see sortgen.py docstring): the key's bytes read as unsigned decimal digit
     * characters ('0'-'9'), compared numerically. Not a full packed/binary/signed decoder. */
    static int compareUnsignedDigits(byte[] a, int aLo, int aHi, byte[] b, int bLo, int bHi) {{
        long av = 0, bv = 0;
        for (int i = aLo; i < aHi; i++) av = av * 10 + Character.digit(a[i] & 0xFF, 10);
        for (int i = bLo; i < bHi; i++) bv = bv * 10 + Character.digit(b[i] & 0xFF, 10);
        return Long.compare(av, bv);
    }}
}}
'''
