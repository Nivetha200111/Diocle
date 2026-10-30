# Where Meta models are used

Every model call in the product goes to a Meta model: Muse Spark through the Meta Model API, or Muse Spark Open through a partner host. No other LLM is called by the product (the `openai` Python package is used only as an OpenAI-compatible HTTP client; its base URLs come from `.env` and point at Meta or the partner host, never at an OpenAI model). Model IDs, endpoints and keys come from `.env` (see `.env.example`), not from code. The development tooling that helped write the code (Claude Code) is separate and not part of the product.

Counts below are from the public run list (`GET https://diocle.vercel.app/api/runs`, read Oct 31, 2026: 36 runs; 34 on Muse Spark, 1 on Muse Spark Open, 1 with no model recorded). Costs are estimates from list prices.

## Models used

| Model (ID) | Role in Diocle | Where in the code | Evidence | Evidence strength |
|---|---|---|---|---|
| Muse Spark (`muse-spark-1.3-contributor` by default, from `META_MODEL_ID`; Meta Model API) | Translator, tool-using repair agent, breaker agent | `services/converter/diocle_converter/translate.py`, `repair.py`, `breaker.py`; client, caps and cost logging in `client.py`, `config.py` | 34 of the 36 public runs, for example [chqclr-20261028-214355](https://diocle.vercel.app/#run=chqclr-20261028-214355); the headline measurement ([MEASUREMENT.md](MEASUREMENT.md)) made 45 first translations and 15 full runs with it | Many runs, but a small, synthetic program set and one model; the measurement is n=15 programs |
| Muse Spark Open (`accounts/fireworks/models/muse-spark-open`; open weights, partner inference on Fireworks) | Private mode (all three agent roles on open weights); independent cross-check (`--crosscheck`, opt-in, CLI only); optional guard review | `services/converter/diocle_converter/config.py` (`OPEN_MODEL_*`), `crosscheck.py`, `guard.py` (`review`, `GUARD_MODEL_*`) | Private mode: one public run, [interest-accrual-20261029-084702](https://diocle.vercel.app/#run=interest-accrual-20261029-084702) (INTACCR certified first time, 1,027/1,027 held-out inputs, 4 model calls, about $0.157). Guard review: configured on the live engine but skipped by the $0.02 cap in the three public sample runs (verdict `error`, summary says so). Cross-check: two real runs on Oct 29 recorded in [HANDOFF.md](HANDOFF.md), not in the public run list | **n=1 public run** for private mode, not in the headline measurement, no cost/accuracy comparison with Muse Spark. This is partner inference (Fireworks), not hardware we control |
| Muse Wonder (`muse-wonder-1.0`; Meta Model API) | "Read a printout": transcribes a photographed COBOL listing back into COBOL that is then compiled and compared with the original; opt-in higher-tier breaker (`MODEL_TIER_BREAKER=3`) | `services/converter/diocle_converter/vision.py`; compile and compare step in `services/verifier/diocle_verifier/transcript.py`; live button in `services/api/diocle_api/livesamples.py`, `samplejob.py`; tiers in `config.py` | Printout: one run in a local sandbox container (Oct 30), 1,013/1,013 inputs matched, $0.0608 ([HANDOFF.md](HANDOFF.md)); the live button was not pressed in the Oct 30 live check ([LIVE_CHECK.md](LIVE_CHECK.md) row 14), but `GET /api/config` shows it available. Breaker: one local run, `interest-accrual-20261029-230750`, a public run on the live site (certified; the breaker role is `muse-wonder-1.0`), about $0.62 | **n=1 per use**, one fixed printout image; Wonder's price is third-party and unconfirmed |
| Muse Voice Transcribe (`muse-voice-transcribe-1.0`) | "Ask the original program": a spoken question is transcribed, then Muse Spark turns it into checkable claims that GnuCOBOL confirms or refutes | `services/converter/diocle_converter/voice.py`, `ask.py`; public path in `services/api/diocle_api/asks.py`, `askjob.py` | One public ask on the live site on Oct 30: transcript by this model, 2 claims, 2 confirmed by GnuCOBOL ([LIVE_CHECK.md](LIVE_CHECK.md) row 15) | **One live public ask**; two bundled clips only; the service is reached over Meta's client WebSocket protocol (not a documented public HTTP API) and its price is our estimate |
| Muse Code (Meta's coding agent) | Uses Diocle as a local plugin: analyze, re-verify, and a gated, capped convert | `editors/muse-code/` (MCP server `editors/muse-code/plugin/mcp/server.py`, skill, slash commands) | Five recorded headless runs, [editors/muse-code/transcripts/](../editors/muse-code/transcripts/) (`run-1.jsonl` to `run-5.jsonl`); one converted and certified INTACCR 1,027/1,027, estimated USD 0.017 | **Five runs where the prompts named the tools** and the owner enabled and capped conversion; unattended use is not shown. A local plugin, not an official Meta integration |

## Meta models named by the hackathon that are not used

| Model | Status |
|---|---|
| Muse Image | Not used. It was removed from the video plan; the code and docs do not call it. |
| SAM 3.1 | Not used. |
| Muse Glimmer | Not used. A local Glimmer experiment was tried and dropped during development ([HANDOFF.md](HANDOFF.md)); no code for it remains in the product. |

## Not Meta models, and why they are disclosed

- The demo video narration is a synthetic voice from ElevenLabs, a non-Meta service used for the video only, not in the product. See [HACKATHON_COMPLIANCE.md](HACKATHON_COMPLIANCE.md).
- The two spoken-question clips in the product are made with macOS `say` (`services/api/diocle_api/voice_clips/`).
- GnuCOBOL is the verifier's oracle and is not a model.
