# Architecture

> The first section describes what is **implemented and tested**. Everything from "Overview" down is the original target design; where it differs from what was built, the first section wins. Diagram of the target design: [architecture.drawio](architecture.drawio) (open in [diagrams.net](https://app.diagrams.net) or the VS Code Draw.io Integration extension).

## Flow that runs today (implemented)

```mermaid
flowchart LR
    REPO["Legacy GitHub repo<br/>COBOL, copybooks, JCL"]
    ANA["services/analyzer<br/>layouts from copybooks,<br/>file wiring, CALLs, findings"]

    subgraph CONV["services/converter (Meta Muse Spark)"]
        TR["Translator"]
        AGENT["Repair agent<br/>read, patch, compile, re-test"]
        BRK["Breaker agent<br/>designs inputs to break it"]
        MEM[("Fix memory<br/>certified lessons only")]
    end

    subgraph VER["services/verifier (the oracle)"]
        RUN["GnuCOBOL vs Java<br/>same inputs, every field,<br/>byte, exit code, stdout"]
        GOLD["Golden replay<br/>mainframe output wins"]
    end

    CERT{"Held-out certification<br/>1,000 unseen inputs"}
    PR["Pull request on target repo<br/>Java + certificate"]
    CI["Target repo CI<br/>reverify on a fresh seed"]
    UI["apps/web<br/>Live runs, Delivery"]

    REPO --> ANA --> TR --> AGENT
    AGENT -- "tool calls" --> RUN
    RUN --- GOLD
    AGENT -- "finish" --> CERT
    CERT -- "fail" --> AGENT
    CERT -- "pass" --> BRK
    BRK -- "breaking input becomes a test" --> AGENT
    CERT -- "lessons" --> MEM --> AGENT
    BRK -- "nothing breaks" --> PR --> CI
    CONV -. "runs, events, cost" .-> UI
```

1. **Import and analyze** (`services/analyzer`, deterministic): clone an allowed GitHub repo at a pinned commit; derive record layouts from copybooks (DISPLAY, COMP-3, COMP, COMP-5, COMP-1/2, every sign mode, P scaling, OCCURS, REDEFINES, edited PICs, COPY REPLACING); wire DD names through SELECT/FD/OPEN and JCL; resolve CALLed programs; flag ROUNDED, truncation, silent overflow, column-72 cuts, clock reads, EBCDIC-sensitive comparisons and hex floats. Programs Diocle cannot run (EXEC SQL/CICS/DLI, INDEXED/RELATIVE files, several files or record types, OCCURS DEPENDING ON, PIC N) are reported as not convertible.
2. **Translate** with Muse Spark (hosted, or Muse Spark Open on Fireworks in private mode). The translator is told GnuCOBOL's storage rules, the pinned clock and the collating sequence.
3. **Repair** with a tool-using agent that can only edit the run's Java. Every test compares the Java with the original compiled by GnuCOBOL 3.2 (-std=ibm): output records field by field and byte by byte (text lines or fixed-length byte records), RETURN-CODE and stdout, with the clock pinned and EBCDIC collation for mainframe code. Inputs: PIC boundaries, seeded random values, fixtures, corpus files, and golden files captured from the mainframe, where the mainframe's output is the oracle.
4. **Certify** on 1,000 held-out inputs from a seed the agent never saw. Failure gives the agent another round, up to `MODEL_MAX_ROUNDS`.
5. **Attack** (optional `--breaker`): a second Muse Spark agent designs inputs to break the certified Java. Any input that breaks it becomes a standing test case and the agent resumes (`MODEL_MAX_BREAKER_CYCLES`); if it is still broken, the run is not certified.
6. **Learn**: lessons from certified runs go into fix memory (proof-gated) and are offered as hints to later runs; in swarm mode, parallel agents receive them mid-run. Memory exports as a skill (`skills/cobol-to-java-semantics/SKILL.md`).
7. **Deliver** (`services/api` `deliver`): each certified program goes to the target repo as `programs/<PROGRAM>/` with the Java, the derived layouts and `certificate.json` (pinned legacy commit, modules, verifier commit, seed, cost). Uncertified programs are listed, never delivered.
8. **Re-prove in CI**: the target repo's workflow pins the legacy repo and the Diocle branch, re-derives layouts from the copybooks, and runs `reverify` on a fresh seed. It does not trust files in the pull request.
9. **Show**: runs and deliveries are served by `services/api` and shown live in the dashboard. `services/mcp` exposes analyze, verify and certify to any agent.

Caps (CLAUDE.md rule 10, all from `.env`): calls per run and per round, repair rounds, breaker attack rounds and cycles, programs per delivery and parallel agents.

Not built from the target design below: the Class Designer and paragraph-level translation, the SonarQube quality gate, LLM-as-a-judge, starting runs from the browser, and support for the program shapes listed as not convertible in step 1.

## Overview
Diocle is an "understand first, convert second" pipeline: **upload > analyze > design > convert > verify ⇄ repair > report**.

Deterministic tools understand and verify the code. Meta models design, convert and repair it. The model never certifies its own output: only execution against the original program compiled with GnuCOBOL does.

```
Portal (apps/web) ⇄ API orchestrator (services/api)
                         ├─ Layer 1 Analyzer   (deterministic)          → analysis-report
                         ├─ Layer 2 Converter  (Meta models)            → conversion-output
                         └─ Layer 3 Verifier   (GnuCOBOL + JDK + Sonar) → verification-report
                                    ▲                     │ diff mismatches + quality issues
                                    └── tool-using repair agent (≤3 rounds)
```

Run states (in `services/api`): `UPLOADED → ANALYZING → DESIGNING → CONVERTING → VERIFYING ⇄ REPAIRING (≤3) → CERTIFIED | NEEDS_REVIEW`. Each transition and agent step is streamed to the portal as a `run-events` SSE message.

## Model backends (CLAUDE.md rule 9)
| Mode | Model | Served by | Why |
|---|---|---|---|
| `hosted` | Muse Spark | Meta Model API | Default; strongest hosted model |
| `private` | Muse Spark Open (`meta-models/muse-spark-open-1026`) | Baseten or Modal (a deployment you control) | Regulated banks can't send source code to a shared cloud API. In private mode the code only goes to an endpoint you deploy. |

- The converter talks to both through one client interface. `MODEL_MODE` in `.env` picks the backend.
- Endpoints, model IDs and keys come from `.env`.
- Every call is logged as `{role, round, mode, tokens, latencyMs}`.
- Hard caps on calls per round and rounds per run (CLAUDE.md rule 10).
- Capabilities such as context size, native tool calling and structured output are **to be verified** per backend on Day 1.

## Layer 1: Analyzer (`services/analyzer`), deterministic, no LLM
- **Parser:** ProLeap COBOL parser (ANTLR4), wrapped in a small Java CLI that emits the AST/ASG as JSON. Fallback: a line-based Python parser limited to the constructs the samples use.
- **Topology graph:** CALL, COPY, EXEC SQL, EXEC CICS. SQL and CICS are graphed and flagged, not executed.
- **Data layout normalizer:**
  - COMP-3 → `BigDecimal` with explicit rounding.
  - REDEFINES → byte-buffer views.
  - OCCURS → 1-based arrays with bounds checks.
  - Emits a layout dictionary: level, PIC, usage, offset, length.
- **Risk rules:** money COMPUTE, ROUNDED, sign handling, REDEFINES, GO TO.
- **Output:** `contracts/analysis-report.schema.json`.

## Layer 2: Converter (`services/converter`), Meta models only
| Role | Input → output |
|---|---|
| 2A Class Designer | analysis report + layouts → packages, DTOs, class skeletons, COBOL→Java variable map |
| 2B Paragraph Translator | class map + variable map + one isolated paragraph → Java method |
| 2C Repair Agent | **tool-using agent** (below) |
| Rule Extractor | flagged paragraph → plain-English business rule |
| Edge-Case Test Designer | layouts + rules → semantic test inputs for the verifier |
| LLM-as-a-Judge | COBOL + Java → control-flow fidelity and idiomatic Java (1–7). **Advisory only.** |

All roles return schema-validated JSON. Generated Java depends on `services/converter/java-runtime`: `CobolDecimal`, `CobolArray`, `RedefinesBuffer`, and fixed-width record I/O.

## Repair Agent (2C): one agent, two kinds of failure
The repair step is an agent, not a fixed re-prompt. It handles both kinds of failure in the same loop:
1. **Equivalence failures:** `javac` errors, or field-level diffs against the GnuCOBOL oracle.
2. **Quality issues:** SonarQube Community findings on the generated Java (bugs, vulnerabilities, code smells).

**The rule that makes this trustworthy: a patch is accepted only if the code compiles, the differential tests still match the COBOL original, and the issue it targeted is gone.** A code-quality "fix" that silently changes behaviour is rejected. This replaces the manual cycle of fix, rebuild, rescan and re-check.

### Tools
| Tool | Implemented by | Returns |
|---|---|---|
| `compile_java(files)` | verifier | success, or `javac` errors with file and line |
| `run_differential_test(program, inputIds?)` | verifier | per-input match + field-level diffs (scale, padding, sign) |
| `get_quality_issues(file?)` | verifier (SonarQube Web API) | open issues with rule, severity, file, line, message |
| `lookup_field_layout(program, field)` | analyzer (report lookup) | level, PIC, usage, offset, length, REDEFINES/OCCURS |
| `read_cobol_paragraph(program, paragraph)` | analyzer (report lookup) | source text of one paragraph |
| `read_java_method(class, method)` | converter workspace | current Java source of one method |
| `patch_java(file, oldText, newText)` | converter workspace | applied / rejected (exact-match edit) |
| `finish(summary)` | converter | ends the round; triggers full re-verification (compile + diff + quality scan) |

The tool names, arguments and results are defined in `contracts/agent-tools.schema.json` (planned). The agent loop lives in `services/converter`. Each tool is implemented by the module that owns the capability, and `services/api` injects the tool executor into the agent.

### Guardrails
- At most 20 tool calls per round and 3 repair rounds. After that the run ends as `NEEDS_REVIEW`.
- Priority order: compile errors → equivalence diffs → quality issues by severity. Quality work never starts while outputs mismatch.
- `patch_java` can only touch the run's own Java workspace. No shell, no network, and no access to the COBOL sources or the oracle.
- **The agent cannot self-certify.** `finish` only requests verification. CERTIFIED is decided by the verifier.

### Observability
Every step emits an `agent-step` event: `{round, step, tool, argsSummary, resultSummary, rationale}`. Here `rationale` is the short explanation the model returns with each step. The portal shows a live agent trace next to the before/after diffs and the issues it cleared.

### Fallback
If a backend lacks native function calling, the same loop runs with a JSON "next action" response format: the model returns `{tool, args, rationale}`, and the converter executes the tool and feeds back the result. The tools, guardrails and trace stay the same.

## Layer 3: Verifier (`services/verifier`), Docker: GnuCOBOL + JDK 21
- **Inputs:** PIC boundary values + random values + model-designed edge cases. Each input is tagged with its source.
- **Oracle:** `cobc -x -std=ibm -I copybooks`, run on fixed-width input records.
- **Converted side:** the Spring Boot service, run on the same inputs as JSON.
- **Diff:** normalized field-by-field comparison of numeric scale, padding, sign and status codes.
- **Analytic checkers:** variable coverage, paragraph ↔ method alignment, hallucinated identifiers.
- **Quality gate (optional):** self-hosted SonarQube Community scan of the generated Java. Its issues feed the repair agent. It needs about 2–4 GB of RAM, so keep the server running ahead of the demo.
- **Output:** `contracts/verification-report.schema.json`, including the **equivalence certificate**: programs, inputs, pass rate, rounds, quality gate status, residual risks.

## Layer 4: Portal (`apps/web`) + API (`services/api`)
- **Portal:** split editor (COBOL ⇄ copybook vars ⇄ Java), topology graph, live run timeline, agent trace with repair-round diffs and cleared issues, model call log (with mode), and the equivalence scorecard/certificate.
- **API:** `POST /runs`, `GET /runs/{id}`, `GET /runs/{id}/events` (SSE). It orchestrates the layers and executes agent tools. It makes no LLM calls itself.

## Contracts (to be updated before implementation)
- `analysis-report`: + `layouts[]`; topology kinds `sql`, `cics`; findings + `paragraph`, `rule`.
- `conversion-output`: + `classDesign`, `modelCalls[]` (with `mode`), `javaServices[].round`.
- `verification-report`: + `inputSource`, `round`, `fieldDiffs[]`, `checks`, `qualityGate` {status, issues[]}, `judge`, `certificate`.
- New: `run-events.schema.json` (including `agent-step`) and `agent-tools.schema.json`.

## Principles
- Contracts first: modules communicate only via the schemas in `contracts/`.
- Meta models only inside the product (Muse Spark, Muse Spark Open).
- Verification is by differential execution, not by trusting model output, judge scores or lint results.
- Samples are synthetic only.
