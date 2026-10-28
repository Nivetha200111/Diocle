// Hosted builds (NEXT_PUBLIC_DIOCLE_HOSTED=1) show only views backed by real data. The API's /config says
// whether starting a delivery needs the admin passcode.
import { useEffect, useState } from "react";
import { API_URL } from "./runs";

export const HOSTED = process.env.NEXT_PUBLIC_DIOCLE_HOSTED === "1";

export const LINKS = {
  diocle: "https://github.com/Nivetha200111/Diocle",
  legacy: "https://github.com/Nivetha200111/quillmark-mainframe",
  target: "https://github.com/Nivetha200111/quillmark-java",
  evidence: "https://github.com/Nivetha200111/quillmark-modern/pull/3",
  certified: "https://github.com/Nivetha200111/Diocle#what-certified-means-and-does-not",
  buildLog: "https://github.com/Nivetha200111/Diocle/blob/main/docs/BUILD_LOG.md",
};

export type ApiConfig = { hosted: boolean; startNeedsPasscode: boolean };

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
