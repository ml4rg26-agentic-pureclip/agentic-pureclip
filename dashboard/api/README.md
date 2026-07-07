# Dashboard API

FastAPI backend that exposes the live run state as JSON. Data only — the React
frontend lives in [`../ui`](../ui).

- `main.py` — the FastAPI app (`/api/*` routes + CORS).
- `collectors.py` — pure-Python data collection: reads running processes and the
  `results/` / `config/` trees to build the status snapshot, run leaderboard,
  binding-site view, and to schedule new runs.

## Run

Launch from the **repository root** — the collectors read `results/` and
`config/` relative to the working directory:

```bash
uv run uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8888 --reload
```

Or in a container (built from the repo root):

```bash
docker build -f dashboard/api/Dockerfile -t agentic-pureclip-api .
docker run -p 8888:8888 \
  -v "$PWD/results:/app/results" -v "$PWD/config:/app/config" \
  agentic-pureclip-api
```

The process list (`ps`) that drives the "active run" view is only meaningful when
the API runs on the same host as the optimisation jobs.
