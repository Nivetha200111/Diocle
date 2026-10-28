# services/api

Status: **read-only slice working.** It serves saved converter runs to the portal. Not yet implemented: upload, starting runs, SSE event streaming.

| Endpoint | Returns |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `GET /runs` | Runs under `runs/` (newest first): program, certified, rounds, calls, estimated cost |
| `GET /runs/{id}` | One run per [`contracts/run.schema.json`](../../contracts/run.schema.json): agent trace, verification before/after, model usage, Java diff |

## Run
```sh
cd services/api
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn diocle_api.app:app --port 8000
.venv/bin/python -m pytest -q
```
`DIOCLE_RUNS_DIR` overrides where runs are read from. `DIOCLE_WEB_ORIGINS` sets the allowed CORS origins (default: localhost ports 3000 and 3001). The API makes no model calls.
