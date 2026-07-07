# Agentic PureCLIP — Dashboard UI

A React Router (SPA) frontend for the agentic-PureCLIP dashboard. It polls the
FastAPI backend's JSON API (`/api/status`, served by `dashboard/api`) and renders:

- **Dashboard** — active run + pipeline stepper, batch queue & ETA, per-dataset
  optimisation trajectories, and the LLM-vs-Optuna head-to-head.
- **Variables** — a plain-English guide to every tunable parameter, what it does,
  and what the optimizer measures (for people new to the project).

## Run it

The API backend runs on the compute VM (port 8888). Tunnel it locally first:

```bash
ssh -f -N -L 8888:localhost:8888 bio
```

Then start the UI (Vite proxies `/api` → the backend):

```bash
cd dashboard/ui
npm install
npm run dev          # http://localhost:5173
```

Point at a different backend with `MONITOR_API`:

```bash
MONITOR_API=http://localhost:9000 npm run dev
```

## Build

```bash
npm run build        # SPA output in build/client/
```

A standalone build hitting a remote backend (rather than a same-origin proxy)
needs the API base baked in at build time:

```bash
VITE_API_BASE=https://api.example.org npm run build
```

This is a pure client-side SPA (`ssr: false`) — it only needs the backend's API at runtime.
