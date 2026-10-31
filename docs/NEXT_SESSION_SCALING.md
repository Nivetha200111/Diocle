# Next track: make Diocle scale (planned, not built)

> **Status: plan and session prompt only. None of this exists yet.** The product on `main` is feature-locked for the hackathon submission (owner decision, Oct 31 2026). Do the work below on a separate branch and worktree, and do not merge it to `main` or deploy it until the owner says the submission and judging window is over.

## Where the limits are today (from the code and docs, Oct 31)

| Area | Today | Where |
|---|---|---|
| Verification sandbox | one job at a time, one container, no network, no secrets | `services/verifier/diocle_verifier/sandbox.py` (`_job_lock`), `docs/ARCHITECTURE.md` |
| API concurrency | in-process threads; module-level `threading.Lock`s in `reverify.py`, `schema.py`, `public.py` and `deliveries.py`; one `ThreadPoolExecutor` (`deliver.py`) for parallel repository deliveries | `services/api/diocle_api/` (`reverify.py`, `schema.py`, `public.py`, `deliveries.py`, `deliver.py`) |
| Run storage | files under `runs/` on the API host; run list read from disk | `services/api/README.md` (`GET /runs`) |
| Deployment | one Vultr VM, Docker Compose, Caddy, a single API and a single sandbox container | `deploy/` |
| Cost control | per-run caps, a shared public-sample budget, per-visitor and cooldown limits, a kill switch | `deploy/diocle.env.example`, `services/api/diocle_api/livesamples.py` |
| Model calls | Meta Model API, and a partner host for Spark Open (Baseten, Fireworks or Modal, set in `.env`), with per-loop caps and token logging | `services/converter` |

## Goal

Run many conversions and verifications at the same time, for many users, without changing what a certificate means: the same differential test (GnuCOBOL against Java, byte for byte), the same refusals, the same hard cost caps. Prove it with a load test and publish the numbers, including where it breaks.

## Phases (each one proven before the next starts)

0. **Measure first.** A repeatable load test (no model calls: re-verify and the free public paths) against the current single node. Record throughput, latency percentiles and the first thing that breaks. This is the baseline every later claim is compared with.
1. **Job queue, stateless API.** Move long work (convert, verify, mutation, minimize, deliver) behind a queue with workers; the API only enqueues and reads status. Idempotent job ids, retries with a cap, back-pressure with a clear "busy, retry in N s" answer.
2. **Sandbox pool.** N identical sandbox workers, one job per worker at a time (keep the isolation rules), no shared writable state, per-job resource limits, hard timeouts, a reaper for stuck jobs. A security review before any multi-tenant use.
3. **Storage.** Runs and artifacts out of the local disk into a database plus object storage; the run contract stays the same (`contracts/run.schema.json`); a migration for existing runs; the evidence page reads from the new store.
4. **Quotas and cost metering.** Per-tenant and per-day money caps enforced in one place before a model call is made, logged per run; the public-sample budget moves there. Nothing may raise a cap without the owner's OK.
5. **Observability.** Structured logs, metrics (queue depth, sandbox utilisation, model spend per minute), alerts on spend and error rate, one dashboard.
6. **Deploy and scale.** Reproducible infrastructure (compose first, then an orchestrator if the load test says it is needed), zero-downtime deploys, autoscaling on queue depth, a rollback path.
7. **Proof.** Re-run the phase 0 load test after each phase; publish before and after numbers in `docs/`, with the sample size and what was not tested.

## Rules that do not change

- Follow `CLAUDE.md` (contracts first, small commits, tests, no secrets in the repo, synthetic data only, Meta models only in the product, hard cost caps) and `docs/HANDOFF.md`.
- A scaled path must produce byte-identical verdicts to the single-node path on the golden programs. The existing suites (`make test`, CI) must stay green on every commit.
- Never claim a number that was not measured. Label stubs as stubs.
- A reviewer-agent pass before every push; check `git log origin/main..HEAD` first; push only your own commits.
- Do not print or read credential files; do not change the live server, its env file or its DNS without the owner's explicit go.

## Prompt to start the new session

Copy everything below the line into a fresh Claude Code session in a new clone of the repository.

---

You are continuing Diocle, a verification layer for AI-written COBOL to Java conversion (github.com/Nivetha200111/Diocle, public, MIT). Read, in this order: `CLAUDE.md`, `docs/HANDOFF.md`, `docs/NEXT_SESSION_SCALING.md` (this plan), `docs/ARCHITECTURE.md`, `README.md`, and `docs/CLAIMS_TO_EVIDENCE.md`.

Your task: make Diocle scale, following the phases in `docs/NEXT_SESSION_SCALING.md`, starting with phase 0 (a measured baseline). Work only on a new branch (for example `scale/phase-0-baseline`) in a separate git worktree. Do not merge to `main`, push to `main`, or deploy anything until the owner says the hackathon submission and judging window is over; the product on `main` is feature-locked. You may push your branch for backup.

Constraints: contracts first (`contracts/`), small commits with imperative messages and no commit-message trailers, tests with every change (`make test` and CI must stay green), synthetic data only, Meta models only in the product, hard cost caps on every model loop and no cap raised without the owner's OK, never read or print `.env`, `deploy/diocle.env` or any credential file, never commit secrets, and never change the live server without the owner's explicit go. Verdicts must stay byte-identical to the single-node path on the golden programs. Never state a number you did not measure. Run a reviewer-agent pass before each push and check `git log origin/main..HEAD` so you push only your own commits.

Start by (1) summarising the current bottlenecks in your own words from the code, (2) writing the phase 0 load-test plan with what it will and will not measure and its cost (it must not make paid model calls), and (3) asking the owner to confirm it before you build anything. Keep `docs/HANDOFF.md` current as you go ("Current state", "Open work", "Done recently"); it is public, so no secrets, personal details or employer names.
