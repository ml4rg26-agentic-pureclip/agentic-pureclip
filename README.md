# Agentic PureCLIP

An LLM-driven parameter optimization framework for eCLIP data analysis, tuning the [PureCLIP](https://github.com/skrakau/PureCLIP) algorithm.

## Overview

Finding parameters for eCLIP peak calling is dataset-dependent. This project utilizes a LangGraph and Gemini-based workflow to iteratively search for PureCLIP and post-processing parameters. 

The LLM analyzes biological priors and observes empirical score trends across iterations to adjust parameters, aiming to maximize cross-replicate reproducibility.

## Key Features

- **Parameter Tuning**: Parameter space search using an LLM and biological priors.
- **Snakemake Integration**: Orchestration of the bioinformatics pipeline, utilizing pre-aligned deduplicated BAM files.
- **Scoring**: Evaluates parameter sets using **Replicate Agreement** (overlap of binding sites across independent replicates) as the primary metric for the agent, and calculates **Motif Hit Rate** for secondary biological validation.

## Quick Start

### Prerequisites
Requires `conda` and a Google Gemini API key.

### Installation & Setup
```bash
# 1. Create environment
conda env create -f environment.yml
conda activate agentic-pureclip
# Note: If you already have the environment and just pulled new updates, run:
# conda env update -f environment.yml --prune

# 2. Configure API keys
cp .env.example .env
# Edit .env to add your GOOGLE_API_KEY (for Google Gemini API)
# Optionally, configure LANGSMITH_API_KEY and LANGSMITH_PROJECT for tracing
```

### Running the Pipeline

1. **Prepare test data** (subsets ENCODE BAM files to `chr21`):
   ```bash
   bash scripts/setup_chr21_bams.sh
   ```

2. **Start the optimization agent**:
   ```bash
   cp config/run_config.test.yaml config/run_config.yaml
   nohup env CONFIG_PATH=config/run_config.yaml MAX_ITER=5 python -m agent.graph > background_run.log 2>&1 &
   ```

The agent writes every iteration to its own configured output directory under `results/runs/`. The optimal parameters are saved to `config/best_config.yaml`.

To generate a PDF summary report from the run's history:
```bash
python agent/report.py config/run_config.yaml results/runs/report.pdf
```

### Reproducible Direct Runs

Run the Snakemake workflow directly with an explicit Snakefile and config:

```bash
snakemake -s workflow/Snakefile -j 8 --configfile config/run_config.yaml --rerun-incomplete
```

Run one of the local full-size datasets:

```bash
snakemake -s workflow/Snakefile -j 8 --configfile config/datasets/RBFOX2_K562.yaml --rerun-incomplete
```

Dataset configs live in `config/datasets/` and point at the ignored local `data/` tree. The workflow can build missing `.bam.bai` indexes with `samtools index`.

To regenerate a dataset config from the registry:

```bash
python scripts/write_dataset_config.py RBFOX2_K562 --out config/datasets/RBFOX2_K562.yaml
```

## Architecture

- [`agent/`](agent/README.md): LangGraph state machine, LLM decision-making, and iteration history. Includes `graph.py` (production) and `graph_mock.py` (offline testing).
- [`pipeline/`](pipeline/README.md): Config validation, dataset registry, and reproducible execution helpers.
- [`workflow/`](workflow/README.md): Snakemake pipeline and `postprocess.py` for biological footprint standardization.
- [`scorers/`](scorers/README.md): Evaluation metrics (`replicate_agreement`, `motif_hit_rate`).
- [`config/`](config/README.md): Datasets configuration and biological priors.
- [`scripts/`](scripts/README.md): Data preparation utilities.
- [`tests/`](tests/README.md): Automated test suite for the Agent and Workflow.

## Testing & Development

For quick testing without running the full pipeline:
```bash
# Run the mock agent (simulates pipeline with fake scores, requires Gemini API)
env CONFIG_PATH=config/run_config.yaml MAX_ITER=3 python -m agent.graph_mock

# Run the mock agent fully offline (no API key needed)
env USE_GEMINI=0 CONFIG_PATH=config/run_config.yaml MAX_ITER=3 python -m agent.graph_mock
```

The mock agent produces identical state transitions and decision-making as the production agent, enabling rapid prototyping and testing without bioinformatics dependencies.

