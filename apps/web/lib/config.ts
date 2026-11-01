// Hosted builds (NEXT_PUBLIC_DIOCLE_HOSTED=1) show only views backed by real data. The API's /config says
// whether starting a delivery needs the admin passcode.
import { useEffect, useState } from "react";
import { API_URL } from "./runs";

export const HOSTED = process.env.NEXT_PUBLIC_DIOCLE_HOSTED === "1";

export const LINKS = {
  diocle: "https://github.com/Nivetha200111/Diocle",
  legacy: "https://github.com/Nivetha200111/quillmark-mainframe",
  target: "https://github.com/Nivetha200111/quillmark-java",
  evidence: "https://github.com/Nivetha200111/quillmark-modern/pull/4",
  evidenceCi: "https://github.com/Nivetha200111/quillmark-modern/actions/runs/40811476870",
  evidenceDoc: "https://github.com/Nivetha200111/Diocle/blob/main/docs/EVIDENCE.md",
  evaluation: "https://github.com/Nivetha200111/Diocle/blob/main/docs/EVALUATION.md",
  measurement: "https://github.com/Nivetha200111/Diocle/blob/main/docs/MEASUREMENT.md",
  showcase: "https://github.com/Nivetha200111/Diocle/blob/main/docs/SHOWCASE_CHQCLR.md",
  vscode: "https://github.com/Nivetha200111/Diocle/tree/main/editors/vscode",
  museCode: "https://github.com/Nivetha200111/Diocle/tree/main/editors/muse-code",
  certified: "https://github.com/Nivetha200111/Diocle#what-certified-means-and-does-not",
  buildLog: "https://github.com/Nivetha200111/Diocle/blob/main/docs/BUILD_LOG.md",
};

// The one delivery cited everywhere: quillmark-modern#4 (it re-delivers INTACCR; the repo's CI re-verifies all six programs
// under one pinned verifier, which is where these numbers come from). The numbers
// come from that pull request's GitHub Actions run (LINKS.evidenceCi) and docs/EVIDENCE.md; that delivery is not
// in this engine's delivery list, so they are cited here with their source rather than counted live.
export const CANONICAL = {
  pr: "quillmark-modern#4",
  programs: [
    { name: "ACCTMTCH", ci: 1601 },
    { name: "DAYCTRL", ci: 1017 },
    { name: "FEESCHD", ci: 1021 },
    { name: "INTACCR", ci: 1019 },
    { name: "PKDPOST", ci: 1037 },
    { name: "TXNPOST", ci: 1024 },
  ],
  differences: 0,
  // INTACCR re-converted ($0.0344) + the five earlier conversions re-certified at zero model calls ($0.0922).
  modelSpendUsd: 0.13,
};
export const CANONICAL_FRESH_INPUTS = CANONICAL.programs.reduce((n, p) => n + p.ci, 0);

// Runs certified under an older verifier that the current one rejects; kept, and labelled, rather than hidden.
export const SUPERSEDED: Record<string, string> = {
  "intaccr-20261028-191523":
    "Superseded: fails the later byte-exact verifier (-000000000 vs +000000000 on 30 of 1,019 inputs). Re-delivered in quillmark-modern#4.",
};

// What a stored run's own counts cannot tell a reader. Shown on the run; the record is unchanged.
export const RUN_NOTES: Record<string, string> = {
  "chqclr-20261028-214355":
    "Read this count with care: when this run was made, the generator filled this program's shared REDEFINES body with a placeholder, so its held-out records had zero amounts and fees and few distinct outputs (found and fixed Nov 1, 2026). The real values here came from the breaker's designed inputs. A later free audit of this Java on 1,000 well-formed cheques and returns with real amounts: all matched. It also found a malformed record this Java still gets different from the COBOL, a return with a blank body, which no attack tried: certified means on the inputs tried (docs/SHOWCASE_CHQCLR.md).",
  "chqclr-20261028-234854":
    "Read this count with care: when this run was made, the generator filled this program's shared REDEFINES body with a placeholder, so its held-out records had zero amounts and fees (found and fixed Nov 1, 2026; docs/SHOWCASE_CHQCLR.md).",
};

// The program on the front page: the breaker agent made it differ after 1,000 generated held-out records had matched.
export const SAMPLE_RUN = { id: "chqclr-20261028-214355", program: "CHQCLR" };

export const MODELS = {
  hosted: "muse-spark-1.3-contributor",
  open: "accounts/fireworks/models/muse-spark-open",
};

export const GLOSSARY: Record<string, string> = {
  copybook: "A shared COBOL file describing a record layout byte by byte, like a struct definition reused by many programs.",
  EBCDIC: "IBM mainframe character encoding. It sorts letters and digits in a different order from ASCII, so comparisons can change.",
  "TRUNC(STD)": "IBM compiler option: numbers are cut to their declared digits on store, silently dropping high-order digits.",
  JCL: "Job Control Language: the mainframe scripts that run batch programs and tell them which files to read and write.",
  CICS: "IBM's online transaction monitor. Programs that use it are reported, not converted.",
  DB2: "IBM's mainframe database, used through EXEC SQL. Programs that use it are reported, not converted.",
  VSAM: "Mainframe indexed and relative files. Programs that update them are reported, not converted.",
  GnuCOBOL: "The open-source COBOL compiler Diocle uses to run the original program next to the Java.",
  "held-out": "Records generated after the agent finished, written to one file and run once through each program. It never saw them, so it cannot have tuned the Java to them. The counts shown are output records compared.",
};

export type PublicImports = {
  enabled: boolean;
  dailyBudgetUsd: number;
  perVisitorPerDay: number;
  maxPrograms: number;
  maxLines: number;
  spentTodayUsd: number;
  budgetLeft: boolean;
  samples?: SamplesStatus; // the two live buttons; absent on an engine without them
};

// contracts/live-sample.schema.json $defs.status (config.publicImports.samples)
export type ButtonStatus = {
  maxUsd: number; perVisitorPerDay: number; perDay: number; usedToday: number; visitorLeft: number;
  available: boolean; reason: string | null;
};
export type SamplesStatus = {
  enabled: boolean; budgetUsd: number; spentTodayUsd: number | null; busy: string | null;
  convert: ButtonStatus; printout: ButtonStatus;
};

export type ApiConfig = { hosted: boolean; startNeedsPasscode: boolean; publicImports?: PublicImports };

export function useApiConfig(): ApiConfig | null {
  const [config, setConfig] = useState<ApiConfig | null>(null);
  useEffect(() => {
    fetch(`${API_URL}/config`, { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);
  return config;
}
