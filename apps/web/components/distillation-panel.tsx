import { ExternalLink } from "lucide-react";
import { DISTILLATION, LINKS } from "@/lib/config";

const BADGE = { running: "badge-amber", done: "badge-green", "not run": "badge-neutral" } as const;

// Typed from docs/DISTILLATION.md, not read from the engine: the experiment runs outside it. Update both together.
export default function DistillationPanel() {
  return (
    <section className="panel" id="distillation">
      <div className="panel-heading">
        <div>
          <h2>Verified distillation: tuning open weights on checked translations</h2>
          <p>
            GnuCOBOL decides what the model may learn from. <strong>In progress as of {DISTILLATION.asOf}: no tuned model exists yet, and
            no run on this site uses one.</strong>
          </p>
        </div>
      </div>
      <div className="table-scroll evidence-table">
        <table className="data-table">
          <thead><tr><th>Step</th><th>Status</th><th>What happens</th></tr></thead>
          <tbody>
            {DISTILLATION.steps.map((s) => (
              <tr key={s.name}>
                <td>{s.name}</td>
                <td><span className={`badge ${BADGE[s.status]}`}>{s.status}</span></td>
                <td style={{ whiteSpace: "normal" }}>{s.what}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="home-list">
        <li><strong>Teacher is open weights only.</strong> The Meta Model API terms restrict training competing models on hosted outputs, so the code refuses Muse Spark outputs, including every stored hosted run.</li>
        <li><strong>The test is fixed in advance.</strong> Four held-out programs, 12 attempts each for base and tuned, reported whatever the outcome. We claim an improvement only if tuned passes at least 3 more attempts than base.</li>
        <li><strong>A small dataset.</strong> Few programs pass the gates, so there are far fewer examples than the 500 or so Meta suggests. A match on generated inputs is a test, not a proof.</li>
      </ul>
      <p className="home-pr">
        <a href={LINKS.distillation} target="_blank" rel="noreferrer">The plan, written before any model call, and every change to it <ExternalLink size={11} /></a>
        {" · "}Built with Muse Spark Open.
      </p>
    </section>
  );
}
