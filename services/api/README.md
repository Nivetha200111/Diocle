# services/api

Status: **read-only slice working.** It serves saved converter runs to the portal. Not yet implemented: upload, starting runs, SSE event streaming.

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /runs` | Runs under `runs/` (newest first): program, certified, rounds, calls, estimated cost |
| `GET /runs/{id}` | One run per [`contracts/run.schema.json`](../../contracts/run.schema.json): agent trace, verification before/after, model usage, Java diff |
| `GET /runs/{id}/source` | The original COBOL (program + copybooks) and the run's Java, per `$defs.source`; not served for visitor runs |
| `GET /runs/{id}/schema` | The run's copybooks as SQL tables with the SQLite round-trip proof (`contracts/sql-schema.schema.json` plus `runId`); computed by the verifier once per sample, no model; not served for visitor runs |

## Visitor imports: uncompilable originals are skipped first
Before any model call, `deliver.py --public` asks the verifier's compile-only job (in the sandbox, see
[`services/verifier` README](../verifier/README.md)) whether GnuCOBOL `-std=ibm` can build each candidate program, in
analyzer order. A program that cannot is listed as `skipped` with the reason
`the original does not compile under GnuCOBOL -std=ibm: <message>`, calls no model, and does not use up one of the
`DIOCLE_PUBLIC_MAX_PROGRAMS` (3) slots: the next compilable convertible program takes its place. Bounds per import:
`DIOCLE_PUBLIC_MAX_PRECHECK` (12) programs checked and `DIOCLE_PUBLIC_PRECHECK_SECONDS` (240) in total; programs
over the line limit or past the 3-program cap are never checked. If the sandbox is busy past the wait or unreachable
twice, the pre-check stops for that import and the remaining programs proceed unchecked, as before. The check runs as a
subprocess of the verifier with only `PATH`, `LANG`, `LC_ALL` and `DIOCLE_SANDBOX_URL` in its environment. Unreadable output from it is logged (last 300 characters of its stderr) and the delivery record gets `precheck` (`checked`, `stopped` with the reason, `notes`). Not exercised in a real container: every sandbox test (compile and verify) uses the sandbox's HTTP handler in-process on a developer machine. The compile path's setuid/kill/cleanup as root, the tmpfs, memory and pids limits and the hung-gcc path (a stuck cobc killed at 30 s / the 60 s job limit) have NOT been run in the container. After a deploy someone must rebuild and recreate the sandbox (`docker compose ps` and image ids show it is the new image), run `docker compose exec api python -I -m diocle_verifier.precheck <sample dir>` once, and confirm it answers `ok` or `fail` (not `unknown`).

## Run
```sh
cd services/api
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn diocle_api.app:app --port 8000
.venv/bin/python -m pytest -q
```
`DIOCLE_RUNS_DIR` overrides where runs are read from. `DIOCLE_WEB_ORIGINS` sets the allowed CORS origins (default: localhost ports 3000 and 3001). The API makes no model calls.
