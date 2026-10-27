# Architecture (DRAFT)

> Draft. Detailed architecture will be added later. Nothing here is implemented yet.

## Overview
Diocle is a pipeline: **upload > analyze > convert > verify > report**.

1. **Upload** (`apps/web` -> `services/api`): COBOL sources and copybooks.
2. **Analyze** (`services/analyzer`): parse programs and copybooks, build a dependency graph, flag risky logic (fraud, payment). Output: `contracts/analysis-report.schema.json`.
3. **Convert** (`services/converter`): copybook trees to SQL schema, COBOL to Java services, generated tests. Uses Muse Spark via the Meta Model API only. Output: `contracts/conversion-output.schema.json`.
4. **Verify** (`services/verifier`): compile the original with GnuCOBOL, run original and converted on the same generated inputs, diff outputs. Optional SonarQube Community scan. Output: `contracts/verification-report.schema.json`.
5. **Report** (`apps/web`): dashboard presenting analysis, conversion, and verification results.

## Modules
| Module | Folder | Notes |
|---|---|---|
| Dashboard | `apps/web` | Next.js |
| API | `services/api` | Python or Node (TBD) |
| Analyzer | `services/analyzer` | |
| Converter | `services/converter` | Muse Spark only |
| Verifier | `services/verifier` | GnuCOBOL |
| Samples | `samples/` | synthetic only |
| Contracts | `contracts/` | JSON Schema |

## Principles
- Contracts first: modules communicate only via the schemas in `contracts/`.
- Muse Spark (Meta Model API) is the only LLM used inside the product.
- Verification is by differential testing, not by trusting model output.
