# Agentic PureCLIP — Architecture Overview

## Core Purpose

Agentic PureCLIP is an automated parameter optimization system for **eCLIP peak calling**. It drives **PureCLIP** (an HMM-based crosslink-site caller) to find the parameter settings that produce the highest-quality RNA-binding protein (RBP) binding site calls from eCLIP sequencing data. Quality is measured against three biological signals: replicate reproducibility, RBP motif enrichment, and recall against a curated ENCODE reference set.

Two interchangeable optimizers are provided:
- **LLM-driven** (DeepSeek via LangGraph) — uses an LLM that reads previous iteration results and reasons about which parameters to try next.
- **Optuna-driven** (TPE sampler) — uses Bayesian optimization with the same objective function, no API key required.

Both run the same `evaluate_config` function, making their results directly comparable.

---

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        Optimizers (agent/)                     │
│   LLM loop (graph.py)          Optuna runner (optuna_runner.py)│
│         │                              │                        │
│         └──────────┬───────────────────┘                        │
│                    ▼                                            │
│           evaluation.py — evaluate_config()                    │
└───────────────────────┬───────────────────────────────────────┘
                        │  writes run_config.yaml, reads score_report.json
                        ▼
┌───────────────────────────────────────────────────────────────┐
│                      Pipeline (workflow/)                       │
│   Snakemake DAG:                                               │
│     merge IP BAMs → PureCLIP (all + per-rep) →                │
│     postprocess.py (footprint normalization) →                  │
│     run_scorers.py → score_report.json                         │
└───────────────────────┬───────────────────────────────────────┘
                        │  score_report.json
                        ▼
┌───────────────────────────────────────────────────────────────┐
│                     Scoring (scorers/)                          │
│  reproducibility · motif PWM hit-rate · benchmark recall       │
│       → composite_objective() → single [0,1] score            │
└───────────────────────────────────────────────────────────────┘
                        │  results written to results/overnight/
                        ▼
┌───────────────────────────────────────────────────────────────┐
│          Monitoring & UI (scripts/dashboard/monitor.py + ui/)            │
│  REST API + React SPA: Dashboard · Runs · Plan run · Variables │
└───────────────────────────────────────────────────────────────┘
```

---

## Top-Level Directory Reference

### `agent/`
The optimizer layer. Contains both search strategies and their shared infrastructure.

| File | Responsibility |
|---|---|
| `graph.py` | LangGraph state-machine for the LLM optimization loop. Calls DeepSeek to propose the next parameter set, executes `evaluate_config`, and loops until `MAX_ITER` is reached or proposals repeat. |
| `optuna_runner.py` | Optuna/TPE-based optimizer using the same `evaluate_config` and objective. |
| `evaluation.py` | Shared `evaluate_config()` — writes a config file, invokes the Snakemake pipeline, reads back `score_report.json`. Used by both optimizers. |
| `decisions.py` | `composite_objective()` (the single source-of-truth scoring formula), prompt builder, and LLM response parser/validator. |
| `state.py` | `AgentState` and `IterationRecord` Pydantic types for the LangGraph loop. |
| `graph_mock.py` | Mock graph for testing without real PureCLIP or API calls. |
| `logging_config.py` | Shared structured logger setup. |

### `pipeline/`
The configuration and data-model layer. Provides types and helpers consumed by both the optimizers and the workflow.

| File | Responsibility |
|---|---|
| `configs.py` | `DEFAULT_SEARCH_BOUNDS` (tunable parameter ranges), config load/save/validate, `tunable_snapshot`, `tried_signatures`. |
| `datasets.py` | Dataset registry — maps dataset IDs to BAM paths, motif files, and benchmark references. Handles motif auto-resolution. |
| `motifs.py` | TRANSFAC/PWM parser, IUPAC regex expansion, `scan_sequence_with_pwm()` for log-odds scoring. |
| `runner.py` | Thin wrappers that shell out to `snakemake` and `run_scorers.py`. |

### `workflow/`
The bioinformatics execution layer, implemented as a Snakemake DAG.

| File | Responsibility |
|---|---|
| `Snakefile` | Defines the full DAG: index BAMs → merge IP replicates → run PureCLIP on merged + per-replicate BAMs → postprocess → run scorers. Reads `run_config.yaml`; writes `score_report.json`. |
| `postprocess.py` | Standardizes raw PureCLIP BED output to a fixed footprint width (~9 nt for these RBPs), merges nearby sites, and filters by minimum crosslink event count. |

### `scorers/`
Scoring logic that runs after each PureCLIP invocation.

| File | Responsibility |
|---|---|
| `run_scorers.py` | Computes the three objective terms — **reproducibility** (chance-corrected replicate agreement), **motif hit-rate** (fraction of sites with a PWM hit, enriched over a dinucleotide-shuffled background), and **benchmark recall** (fraction of ENCODE reference regions recovered). Writes `score_report.json`. |

### `scripts/`
Operational tooling for running experiments and managing data.

| File | Responsibility |
|---|---|
| `overnight_batch.py` | Failure-tolerant batch runner. Executes a list of jobs from a YAML manifest within a wall-clock budget, never aborts on a single failure, records all outcomes to `results/overnight/`. |
| `monitor.py` | HTTP server (stdlib `http.server`) that exposes a REST API over `results/overnight/` and serves the compiled React SPA. This is the production entry point for the dashboard. |
| `download_data.sh` / `download_genome.sh` | Download eCLIP BAMs from ENCODE and the GRCh38 genome FASTA. |
| `setup_chr21_bams.sh` / `extract_chromosome.sh` | Subset BAMs to chr21 for fast iteration (`learn_on_chr21: true`). |
| `write_dataset_config.py` | Helper to generate `config/datasets/*.yaml` entries. |
| `list_motifs.py` / `reorganize_motifs.py` | Utilities for managing the motif file library under `data/motifs/`. |
| `batch_runner.py` | Earlier batch runner prototype (superseded by `overnight_batch.py`). |

### `ui/`
React Router v8 single-page application providing the experiment dashboard.

| Path | Responsibility |
|---|---|
| `app/routes/dashboard.tsx` | Active run view: dataset info, current iteration/stage stepper, queue and ETA, results leaderboard with LLM-vs-Optuna head-to-head. |
| `app/routes/runs.tsx` | Per-run decision trail: shows parameters changed and LLM reasoning at each iteration (sourced from `decisions.jsonl`). |
| `app/routes/plan.tsx` | Run planner: pick dataset, set parameter ranges, submit a new job via `POST /api/schedule`. |
| `app/routes/variables.tsx` | Plain-English guide to all tunable parameters and their effects. |
| `app/lib/` | Shared API fetch helpers, type definitions. |

Built with React 19, React Router 8, Tailwind CSS v4, and Vite. Production build (`npm run build`) produces `ui/build/client/` which `monitor.py` serves statically.

### `config/`
Run configuration files — not code, but part of the reproducible experiment record.

| Path | Responsibility |
|---|---|
| `run_config.yaml` | Template/active run config: dataset, sample BAM paths, PureCLIP params, postprocessing params, resource limits. |
| `datasets/*.yaml` | Per-dataset configs (RBFOX2_K562, RBFOX2_HepG2, QKI_K562, QKI_HepG2, PUM1_K562, ENCORE_RBFOX2_K562). |
| `priors.json` | LLM-facing priors: objective weights, known motifs, expected footprint width. |
| `*_jobs.yaml` | Batch manifests consumed by `overnight_batch.py` (e.g., `bigrun2_jobs.yaml`). |

### `tests/`
Pytest suite covering the objective function, PWM scoring, LLM agent resilience (mocked), config validation, Optuna runner, and Snakemake workflow smoke tests.

### `.github/workflows/`
CI: `pytest.yml` runs the test suite on push/PR (`DEEPSEEK_API_KEY=dummy`).

---

## Key Data Flows

### Single optimization iteration
1. Optimizer proposes a `dict` of tunable parameter changes.
2. `evaluation.py` merges these into a copy of `run_config.yaml` and writes it to disk.
3. Snakemake executes: merge BAMs → PureCLIP → postprocess → `run_scorers.py`.
4. `run_scorers.py` writes `score_report.json` (reproducibility, motif, recall, site count, plus the params that produced them).
5. `evaluation.py` reads the report back and returns it to the optimizer.
6. `composite_objective()` in `decisions.py` computes the blended `[0,1]` score.

### Composite objective formula
```
composite = (0.5·reproducibility + 0.25·motif + 0.25·recall)   # renormalised over present terms
            × min(1, n_binding_sites / 10)                       # collapse guard
```
Weights are configurable via `priors.json`. The formula lives in `agent/decisions.py` and is imported by `monitor.py` so the dashboard always reflects the live objective.

### Overnight batch
`overnight_batch.py` iterates through a YAML manifest of jobs, launches each as a subprocess, enforces a wall-clock budget, and writes `iterations.jsonl`, `jobs.jsonl`, and `summary.csv` under `results/overnight/`.

### Dashboard
`monitor.py` serves the API at `/api/*` by reading the JSONL/CSV files from `results/overnight/`. The React SPA polls these endpoints and renders the live experiment state.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Python runtime | Python ≥ 3.10, managed by **uv** |
| LLM integration | LangGraph + LangChain OpenAI SDK → **DeepSeek** (`deepseek-chat`) |
| Bayesian optimization | **Optuna** (TPE sampler) |
| Bioinformatics workflow | **Snakemake** + `samtools` + `pureclip2` binary |
| Data handling | pandas, PyYAML, Pydantic v2 |
| Frontend | React 19, React Router 8, Tailwind CSS v4, Vite 8, TypeScript |
| Backend API | Python stdlib `http.server` (no framework) |
| Testing | pytest |
| CI | GitHub Actions |
