# Agentic PureCLIP

Parameter optimization for **eCLIP** peak calling with
[PureCLIP](https://github.com/skrakau/PureCLIP). An optimizer proposes PureCLIP
+ post-processing parameters; for each set the pipeline runs PureCLIP, scores the
result against biological quality signals, and iterates to maximize a composite
quality score. Two interchangeable optimizers are available — an **LLM agent**
(DeepSeek, via LangGraph) and **Optuna** (TPE/Bayesian) — sharing the same
evaluation and objective, so they can be compared apples-to-apples.

> This README is the practical quick-start (eCLIP, PureCLIP, the RBPs and their
> motifs, cell lines, and the scoring rationale).

## What it does

From pre-aligned, deduplicated ENCODE BAM files (IP replicates + size-matched
input), the Snakemake pipeline merges IP → runs `pureclip2` → per-replicate
PureCLIP → post-processes to a standardized footprint → scores. The optimizer
loops this, searching for the parameters that give the most trustworthy
binding sites.

### Objective (`agentic_pureclip.scoring.objective::composite_objective`)

```
composite = (0.5·reproducibility + 0.25·motif + 0.25·recall) × min(1, n_sites/10)
```

- **reproducibility** — chance-corrected cross-replicate agreement.
- **motif** — fraction of sites bearing the RBP's RNA motif (log-odds PWM, most-enriched).
- **recall** — fraction of known-strong ENCODE reference regions recovered.
- **collapse guard** — `min(1, n_sites/10)` so collapsing to a few "perfect" sites can't win.

Weights are configurable per run via `priors.objective_weights`.

## Quick start

Toolchain is **uv**; the LLM is **DeepSeek** (`DEEPSEEK_API_KEY` in `.env`).

```bash
uv sync
cp .env.example .env            # add DEEPSEEK_API_KEY (Optuna runs need no key)
uv run python -m pytest tests/ -q   # tests (DEEPSEEK_API_KEY=dummy is fine)
```

### Run an optimization

`uv sync` installs the project editable, so the `agentic_pureclip` package and
its `python -m` entry points resolve without a `PYTHONPATH` hack.

```bash
# LLM agent
CONFIG_PATH=config/run_config.yaml MAX_ITER=8 uv run python -m agentic_pureclip.loop.graph

# Optuna (same eval + objective, no API key)
CONFIG_PATH=config/run_config.yaml MAX_ITER=12 uv run python -m agentic_pureclip.loop.optuna_runner
```

`learn_on_chr21: true` in the config restricts PureCLIP to chr21 ("fast mode",
minutes/iter); set it `false` for a full-genome run (hours/pass). The best
parameters are saved to `config/best_config.yaml`.

### Failure-tolerant batches

`scripts/run/overnight_batch.py` runs many jobs within a wall-clock budget, isolating
each job and never aborting the batch on a failure. Manifests live in `config/`
(e.g. `bigrun2_jobs.yaml`). Results accumulate in `results/overnight/`
(`iterations.jsonl`, `jobs.jsonl`, `summary.csv`, `<job>/decisions.jsonl`).

```bash
uv run python scripts/run/overnight_batch.py \
    --manifest config/bigrun2_jobs.yaml --hours 12 --no-repeat \
    --pureclip-dir /vol/storage1/johannes/projects
```

### Dashboard + UI

`scripts/dashboard/monitor.py` serves a JSON API (`/api/status`, `/api/runs`,
`/api/options`, `POST /api/schedule`) and the built React UI.

```bash
uv run python scripts/dashboard/monitor.py --port 8888                   # backend + UI
cd ui && npm install && npm run dev                            # UI dev (proxies /api)
cd ui && npm run build                                         # SPA → ui/build/client
```

UI pages: **Dashboard** (active run, queue/ETA, leaderboard with LLM-vs-Optuna
head-to-head), **Runs** (per-iteration decision trail), **Plan run** (configure +
schedule a run), **Variables** (plain-English guide to every knob).

## Datasets

Registered in `agentic_pureclip.pipeline.datasets`: RBFOX2_K562, RBFOX2_HepG2, QKI_K562,
QKI_HepG2, PUM1_K562 (+ ENCORE_RBFOX2_K562). `data/` and `results/` are
gitignored. Regenerate a dataset config:

```bash
python scripts/data/write_dataset_config.py RBFOX2_K562 --out config/datasets/RBFOX2_K562.yaml
```

## Repo layout

The core is one installable package, `src/agentic_pureclip/`, whose subpackages
are the three things this project contributes — the optimization **loop**, the
**scoring**, and the **postprocessing** — with the un-glamorous plumbing kept
separate under `pipeline/`.

| Path | What |
|------|------|
| `src/agentic_pureclip/loop/` | **The optimization loop.** `graph.py` (LLM/LangGraph), `optuna_runner.py` (TPE) — interchangeable optimizers sharing `evaluation.py` (one iter: run → score → objective), `state.py`, `report.py` |
| `src/agentic_pureclip/scoring/` | **Quality signals + objective.** `run_scorers.py` (reproducibility, motif, recall) and `objective.py` (`composite_objective`, weights, prompt) |
| `src/agentic_pureclip/postprocess/` | **Standardized footprint.** `postprocess.py` (filter/format PureCLIP output) + the `Snakefile` that drives the pipeline |
| `src/agentic_pureclip/pipeline/` | Plumbing: `configs.py` (bounds/validation), `datasets.py`, `motifs.py` (PWM log-odds), `runner.py` (invokes Snakemake), `logging_config.py` |
| `scripts/` | Ops utilities grouped by purpose: `data/` (download + prepare datasets), `motifs/` (motif library), `run/` (`batch_runner.py`, `overnight_batch.py`), `dashboard/` (`monitor.py` backend + `start_ui.sh`) |
| `ui/` | React Router SPA |
| `config/` | run configs, dataset configs, batch manifests, priors |
| `tests/` | pytest suite |
| `docs/` | architecture notes, meeting artifacts, and the LaTeX thesis (`docs/report/`) |

## Compute VM

Long runs and the dashboard run on `ssh bio`
(`/vol/storage1/johannes/projects/agentic-pureclip`). `pureclip2` is not on the
default PATH — prepend `/vol/storage1/johannes/projects`. Tunnel the dashboard:
`ssh -f -N -L 8888:localhost:8888 bio`.
