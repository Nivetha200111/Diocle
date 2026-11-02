"""Verified distillation (docs/DISTILLATION.md): Muse Spark Open teaches a Muse Glimmer LoRA, and GnuCOBOL decides what it
may learn from. This module holds the gates and the host calls; eval/distill_glimmer.py runs the stages."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .sources import Program
from .translate import translation_messages

TEACHER_MARK = "muse-spark-open"
HELD_OUT = ("BRNCHSUM", "CHQCLR", "FXCONV", "LOANAMRT")
ORACLE_SEED, ORACLE_CASES, MIN_RECORDS = 7701, 1000, 100
HELD_OUT_SIMILARITY, GENERATED_SIMILARITY = 0.30, 0.60
MAX_TRAINING_TOKENS = 3_000_000
FIREWORKS = "https://api.fireworks.ai/v1"
_ACCOUNTS: set[str] = set()  # names to keep out of logs and result files: a host account can be derived from an email address

GATES = ("generation-failed", "does-not-compile", "analyzer-refused", "weak-oracle", "too-similar", "not-open-weights", "translation-failed",
         "policy-blocked", "differential-failed", "too-few-records", "spend-cap")

# Topics for generated programs. Cheque clearing, branch totals, FX and loan amortization are left out: they are held out.
DOMAINS = ("savings dividend posting", "dormant account flagging", "standing order scheduling", "card annual fee billing",
           "overdraft interest charging", "term deposit maturity", "teller cash drawer balancing", "payroll deduction posting",
           "merchant settlement batching", "insurance premium allocation", "pension contribution matching",
           "safe deposit box rental billing", "wire transfer fee tiers", "ATM withdrawal limit checks", "escrow shortage spreading")
TECHNIQUES = ("COMPUTE ROUNDED with a truncating MOVE into a smaller field", "packed decimal (COMP-3) amounts and signed totals",
              "a control break with subtotals and a final trailer record", "an OCCURS table searched with PERFORM VARYING",
              "EVALUATE TRUE over 88-level conditions", "SIGN LEADING SEPARATE amounts and DIVIDE ... REMAINDER",
              "INSPECT and reference modification on a text field", "a REDEFINES record with two record types")

GENERATOR_SYSTEM = """You write small synthetic COBOL batch programs for GnuCOBOL 3.2 used to test a translator.
Rules:
- Fictional data and names only. The first line of every file is the comment `      * SYNTHETIC. Fictional.`
- Fixed-format COBOL. PROGRAM-ID exactly as asked. 60 to 180 lines. Terminate with GOBACK or STOP RUN and exit code 0.
- Code starts in column 8 and stops by column 72; column 7 holds only a space or `*`. Every comment line has `*` in column 7.
- One input file and one output file, each record in its own copybook. Use `ORGANIZATION IS LINE SEQUENTIAL`, except that a file whose record has COMP-3 fields must use `ORGANIZATION IS SEQUENTIAL` and no text fields after the packed ones are needed.
- Each copybook holds exactly one 01 level. Under each FD write only the COPY line: never write your own 01 above or below it, in the FD or for the same file.
- A REDEFINES goes inside that single 01; never give a file a second 01.
- The input record has at least four separate fields, including at least two numeric ones, so generated data exercises the logic.
- Every input record yields one or more output records.
- No CALL, no EXEC SQL, no CICS, no ACCEPT, no INDEXED or RELATIVE files, no SORT, no date or time functions.
- Assign the files exactly as `ASSIGN TO INFILE` and `ASSIGN TO OUTFILE`, unquoted.
- Pull each copybook in with an unquoted member name, as in `COPY GEN0001I.`, never `COPY "GEN0001I".`"""


def scrub(text: object) -> str:
    """Host text with the account name taken out. Everything bound for a log or a result file goes through this."""
    out = str(text)
    for account in _ACCOUNTS:
        out = out.replace(account, "<account>")
    return out


def assert_scrubbed(text: str) -> None:
    """The last check before a result file is written: refuse rather than publish the account name."""
    if any(account in text for account in _ACCOUNTS):
        raise ValueError("refused to write a result file: it contains the host account name")


class NotOpenWeights(RuntimeError):
    """A call behind a training example was not Muse Spark Open: Meta Model API outputs may not train this model."""


def check_teacher_calls(calls) -> None:
    """Every call behind an example must be Muse Spark Open. There is no way to switch this off."""
    if not calls:
        raise NotOpenWeights("no recorded model call behind this example")
    other = sorted({c.model for c in calls if TEACHER_MARK not in c.model})
    if other:
        raise NotOpenWeights(f"refused: {', '.join(other)} is not Muse Spark Open")


def _input_layouts(meta: dict) -> list[dict]:
    if "files" in meta:
        return [f.get("layout") or {} for f in meta["files"] if f.get("direction") in ("input", "io")]
    layouts = meta.get("layouts") or {}
    return [layouts["input"]] if "input" in layouts else []


def oracle_can_see(sample_dir: Path) -> bool:
    """False for no input, or a record that is one flat field: generated inputs for it do not vary."""
    layouts = _input_layouts(json.loads((Path(sample_dir) / "sample.json").read_text()))
    return bool(layouts) and all(len(x.get("fields") or []) >= 2 for x in layouts)


def _shingles(text: str) -> set:
    words = [w for w in re.findall(r"[A-Z0-9-]{3,}", text.upper())]
    return set(zip(words, words[1:], words[2:]))


def similarity(a: str, b: str) -> float:
    """Jaccard similarity of word trigrams: 1.0 for copies, near 0 for unrelated programs."""
    x, y = _shingles(a), _shingles(b)
    return len(x & y) / len(x | y) if x | y else 0.0


def closest(text: str, others: dict[str, str]) -> tuple[str | None, float]:
    best, score = None, 0.0
    for name, other in others.items():
        s = similarity(text, other)
        if s > score:
            best, score = name, s
    return best, score


def passes_oracle(report: dict) -> tuple[bool, str | None]:
    """The verifier's own definition of equivalence, plus enough compared records and a clean exit of the original."""
    from diocle_verifier.verify import passes

    if not passes(report):
        return False, "differential-failed"
    if report["summary"]["total"] < MIN_RECORDS:
        return False, "too-few-records"
    if report["runs"]["original"].get("exitCode") not in (0, None):
        return False, "differential-failed"
    return True, None


def training_line(program: Program, result: dict, java_source: str) -> dict:
    """One chat example: the translator's exact prompt, then the JSON answer the translator is asked for."""
    answer = json.dumps({"mainClass": result["mainClass"], "javaSource": java_source, "notes": result.get("notes", "")})
    return {"messages": [*translation_messages(program), {"role": "assistant", "content": answer}]}


def final_answer(text: str) -> dict:
    """The Java from a raw Muse Glimmer completion, read from the channel addressed to the user, after any reasoning.
    The hosted route forces the JSON shape with a schema, and no prompt names it, so a base model that never saw the shape
    must not fail for answering in plain Java: the same rule accepts the JSON or the Java, for base and tuned."""
    tail = text.rsplit("to=user<|message|>", 1)[-1].split("<|eot|>", 1)[0].split("<|end_of_text|>", 1)[0]
    start, end = tail.find("{"), tail.rfind("}")
    if start >= 0 and end > start:
        try:
            answer = json.loads(tail[start:end + 1], strict=False)
        except ValueError:
            answer = None
        if isinstance(answer, dict) and isinstance(answer.get("javaSource"), str):
            return {"mainClass": answer.get("mainClass", ""), "javaSource": answer["javaSource"], "notes": str(answer.get("notes", ""))}
    fence = re.search(r"```(?:java)?[ \t]*\n(.*?)```", tail, re.S)
    java = fence.group(1) if fence else tail
    if not re.search(r"\bclass\s+\w+", java):
        raise ValueError("no JSON answer and no Java class in the answer")
    return {"mainClass": "", "javaSource": java.strip() + "\n", "notes": ""}


def check_no_leak(lines: list[dict], held_out_sources: dict[str, str]) -> None:
    """Fails if a held-out program's PROGRAM-ID or source shows up in a training line. The last check before an upload."""
    for i, line in enumerate(lines):
        user = next(m["content"] for m in line["messages"] if m["role"] == "user")
        for name in held_out_sources:
            if re.search(rf"PROGRAM-ID\.\s+{name}\b", user):
                raise ValueError(f"line {i}: held-out program {name} is in the training data")
        who, score = closest(user, held_out_sources)
        if score >= HELD_OUT_SIMILARITY:
            raise ValueError(f"line {i}: {score:.2f} similar to held-out {who}")


def dataset_bytes(lines: list[dict]) -> bytes:
    return "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in lines).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def estimate_training_tokens(data: bytes, epochs: int) -> int:
    return len(data) // 3 * epochs


def generation_format() -> dict:
    return {"type": "json_schema", "json_schema": {"name": "synthetic_program", "schema": {
        "type": "object",
        "properties": {"cobol": {"type": "string"}, "inputCopybook": {"type": "string"}, "outputCopybook": {"type": "string"}},
        "required": ["cobol", "inputCopybook", "outputCopybook"], "additionalProperties": False}}}


def topics(count: int) -> list[tuple[str, str, str]]:
    """(PROGRAM-ID, domain, technique): a pure function of count, so a resumed harvest asks for the same programs."""
    out = []
    for i in range(count):
        domain, technique = DOMAINS[i % len(DOMAINS)], TECHNIQUES[i % len(TECHNIQUES)]  # 15 and 8: 120 distinct pairs
        out.append((f"GEN{i + 1:04d}", domain, technique))
    return out


def generation_messages(name: str, domain: str, technique: str) -> list[dict]:
    user = (f"Write PROGRAM-ID {name}: {domain} for a fictional institution, using {technique}. "
            f"The copybooks are members {name}I (input record) and {name}O (output record). Return the source and both copybooks.")
    return [{"role": "system", "content": GENERATOR_SYSTEM}, {"role": "user", "content": user}]


def contained(cobol: str, *copybooks: str) -> bool:
    """A generated program may touch only INFILE and OUTFILE and may call nothing, and that includes what its copybooks
    bring in with COPY. It is compiled and run on this machine."""
    text = "\n".join(line for part in (cobol, *copybooks) for line in part.upper().splitlines() if line[6:7] != "*")
    assigns = re.findall(r"\bASSIGN\s+(?:TO\s+)?(\S+?)\.?(?=\s|$)", text)
    return sorted(assigns) == ["INFILE", "OUTFILE"] and not re.search(r"(?<![A-Z0-9-])(CALL|ACCEPT|EXEC)(?![A-Z0-9-])", text)


def compile_errors(root: Path, name: str) -> str | None:
    """Free check before any translation is paid for: cobc's first errors, or None when the program parses."""
    cobc = shutil.which("cobc")
    if cobc is None:
        raise RuntimeError("cobc not found")
    done = subprocess.run([cobc, "-x", "-fsyntax-only", "-I", str(root), str(root / f"{name}.cbl")], capture_output=True, text=True, timeout=60)
    if done.returncode == 0:
        return None
    errors = "\n".join(line for line in done.stderr.splitlines() if "error" in line)
    return errors.replace(f"{root}/", "")[:1500] or "cobc failed"  # no machine paths: this reaches a prompt and a result file


def fix_messages(messages: list[dict], answer: str, errors: str) -> list[dict]:
    """One chance for the teacher to fix its own compile errors."""
    return [*messages, {"role": "assistant", "content": answer},
            {"role": "user", "content": f"GnuCOBOL refused this:\n{errors}\nReturn the corrected source and both copybooks."}]


def write_generated(name: str, answer: dict, root: Path) -> Path:
    """Lay a generated program out as a small repository for the analyzer."""
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.cbl").write_text(answer["cobol"])
    (root / f"{name}I.cpy").write_text(answer["inputCopybook"])
    (root / f"{name}O.cpy").write_text(answer["outputCopybook"])
    return root


def sample_from_repo(root: Path, name: str, out_dir: Path) -> Path | None:
    """The analyzer's verdict on a generated program: its sample directory, or None when refused."""
    from diocle_analyzer.analyze import analyze, write_sample

    report = analyze(root)
    program = next((p for p in report["programs"] if p["name"] == name), None)
    if program is None or not program["convertible"]:
        return None
    return write_sample(root, report, program, out_dir)


@dataclass
class Fireworks:
    """The few host calls this needs. Account and key come from the environment and are never logged."""
    account: str
    key: str
    _http: object = None

    def __post_init__(self) -> None:
        _ACCOUNTS.add(self.account)
        if self._http is None:
            import httpx

            self._http = httpx.Client(base_url=f"{FIREWORKS}/accounts/{self.account}", timeout=120,
                                      headers={"Authorization": f"Bearer {self.key}"})

    @classmethod
    def from_env(cls) -> "Fireworks":
        from .config import load_dotenv

        load_dotenv()
        key = os.environ.get("OPEN_MODEL_API_KEY", "")
        if not key:
            raise SystemExit("Set OPEN_MODEL_API_KEY in .env")
        account = os.environ.get("FIREWORKS_ACCOUNT_ID", "")
        if not account:  # the key's own account; it may be derived from an email address, so it is never written to a report
            import httpx

            response = httpx.get(f"{FIREWORKS}/accounts", headers={"Authorization": f"Bearer {key}"}, timeout=30)
            response.raise_for_status()
            account = response.json()["accounts"][0]["name"].rsplit("/", 1)[-1]
        return cls(account, key)

    def _json(self, response) -> dict:
        if response.status_code >= 400:
            raise RuntimeError(scrub(f"{response.request.method} {response.request.url.path}: {response.status_code} {response.text[:400]}"))
        return response.json() if response.content else {}

    def upload_dataset(self, dataset_id: str, data: bytes, examples: int) -> dict:
        """Safe to run again: a dataset left in UPLOADING by a failed upload is reused, a READY one is left alone."""
        existing = self._http.get(f"/datasets/{dataset_id}")
        if existing.status_code == 404:
            self._json(self._http.post("/datasets", json={"datasetId": dataset_id,
                                                          "dataset": {"userUploaded": {}, "exampleCount": str(examples)}}))
        elif self._json(existing).get("state") == "READY":
            return existing.json()
        self._json(self._http.post(f"/datasets/{dataset_id}:upload", files={"file": ("train.jsonl", data)}))
        return self.dataset(dataset_id)

    def dataset(self, dataset_id: str) -> dict:
        return self._json(self._http.get(f"/datasets/{dataset_id}"))

    def create_job(self, job_id: str, base_model: str, dataset_id: str, output_model: str, epochs: int, lora_rank: int) -> dict:
        body = {"baseModel": base_model, "dataset": dataset_id, "outputModel": f"accounts/{self.account}/models/{output_model}",
                "epochs": epochs, "loraRank": lora_rank}
        return self._json(self._http.post("/supervisedFineTuningJobs", params={"supervisedFineTuningJobId": job_id}, json=body))

    def job(self, job_id: str) -> dict:
        return self._json(self._http.get(f"/supervisedFineTuningJobs/{job_id}"))

    def create_deployment(self, base_model: str, accelerator: str, count: int, scale_to_zero: str = "300s") -> dict:
        """Add-ons on, one replica at most, scales to zero on its own if this script dies."""
        body = {"baseModel": base_model, "acceleratorType": accelerator, "acceleratorCount": count, "minReplicaCount": 0,
                "maxReplicaCount": 1, "scaleToZeroWindow": scale_to_zero, "enableAddons": True}
        return self._json(self._http.post("/deployments", json=body))

    def deployment(self, deployment_id: str) -> dict:
        return self._json(self._http.get(f"/deployments/{deployment_id}"))

    def delete_deployment(self, deployment_id: str) -> None:
        self._json(self._http.delete(f"/deployments/{deployment_id}", params={"hard": "true"}))

    def load_adapter(self, deployment_id: str, model: str) -> dict:
        name = f"accounts/{self.account}/deployments/{deployment_id}"
        return self._json(self._http.post("/deployedModels", json={"model": f"accounts/{self.account}/models/{model}",
                                                                    "deployment": name, "default": False}))


def wait_for(read, done, *, every: float = 30.0, limit: float = 3600.0, sleep=time.sleep, clock=time.monotonic):
    """Poll read() until done(value). Raises TimeoutError at the limit, so nothing waits (or bills) forever."""
    end = clock() + limit
    while True:
        value = read()
        if done(value):
            return value
        if clock() >= end:
            raise TimeoutError(f"still waiting after {limit:.0f} s")  # not the host's reply: it can carry the account name
        sleep(every)
