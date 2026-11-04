import { ExternalLink } from "lucide-react";
import { LINKS } from "@/lib/config";

export const MEASURED_TITLE = "Measured: passing a large test is not the same as matching everywhere";
export const MEASURED_HINT = "15 synthetic COBOL programs, Muse Spark, GnuCOBOL as the judge";

// The measurement behind "4 of 10", shown in full on the home and Evidence pages. Its caveats are the point: do not trim them here.
export function MeasuredBody() {
  return (
    <>
      <dl className="eff-grid home-evidence">
        <div><dt>First translations passing the held-out check of 1,000 random records (3 tries x 15 programs)</dt><dd className="mono">37/45</dd></div>
        <div><dt>Attackable, test-passing translations that differed under attack</dt><dd className="mono">4/10</dd></div>
        <div><dt>Programs certified by a full Diocle run</dt><dd className="mono">14/15</dd></div>
      </dl>
      <p className="home-pr">
        In a separate attack run (one fresh translation per program), the breaker&apos;s designed inputs made four of the ten
        attackable translations that passed the check differ from the original: CHQCLR on malformed numeric fields, and DAYCTRL, INTACCR
        and TXNPOST on the sign of a zero at an overflow boundary (same value, different bytes), by the breaker&apos;s stated reasons. No stored record-level break is a wrong amount on a
        well-formed record; value errors on well-formed records showed up in first translations and in one private-mode run&apos;s printed total. Until Nov 1 the attack compared output records only, so a surviving translation was not checked on its display output under attack. Three of those four had passed all three first-try trials. The three figures count
        different things, so they are not a &ldquo;model alone vs Diocle&rdquo; score. One program, CHQCLR, was not certified in that run. Small sample, one model, synthetic
        programs, about $0.69 of model spend: <a href={LINKS.measurement} target="_blank" rel="noreferrer">method, per-program table and caveats <ExternalLink size={11} /></a>. Re-measured Nov 2 with two flaws in our own check fixed: 4 of 10 again, the same four programs. This is not a defect-detection rate.
      </p>
    </>
  );
}
