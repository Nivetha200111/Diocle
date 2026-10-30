"""FastAPI app. Run: uvicorn diocle_api.app:app --port 8000"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from typing import Literal

from pydantic import BaseModel, ConfigDict
from fastapi.middleware.cors import CORSMiddleware

import hmac

from fastapi import Header

from . import livesamples, public
from .deliveries import get_delivery, list_deliveries, running_delivery, start_delivery, start_lock
from .deliver import GITHUB_URL
from .reverify import Busy, reverify_run
from .runs import get_run, get_source, list_runs
from .schema import run_schema

app = FastAPI(title="Diocle API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DIOCLE_WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Diocle-Admin"],
)


def _sandbox_addresses() -> set[str]:
    """Addresses of the sandbox container (from DIOCLE_SANDBOX_URL), resolved once."""
    import socket
    from urllib.parse import urlparse

    host = urlparse(os.environ.get("DIOCLE_SANDBOX_URL", "")).hostname
    try:
        return {info[4][0] for info in socket.getaddrinfo(host, None)} if host else set()
    except OSError:
        return set()


_sandbox_cache: tuple[float, set[str]] = (0.0, set())


def _sandbox() -> set[str]:
    """Re-resolved every minute: a restarted sandbox may get a new address."""
    global _sandbox_cache
    import time
    if time.time() - _sandbox_cache[0] > 60:
        _sandbox_cache = (time.time(), _sandbox_addresses())
    return _sandbox_cache[1]


@app.middleware("http")
async def refuse_the_sandbox(request: Request, call_next):
    """Code running in the sandbox can reach this api on the internal network; it gets nothing here."""
    if request.client and request.client.host in _sandbox():
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/runs")
def runs() -> list[dict]:
    return list_runs()


@app.get("/runs/{run_id}")
def run(run_id: str) -> dict:
    result = get_run(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@app.get("/runs/{run_id}/source")
def run_source(run_id: str) -> dict:
    result = get_source(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@app.get("/runs/{run_id}/schema")
def run_sql_schema(run_id: str) -> dict:
    result = run_schema(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="no schema for this run")
    return result


@app.get("/deliveries")
def deliveries() -> list[dict]:
    with start_lock:
        running_delivery()  # marks a delivery whose process died as failed, so the list tells the truth
    return list_deliveries()


@app.get("/deliveries/{delivery_id}")
def delivery(delivery_id: str) -> dict:
    result = get_delivery(delivery_id)
    if result is None:
        raise HTTPException(status_code=404, detail="delivery not found")
    return result



class DeliveryRequest(BaseModel):
    """contracts/delivery.schema.json $defs.request"""
    legacy: str
    target: str | None = None
    parallel: bool = False
    breaker: bool = False
    convertAnyway: bool = False  # admin only (a visitor who sets it is refused): see deliver.py --convert-anyway


def _admin_configured() -> bool:
    return bool(os.environ.get("DIOCLE_ADMIN_TOKEN")) or os.environ.get("DIOCLE_HOSTED") == "1"


def _loopback(request: Request) -> bool:
    """The request came from this machine itself, not through a proxy (a forwarded header means someone else is behind it)."""
    if any(request.headers.get(h) for h in ("x-forwarded-for", "x-vercel-forwarded-for", "x-real-ip", "forwarded")):
        return False
    return bool(request.client) and request.client.host in ("127.0.0.1", "::1", "localhost")


def _admin_ok(token: str | None) -> bool:
    """Starting a delivery spends model credits. With DIOCLE_ADMIN_TOKEN set it needs that token; a hosted
    deployment (DIOCLE_HOSTED=1) without a token refuses to start anything."""
    expected = os.environ.get("DIOCLE_ADMIN_TOKEN", "")
    if not expected:
        return os.environ.get("DIOCLE_HOSTED") != "1"
    return bool(token) and hmac.compare_digest(token.encode(), expected.encode())


def _visitor(request: Request) -> str:
    """Best-effort visitor address: Vercel's forwarded header, else the connecting address."""
    for header in ("x-vercel-forwarded-for", "x-real-ip"):
        if request.headers.get(header):
            return request.headers[header].split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.get("/config")
def config(http: Request) -> dict:
    return {"hosted": os.environ.get("DIOCLE_HOSTED") == "1",
            "startNeedsPasscode": bool(os.environ.get("DIOCLE_ADMIN_TOKEN")) or os.environ.get("DIOCLE_HOSTED") == "1",
            # `samples` (contracts/live-sample.schema.json $defs.status): the two live buttons, additive
            "publicImports": {**public.status(), "samples": livesamples.status(_visitor(http))}}


@app.post("/deliveries", status_code=202)
def start(request: DeliveryRequest, http: Request, x_diocle_admin: str | None = Header(default=None)) -> dict:
    """Start a delivery (spends model credits within the converter's caps). With the admin passcode: a pull request
    on an allowed target. Without it: a visitor import of any public repository, sandboxed, capped, no pull request."""
    admin = _admin_ok(x_diocle_admin)
    if request.convertAnyway and not admin:
        raise HTTPException(status_code=403, detail="convert anyway needs the admin passcode or the local command line")
    if request.convertAnyway and not _admin_configured() and not _loopback(http):
        # with neither DIOCLE_HOSTED nor DIOCLE_ADMIN_TOKEN set the admin check is open: only this machine may use the mode
        raise HTTPException(status_code=403, detail="convert anyway over the network needs DIOCLE_ADMIN_TOKEN (or DIOCLE_HOSTED=1) on the engine")
    if not admin:
        if x_diocle_admin:
            raise HTTPException(status_code=403, detail="wrong passcode")
        if not public.enabled():
            raise HTTPException(status_code=403, detail="starting a delivery needs the admin passcode")
    try:
        with start_lock:  # busy check, budget and the new record together: parallel requests start one job
            if admin:
                if not request.target:
                    raise ValueError("a target repository is required")
                return {"id": start_delivery(request.legacy, request.target, request.parallel, request.breaker,
                                               convert_anyway=request.convertAnyway)}
            if not GITHUB_URL.match(request.legacy.strip()):
                raise ValueError(f"not a GitHub repository URL: {request.legacy!r}")
            busy = running_delivery() or livesamples.running_job()
            if busy:
                raise RuntimeError(f"{busy} is still running; try again when it finishes")
            public.admit(_visitor(http))
            return {"id": start_delivery(request.legacy, None, False, False, public=True)}
    except PermissionError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, SystemExit) as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/runs/{run_id}/reverify")
def reverify(run_id: str) -> dict:
    """Anyone may re-check a certified run on fresh random inputs: CPU only, no model calls, one at a time."""
    try:
        result = reverify_run(run_id)
    except Busy as e:
        raise HTTPException(status_code=429, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except (RuntimeError, OSError) as e:
        raise HTTPException(status_code=502, detail=f"the verifier could not run: {e}")
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result


class LiveSampleRequest(BaseModel):
    """contracts/live-sample.schema.json $defs.request: a name from a fixed list and nothing else (any other field is refused)."""
    model_config = ConfigDict(extra="forbid")
    sample: Literal["addfee", "loyalty-waiver-printout"]


@app.post("/samples/live", status_code=202)
def start_live_sample(request: LiveSampleRequest, http: Request) -> dict:
    """The public "try it live" buttons. No passcode: the request cannot carry anything but a sample name, the job runs one
    bundled synthetic sample under hard caps (livesamples.py), and anything model-written runs in the sandbox only."""
    try:
        with start_lock:  # the busy check, the caps and the new job record together, shared with deliveries and imports
            return {"id": livesamples.start(request.sample, _visitor(http))}
    except livesamples.Refused as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@app.get("/samples/live/{job_id}")
def live_sample(job_id: str) -> dict:
    job = livesamples.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@app.get("/samples/printout-image")
def printout_image():
    """The one bundled printout the printout button reads (a fixed file; there is no path parameter)."""
    from fastapi.responses import FileResponse

    from .samplejob import PRINTOUT_IMAGE

    return FileResponse(PRINTOUT_IMAGE, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})
