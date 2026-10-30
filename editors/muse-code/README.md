# Diocle for Muse Code (local plugin)

A **local** Muse Code plugin: an MCP server (Python standard library only), a skill and four slash commands that let Meta's
Muse Code coding agent use Diocle on your machine: analyze COBOL, re-verify a conversion against the original with GnuCOBOL,
read run records, and (only if you turn it on) run one capped real conversion.

**This is not an official Meta integration and not a marketplace plugin.** It is a local plugin you install from this checkout.
Tested with Muse Code 1.4.14 on macOS (see "What was tested" for exactly how far).

## Install

Needs Muse Code (`muse`), Python 3.11+, and for the verify and convert tools GnuCOBOL 3.2, JDK 21 and a Diocle venv
(`sh scripts/quickstart.sh --check` shows what is missing; a first `sh scripts/quickstart.sh --no-key` builds `services/converter/.venv`).

```sh
sh editors/muse-code/install.sh --dry-run     # print what would change
sh editors/muse-code/install.sh               # stage a copy, `muse plugins install` it (user scope)
muse plugins inspect diocle                   # review the MCP server, then approve it yourself:
muse plugins approve diocle:mcp_server:diocle
sh editors/muse-code/install.sh --uninstall   # remove it again
```

The script changes only: a staged copy under `~/.local/share/diocle-muse/plugin` (with `mcp/repo.txt` = this checkout's path), the
Muse Code plugin registration, and with `--allow-convert` an empty marker file `~/.config/diocle-muse/allow-convert`. Muse Code
requires review of a third-party plugin's MCP server; the script never approves it for you. Re-running `install.sh` after a change
makes Muse Code ask for a new approval. If a Diocle venv exists at `services/*/.venv` the server uses it; otherwise set
`DIOCLE_PYTHON`. `DIOCLE_REPO` overrides the checkout path.

**Install is user-scope and changes your global Muse Code configuration** (plugin registry under your Muse data directory); `--uninstall` reverses it. The `allow-convert` marker is only as strong as Muse Code's own file-write permission: anything that can write that file (including the agent, if you grant it write access to your config directory) can turn convert on, so keep the agent's writes off `~/.config` and keep the converter's `--max-usd` cap in mind.

## What you get

| Piece | What |
|---|---|
| `diocle_analyze(path)` | Programs, files, record layouts, risk flags, and the refusal reason for programs that cannot be verified. Free. |
| `diocle_verify_stored(sample, random?)` | Re-verify `samples/<name>/certified-java` against the original with GnuCOBOL, as `scripts/quickstart.sh --no-key`. Free, a few seconds. |
| `diocle_live_run(run_id?)` | Read-only GET of a run summary from `https://diocle.vercel.app/api` (no id: list recent runs). |
| `diocle_explain(run)` | Plain-English summary of `runs/<id>` from `run.json` and its verification report. No model. |
| `diocle_coverage()` | What converts and what is refused, with reasons, from the README and the samples. |
| `diocle_mutation_report(run)` | Reads a stored `mutation-report.json`; produces nothing. |
| `diocle_convert(sample, max_usd?)` | **Real model spend** on your own Meta key. Disabled by default; see below. |
| Resources | `diocle://samples/<name>/src/*.cbl` and `copybooks/*.cpy` (read-only synthetic COBOL). |
| Prompts | `certify-a-cobol-program`, `explain-a-run`. |
| Skill `diocle` | Tells the agent the workflow: analyze, explain refusals, ask before spending, convert, verify, report honestly ("matched on the tested inputs, not proven equivalent"). |
| Commands | `/diocle-analyze`, `/diocle-verify`, `/diocle-convert`, `/diocle-explain`. |

### `diocle_convert` (money)

Off unless you set `DIOCLE_MCP_ALLOW_CONVERT=1` for the server or run `install.sh --allow-convert` (Muse Code starts plugin servers
with a small fixed environment, so the marker file is the plugin route). It runs `python -m diocle_converter run samples/<name>
--no-memory --max-usd N`, always capped: default 0.10, hard maximum 0.25, anything else is rejected. The key is never an argument:
the converter reads `META_MODEL_API_KEY` from the repo's gitignored `.env` (see `.env.example`) as in `scripts/quickstart.sh`. The
skill makes the agent ask you before calling it. A conversion typically costs a few cents (the stored run for this sample cost
USD 0.047 with memory; a public run USD 0.0032 for another program); the Muse Code agent's own tokens are billed separately by Muse Code.

## Limits and security

- Paths are resolved and must stay inside the repo root; symlinks pointing outside are rejected; sample names, run ids and run
  directories are regex-validated; no shell (argv arrays only); output capped at 16 KB; per-tool timeouts (analyze 90 s, verify
  240 s, convert 900 s); secrets are scrubbed from output; subprocesses get a small environment (the model variables only for convert).
- Nothing is written outside a temp directory, except `diocle_convert`, whose converter writes its run record to the repo's
  gitignored `runs/`. `diocle_live_run` only talks to `diocle.vercel.app`.
- Tools work on repo paths: your own COBOL has to be inside the checkout. `diocle_convert` converts bundled samples only.
- The verify tools compile and run what is in the repo; run the server only for your own agent.
- Results mean the Java matched GnuCOBOL on the tested inputs, not that it is proven equivalent.

## Tests

```sh
DIOCLE_PYTHON=services/converter/.venv/bin/python services/converter/.venv/bin/python -m pytest editors/muse-code/tests
```

29 tests: JSON-RPC handshake, tools/resources/prompts lists, protocol errors, each tool (the analyzer and verifier tests run the real
tools and need cobc and a JDK; they skip otherwise), path and symlink escape attempts, validation errors, convert disabled by
default, cap and key-argument rejection, secret scrubbing, type-confused and oversized messages (the server must not die), resource symlink confinement, refused redirects, process-group kill on timeout, install.sh's update path against a stub `muse`, a local stub for the live-run tool.

## What was tested with the real `muse` binary (Muse Code 1.4.14, macOS)

- **Verified:** `muse plugins validate` passes; the plugin installs, shows `review_needed`, and after approval `muse exec` starts the
  server: Muse Code logged a successful stdio handshake and discovery of 7 tools, 45 resources and 2 prompts
  (`transcripts/connect-check.jsonl`, rendered to a short real capture). The tools were also run directly over JSON-RPC
  (`transcripts/direct-tool-calls.txt`, not through Muse Code).
- **Verified with real model-driven runs (Oct 31, owner's own Muse login; five headless `muse exec --json --disable-approval --disable-shell --disable-write --disable-web-tools --max-model-steps 12` runs; transcripts in `transcripts/run-1.jsonl` to `run-5.jsonl`: the muse event stream wrapped with timings, the local username path replaced by `~` and the temp directory by `$TMPDIR`).** Every prompt named the tools, and run 3 pre-authorised spend ("I agree to spend up to USD 0.10"); what the runs show is that Muse Code chose, sequenced and called the tools and reported their output, not that it decided anything about spending.
  1. *analyze + re-verify* (62 s): Muse Code called `diocle_analyze` and `diocle_verify_stored` on `samples/interest-accrual` and reported INTACCR convertible, 9 risk flags, and the checked-in Java matched on 1027 of 1027 inputs, with the caveat.
  2. *live run lookup*: `diocle_live_run` read the stored CHQCLR run (certified, 1006/1006, the attacker tried 24 inputs and broke 2, both fixed).
  3. *convert and certify* (310 s): `diocle_convert` (enabled by the owner with `install.sh --allow-convert`, capped at USD 0.10): CERTIFIED, 1027 of 1027, 2 model calls, 6,930 in / 21,735 out tokens, est. USD 0.016957 (Muse Code's own agent tokens are billed separately).
  4. *guardrail*: `diocle_analyze` on `/etc` and `../../../etc` were both refused ("path is outside the Diocle repository").
  5. *guardrail*: with the allow-convert marker removed again, `diocle_convert` was refused ("diocle_convert is disabled ... Nothing was run. Ask the owner; do not try to work around this.").
  An earlier attempt at run 1 (not kept in this repo; from the owner's session, not from a transcript) failed with `No module named 'jsonschema'` because the checkout had no Python environment yet: run `sh scripts/quickstart.sh --no-key` first. The model ids in the transcripts carry a `-contributor` suffix: Muse Code's Contributor mode may use content for product improvement (check your own Muse Code settings); these runs used only synthetic samples.
  Still untested: slash-command argument passing, the project-scope install path (Muse blocks it for untrusted workspaces), and other Muse Code versions.
