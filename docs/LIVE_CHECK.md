# Live check of the README's claims

Checked against the live site https://diocle.vercel.app (API under `/api`) on **Fri Oct 30, 2026, 22:25 to 22:45 IST** (16:55 to 17:15 UTC).
Engine commit read over SSH (read-only): `e93f2f7`; origin/main is ahead of it only by web strings and docs.
"Pass" means the behaviour was observed on the live site or engine in this check. "Not checked" means it was not exercised live (a cost limit, an
admin-only route, or nothing stored to look at); such features are labelled experimental in the README and the web pages. Nothing here was faked.

Public budget used by this check: **$0.0056** of the daily public pool (the pool's `spentTodayUsd` went from 1.3343 to 1.3399 of $2.00; the sample
pool from 0.1236 to 0.1292 of $1.00). That is one "Convert a sample now" press (run cost $0.0032 at list prices) and one public ask (hard cap $0.01).
No delivery, no repository creation, no admin endpoint and no upload was used.

| # | Feature (README claim) | How checked | IST | Result | Notes |
|---|---|---|---|---|---|
| 1 | API is up | `GET /api/health` | 22:25 | pass | `{"status":"ok"}` |
| 2 | Public budget and live-button limits | `GET /api/config` | 22:25 | pass | $2.00 daily budget, samples pool $1.00, asks enabled, 2 bundled clips, uploads not allowed |
| 3 | Runs list with real runs | `GET /api/runs` | 22:25 | pass | 35 runs when the check started; my convert press adds a labelled live sample run |
| 4 | Stored run with breaker trace (CHQCLR) | `GET /api/runs/chqclr-20261028-214355` | 22:26 | pass | 2 of 24 designed inputs broke it, repaired, certified |
| 5 | COBOL and Java source of a run | `GET /api/runs/{id}/source` for CHQCLR, INTACCR, ACCTRPT, ADDFEE | 22:26 | pass | 200 for all four |
| 6 | Copybooks as SQL schema | `GET /api/runs/{id}/schema` for the same four | 22:26 | pass | DDL returned, "no model involved" |
| 7 | Stored behaviour claims (verified documentation) | `GET /api/runs/interest-accrual-20261030-091344` | 22:30 | pass | run record has a `behavior` object; CHQCLR has none (not generated for it) |
| 8 | Re-verify on fresh inputs (public, free), sequential file | `POST /api/runs/chqclr-20261028-214355/reverify` | 22:26 | pass | 1,004 of 1,004, seed 487906970, stdout and exit code match, 1.8 s |
| 9 | Embedded SQL subset on the SQLite stand-in, in the sandbox | `POST /api/runs/db2-account-report-20261030-111941/reverify` | 22:26 | pass | 1,380 of 1,380, 2.9 s. This re-verifies a stored run; a conversion from scratch was not re-run |
| 10 | Mutation testing "How strong is this verification?" | `GET` before (404, none stored), `POST /api/runs/chqclr-20261028-214355/mutation`, then the run page | 22:26 | pass | 75 s; 40 mutants run: 14 killed, 21 survived, 5 did not compile (score 0.4); no model call. A survivor is a coverage question, not a verdict |
| 11 | Mutation report stored and served | `GET /api/runs/{id}/mutation` after the POST | 22:28 | pass | 200 with the same report (see note in row 10 on the earlier 404) |
| 12 | Smallest-reproducer route | `GET /api/runs/{id}/reproducers` | 22:26 | pass (route only) | returns an empty list for every run: `minimize` is skipped when a sandbox is configured, so the card is empty on the live site. Extraction itself: **not checked live, labelled experimental** |
| 13 | Live button "Convert a sample now" | `POST /api/samples/live {"sample":"addfee"}` once, polled | 22:30 | pass | run `addfee-20261030-170052` certified, 1,005 of 1,005 held-out inputs, 3 min 9 s, $0.003225 |
| 14 | Live button "Read a printout" (Muse Wonder) | not pressed | | not checked | the printout limit for this visitor was already used today (`/config`: `visitorLeft: 0`); not worked around |
| 15 | Ask the original program (voice question) | `POST /api/asks` once, clip `fee-overdrawn`, polled | 22:35 | pass | transcript "What happens to the fee when the account is overdrawn??" by `muse-voice-transcribe-1.0`; 2 claims, 2 confirmed by GnuCOBOL, 5 examples run; 36 s. Transcription price is flagged unconfirmed by the API |
| 16 | Bundled voice clip served | `GET /api/asks/clips/fee-overdrawn` | 22:36 | pass | 206 |
| 17 | Keyed (VSAM-style) files verified on the indexed handler | `cobc --info` in the API and sandbox containers over SSH (read-only) | 22:20 | not checked (infrastructure pass) | both containers report `indexed file handler : BDB`, but no keyed run is stored and no public route converts one. **Labelled experimental** (README, coverage matrix) |
| 18 | DB2 subset conversion from scratch | not run (costed) | | not checked | only the stored run's re-verify (row 9). Labelled as stored/re-verified only |
| 19 | Whole-repository build check, deliveries, create-target repository | not run (costed, admin-only or creates repositories) | | not checked | **labelled experimental**; `GET /api/deliveries` lists a stored delivery (200) but its build card was not inspected |
| 20 | Home page: headline panel, CHQCLR COBOL and Java, schema.sql tab, Try the sample, evidence strip, "What certified means" | Playwright (Chrome) screenshot and page text | 22:28 | pass | 37/45, 4/10, 14/15 and $0.69 shown and equal to `docs/MEASUREMENT.md`; screenshot inspected |
| 21 | Mission control: live buttons, ask panel | page text | 22:28 | pass | both buttons and the ask panel present; printout button disabled with its reason (row 14) |
| 22 | Evidence page: scoreboard, coverage matrix, canonical delivery | page text | 22:28 | pass | scoreboard computed from 26 certified runs, 11 programs. The live page still showed the old "Against a human reviewer" block and "Keyed files: in progress, not merged"; both are changed in the source (this branch) and appear after the next web deploy |
| 23 | Bug of the day wall | page text | 22:28 | pass | CHQCLR fee 20.00 vs 0.00 and debit -121.23 vs 0.00 cards, "checked against the live run record" |
| 24 | Run page panels | page text for CHQCLR | 22:28 | pass | Re-verify, "How strong is this verification?", schema.sql, source, model card present. No "Smallest reproducer" or "Behaviour spec" card for this run (no data, see rows 7 and 12) |
| 25 | Delivery page | page text | 22:28 | pass (loads) | no delivery started |
| 26 | Canonical delivery PR quillmark-modern#4 exists | HTTP HEAD to GitHub | 22:44 | pass | 200; its CI run (6,719 inputs) was not re-run |
| 27 | Quickstart script | `sh scripts/quickstart.sh --check` in a clean worktree | 22:30 | pass (check only) | prerequisites found, falls through to no-key mode as documented; the 12 s and 2.5 min timings and `--no-key` itself were not re-run |
| 28 | Measurement numbers (37/45, 4/10, 14/15, $0.69) | compared the home page and README with `docs/MEASUREMENT.md` | 22:30 | pass (consistent) | the measurement itself was not re-run (spend), so these are copied, not re-measured |
| 29 | Engine is the latest code | SSH `git log -1` on `/opt/diocle` | 22:20 | pass | `e93f2f7`, 2026-10-30 21:19 IST |
| 30 | VS Code extension, Notepad++ script, MCP server | local tools | | not checked | not part of the live site |

## Summary

- **Pass: 25** (rows 1 to 13, 15, 16 and 20 to 29; row 12 passes for the route only).
- **Fail: 0.**
- **Not checked: 5 rows** (14, 17, 18, 19, 30), plus the extraction half of row 12.

## What changed in the README and web because of this

- Keyed files, the whole-repository build check, smallest-reproducer extraction and verified documentation from the command line are labelled **experimental** in the README Limits block and the web coverage matrix.
- README statements that the mutation job and verified documentation "have not been run on the live engine" were replaced by what was observed (rows 7, 10, 15); the statement that the DB2 subset "was not exercised in the real sandbox container" was replaced by row 9, with the from-scratch conversion marked not re-run.
- The "Against a human reviewer" multiplier on the Evidence page was removed (raw model spend only).

## Not verified, so not claimed

The "Read a printout" button today, keyed-file conversion on the site, a from-scratch DB2-subset conversion, deliveries and the build check, the smallest-reproducer card with data, and the measurement's own numbers (copied from `docs/MEASUREMENT.md`, not re-run).
