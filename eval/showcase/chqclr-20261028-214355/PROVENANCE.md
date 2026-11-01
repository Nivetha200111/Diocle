# Stored evidence from run chqclr-20261028-214355 (SYNTHETIC program)

Copied unchanged from the run folder on Nov 1, 2026 so the audit (`eval/audit_chqclr.py`) can run from a clean clone.

- `java/Chqclr.java`: the certified Java. Translated by `muse-spark-1.3-contributor`, then one patch by the repair agent.
- `breaker.json`: every input the breaker designed, the stored differences and the agent's stated reasons.

The Java as it was **before** the repair was not stored, so the stored differences (`20.00` vs `0.00`, `-121.23` vs `0.00`)
cannot be re-run against it. The original's output and the repaired Java's output can: the audit does.
