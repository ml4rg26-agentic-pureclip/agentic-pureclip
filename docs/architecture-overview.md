# Architecture overview

Agentic PureCLIP is organized around one controlled comparison: different
optimizers propose parameters, but every proposal is evaluated by the same
PureCLIP workflow and biological objective.

## System boundary

```text
                         ┌───────────────────────┐
                         │ Optimizer             │
                         │ LLM agent or TPE      │
                         └───────────┬───────────┘
                                     │ candidate parameters
                                     ▼
┌──────────────────┐      ┌───────────────────────┐
│ eCLIP BAMs       │─────▶│ Shared evaluation     │
│ GRCh38 reference │      │ config + Snakemake    │
│ ENCODE benchmark │      └───────────┬───────────┘
│ motif PWMs       │                  │ binding sites
└──────────────────┘                  ▼
                         ┌───────────────────────┐
                         │ Biological scoring    │
                         │ reproducibility       │
                         │ motif support         │
                         │ reference recall      │
                         └───────────┬───────────┘
                                     │ score report
                         ┌───────────▼───────────┐
                         │ Durable run records   │
                         │ + monitoring UI       │
                         └───────────────────────┘
```

The optimizer boundary is deliberate. Both search strategies call the same
`evaluate_config()` function, use the same parameter bounds, and receive scores
from the same objective implementation. This prevents optimizer-specific
pipeline behavior from confounding the comparison.

## Python package

The installable package uses a `src/` layout under
`src/agentic_pureclip/`.

### `loop/`: optimization strategies

| File | Responsibility |
|---|---|
| `graph.py` | LangGraph state machine for the LLM optimization loop. |
| `optuna_runner.py` | Optuna TPE search over the shared parameter bounds. |
| `evaluation.py` | Shared `evaluate_config()` implementation used by both optimizers. |
| `state.py` | Iteration records and optimizer state types. |
| `report.py` | Decision prompting, run reporting, and HTML report generation. |
| `graph_mock.py` | Pipeline-independent mock graph used by tests. |

### `pipeline/`: shared configuration and execution support

| File | Responsibility |
|---|---|
| `configs.py` | Search bounds, configuration validation, tunable snapshots, and duplicate detection. |
| `datasets.py` | Dataset registry and generation of dataset-specific run configurations. |
| `motifs.py` | TRANSFAC parsing, PWM loading, IUPAC expansion, and sequence scanning. |
| `runner.py` | BAM-index checks and Snakemake invocation. |
| `logging_config.py` | Shared logging setup. |

### `postprocess/`: bioinformatics workflow

| File | Responsibility |
|---|---|
| `Snakefile` | BAM indexing and merging, merged and per-replicate PureCLIP calls, post-processing, and scoring. |
| `postprocess.py` | Region filtering, merging, summit centering, and fixed-width footprint generation. |

The workflow consumes one YAML run configuration. It calls `pureclip2` on the
merged IP signal and independently on each IP replicate, then standardizes the
merged binding sites before scoring them.

### `scoring/`: evaluation signals

| File | Responsibility |
|---|---|
| `run_scorers.py` | Chance-corrected replicate agreement, PWM motif support, ENCODE benchmark recall, and score-report serialization. |
| `objective.py` | Single source of truth for the weighted composite objective and few-site penalty. |

The dashboard imports the same objective function rather than reimplementing the
formula, so displayed scores and optimizer decisions use identical semantics.

### `run/`: scheduling and CLI

| File | Responsibility |
|---|---|
| `schedule.py` | Validates run requests and builds batch manifests. |
| `launcher.py` | Writes manifests and launches the failure-tolerant batch runner. |
| `cli.py` | Implements the `agentic-pureclip-run` command. |

## One evaluation

1. An optimizer proposes changes within the configured parameter bounds.
2. `loop/evaluation.py` merges them into a run configuration.
3. `pipeline/runner.py` invokes the Snakemake workflow.
4. The workflow merges IP BAMs and runs PureCLIP on merged and replicate data.
5. `postprocess/postprocess.py` produces standardized binding-site footprints.
6. `scoring/run_scorers.py` writes the decomposed biological measurements.
7. `scoring/objective.py` reduces those measurements to a scalar score.
8. The iteration record becomes feedback for the next optimizer proposal.

The default objective is:

```text
S = (0.50 × reproducibility + 0.25 × motif support + 0.25 × reference recall)
    × min(1, number of binding sites / 10)
```

Weights are configurable and renormalized over present components. The final
factor prevents a very small call set from winning through trivially high
agreement or motif support.

## Experiment and result records

`config/` contains run templates, dataset definitions, search bounds, priors,
and batch manifests. Generated results are written beneath `results/`, including
iteration histories, job records, summaries, and per-run decision traces. Large
inputs and outputs are ignored by Git; configurations and code are the committed
description of an experiment.

The batch runner in `scripts/run/overnight_batch.py` isolates failures and
enforces a wall-clock budget so one failed evaluation does not discard an entire
experimental batch.

## Monitoring application

The monitoring application has two components:

- `dashboard/api/`: FastAPI endpoints that read configuration and result
  artifacts and inspect project-owned host processes.
- `dashboard/ui/`: React and TypeScript interface for run status, iteration
  histories, experiment planning, and parameter explanations.

The production Docker Compose deployment is monitor-only: results and
configuration are mounted read-only, and runs are started on the host through
the CLI. See [developer onboarding](developer-onboarding.md) for local and VM
instructions.

## Supporting directories

| Path | Responsibility |
|---|---|
| `config/` | Run, dataset, prior, and batch definitions. |
| `scripts/data/` | Input and reference preparation. |
| `scripts/motifs/` | Motif-catalog management. |
| `scripts/run/` | Batch execution. |
| `scripts/analysis/` | Report figures and frozen analysis inputs. |
| `tests/` | Unit and workflow tests. |
| `docs/report/` | Research manuscript and bibliography. |
| `dashboard/` | Monitoring API, UI, proxy, and container definitions. |
