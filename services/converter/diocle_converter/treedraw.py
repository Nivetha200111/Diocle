"""One small Muse Image drawing of a delivery's dependency tree, checked the same way as eval/draw_dependency_trees.py.

  python -m diocle_converter tree-draw DELIVERY_DIR --ledger LEDGER_FILE

Started by services/api diocle_api.deliver in the background, once per delivery, after the analyzer's tree is recorded. It reads
that tree from DELIVERY_DIR/delivery.json, writes its own DELIVERY_DIR/tree-drawing.json (contracts/delivery.schema.json
dependencyDrawing) and keeps a drawing only if it passed.

Off unless TREE_IMAGE_MODEL_ID and VISION_MODEL_ID are set, on a Meta key (rule 9). Public visitors trigger paid calls here, so
every cap below is checked BEFORE the call it limits and fails closed (rule 10). The caps are constants on purpose: raising one
is the owner's decision. Muse Image's price is not published, so images are counted, not priced. The read-back has its own dollar
cap at the Muse Wonder list price. None of this counts against, or is limited by, the public budget for imports.

Repository text reaches the image prompt only as labels matching LABEL: at most 9 upper-case labels of up to two words each, with no other punctuation. The read-back gets the picture and a
fixed prompt, never the graph; its reply is only parsed as data and compared by code.
"""

from __future__ import annotations

import base64
import binascii
import fcntl
import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import PRICES, Settings, load_dotenv

MAX_ATTEMPTS = 2  # per delivery
MAX_IMAGES_PER_DAY = 6  # across all visitors, from the ledger on disk
MAX_READ_USD = 0.15  # read-back spend per delivery, estimated at list price
MIN_LINKS, MAX_LINKS = 2, 8
# The worst case of one read-back, reserved before an image is drawn. A 1024x1024 PNG read as 3,439 input tokens in the one real
# run here; recorded reads of small trees cost about $0.02 to $0.09. The output cap goes in the request, so it bounds the bill.
READ_INPUT_ESTIMATE, READ_MAX_OUTPUT = 4000, 3500
MAX_IMAGE_BYTES = 4_000_000  # what is stored and sent on
MAX_RESPONSE_BYTES = 8_000_000
MAX_READ_ITEMS, MAX_READ_LABEL = 100, 100
IMAGE_TIMEOUT, READ_TIMEOUT, JOB_SECONDS = 150, 120, 540

LABEL = re.compile(r"[A-Z0-9#@$-]{1,30}( [A-Z0-9#@$-]{1,30})?")
RECORD_NAME = "tree-drawing.json"
# Fixed file names, one per format: nothing from a repository or a model ever names a file.
IMAGE_FILES = {"image/png": "tree-drawing.png", "image/webp": "tree-drawing.webp", "image/jpeg": "tree-drawing.jpg"}


class CallFailed(Exception):
    def __init__(self, status: int | None, maybe_billed: bool):
        super().__init__(f"HTTP {status}" if status else "no usable answer")
        self.status, self.maybe_billed = status, maybe_billed


class LedgerError(Exception):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def select_part(edges: list) -> tuple[str, list[tuple[str, str]]] | None:
    """The first name in analyzer order with MIN_LINKS to MAX_LINKS links of its own, those links only, upper-cased. A link to
    itself is not drawn. A part with a label outside LABEL is skipped, so repository text cannot enter the image prompt."""
    parts: dict[str, set[str]] = {}
    for edge in edges:
        source, to = (edge["from"], edge["to"]) if isinstance(edge, dict) else edge
        parts.setdefault(str(source).strip().upper(), set()).add(str(to).strip().upper())
    for program, targets in parts.items():
        pairs = sorted((program, to) for to in targets if to != program)
        if MIN_LINKS <= len(pairs) <= MAX_LINKS and all(LABEL.fullmatch(label) for pair in pairs for label in pair):
            return program, pairs
    return None


def compare(expected: list[tuple[str, str]], read: dict) -> dict:
    """Exact comparison, ignoring only case and spaces around a label; boxes as well as arrows. As eval/draw_dependency_trees.py."""
    norm = lambda s: str(s).strip().upper()  # noqa: E731
    want = {(norm(a), norm(b)) for a, b in expected}
    got = {(norm(e["from"]), norm(e["to"])) for e in read["edges"]}
    want_nodes = {n for pair in want for n in pair}
    got_nodes = {norm(n) for n in read["nodes"]} | {n for pair in got for n in pair}
    return {"match": want == got and want_nodes == got_nodes, "missingEdges": len(want - got), "inventedEdges": len(got - want),
            "missingNodes": len(want_nodes - got_nodes), "inventedNodes": len(got_nodes - want_nodes)}


def parse_read(content: object) -> dict | None:
    """A read-back reply as data: {"nodes": [str], "edges": [{"from": str, "to": str}]}, bounded. Anything else is None."""
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("nodes"), list) or not isinstance(data.get("edges"), list):
        return None
    if len(data["nodes"]) > MAX_READ_ITEMS or len(data["edges"]) > MAX_READ_ITEMS:
        return None
    short = lambda s: isinstance(s, str) and len(s) <= MAX_READ_LABEL  # noqa: E731
    if not all(short(n) for n in data["nodes"]):
        return None
    if not all(isinstance(e, dict) and short(e.get("from")) and short(e.get("to")) for e in data["edges"]):
        return None
    return {"nodes": data["nodes"], "edges": data["edges"]}


def image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _post(url: str, key: str, body: dict, timeout: int) -> dict:
    """One paid call. A failure carries only the HTTP status, so a provider's body never reaches a log or a record."""
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise CallFailed(e.code, maybe_billed=False) from None
    except (OSError, http.client.HTTPException):  # a timeout or a dropped connection: the call may have been billed
        raise CallFailed(None, maybe_billed=True) from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise CallFailed(None, maybe_billed=True)
    try:
        data = json.loads(raw)
    except ValueError:
        raise CallFailed(None, maybe_billed=True) from None
    if not isinstance(data, dict):
        raise CallFailed(None, maybe_billed=True)
    return data


def _counts(usage: object) -> dict:
    """Token counts as returned; numbers only, so nothing else from a response reaches the record."""
    if not isinstance(usage, dict):
        return {}
    return {k: v for k, v in usage.items() if isinstance(k, str) and len(k) <= 40 and type(v) is int and v >= 0}


def draw(base_url: str, key: str, model: str, pairs: list[tuple[str, str]]) -> tuple[bytes, str, dict]:
    lines = "; ".join(f"{a} -> {b}" for a, b in pairs)
    prompt = ("A clean technical dependency tree diagram on a plain white background, black text in a monospaced font, thin black arrows, "
              "laid out top to bottom. Exactly these boxes and arrows and no others, with every label spelled exactly as written: "
              + lines + ". No title and no other text.")
    answer = _post(base_url + "/images/generations", key,
                   {"model": model, "prompt": prompt, "n": 1, "size": "1024x1024", "output_format": "png"}, IMAGE_TIMEOUT)
    usage = _counts(answer.get("usage"))
    try:
        image = base64.b64decode(answer["data"][0]["b64_json"], validate=True)
    except (KeyError, IndexError, TypeError, ValueError, binascii.Error):
        raise CallFailed(None, maybe_billed=True) from None
    media_type = image_type(image)
    if media_type is None or len(image) > MAX_IMAGE_BYTES:
        raise CallFailed(None, maybe_billed=True)
    return image, media_type, usage


READ_PROMPT = ('This picture is a dependency diagram. Read it exactly as drawn. Answer only with JSON: {"nodes": ["label", ...], '
               '"edges": [{"from": "label", "to": "label"}, ...]}, where an edge follows the direction of an arrow. '
               'Spell labels exactly as drawn, even if they look wrong.')


def read_back(settings: Settings, image: bytes, media_type: str) -> tuple[dict | None, dict]:
    """Muse Wonder sees only the picture and the fixed prompt. Returns the parsed reply (None: not usable) and the usage."""
    url = f"data:{media_type};base64," + base64.b64encode(image).decode()
    answer = _post(settings.base_url.rstrip("/") + "/chat/completions", settings.api_key, {
        "model": settings.model, "response_format": {"type": "json_object"}, "max_tokens": READ_MAX_OUTPUT,
        "reasoning_effort": settings.reasoning_effort,
        "messages": [{"role": "user", "content": [{"type": "text", "text": READ_PROMPT}, {"type": "image_url", "image_url": {"url": url}}]}]},
        READ_TIMEOUT)
    try:
        content = answer["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    return parse_read(content), _counts(answer.get("usage"))


class Ledger:
    """Images requested, one line each, written BEFORE the call: a crash or a failed call still counts. Unreadable means no call."""

    def __init__(self, path: Path):
        self.path = path

    def _entries(self) -> list[dict]:
        try:
            lines = self.path.read_text().splitlines() if self.path.exists() else []
            entries = [json.loads(line) for line in lines]
            if not all(isinstance(e, dict) and isinstance(e["at"], (int, float)) and isinstance(e["delivery"], str) for e in entries):
                raise LedgerError("unexpected entry")
            return entries
        except (OSError, ValueError, KeyError) as e:
            raise LedgerError(type(e).__name__) from None

    def counts(self, delivery: str, now: float) -> tuple[int, int]:
        entries = self._entries()
        return sum(1 for e in entries if now - e["at"] < 86400), sum(1 for e in entries if e["delivery"] == delivery)

    def add(self, delivery: str, attempt: int, now: float) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps({"at": now, "delivery": delivery, "attempt": attempt}) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            raise LedgerError(type(e).__name__) from None


class _Record:
    def __init__(self, path: Path, model: str, read_model: str | None):
        self.path = path
        self.state = {"status": "drawing", "reason": None, "verified": False, "model": model, "readModel": read_model, "part": None,
                      "passedOnAttempt": None, "mediaType": None, "attempts": [], "imagesDrawn": 0,
                      "tokenUsage": {"image": {}, "read": {}}, "readCostUsd": 0.0, "startedAt": _now_iso(), "finishedAt": None}
        self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, indent=2) + "\n")
        tmp.replace(self.path)

    def finish(self, status: str, reason: str | None = None) -> dict:
        self.state.update(status=status, reason=reason, finishedAt=_now_iso())
        self.save()
        return self.state


def _add_usage(total: dict, usage: dict) -> None:
    for key, value in usage.items():
        total[key] = total.get(key, 0) + value


def run_job(delivery_dir: Path, ledger_path: Path, log=print) -> dict | None:
    """Never raises for a model, cap or file failure: the record says what happened. Returns it (None: the feature is off, or this
    delivery already has a record; nothing is written and nothing is called)."""
    delivery_dir = Path(delivery_dir)
    record_path = delivery_dir / RECORD_NAME
    load_dotenv()
    model = os.environ.get("TREE_IMAGE_MODEL_ID", "")
    if not model or record_path.exists():
        return None
    settings = Settings.vision_from_env()
    record = _Record(record_path, model, settings.model if settings else None)
    base_url = os.environ.get("META_MODEL_BASE_URL", "").rstrip("/")
    key = os.environ.get("META_MODEL_API_KEY", "")
    price = PRICES.get(settings.model) if settings else None
    if not (settings and base_url and key and price):  # no read-back, or no price for it: an image could never be checked or capped
        return record.finish("not-drawn", "not-configured")
    try:
        delivery = json.loads((delivery_dir / "delivery.json").read_text())
        delivery_id = str(delivery["id"])
        part = select_part((delivery.get("dependencyTree") or {}).get("edges") or [])
    except (OSError, ValueError, KeyError, TypeError):
        return record.finish("not-drawn", "job-stopped")
    if part is None:
        return record.finish("not-drawn", "no-suitable-part")
    program, pairs = part
    record.state["part"] = {"program": program, "edges": [list(p) for p in pairs]}
    record.save()
    worst_read = READ_INPUT_ESTIMATE * price[0] / 1e6 + READ_MAX_OUTPUT * price[2] / 1e6
    try:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        lock = (ledger_path.parent / (ledger_path.name + ".lock")).open("w")
    except OSError:
        return record.finish("not-drawn", "ledger-error")
    with lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)  # one at a time; released when the process ends, however it ends
        except OSError:
            return record.finish("not-drawn", "busy")
        return _attempts(record, Ledger(ledger_path), delivery_dir, delivery_id, pairs, model, base_url, key, settings, price, worst_read, log)


def _attempts(record, ledger, delivery_dir, delivery_id, pairs, model, base_url, key, settings, price, worst_read, log) -> dict:
    state, stop_reason, deadline = record.state, None, time.time() + JOB_SECONDS
    for n in range(1, MAX_ATTEMPTS + 1):
        if time.time() > deadline:
            stop_reason = "job-stopped"
            break
        if state["readCostUsd"] + worst_read > MAX_READ_USD:  # before the image: a drawing that cannot be read back is wasted
            stop_reason = "read-cap"
            break
        now = time.time()
        try:
            today, mine = ledger.counts(delivery_id, now)
            if today >= MAX_IMAGES_PER_DAY:
                stop_reason = "daily-cap"
                break
            if mine >= MAX_ATTEMPTS:
                stop_reason = "attempt-cap"
                break
            ledger.add(delivery_id, n, now)
        except LedgerError:
            stop_reason = "ledger-error"
            break
        state["imagesDrawn"] += 1
        attempt = {"attempt": n, "outcome": "image-error", "imageTokens": {}, "readTokens": {}, "readUsd": 0.0}
        state["attempts"].append(attempt)
        record.save()
        try:
            image, media_type, usage = draw(base_url, key, model, pairs)
        except CallFailed as e:
            log(f"attempt {n}: image call failed ({e})", flush=True)
            record.save()
            continue
        attempt["imageTokens"] = usage
        _add_usage(state["tokenUsage"]["image"], usage)
        record.save()
        reply, charged = None, 0.0
        try:
            reply, read_usage = read_back(settings, image, media_type)
            attempt["readTokens"] = read_usage
            _add_usage(state["tokenUsage"]["read"], read_usage)
            if "prompt_tokens" in read_usage and "completion_tokens" in read_usage:
                charged = (read_usage["prompt_tokens"] * price[0] + read_usage["completion_tokens"] * price[2]) / 1e6
            else:  # no usage to go by: charge the worst case, so the cap fails closed
                charged = worst_read
            attempt["outcome"] = "read-garbage"
        except CallFailed as e:
            log(f"attempt {n}: read-back failed ({e})", flush=True)
            attempt["outcome"] = "read-error"
            charged = worst_read if e.maybe_billed else 0.0
        attempt["readUsd"] = round(charged, 6)
        state["readCostUsd"] = round(state["readCostUsd"] + charged, 6)
        if reply is not None:
            result = compare(pairs, reply)
            attempt.update(outcome="match" if result["match"] else "no-match", **{k: v for k, v in result.items() if k != "match"})
        log(f"attempt {n}: {attempt['outcome']}, read cost ${attempt['readUsd']:.4f}", flush=True)
        record.save()
        if attempt["outcome"] == "match":
            if _store(delivery_dir, image, media_type):
                state.update(verified=True, passedOnAttempt=n, mediaType=media_type)
                return record.finish("passed")
            attempt["outcome"] = "store-error"
            stop_reason = "store-error"
            break
    read_any = any(a["outcome"] not in ("image-error",) for a in state["attempts"])
    if read_any:
        return record.finish("failed", stop_reason)
    return record.finish("not-drawn", stop_reason or "image-error")


def _store(delivery_dir: Path, image: bytes, media_type: str) -> bool:
    if len(image) > MAX_IMAGE_BYTES:
        return False
    target = delivery_dir / IMAGE_FILES[media_type]
    tmp = target.with_suffix(".tmp-image")
    try:
        tmp.write_bytes(image)
        tmp.replace(target)
        return True
    except OSError:
        return False


def run_cli(args) -> int:
    try:
        record = run_job(args.delivery_dir, args.ledger)
    except Exception as e:  # the type only: this job must never take anything else with it
        print(f"tree-draw stopped: {type(e).__name__}", flush=True)
        return 1
    print(f"tree-draw: {record['status'] if record else 'nothing to do'}", flush=True)
    return 0
