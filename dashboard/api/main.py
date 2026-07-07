"""FastAPI backend for the agentic PureCLIP monitoring dashboard.

A thin JSON API over the data collectors in ``dashboard.api.collectors``. It
serves data only — the React frontend in ``dashboard/ui`` is a separate service
(Vite dev server, or its own container) that calls these ``/api/*`` endpoints.

Run it from the repository root (the collectors read ``results/`` and
``config/`` relative to the working directory)::

    uv run uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8888

    # tunnel from a workstation:
    ssh -L 8888:localhost:8888 bio   →   http://localhost:8888/api/status
"""

from __future__ import annotations

import json

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agentic_pureclip.pipeline.configs import DEFAULT_SEARCH_BOUNDS
from agentic_pureclip.pipeline.datasets import list_datasets

from . import collectors
from .collectors import DEFAULT_OBJECTIVE_WEIGHTS

app = FastAPI(title="Agentic PureCLIP Dashboard API")

# The frontend is served from a different origin (Vite dev server, or a separate
# container), so allow cross-origin reads — the API is read-mostly and unauthenticated.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/status")
def status() -> dict:
    """Live snapshot: host, pipeline stages, active run, plan and all experiments."""
    return collectors.build_status()


@app.get("/api/options")
def options() -> dict:
    """Form options for scheduling a run: datasets, parameter bounds, weights."""
    return {
        "datasets": list_datasets(),
        "bounds": DEFAULT_SEARCH_BOUNDS,
        "weights": DEFAULT_OBJECTIVE_WEIGHTS,
        "run_active": collectors._run_active(),
    }


@app.get("/api/runs")
def runs() -> dict:
    """Every recorded run with its best score and per-iteration decision trail."""
    return {"runs": collectors.collect_runs()}


@app.get("/api/run_sites")
def run_sites(dataset: str = "") -> Response:
    """Binding sites for a dataset's best run (for the genome-track view)."""
    if not dataset:
        return JSONResponse({"error": "missing ?dataset="}, status_code=400)
    try:
        return JSONResponse(collectors.collect_run_sites(dataset))
    except Exception as exc:  # never 500 the UI on a bad dataset
        return JSONResponse(
            {"error": str(exc), "dataset": dataset, "sites": []}, status_code=500
        )


@app.post("/api/schedule")
async def schedule(request: Request) -> Response:
    """Validate a UI run request, write a manifest and launch the CLI runner."""
    raw = await request.body()
    try:
        spec = json.loads(raw or b"{}")
    except Exception:
        return JSONResponse({"ok": False, "error": "invalid JSON body"}, status_code=400)
    try:
        code, result = collectors.schedule_run(spec)
    except Exception as exc:  # never crash the server on a bad request
        code, result = 500, {"ok": False, "error": str(exc)}
    return JSONResponse(result, status_code=code)
