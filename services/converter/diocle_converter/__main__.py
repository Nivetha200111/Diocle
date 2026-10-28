"""CLI.

  python -m diocle_converter smoke                       one tiny model call to check the key and endpoint
  python -m diocle_converter repair SAMPLE [--java-dir]  verify an existing conversion and repair it (bring your own)
  python -m diocle_converter run SAMPLE                  translate with the Meta model, then verify and repair
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .client import ModelClient
from .config import REPO_ROOT, Settings
from .repair import RepairAgent, report_passes
from .sources import Program
from .translate import translate
from .workspace import Workspace


def _verifier():
    try:
        from diocle_verifier.verify import validate_report, verify_sample
    except ImportError:
        sys.exit("diocle-verifier is not installed: pip install -e ../verifier")

    def verify(sample_dir: Path):
        def run(java_dir: Path, seed: int, random_count: int) -> dict:
            report = verify_sample(sample_dir, java_dir, seed=seed, random_count=random_count)
            validate_report(report)
            return report

        return run

    return verify


def _print_event(event: dict) -> None:
    if event["type"] == "agent-step":
        why = f"  why: {event['rationale']}" if event["rationale"] else ""
        print(f"[round {event['round']} · step {event['step']:>2}] {event['tool']} {json.dumps(event['argsSummary'])}{why}")
        print(f"    -> {event['resultSummary'].splitlines()[0] if event['resultSummary'] else ''}")
    elif event["type"] == "certification":
        print(f"=== round {event['round']} certification on held-out inputs: {'PASS' if event['passed'] else 'FAIL'}")
        print("    " + event["result"].replace("\n", "\n    "))
    else:
        print(f"[{event['type']}] {event.get('message', '')}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diocle_converter", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("smoke")
    for name in ("repair", "run"):
        p = sub.add_parser(name)
        p.add_argument("sample_dir", type=Path)
        if name == "repair":
            p.add_argument("--java-dir", type=Path, help="existing Java conversion (default: the sample's javaConversion dir)")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    client = ModelClient(settings)
    print(f"model: {settings.model} ({settings.mode}), reasoning_effort={settings.reasoning_effort}, "
          f"caps: {settings.max_calls_per_run} calls/run, {settings.max_calls_per_round}/round, {settings.max_rounds} rounds")

    if args.command == "smoke":
        choice = client.chat(role="smoke", round=0, messages=[{"role": "user", "content": "Reply with exactly: DIOCLE OK"}])
        print(choice.message.content)
        print(json.dumps({k: v for k, v in client.usage_summary().items() if k != "modelCalls"}))
        return 0

    program = Program.load(args.sample_dir)
    run_dir = REPO_ROOT / "runs" / f"{args.sample_dir.resolve().name}-{time.strftime('%Y%m%d-%H%M%S')}"
    events: list[dict] = []

    def on_event(event: dict) -> None:
        events.append(event)
        _print_event(event)

    if args.command == "repair":
        meta = json.loads((program.sample_dir / "sample.json").read_text())
        source = (args.java_dir or program.sample_dir / meta["javaConversion"]["dir"]).resolve()
        workspace = Workspace.from_copy(source, run_dir / "java")
        translation = None
    else:
        workspace = Workspace(run_dir / "java")
        print("translating with the Meta model...")
        translation = translate(program, client, workspace)
        print(f"wrote {translation['file']}; translator notes: {translation['notes'][:400]}")

    verify = _verifier()(program.sample_dir)
    agent = RepairAgent(program, workspace, client, verify, on_event)
    first = verify(workspace.root, 1026, 200)
    (run_dir / "initial-verification.json").write_text(json.dumps(first, indent=2) + "\n")
    if report_passes(first) and report_passes(verify(workspace.root, 4243, 1000)):
        print("conversion already passes, including held-out inputs: no repair needed")
        outcome = {"certified": True, "rounds": [], "certificationReport": None}
    else:
        outcome = agent.run()

    usage = client.usage_summary()
    origin = (f"copied from {source.relative_to(REPO_ROOT)}" if translation is None
              else f"translated by {settings.model}")
    patches = sum(1 for e in events if e.get("tool") == "patch_java" and e["resultSummary"].startswith("applied"))
    (run_dir / "PROVENANCE.md").write_text(
        f"# Provenance of java/\n\n- Started as: {origin}\n"
        f"- Then modified by the Diocle repair agent ({settings.model}, {settings.mode} mode): {patches} applied patches. "
        "See events.jsonl for every step.\n"
        "- Any header comment inside the Java files describes the starting file, not the repaired result.\n"
    )
    (run_dir / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    if outcome["certificationReport"]:
        (run_dir / "verification-report.json").write_text(json.dumps(outcome["certificationReport"], indent=2) + "\n")
    (run_dir / "run.json").write_text(json.dumps({
        "program": program.name, "command": args.command, "javaOrigin": origin, "translation": translation,
        "certified": outcome["certified"], "rounds": outcome["rounds"], "usage": usage,
    }, indent=2) + "\n")
    print(f"\n{'CERTIFIED' if outcome['certified'] else 'NOT CERTIFIED'}  ·  {usage['calls']} model calls, "
          f"{usage['inputTokens']} in ({usage['cachedInputTokens']} cached) / {usage['outputTokens']} out tokens, est. ${usage['estimatedCostUsd']}")
    print(f"run saved to {run_dir.relative_to(REPO_ROOT)}")
    return 0 if outcome["certified"] else 1


if __name__ == "__main__":
    sys.exit(main())
