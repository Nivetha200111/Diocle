"""FastAPI app. Run: uvicorn diocle_api.app:app --port 8000"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .runs import get_run, list_runs

app = FastAPI(title="Diocle API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("DIOCLE_WEB_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001").split(","),
    allow_methods=["GET"],
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
