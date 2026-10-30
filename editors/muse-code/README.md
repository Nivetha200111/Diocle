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

21 tests: JSON-RPC handshake, tools/resources/prompts lists, protocol errors, each tool (the analyzer and verifier tests run the real
tools and need cobc and a JDK; they skip otherwise), path and symlink escape attempts, validation errors, convert disabled by
default, cap and key-argument rejection, secret scrubbing, a local stub for the live-run tool.

## What was tested with the real `muse` binary (Muse Code 1.4.14, macOS)

- **Verified:** `muse plugins validate` passes; the plugin installs, shows `review_needed`, and after approval `muse exec` starts the
  server: Muse Code logged a successful stdio handshake and discovery of 7 tools, 45 resources and 2 prompts
  (`transcripts/connect-check.jsonl`, rendered to a short real capture). The tools were also run directly over JSON-RPC
  (`transcripts/direct-tool-calls.txt`, not through Muse Code).
- **Not verified:** a model-driven Muse Code run that calls the tools. The build session had no Muse login or key and was not allowed to
  take the owner's from `.env`, so no headless prompt was run and no transcript of Muse choosing and calling the tools exists. The
  owner can record it with `demo/run-demo.sh` (five prompts: analyze+verify, live run, convert+certify, two guardrail refusals), then
  `demo/render_capture.py` turns the recorded transcripts into a terminal-style mp4 (needs Pillow and ffmpeg; real text and
  timings, idle waits shortened and marked). Whether Muse Code runs MCP tools unattended under `--disable-approval` is untested.
