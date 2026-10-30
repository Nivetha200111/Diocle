// "Bug of the day" wall: real catches, each tied to a stored run. A card is shown from the LIVE run record only when the
// record still contains the facts the card states (checked by the extractors below). When the engine cannot be reached,
// the repository-sourced fallback values are shown and labelled as such. Nothing here is generated or invented.
import type { Run } from "./runs";

export type Role = "breaker" | "verifier" | "cobol-repair" | "verifier-change";

export type Catch = {
  original: string; // what the COBOL produced
  java: string; // what the AI-written Java produced
  field: string;
  role: Role;
  model: string; // "none (GnuCOBOL and a byte comparison)" for the verifier
  round: string;
  costUsd: number | null;
  costNote?: string;
};

export type CardSpec = {
  key: string;
  title: string;
  program: string;
  runId: string | null; // null: the record is not on the engine; the card says so
  why: string;
  caveat?: string;
  // Repository fallback (also what a repo-only card shows). Values copied from run records / docs, see `source`.
  repo: Catch;
  source: { label: string; href: string };
  // Returns the catch from the live run, or null when the run does not contain it.
  extract?: (run: Run) => Catch | null;
};

const DOCS = "https://github.com/Nivetha200111/Diocle/blob/main/docs";
export const VERIFIER_NONE = "no model: GnuCOBOL and a byte comparison";

const parseDiff = (diff: string) => {
  const m = /^(.+?): original '?(.*?)'? converted '?(.*?)'?(?: \(.*\))?$/.exec(diff.trim());
  return m ? { field: m[1], original: m[2], java: m[3] } : null;
};

const costOf = (run: Run) => run.usage.estimatedCostUsd ?? run.efficiency.estimatedCostUsd ?? null;

// The breaker agent designed an input that broke Java which had already passed; match its counterexample by field and values.
function breakerCatch(field: string, original: string, java: string): (run: Run) => Catch | null {
  return (run) => {
    const hit = (run.breaker?.counterexamples ?? []).map((c) => parseDiff(c.diff)).find((d) => d && d.field === field && d.original === original && d.java === java);
    const ev = run.events.find((e) => e.type === "breaker" && (e.broke ?? 0) > 0);
    if (!hit || !ev) return null;
    const round = ev.round ?? 1;
    const models = [...new Set(run.usage.modelCalls?.filter((c) => c.role === "breaker" && c.round === round).map((c) => c.model) ?? [])];
    if (!models.length) return null;
    const cost = costOf(run);
    return {
      original: hit.original, java: hit.java, field, role: "breaker", model: models.join(", "), round: `breaker attack round ${round}`,
      costUsd: cost, costNote: models.some((m) => m.startsWith("muse-wonder")) ? "est., list prices; Muse Wonder's price is third-party and unconfirmed" : "est., list prices",
    };
  };
}

// The verifier's own starting tests failed on the model's first Java; the repair agent then fixed it.
function startingFailure(field: string, original: string, java: string): (run: Run) => Catch | null {
  return (run) => {
    const hit = run.before?.failingExamples.flatMap((e) => e.fieldDiffs ?? []).find((d) => d.field === field && d.original === original && d.converted === java);
    if (!hit || !run.certified || run.assurance === "certified-against-repaired-cobol") return null;
    return {
      original, java, field, role: "verifier", model: VERIFIER_NONE, round: "starting tests, before any repair",
      costUsd: costOf(run), costNote: "est., list prices",
    };
  };
}

export const CARDS: CardSpec[] = [
  {
    key: "chqclr-fee", title: "Returned-cheque fee came out as 0.00", program: "CHQCLR", runId: "chqclr-20261028-214355",
    why: "A wrong fee on a bounced cheque is a wrong charge on a customer account, and the Java had already passed 1,000 held-out inputs without it.",
    caveat: "The COBOL states no currency, so none is shown. The input carries malformed numeric data, so this shows agreement with GnuCOBOL's handling of bad data, not proven IBM behaviour.",
    repo: { original: "20.00", java: "0.00", field: "CL-FEE", role: "breaker", model: "muse-spark-1.3-contributor", round: "breaker attack round 1", costUsd: 0.017605, costNote: "est., list prices" },
    source: { label: "docs/EVALUATION.md", href: `${DOCS}/EVALUATION.md` },
    extract: breakerCatch("CL-FEE", "20.00", "0.00"),
  },
  {
    key: "chqclr-debit", title: "A debit of -121.23 came out as 0.00", program: "CHQCLR", runId: "chqclr-20261028-214355",
    why: "Money going out of an account was recorded as nothing.",
    caveat: "Same run as the card above; the same malformed-data caveat applies.",
    repo: { original: "-121.23", java: "0.00", field: "CL-DEBIT", role: "breaker", model: "muse-spark-1.3-contributor", round: "breaker attack round 1", costUsd: 0.017605, costNote: "est., list prices" },
    source: { label: "docs/EVALUATION.md", href: `${DOCS}/EVALUATION.md` },
    extract: breakerCatch("CL-DEBIT", "-121.23", "0.00"),
  },
  {
    key: "intaccr-wonder", title: "Negative zero: -000000000 became +000000000", program: "INTACCR", runId: "interest-accrual-20261029-230750",
    why: "When the interest overflows its field the COBOL leaves a negative zero. Downstream programs reading the file byte for byte would see a different record from the one the mainframe wrote.",
    repo: { original: "-000000000", java: "+000000000", field: "OUT-INTEREST", role: "breaker", model: "muse-wonder-1.0", round: "breaker attack round 1", costUsd: 0.619124, costNote: "est., list prices; Muse Wonder's price is third-party and unconfirmed" },
    source: { label: "docs/EVALUATION.md", href: `${DOCS}/EVALUATION.md` },
    extract: breakerCatch("OUT-INTEREST", "-000000000", "+000000000"),
  },
  {
    key: "intaccr-spark", title: "The same negative zero, found by a different agent", program: "INTACCR", runId: "interest-accrual-20261029-234240",
    why: "Two independent runs, two different breaker models, the same hole: evidence that the attack is not luck. This run's breaker found it only in its third attack round, after two rounds of 12 inputs had matched.",
    repo: { original: "-000000000", java: "+000000000", field: "OUT-INTEREST", role: "breaker", model: "muse-spark-1.3", round: "breaker attack round 3", costUsd: 0.41302, costNote: "est., list prices" },
    source: { label: "docs/EVALUATION.md", href: `${DOCS}/EVALUATION.md` },
    extract: breakerCatch("OUT-INTEREST", "-000000000", "+000000000"),
  },
  {
    key: "intaccr-overflow", title: "Balance kept digits the COBOL field cannot hold", program: "INTACCR", runId: "interest-accrual-20261029-234240",
    why: "The COBOL silently drops the high digits of an overflowing field; the first Java kept them. A balance wrong by hundreds of millions, caught before the repair agent was even called.",
    caveat: "This was the model's first Java; the verifier's starting tests caught it and the repair agent fixed it. It is not a catch on the final, certified Java.",
    repo: { original: "9589314.78", java: "369589314.78", field: "OUT-NEW-BAL", role: "verifier", model: VERIFIER_NONE, round: "starting tests, before any repair", costUsd: 0.41302, costNote: "est., list prices" },
    source: { label: "run record", href: "/runs#run=interest-accrual-20261029-234240" },
    extract: startingFailure("OUT-NEW-BAL", "9589314.78", "369589314.78"),
  },
  {
    key: "txnpost-charge", title: "A posting charge of 13.34 was written as 15.00", program: "TXNPOST", runId: "txnpost-20261028-200111",
    why: "One record in the starting tests carried the wrong charge and a balance off by 1.66, enough to fail a reconciliation.",
    caveat: "The model's first Java; the repair agent fixed it before certification. The run record does not state the cause, so none is claimed.",
    repo: { original: "13.34", java: "15.00", field: "POST-CHARGE", role: "verifier", model: VERIFIER_NONE, round: "starting tests, before any repair", costUsd: 0.023508, costNote: "est., list prices" },
    source: { label: "run record", href: "/runs#run=txnpost-20261028-200111" },
    extract: startingFailure("POST-CHARGE", "13.34", "15.00"),
  },
  {
    key: "cbl0014-sign", title: "A printed result lost its plus sign", program: "CBL0014", runId: "cbl0014-20261030-022445",
    why: "Report output is compared as text: +041524 and 041524 are different lines for anything that reads them.",
    caveat: "A visitor's import of public COBOL, not one of our synthetic samples. The model's first Java; the verifier caught it on the first comparison and the repair agent fixed it.",
    repo: { original: "Result: +041524", java: "Result: 041524", field: "stdout line 2", role: "verifier", model: VERIFIER_NONE, round: "starting tests, before any repair", costUsd: 0.002893, costNote: "est., list prices" },
    source: { label: "run record", href: "/runs#run=cbl0014-20261030-022445" },
    extract: (run) => {
      const hit = run.before?.failingExamples.find((e) => e.diff.includes("original 'Result: +041524' converted 'Result: 041524'"));
      if (!hit || !run.certified) return null;
      return { original: "Result: +041524", java: "Result: 041524", field: "stdout line 2", role: "verifier", model: VERIFIER_NONE, round: "starting tests, before any repair", costUsd: costOf(run), costNote: "est., list prices" };
    },
  },
];

// Catches whose run record is NOT on the live engine. Always shown as repository-sourced; never presented as live.
export const REPO_ONLY: CardSpec[] = [
  {
    key: "verifier-negzero", title: "Our own verifier was too lenient", program: "INTACCR", runId: null,
    why: "A stricter byte comparison, added after the frozen evaluation, found that an earlier delivered conversion wrote -000000000 where the COBOL writes +000000000 on about 3% of inputs. The correction is published rather than hidden.",
    repo: { original: "+000000000", java: "-000000000", field: "OUT-INTEREST", role: "verifier-change", model: VERIFIER_NONE, round: "after the frozen evaluation (docs/EVALUATION.md)", costUsd: null, costNote: "not recorded" },
    source: { label: "docs/EVALUATION.md", href: `${DOCS}/EVALUATION.md` },
  },
  {
    key: "badname-cobol", title: "The COBOL itself did not compile: WS-FEES vs WS-FEE", program: "BADNAME", runId: null,
    why: "A name used but never defined stops GnuCOBOL from building the original, so nothing can be compared. The model's COBOL repair loop changed one line and the build passed.",
    caveat: "The run record is not on the live engine: this card comes from the repository's hand-off notes (5 model calls, about $0.0008 for the repair, $0.0039 for the run) and the sample samples/convert-anyway-repo/cobol/BADNAME.cbl. The result is labelled certified against REPAIRED COBOL, not plain certified.",
    repo: { original: "does not compile (undefined WS-FEES)", java: "n/a", field: "WS-FEES", role: "cobol-repair", model: "muse-spark-1.3-contributor (COBOL repair loop)", round: "COBOL repair, before the comparison", costUsd: 0.0039, costNote: "est., from docs/HANDOFF.md" },
    source: { label: "docs/HANDOFF.md", href: `${DOCS}/HANDOFF.md` },
  },
];

// Verifier mutants: deliberately wrong Java written in the unit tests to prove the verifier fails. NOT model output.
export const MUTANTS = [
  { title: "An UPDATE that is off by one", test: "services/verifier/tests/test_sql.py::test_off_by_one_update_is_caught_by_the_table_diff", how: "The table diff after COBOL and after the Java differs in one row." },
  { title: "An INSERT that never happens", test: "services/verifier/tests/test_sql.py::test_missing_insert_is_caught_by_the_row_count", how: "The row counts of the final tables differ." },
];

export const roleLabel = (r: Role) =>
  r === "breaker" ? "Breaker agent" : r === "verifier" ? "Verifier (starting tests)" : r === "cobol-repair" ? "COBOL repair loop" : "Verifier (stricter check)";

export type Resolved = { spec: CardSpec; catch: Catch; live: boolean };

// Live-verified cards; cards whose run exists but no longer contains the catch are counted as unconfirmed and not shown.
export function resolveCards(runs: Record<string, Run>): { shown: Resolved[]; unconfirmed: number } {
  const shown: Resolved[] = [];
  let unconfirmed = 0;
  for (const spec of CARDS) {
    const run = spec.runId ? runs[spec.runId] : undefined;
    const got = run && spec.extract ? spec.extract(run) : null;
    if (got) shown.push({ spec, catch: got, live: true });
    else unconfirmed += 1;
  }
  return { shown, unconfirmed };
}

export const fallbackCards = (): Resolved[] => CARDS.map((spec) => ({ spec, catch: spec.repo, live: false }));
