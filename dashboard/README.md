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

## Production (Docker Compose)

For a reliable, always-up deployment on the compute VM, run both services (plus a
reverse proxy) with `docker-compose.yml` at the repo root:

```bash
docker compose up -d --build      # from the repo root
# → whole dashboard on http://localhost:8080
ssh -f -N -L 8080:localhost:8080 bio     # tunnel the single public port
```

Three containers: `api` (FastAPI), `ui` (React SPA) and `proxy` (Caddy) that gives
them one origin (`/api/*` → api, everything else → ui). `results/` and `config/`
are bind-mounted **read-only**, and everything restarts on failure/reboot.

### Monitor-only — what containerising does *not* do

The API is coupled to its host in two ways, so this deployment is deliberately
**read-only monitoring**:

- **Live status** (`/api/status` active run, stage, elapsed) comes from scanning the
  host process table for pipeline jobs. The `api` container therefore runs with
  `pid: host` and ships `procps` so its `ps` sees those host processes.
- **Scheduling** (`POST /api/schedule`) launches the real PureCLIP/snakemake pipeline
  as a host subprocess — which can't run from inside the container. It is disabled
  here (`DASHBOARD_READ_ONLY=1` → 403); **start runs from the CLI on the host** and
  the dashboard will pick them up from `results/`.

## Endpoints

- `GET  /api/status` — host, pipeline stages, active run, plan, all experiments
- `GET  /api/options` — datasets, parameter bounds, objective weights, `run_active`
- `GET  /api/runs` — every recorded run with best score + per-iteration trail
- `GET  /api/run_sites?dataset=<id>` — binding sites for a dataset's best run
- `POST /api/schedule` — validate a run request, write a manifest, launch the runner
