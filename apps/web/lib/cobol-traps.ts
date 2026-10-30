// "For COBOL people" on /evidence: real traps Diocle handles, each with the repository fact it rests on and the evidence on
// this site. Every run id below was checked with GET /runs/<id> on the live engine (Oct 30). Wording rule: "caught on the
// inputs tried", never "proven". A trap with no live evidence says where it is documented instead of linking anything.
const DOCS = "https://github.com/Nivetha200111/Diocle/blob/main";

export type Evidence = { kind: "run"; id: string; label: string } | { kind: "page"; href: string; label: string } | { kind: "doc"; href: string; label: string };

export type Trap = { key: string; title: string; what: string; how: string; evidence: Evidence[]; note?: string };

export const TRAPS: Trap[] = [
  {
    key: "packed", title: "Packed decimals (COMP-3), binary and signed fields",
    what: "A packed field holds two digits per byte with the sign in the last nibble; a zoned field carries its sign in the last digit's zone. Read as text, both are garbage.",
    how: "The analyzer derives each record layout byte by byte from the copybooks (DISPLAY, COMP-3, COMP, COMP-5, all sign modes, REDEFINES, OCCURS), and the verifier compares fixed-length records byte for byte, not as numbers.",
    evidence: [{ kind: "run", id: "pkdpost-20261028-195219", label: "PKDPOST: packed fixed-length posting, 1,037 of 1,037 held-out inputs" }],
  },
  {
    key: "negzero", title: "The sign of zero: -000000000 versus +000000000",
    what: "Both are zero as a number, but they are different bytes. A program that reads the file byte for byte sees a different record.",
    how: "The comparator is byte-exact, not by value. In two INTACCR runs the breaker agent designed an input where the COBOL leaves -000000000 and the Java wrote +000000000; the repair agent fixed it. Caught on the inputs tried, by two different breaker models.",
    evidence: [
      { kind: "run", id: "interest-accrual-20261029-230750", label: "INTACCR run: breaker found it in round 1" },
      { kind: "run", id: "interest-accrual-20261029-234240", label: "INTACCR run: breaker found it in round 3" },
      { kind: "page", href: "/bugs#bug-intaccr-wonder", label: "Bug of the day card" },
    ],
  },
  {
    key: "trunc", title: "TRUNC(STD) overflow wrap",
    what: "Under IBM's TRUNC(STD) a result that does not fit its PIC loses its high-order digits silently. A natural Java translation keeps them.",
    how: "The original is compiled with TRUNC(STD) behaviour, so the Java must wrap the same way. In one INTACCR run the model's first Java kept digits the COBOL field cannot hold (balance 369589314.78 against the COBOL's 9589314.78); the verifier's starting tests caught it before the repair agent was called.",
    evidence: [
      { kind: "run", id: "interest-accrual-20261029-234240", label: "INTACCR run with that starting failure" },
      { kind: "page", href: "/bugs#bug-intaccr-overflow", label: "Bug of the day card" },
    ],
  },
  {
    key: "ibm", title: "IBM versus GnuCOBOL differences",
    what: "The oracle is GnuCOBOL, which is not IBM Enterprise COBOL. Collating order, truncation and DISPLAY defaults differ out of the box.",
    how: "The original is compiled with cobc -std=ibm, IBM's TRUNC(STD) and DISPLAY defaults, and EBCDIC collating order (-fdefault-colseq=EBCDIC). Honest limit: where GnuCOBOL still differs from IBM (intermediate precision, NUMPROC, hex floats) and no captured mainframe output exists, a certificate does not cover it. The generated GitHub Actions re-verify workflow builds GnuCOBOL 3.2 from source because the Ubuntu package rejected the EBCDIC flag.",
    evidence: [
      { kind: "doc", href: `${DOCS}/services/verifier/README.md`, label: "services/verifier/README.md" },
      { kind: "doc", href: `${DOCS}/README.md#not-supported-yet`, label: "README: Not supported yet" },
    ],
  },
  {
    key: "period", title: "PROGRAM-ID without its period",
    what: "IBM's compiler accepts it. GnuCOBOL with -std=ibm rejects it, so the original cannot be built and nothing can be compared.",
    how: "Public imports run a compile-only check before any model call and skip the program with the compiler's reason. The local and admin convert-anyway mode may apply a bounded patch, and then labels the result VERIFIED AGAINST REPAIRED COBOL, never CERTIFIED.",
    evidence: [{ kind: "page", href: "#course-import", label: "Course repository import below: 11 skipped before any model spend" }],
  },
  {
    key: "loop", title: "Programs that never terminate",
    what: "A loop whose exit condition nothing ever sets. The original runs until it is killed, so there is no output to compare.",
    how: "The verifier's time limit stops the original and the run is not certified. The engine currently reports this as a verifier failure rather than saying plainly that the program never ends (a known gap).",
    evidence: [{ kind: "run", id: "cbl0015-20261030-022640", label: "CBL0015 from the public course repository: not certified" }],
  },
  {
    key: "jcl", title: "Whole JCL jobs: SORT step, then a COBOL step",
    what: "A batch job is JCL steps wired together by DD names; the SORT step's output file is the COBOL step's input.",
    how: "The analyzer maps DD names (procs, symbolics, overrides) to datasets, and a job-level check runs one SORT step (SORT FIELDS= with character keys) feeding one COBOL step both ways. Jobs with three or more steps, several SORT steps, COND-gated steps, numeric sort keys, INCLUDE/OMIT and similar are reported as not convertible. This is a library function, not yet wired into the site, CLI or delivery flow.",
    evidence: [{ kind: "doc", href: `${DOCS}/services/verifier/README.md#whole-jcl-job-verification-v1-one-sort-step-feeding-one-cobol-step`, label: "services/verifier/README.md: whole-JCL-job verification" }],
    note: "No live run on this site.",
  },
  {
    key: "sql", title: "Embedded SQL (EXEC SQL) in a named subset",
    what: "DB2 programs read and write tables, so the output includes database state, not only files.",
    how: "A stated subset (db2-subset-1) is rewritten by a small precompiler for the COBOL and run through JDBC for the Java, both on the same seeded database. Output files, stdout, exit code and the final contents of every table touched are compared. The engine is SQLite, a stand-in: equivalent on this engine, for these statements, on the inputs tried. Not real DB2.",
    evidence: [{ kind: "run", id: "db2-account-report-20261030-111941", label: "ACCTRPT: 1,372 of 1,372, ACCOUNTS and AUDIT tables compared" }],
  },
  {
    key: "refused", title: "What is refused, with a reason",
    what: "CICS, IMS (DLI), keyed (INDEXED/RELATIVE) files, EXEC SQL outside the subset, dynamic CALLs whose target is not a literal, CALLs to programs not in the repository, and missing IBM copybooks.",
    how: "The analyzer reports the program as not convertible with the exact reason, and no model money is spent on it. A public sample, CardDemo, analysed locally: 0 of 44 programs convertible (missing IBM copybooks, calls to CEE3ABD and CEEDAYS, dynamic CALLs, CICS, DLI, SQL). Nothing is guessed.",
    evidence: [
      { kind: "doc", href: `${DOCS}/README.md#not-supported-yet`, label: "README: Not supported yet" },
      { kind: "doc", href: `${DOCS}/docs/HANDOFF.md`, label: "docs/HANDOFF.md (CardDemo screening)" },
    ],
    note: "Documented in the repository; no live run on this site.",
  },
];
