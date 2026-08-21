"""FastAPI backend — demo solver for frontend integration testing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import agent as ucs_agent

app = FastAPI(title="Emergency Control API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SCENARIO_PATH = Path(__file__).resolve().parents[2] / "scenarios" / "scenario.json"


def _load_default_scenario() -> dict[str, Any]:
    with SCENARIO_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/scenario")
def get_scenario() -> dict[str, Any]:
    return _load_default_scenario()


@app.post("/api/solve")
def solve(scenario: dict[str, Any]) -> dict[str, Any]:
    """Solve the mission with the UCS search agent (agent.py).

    Kept as a plain `def` (not `async def`) on purpose: FastAPI runs
    synchronous path functions in a worker thread automatically, so a
    CPU-bound search that can take tens of seconds does not block the event
    loop / other requests (e.g. GET /api/health while a solve is running).

    Response contract: solution_found, total_cost, steps[{op, cost, ...}].
    """
    data = scenario if scenario else _load_default_scenario()
    return ucs_agent.solve(data)