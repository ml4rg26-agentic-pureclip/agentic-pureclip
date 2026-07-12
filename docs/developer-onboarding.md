# Developer onboarding

This guide covers installation, repository structure, local execution, testing,
dashboard development, and VM deployment. For the research question, study
design, and findings, start with the [project README](../README.md). For a deeper
description of internal data flow, see
[`architecture-overview.md`](architecture-overview.md).

## Prerequisites and installation

Core development requires:

- **Python 3.10 or newer**.
- **[uv](https://docs.astral.sh/uv/)** for the Python environment and package
  installation. Snakemake and the Python dependencies are installed by `uv sync`.
- **PureCLIP 2** with the `pureclip2` executable available on `PATH` for real
  pipeline evaluations.
- **samtools** for BAM merging and indexing.
- **BEDTools** for interval operations, genomic shuffling, and sequence
  extraction.

Optional components require:

- **Node.js 20 or newer and npm** for dashboard UI development.
- **Docker and Docker Compose v2** for the containerized dashboard stack.
- **TeX Live, latexmk, and biber** to build the research report; see the
  [report-specific setup](report/ONBOARDING.md).
- A **`DEEPSEEK_API_KEY`** for LLM optimization. TPE needs no API key, and tests
  accept a dummy value.

Create the Python environment from the repository root:

```bash
uv sync
cp .env.example .env
uv run python -m pytest tests/ -q
```

`uv sync` installs `agentic_pureclip` editable, so the `python -m` entry points
and the `agentic-pureclip-run` console script resolve without a `PYTHONPATH` hack.

Before a real evaluation, verify the external executables:

```bash
pureclip2 --help
samtools --version
bedtools --version
```

## Data and reference preparation

The pipeline expects pre-aligned, deduplicated eCLIP BAM files, a GRCh38 FASTA
with its `.fai` index, ENCODE benchmark regions, and the motif PWM catalog. These
large files are stored below `data/` and are not committed.

```bash
# Download the available eCLIP datasets and motif catalog.
bash scripts/data/download_data.sh

# Download the full reference, or add --chr21 for the small development reference.
bash scripts/data/download_genome.sh --chr21
```

Dataset-specific paths and priors are recorded in `config/datasets/*.yaml`.
Generate a configuration from the registry with:

```bash
uv run python scripts/data/write_dataset_config.py RBFOX2_K562 \
  --out config/datasets/RBFOX2_K562.yaml
```

Do not commit downloaded BAMs, references, credentials, or generated results.

## Repository structure

| Path | Responsibility |
|---|---|
| `src/agentic_pureclip/loop/` | LLM and TPE optimization loops, shared evaluation state, prompts, and reports. |
| `src/agentic_pureclip/scoring/` | Reproducibility, motif, and benchmark scoring plus the composite objective. |
| `src/agentic_pureclip/postprocess/` | Snakemake workflow and binding-site footprint normalization. |
| `src/agentic_pureclip/pipeline/` | Configuration, dataset and motif registries, bounds, and workflow execution helpers. |
| `src/agentic_pureclip/run/` | CLI scheduling, manifest validation, and detached run launching. |
| `config/` | Reproducible run, dataset, prior, and batch definitions. |
| `scripts/data/` | Dataset and reference download/preparation utilities. |
| `scripts/motifs/` | Motif-catalog inspection and reorganization utilities. |
| `scripts/run/` | Batch execution and operational run tooling. |
| `tests/` | Pytest suite mirroring the core Python modules and failure paths. |
| `dashboard/api/` | FastAPI monitoring backend. |
| `dashboard/ui/` | React and TypeScript dashboard. |
| `docs/report/` | LaTeX research report, bibliography, figures, and build instructions. |
| `docs/` | Architecture, investigation, deployment, presentation, and onboarding material. |

The package uses a `src/` layout. Run commands from the repository root because
the workflow resolves `config/`, `data/`, `results/`, and `scripts/` relative to
the current directory.

## Running an optimization

For a short direct run, choose a dataset configuration and an optimizer:

```bash
# LLM agent
CONFIG_PATH=config/run_config.yaml MAX_ITER=8 \
  uv run python -m agentic_pureclip.loop.graph

# TPE using the same evaluation and objective
CONFIG_PATH=config/run_config.yaml MAX_ITER=12 \
  uv run python -m agentic_pureclip.loop.optuna_runner
```

Set `learn_on_chr21: true` for development-scale chromosome-21 evaluations; a
full-genome evaluation is substantially more expensive.

For scheduled or failure-tolerant runs, use the project CLI:

```bash
uv run agentic-pureclip-run \
  --dataset RBFOX2_K562 --optimizer llm \
  --max-iter 8 --hours 4 --threads 32 --chr21 \
  --weight reproducibility=0.5 --weight motif=0.25 --weight recall=0.25 \
  --param pureclip.bandwidth_nt=20:100 \
  --param postprocessing.force_width=3:15
```

Add `--dry-run` to validate and inspect the generated manifest without starting
the workflow. Batch outputs accumulate under `results/overnight/`.

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
