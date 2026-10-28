"""FastAPI app. Run: uvicorn diocle_api.app:app --port 8000"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

import hmac

from fastapi import Header

from .deliveries import get_delivery, list_deliveries, start_delivery
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
    target: str
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
            "startNeedsPasscode": bool(os.environ.get("DIOCLE_ADMIN_TOKEN")) or os.environ.get("DIOCLE_HOSTED") == "1"}


@app.post("/deliveries", status_code=202)
def start(request: DeliveryRequest, x_diocle_admin: str | None = Header(default=None)) -> dict:
    """Start a delivery (spends model credits within the converter's caps)."""
    if not _admin_ok(x_diocle_admin):
        raise HTTPException(status_code=403, detail="starting a delivery needs the admin passcode")
    try:
        return {"id": start_delivery(request.legacy, request.target, request.parallel, request.breaker)}
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
