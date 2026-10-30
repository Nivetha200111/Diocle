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

// The program on the front page: the breaker agent broke it after 1,000 held-out inputs had passed.
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
  "held-out": "Inputs generated after the agent finished. It never saw them, so it cannot have tuned the Java to them.",
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
