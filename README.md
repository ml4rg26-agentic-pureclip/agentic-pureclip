# Agentic PureCLIP
some change

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

# 2. Configure API keys
cp .env.example .env
# Edit .env to add your GEMINI_API_KEY
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

The agent logs its reasoning to `results/logs/`. The optimal parameters are saved to `config/best_config.yaml`.

## Architecture

- [`agent/`](agent/README.md): LangGraph state machine, LLM decision-making, and iteration history.
- [`workflow/`](workflow/README.md): Snakemake pipeline and `postprocess.py` for biological footprint standardization.
- [`scorers/`](scorers/README.md): Evaluation metrics (`replicate_agreement`, `motif_hit_rate`).
- [`config/`](config/README.md): Datasets configuration and biological priors.
- [`scripts/`](scripts/README.md): Data preparation utilities.
- [`tests/`](tests/README.md): Automated test suite for the Agent and Workflow.
