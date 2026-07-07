# Dashboard

The live monitoring dashboard for agentic PureCLIP runs — two independent
services:

| Dir | What | Stack | Dev | Docker |
|-----|------|-------|-----|--------|
| [`api/`](api/) | JSON data provider (`/api/*`) | FastAPI + uvicorn | `uv run uvicorn dashboard.api.main:app --port 8888` | `dashboard/api/Dockerfile` |
| [`ui/`](ui/) | React Router SPA | React 19 + Vite | `cd dashboard/ui && npm run dev` | `dashboard/ui/Dockerfile` |

The UI calls the API over `/api/*`. In dev, the Vite proxy forwards `/api` to the
backend (`MONITOR_API`, default `http://localhost:8888`); for a standalone build
set `VITE_API_BASE` to the backend URL.

## Local development

```bash
# terminal 1 — data API (from the repo root; it reads results/ and config/)
uv run uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8888 --reload

# terminal 2 — UI
cd dashboard/ui && npm install && npm run dev      # http://localhost:5173
```

On the compute VM the API runs on port 8888; tunnel it:
`ssh -f -N -L 8888:localhost:8888 bio`.

## Endpoints

- `GET  /api/status` — host, pipeline stages, active run, plan, all experiments
- `GET  /api/options` — datasets, parameter bounds, objective weights, `run_active`
- `GET  /api/runs` — every recorded run with best score + per-iteration trail
- `GET  /api/run_sites?dataset=<id>` — binding sites for a dataset's best run
- `POST /api/schedule` — validate a run request, write a manifest, launch the runner
