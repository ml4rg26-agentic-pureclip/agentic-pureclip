# Agentic PureCLIP — UI

A React Router (SPA) frontend for the agentic-PureCLIP monitor. It polls the
monitor's JSON API (`/api/status`, served by `scripts/monitor.py`) and renders:

- **Dashboard** — active run + pipeline stepper, batch queue & ETA, per-dataset
  optimisation trajectories, and the LLM-vs-Optuna head-to-head.
- **Variables** — a plain-English guide to every tunable parameter, what it does,
  and what the optimizer measures (for people new to the project).

## Run it

The monitor runs on the compute VM (port 8888). Tunnel it locally first:

```bash
ssh -f -N -L 8888:localhost:8888 bio
```

Then start the UI (Vite proxies `/api` → the monitor):

```bash
cd ui
npm install
npm run dev          # http://localhost:5173
```

Point at a different monitor with `MONITOR_API`:

```bash
MONITOR_API=http://localhost:9000 npm run dev
```

## Build

```bash
npm run build        # SPA output in build/client/
```

This is a pure client-side SPA (`ssr: false`) — it only needs the monitor's API at runtime.
