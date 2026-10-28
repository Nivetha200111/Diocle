"""FastAPI app. Run: uvicorn diocle_api.app:app --port 8000"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

import hmac

from fastapi import Header

from . import public
from .deliveries import get_delivery, list_deliveries, running_delivery, start_delivery
from .reverify import Busy, reverify_run
from .runs import get_run, list_runs

app = FastAPI(title="Diocle API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DIOCLE_WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Diocle-Admin"],
)


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


@app.get("/deliveries")
def deliveries() -> list[dict]:
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


def _admin_ok(token: str | None) -> bool:
    """Starting a delivery spends model credits. With DIOCLE_ADMIN_TOKEN set it needs that token; a hosted
    deployment (DIOCLE_HOSTED=1) without a token refuses to start anything."""
    expected = os.environ.get("DIOCLE_ADMIN_TOKEN", "")
    if not expected:
        return os.environ.get("DIOCLE_HOSTED") != "1"
    return bool(token) and hmac.compare_digest(token.encode(), expected.encode())


@app.get("/config")
def config() -> dict:
    return {"hosted": os.environ.get("DIOCLE_HOSTED") == "1",
            "startNeedsPasscode": bool(os.environ.get("DIOCLE_ADMIN_TOKEN")) or os.environ.get("DIOCLE_HOSTED") == "1",
            "publicImports": public.status()}


def _visitor(request: Request) -> str:
    """Best-effort visitor address: Vercel's forwarded header, else the connecting address."""
    for header in ("x-vercel-forwarded-for", "x-real-ip"):
        if request.headers.get(header):
            return request.headers[header].split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.post("/deliveries", status_code=202)
def start(request: DeliveryRequest, http: Request, x_diocle_admin: str | None = Header(default=None)) -> dict:
    """Start a delivery (spends model credits within the converter's caps). With the admin passcode: a pull request
    on an allowed target. Without it: a visitor import of any public repository, sandboxed, capped, no pull request."""
    admin = _admin_ok(x_diocle_admin)
    if not admin:
        if x_diocle_admin:
            raise HTTPException(status_code=403, detail="wrong passcode")
        if not public.enabled():
            raise HTTPException(status_code=403, detail="starting a delivery needs the admin passcode")
    try:
        if admin:
            if not request.target:
                raise ValueError("a target repository is required")
            return {"id": start_delivery(request.legacy, request.target, request.parallel, request.breaker)}
        busy = running_delivery()
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
