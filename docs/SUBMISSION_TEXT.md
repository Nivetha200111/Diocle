# Submission text (draft for the owner to paste; every claim is sourced in CLAIMS_TO_EVIDENCE.md)

**Name:** Diocle. **Track:** Indie, Build for Your World. **Video:** the link in the README's first line. **Repo:** https://github.com/Nivetha200111/Diocle. **Live:** https://diocle.vercel.app

**One line.** AI writes the Java; Diocle compares it with the original COBOL, attacks what passes, repairs what differs, and leaves evidence anyone can re-run.

**The problem.** I worked on a COBOL modernization at a global finance company where every translated program was checked by hand. AI can now write the Java in minutes. The bottleneck is deciding whether to accept it: a modernization lead or systems integrator needs to know whether the Java does what the batch program did, on more than the inputs someone thought of.

**What it does.** Muse Spark translates. GnuCOBOL runs the original and a JVM runs the Java on the same generated records, and every output byte, display line and exit code must match. Java that passes is then attacked: Muse Spark designs inputs aimed at where it might differ, each run through both programs. A repair agent with tools fixes observed mismatches and is re-checked on records it never saw. No model certifies; the comparison does. Delivery is a pull request with an equivalence report and CI that re-runs the comparison on fresh inputs.

**The finding.** On 15 synthetic programs with one model, 4 of the 10 attackable translations that passed a held-out check of 1,000 generated records then differed from the original on inputs Muse Spark designed: one on malformed numeric fields, three on a negative-zero sign byte at an overflow boundary. For example, on a returned cheque with a space in its numeric fee, the COBOL on GnuCOBOL charged 20.00 and the Java 0.00. That is byte-level disagreement under GnuCOBOL, not a claim about IBM's compiler, and no stored break is a wrong amount on a well-formed record. Reviewing our own evidence, we also found our generator gave that showcased program near-identical records; we fixed it and published the audit.

**Meta models, by role.** Muse Spark: translator, tool-using repair agent and breaker, in nearly every run. Also, with thinner evidence, stated per model in docs/META_MODELS.md: Muse Spark Open on partner hosts (private mode, optional cross-check and guard review), Muse Wonder (reading a printed listing), Muse Voice Transcribe (a spoken question answered from what GnuCOBOL confirmed), and Muse Code (a local plugin). Not every run uses every model.

**Try it in three minutes.** Open the site and press Try the sample (re-checks stored Java on fresh records, no model). Open the CHQCLR run for the mismatch, the repair and the list of which checks ran. Or locally with no key: `sh scripts/quickstart.sh --no-key` (1,027 of 1,027 output records; a re-check of stored Java, not a new conversion).

**Limits.** Testing on stated inputs, not a formal proof. GnuCOBOL, not IBM Enterprise COBOL. SQLite and Berkeley DB stand in for the DB2 and VSAM subsets. The breaker attacks single-file record programs. Optional guard and cross-check steps can be skipped, and a run says so. Synthetic programs, small sample, one model in the measurement. Model spend is about two cents median per certified run; compute, hosting and human review are not measured. No customers or pilots are claimed.

**Built in the window.** First commit Oct 27, 2026; the repository lists what was built here and what pre-existed. All programs and data are synthetic.
