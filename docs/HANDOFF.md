# Hand-off: where Diocle stands and what is next

Read this first in every session; update it as you build (see CLAUDE.md, "Session hand-off").
Newest state at the top of each section. Dates are 2026, times IST unless marked UTC.
This repository is public: never write secrets, passcodes, personal details or employer names here.

## Current state (updated 2026-10-28 late evening)

**Pitch.** Diocle is a verification layer for AI-written COBOL→Java: "AI writes the code. Diocle checks it
against the original before anyone has to trust it." Never claim proof for all inputs (README, "What certified
means and does not"). Meta Global AI Developer Hackathon, Indie track, submit by **Nov 4, 9 PM ET**.

**Live product.**
- Site: https://diocle.vercel.app (Vercel Hobby, project root `apps/web`, env `NEXT_PUBLIC_DIOCLE_HOSTED=1`,
  `NEXT_PUBLIC_DIOCLE_API_URL=/api`, `DIOCLE_API_ORIGIN=https://65-20-92-159.sslip.io`). Vercel redeploys on
  every push to `main`.
- Engine: Vultr, Mumbai, Ubuntu 24.04, 1 vCPU / 2 GB, IP `65.20.92.159`, HTTPS at `65-20-92-159.sslip.io`
  (sslip.io + Caddy; no domain bought). Code in `/opt/diocle`; config in `/opt/diocle/deploy/diocle.env`
  (secrets, root-only, never print it) and `/opt/diocle/deploy/.env` (`DIOCLE_API_DOMAIN`).
- Containers (`deploy/docker-compose.api.yml`): `api` (holds secrets), `sandbox` (no secrets, internal network
  only, read-only rootfs), `caddy`. Update: `ssh root@65.20.92.159`, `cd /opt/diocle && git pull && cd deploy &&
  docker compose -f docker-compose.api.yml up -d --build`. Rebuilding restarts the api and kills a running
  delivery.
- SSH key `~/.ssh/diocle` exists only on the original Mac. On a new machine: create a key
  (`ssh-keygen -t ed25519 -f ~/.ssh/diocle`), add the `.pub` in the Vultr console (server → Settings → SSH keys,
  or use the Vultr web console to append it to `/root/.ssh/authorized_keys`).
- Seeded data: 14 runs (12 certified) and 4 deliveries via `deploy/seed-runs.sh root@65.20.92.159`. Public
  re-verify checked on 11 runs, all pass in about 2 s each.
- Admin passcode (`DIOCLE_ADMIN_TOKEN`) was generated on the server; the owner has it. It unlocks
  "Deliver as a pull request" on the Delivery page.

**Visitor imports: built, deployed, currently OFF** (`DIOCLE_PUBLIC_IMPORTS=0` on the server). Goal from the
owner: judges must be able to *use* it, i.e. import any public GitHub repo and have Muse Spark convert it, open
access without a passcode, but secure. Built (commits 6d71ca9..fb3fa74): contract delivery v0.3, sandbox
service (`services/verifier/diocle_verifier/sandbox.py`, `runners._exec` forwards when `DIOCLE_SANDBOX_URL` is
set), hardened clone (no symlinks, 300 MB cap, `DIOCLE_IMPORT_ANY=1` only for visitor runs), `public.py`
(daily USD budget, per-visitor limit, 3 programs x 1500 lines), import form on the Delivery page, `#run=<id>`
deep links. A real visitor import through the live site certified ACCTMTCH 1585/1585 through the sandbox.
It was switched off after a security review found the problems below. Nothing was exposed: the only import
that ran was our own.

### Security findings to fix before turning visitor imports back on (in order)
1. **Critical: symlink exfiltration.** A program in the sandbox can `ln -sf /proc/1/environ original.out` in
   the shared work dir; the api container (holding the Meta key) then reads it in `runners.read_records` /
   `verify.py` / `diff.py` and the secret lands in public `run.json`. Fix: do every read of program outputs
   inside the sandbox and return records in the `/exec` response (or at least `O_NOFOLLOW` + regular-file
   check + path under workdir) for every api read/write on the work volume.
2. **High: background processes survive a job.** `subprocess.run(timeout=)` kills only the child; a program can
   leave a process that tampers with later builds (forged certification) or plants symlinks in api temp dirs.
   Fix: `start_new_session=True` + `os.killpg` after each job; better, per-job directory shared and api
   `TMPDIR` off the shared volume.
3. **High: sandbox mounts all of `runs/` read-only**, so a visitor program can print other runs, deliver logs,
   `memory.json`. Fix: copy only that job's sample and `java/` into the job's work dir.
4. **Medium: race** in check-busy / admit / Popen lets parallel POSTs start several jobs and bypass the
   budget; ids collide within a second. Fix: process lock, write `delivery.json` (queued) before returning,
   random id suffix.
5. **Medium: a killed job stays "converting" forever** and blocks all starts (409). Fix: record the child PID;
   treat dead PID or max age as failed.
6. **Medium: visitor runs write fix memory** used by the owner's later runs and skill export. Fix: visitor runs
   read memory but never write (pass `--no-memory` or a separate file).
7. **Low: budget ignores unpriced models** (cost None counts as 0) and filters by directory date, not UTC
   `startedAt`. Fix: refuse public imports when the price is unknown; filter on `startedAt`.
After fixing: run all suites, ask the reviewer agent to re-review, redeploy, test isolation on the server
(no secrets/internet in sandbox, symlink test), then set `DIOCLE_PUBLIC_IMPORTS=1`.

Known gap: programs that only DISPLAY (no output file) are skipped as "writes no output file to compare";
stdout could be compared. Seen on github.com/openmainframeproject/cobol-programming-course (17 of 34 programs
convertible; EXEC SQL ones correctly refused). Good test repo for visitor imports.

## Open work (priority order)
1. Security fixes above, then re-enable visitor imports.
2. Frozen evaluation (`eval/run_eval.py`, tag `eval-freeze-1`, 4 unseen programs): FXCONV certified (0 repair
   rounds), CHQCLR certified (1 round), BRNCHSUM **not certified** after 3 rounds / 60 calls, LOANAMRT still
   running on the original Mac at hand-off (results land in eval/; commit them). Write `docs/EVALUATION.md` reporting failures honestly.
3. Breaker test on `samples/loyalty-waiver` (narrow 5000.00 defect): `repair --breaker`. The breaker is
   reported as unproven until it finds a defect other inputs missed.
4. Demo video (under 3 min): one visible failure and repair on the live site, then re-verify.
5. A review from a COBOL maintainer (owner arranges). Module README consistency.

## Done recently
- 2026-10-28: hosted on Vercel + Vultr; fixed `GET /runs` crash on a latin-1 byte (d5e0ecb) and macOS `._*`
  files breaking re-verify (9d8d149); visitor imports built then paused (above).
- quillmark-modern PR #3 (refreshed 6-program delivery, CI green on 6,714 fresh inputs) merged.
- quillmark-java PR #1 merged (from quillmark-mainframe, a z/OS-style PDS export), CI green on 6,709 inputs.
- Earlier history: `docs/BUILD_LOG.md`.

## Repositories (all public, owner Nivetha200111)
Diocle (product); quillmark-legacy → quillmark-modern; quillmark-mainframe → quillmark-java. The bank
"Quillmark Trust & Savings" is fictional and all data is synthetic.

## Working agreements with the owner
- Budget is very tight: flag any cost before incurring it; prefer free tiers. Vultr is about $12/month.
- Secrets: never ask for keys in chat, never read or print `.env` / `diocle.env`; the owner types secrets on
  the server.
- Before every push: `git log origin/main..HEAD`; push only your own commits; ask if others' are present.
  The owner's local edits to `apps/web/next-env.d.ts` and `apps/web/tsconfig.json` are theirs: leave them.
- Small commits, one module each, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Run every touched module's tests (and `npx tsc --noEmit` + `next build` for web) before committing.
- Use the reviewer agent on security-sensitive or large batches of work; it has found real bugs every time.
- The product should look like a real product (no "demo" wording), keeping the 90s retro operator-console look.
- Account creation, payments and repo visibility changes are done by the owner, not by Claude.
