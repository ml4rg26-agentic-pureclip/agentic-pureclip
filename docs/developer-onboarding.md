# Developer onboarding

Practical setup for working on Agentic PureCLIP — local dev, how runs are
launched, and how the dashboard is deployed. For the science and the day-to-day
user commands, start with the [README](../README.md); for the internals, see
[`architecture-overview.md`](architecture-overview.md).

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** — Python toolchain (installs the project + deps).
- **Node 20+ / npm** — for the dashboard UI (`dashboard/ui`).
- **Docker + Docker Compose v2** — to run the dashboard stack (deployment only).
- A **`DEEPSEEK_API_KEY`** in `.env` for LLM runs (Optuna needs none; tests accept a dummy).

```bash
uv sync
cp .env.example .env
uv run python -m pytest tests/ -q
```

`uv sync` installs `agentic_pureclip` editable, so the `python -m` entry points
and the `agentic-pureclip-run` console script resolve without a `PYTHONPATH` hack.

## How a run is launched

There is one code path for starting a run, shared by the CLI and the dashboard, so
a run started from either is identical:

```
agentic-pureclip-run  ─┐
                       ├─▶  agentic_pureclip.run.schedule.build_manifest()  (validate + build manifest)
dashboard  /api/schedule ┘   └▶  agentic_pureclip.run.launcher.launch_detached()  (write manifest + spawn overnight_batch.py)
```

- **`src/agentic_pureclip/run/schedule.py`** — `build_manifest(spec)`: validates a
  run request (dataset, optimizer, iters/hours/threads, objective weights, and
  per-parameter search bounds clamped to `DEFAULT_SEARCH_BOUNDS`) and returns the
  overnight-batch manifest. Pure, no I/O — this is the single source of truth.
- **`src/agentic_pureclip/run/launcher.py`** — writes the manifest to
  `config/ui_runs/<job_id>.yaml` and spawns `scripts/run/overnight_batch.py`
  detached, with `PYTHONPATH=.` and the pureclip dir on `PATH`.
- **`src/agentic_pureclip/run/cli.py`** — the `agentic-pureclip-run` CLI
  (registered in `pyproject.toml` under `[project.scripts]`).

The runner and everything it launches read `results/`, `config/` and `scripts/`
**relative to the current directory**, so always run from the repo root.

## Dashboard — local development

Two services; in dev the Vite proxy forwards `/api` to the backend.

```bash
# terminal 1 — data API (from the repo root; reads results/ and config/)
uv run uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8888 --reload

# terminal 2 — UI (http://localhost:5173, proxies /api → :8888)
cd dashboard/ui && npm install && npm run dev
```

The UI calls `/api/*`; the backend serves JSON only (`/api/status`, `/api/runs`,
`/api/options`, `/api/run_sites`, `/api/report`, `POST /api/schedule`). See
[`dashboard/README.md`](../dashboard/README.md) for the endpoint list.

## Dashboard — production (Docker Compose)

`docker-compose.yml` at the repo root defines three containers:

| Service | Image | Role |
|---------|-------|------|
| `api`   | `dashboard/api/Dockerfile` | FastAPI data provider. Runs with **`pid: host`** (+ `procps`) so its process scan sees the host's pipeline jobs, which is how live status is derived. |
| `ui`    | `dashboard/ui/Dockerfile`  | React Router SPA (static server). |
| `proxy` | `caddy:2-alpine`           | One origin: `/api/*` → api, everything else → ui. Only this port (**8080**) is published. |

```bash
docker compose up -d --build      # from the repo root
ssh -N -L 8080:localhost:8080 -p 30121 -i ~/.ssh/id_ed25519 ubuntu@194.94.4.28
# → http://localhost:8080
```

### Monitor-only, by design

`results/` and `config/` are bind-mounted **read-only**, and `POST /api/schedule`
is disabled (`DASHBOARD_READ_ONLY=1` → 403). The API is host-coupled in two ways
that a container can't reproduce:

1. **Live status** comes from scanning the host process table for pipeline jobs —
   handled by `pid: host` + `procps` in the image.
2. **Scheduling** launches the real PureCLIP/snakemake pipeline as a host
   subprocess, which can't run inside the API container. So the container never
   launches runs — use `agentic-pureclip-run` on the host instead, and the Plan
   page emits that command.

## Deploying to the VM

The VM copy at `/vol/storage1/johannes/projects/agentic-pureclip` is a plain
directory (not a git checkout), so sync your code and rebuild:

```bash
# from your local checkout (real host: see the SSH block above)
rsync -avR --exclude results --exclude data --exclude .git --exclude node_modules \
    src dashboard scripts pyproject.toml uv.lock docker-compose.yml \
    bio:/vol/storage1/johannes/projects/agentic-pureclip/

ssh bio 'cd /vol/storage1/johannes/projects/agentic-pureclip && docker compose up -d --build'
```

(`bio` is a convenience SSH alias for
`ssh -p 30121 -i ~/.ssh/id_ed25519 ubuntu@194.94.4.28`; add it to `~/.ssh/config`
or use the full command.)

### VM storage note

The VM's **root disk (`/dev/vda1`) is only ~19 GB and stays near full**; the large
disk is **`/vol/storage1`** (`/dev/vdb`, ~984 GB). Docker and its containerd image
store are pointed at `/vol/storage1` (`/etc/docker/daemon.json` `data-root`, and
`/etc/containerd/config.toml` `root = /vol/storage1/containerd`). If image
builds/pulls fail with *"No space left on device"*, check that these still point
at `/vol` and that the root disk hasn't filled from something else. The VM is
shared with other users, so treat Docker/containerd restarts as shared-infra
changes.

## Testing

```bash
uv run python -m pytest tests/ -q         # full suite
uv run python -m pytest tests/ -q -k run  # e.g. just the run/CLI tests
```

`agentic-pureclip-run --dry-run …` is the fastest way to check that a run request
validates and produces the manifest you expect, without launching anything.
