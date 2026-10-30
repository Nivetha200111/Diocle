"""Speech to text for the voice question (contracts/voice-question.schema.json): Meta's Muse Voice Transcribe.

ROUTE (found by reading the Muse Code binary's strings and watching what `muse voice transcribe` sends to a local
WebSocket listener; see docs/HANDOFF.md): a duplex WebSocket, not the OpenAI-style HTTP routes (those 404 for this
model). The client opens wss://<host>/voyager/v1/asr/duplex, sends one JSON text frame
  {"mode": "DEFAULT", "authorization": {"accessToken": "OAuth <META key>"}, "audioEncoding": "PCM_16KHZ", "model": "..."}
waits for {"sessionId": ...}, streams raw 16-bit little-endian mono 16 kHz PCM in binary frames (100 ms = 3200 bytes) and
ends with {"endStream": {}}; the service answers with transcript messages. This is the protocol of Meta's own client; it
is NOT a documented public API and may change. The host, the wire model name and the label come from the environment
(rule 9): VOICE_ASR_URL, VOICE_ASR_MODEL, VOICE_MODEL_ID. The key is the same Meta key as hosted mode (META_MODEL_API_KEY).

Safety: the audio is validated by magic bytes (a RIFF/WAVE header with PCM 16 kHz mono 16-bit), never by file name, and
capped at 10 s and 500 KB. The transcript is UNTRUSTED text: capped, control characters stripped, and wrapped by ask.py
in fenced data. Errors are fixed phrases; what the service says is never passed on. Standard library only.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import time
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlsplit

from .config import VOICE_PRICES, load_dotenv

MAX_AUDIO_BYTES = 500 * 1024
MAX_AUDIO_SECONDS = 10.0
MIN_AUDIO_SECONDS = 0.3
MAX_TRANSCRIPT_CHARS = 300
RATE, CHUNK = 16000, 3200  # 16 kHz, 100 ms of 16-bit mono per frame
CONNECT_TIMEOUT = 10.0
TOTAL_TIMEOUT = 30.0
MAX_REPLY_FRAME = 64 * 1024


class VoiceError(Exception):
    """A transcription that did not happen. `str(e)` is a fixed phrase that is safe to show; it never holds provider text."""


@dataclass(frozen=True)
class Clip:
    pcm: bytes
    seconds: float


@dataclass(frozen=True)
class Transcript:
    text: str  # sanitised, at most MAX_TRANSCRIPT_CHARS
    model: str
    audio_seconds: float
    cost_usd: float
    price_confirmed: bool


def validate_wav(data: bytes) -> Clip:
    """The PCM inside a 16 kHz mono 16-bit WAV, judged by the bytes alone. Anything else (an executable renamed .wav, an
    MP3, m4a, webm, a stereo or 44.1 kHz file, an empty or oversize file, more than 10 s) is refused with a fixed phrase."""
    if not data:
        raise VoiceError("the audio clip is empty")
    if len(data) > MAX_AUDIO_BYTES:
        raise VoiceError(f"the audio clip is larger than {MAX_AUDIO_BYTES // 1024} KB")
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise VoiceError("the audio clip is not a WAV file (16 kHz mono 16-bit WAV only)")
    pos, fmt, pcm = 12, None, None
    while pos + 8 <= len(data):
        tag, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if tag == b"fmt " and size >= 16 and body + 16 <= len(data):
            fmt = struct.unpack("<HHIIHH", data[body:body + 16])
        elif tag == b"data":
            pcm = data[body:body + min(size, len(data) - body)]  # a streamed WAV may claim more than it holds
            break
        pos = body + size + (size & 1)
    if fmt is None or pcm is None:
        raise VoiceError("the audio clip is not a complete WAV file")
    fmt_tag, channels, rate, _, _, bits = fmt
    if (fmt_tag, channels, rate, bits) != (1, 1, RATE, 16):
        raise VoiceError("the audio clip must be 16 kHz mono 16-bit PCM WAV")
    pcm = pcm[: len(pcm) // 2 * 2]
    seconds = len(pcm) / (RATE * 2)
    if seconds > MAX_AUDIO_SECONDS:
        raise VoiceError(f"the audio clip is longer than {MAX_AUDIO_SECONDS:.0f} seconds")
    if seconds < MIN_AUDIO_SECONDS:
        raise VoiceError("the audio clip is too short")
    return Clip(pcm, seconds)


def clean_text(raw) -> str:
    """Untrusted transcript text: one line, no control or format characters, at most 300 characters."""
    if not isinstance(raw, str):
        return ""
    kept = "".join(" " if ch.isspace() else ch for ch in raw if not unicodedata.category(ch).startswith(("C",)) or ch.isspace())
    return " ".join(kept.split())[:MAX_TRANSCRIPT_CHARS]


def clean_question(raw) -> str:
    return clean_text(raw)


def price_of(model: str, seconds: float) -> tuple[float, bool] | None:
    """(USD, price confirmed) for this much audio, or None for a model with no price (fail closed)."""
    entry = VOICE_PRICES.get(model)
    return None if entry is None else (round(entry[0] * seconds, 6), entry[1])


def worst_case_usd(model: str) -> float | None:
    entry = price_of(model, MAX_AUDIO_SECONDS)
    return None if entry is None else entry[0]


@dataclass(frozen=True)
class VoiceSettings:
    url: str
    wire_model: str
    model: str  # the label, e.g. muse-voice-transcribe-1.0, priced in VOICE_PRICES
    api_key: str

    @classmethod
    def from_env(cls) -> "VoiceSettings | None":
        load_dotenv()
        url, wire, model = (os.environ.get(n, "") for n in ("VOICE_ASR_URL", "VOICE_ASR_MODEL", "VOICE_MODEL_ID"))
        key = os.environ.get("VOICE_API_KEY") or os.environ.get("META_MODEL_API_KEY", "")
        if not (url and wire and model and key):
            return None
        return cls(url, wire, model, key)


# --- a small WebSocket client (RFC 6455), client side only -----------------------------------------------------------

def _recv(sock, n: int, deadline: float | None = None) -> bytes:
    out = b""
    while len(out) < n:
        if deadline is not None:  # an absolute deadline: a slow trickle cannot stretch the call past TOTAL_TIMEOUT
            left = deadline - time.monotonic()
            if left <= 0:
                raise VoiceError("the speech service timed out")
            sock.settimeout(left)
        try:
            chunk = sock.recv(n - len(out))
        except (TimeoutError, socket.timeout):
            raise VoiceError("the speech service timed out") from None
        if not chunk:
            raise VoiceError("the speech service closed the connection")
        out += chunk
    return out


def _send(sock, opcode: int, payload: bytes) -> None:
    mask = os.urandom(4)
    head = bytes([0x80 | opcode])
    n = len(payload)
    head += bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n)
    sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))


def _read_frame(sock, deadline: float | None = None) -> tuple[int, bytes]:
    b0, b1 = _recv(sock, 2, deadline)
    n = b1 & 0x7F
    if n == 126:
        n = struct.unpack(">H", _recv(sock, 2, deadline))[0]
    elif n == 127:
        n = struct.unpack(">Q", _recv(sock, 8, deadline))[0]
    if n > MAX_REPLY_FRAME:
        raise VoiceError("the speech service sent an oversize reply")
    body = _recv(sock, n, deadline) if n else b""
    return b0 & 0x0F, body


class _Buffered:
    """The socket plus bytes that arrived together with the handshake reply."""

    def __init__(self, sock, first: bytes):
        self.sock, self.buf = sock, first

    def recv(self, n: int) -> bytes:
        if self.buf:
            out, self.buf = self.buf[:n], self.buf[n:]
            return out
        return self.sock.recv(n)

    def sendall(self, data): self.sock.sendall(data)
    def settimeout(self, t): self.sock.settimeout(t)
    def close(self): self.sock.close()


def _connect(url: str):
    parts = urlsplit(url)
    if parts.scheme not in ("wss", "ws") or not parts.hostname:
        raise VoiceError("the speech service address is not valid")
    secure = parts.scheme == "wss"
    if not secure and parts.hostname not in ("127.0.0.1", "::1", "localhost"):
        raise VoiceError("the speech service address must be wss:// (plain ws:// is only allowed for this machine)")
    port = parts.port or (443 if secure else 80)
    try:
        sock = socket.create_connection((parts.hostname, port), timeout=CONNECT_TIMEOUT)
        if secure:
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=parts.hostname)
        key = base64.b64encode(os.urandom(16)).decode()
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {parts.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head and len(head) < 8192:
            chunk = sock.recv(4096)
            if not chunk:
                break
            head += chunk
    except (OSError, ssl.SSLError):
        raise VoiceError("cannot reach the speech service") from None
    head, _, rest = head.partition(b"\r\n\r\n")  # `rest` may already hold the first frames: keep them
    accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    lines = head.decode("latin-1").split("\r\n")
    headers = {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in lines[1:] if ":" in l}
    if not lines[0].startswith("HTTP/1.1 101") or headers.get("sec-websocket-accept") != accept:
        sock.close()
        raise VoiceError("the speech service refused the connection")
    return _Buffered(sock, rest)


def _extract(msg: dict) -> tuple[str | None, bool]:
    """(text, final) of one service message; text None when it carries none. Accepts the shapes seen on the wire."""
    t = msg.get("transcript")
    if isinstance(t, dict):
        text = t.get("text", t.get("transcript"))
        return (text if isinstance(text, str) else None), bool(t.get("final", msg.get("final")))
    return (t if isinstance(t, str) else None), bool(msg.get("final"))


def transcribe_pcm(clip: Clip, settings: VoiceSettings, *, connect=_connect, deadline_seconds: float = TOTAL_TIMEOUT) -> str:
    """Stream the PCM to the speech service and return the raw final text. `connect` is a seam for tests."""
    start = time.monotonic()
    deadline = start + deadline_seconds
    sock = connect(settings.url)
    sock.settimeout(CONNECT_TIMEOUT)
    finals: list[str] = []
    last_partial = ""
    try:
        _send(sock, 1, json.dumps({"mode": "DEFAULT", "authorization": {"accessToken": f"OAuth {settings.api_key}"},
                                   "audioEncoding": "PCM_16KHZ", "model": settings.wire_model}).encode())
        opened = False
        while not opened:
            op, body = _read_frame(sock, deadline)
            if op == 1:
                try:
                    msg = json.loads(body or b"{}")
                except ValueError:
                    raise VoiceError("the speech service sent an unreadable reply") from None
                if isinstance(msg, dict) and msg.get("error"):
                    raise VoiceError("the speech service failed")
                opened = isinstance(msg, dict) and "sessionId" in msg
            elif op == 8:
                raise VoiceError("the speech service refused the credential")
        for i in range(0, len(clip.pcm), CHUNK):
            _send(sock, 2, clip.pcm[i:i + CHUNK])
        _send(sock, 1, b'{"endStream": {}}')
        while time.monotonic() - start <= deadline_seconds:
            try:
                op, body = _read_frame(sock, deadline)
            except VoiceError as e:
                if "timed out" in str(e):
                    raise
                break
            if op == 9:
                _send(sock, 10, body)
            elif op == 8:
                break
            elif op == 1:
                try:
                    msg = json.loads(body)
                except ValueError:
                    continue
                if not isinstance(msg, dict):
                    continue
                if msg.get("error"):
                    raise VoiceError("the speech service failed")
                text, final = _extract(msg)
                if text:
                    last_partial = text
                    if final:
                        finals.append(text)
        else:
            raise VoiceError("the speech service timed out")
    except (OSError, ssl.SSLError):
        raise VoiceError("cannot reach the speech service") from None
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return " ".join(finals) if finals else last_partial


def transcribe(wav: bytes, settings: VoiceSettings | None = None, *, max_usd: float, connect=_connect) -> Transcript:
    """Validate the clip, check the dollar cap BEFORE any call, transcribe, return the sanitised text and its cost."""
    settings = settings or VoiceSettings.from_env()
    if settings is None:
        raise VoiceError("voice transcription is not configured on this machine")
    clip = validate_wav(wav)
    cost = price_of(settings.model, clip.seconds)
    if cost is None:
        raise VoiceError("the transcription model has no known price, so the cost cap cannot be enforced")
    if cost[0] > max_usd:
        raise VoiceError("the transcription could cost more than the dollar cap")
    text = clean_text(transcribe_pcm(clip, settings, connect=connect))
    if not text:
        raise VoiceError("no words were heard in the clip")
    return Transcript(text, settings.model, round(clip.seconds, 2), cost[0], cost[1])
