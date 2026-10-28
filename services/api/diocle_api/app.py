"""FastAPI app. Run: uvicorn diocle_api.app:app --port 8000"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from .deliveries import get_delivery, list_deliveries, start_delivery
from .runs import get_run, list_runs

app = FastAPI(title="Diocle API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DIOCLE_WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001").split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
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


@app.post("/deliveries", status_code=202)
def start(request: DeliveryRequest) -> dict:
    """Start a delivery (spends model credits within the converter's caps). Bind the API to localhost only."""
    try:
        return {"id": start_delivery(request.legacy, request.target, request.parallel, request.breaker)}
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except (ValueError, SystemExit) as e:
        raise HTTPException(status_code=400, detail=str(e))
